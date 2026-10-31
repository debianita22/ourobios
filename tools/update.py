#!/usr/bin/env python3
# update.py - aggiorna ouroBIOS, il firmware del W541 e del ThinkCentre
# M920x, da Linux con una capsula UEFI (docs/update.md). Ogni release ha,
# per variante, una capsula firmata (w541-coreboot-vX.Y.Z-mrc.cap,
# m920x-coreboot-vX.Y.Z-fsp.cap): la si copia in \EFI\UpdateCapsule
# dell'ESP, si accende il bit "capsule su disco" di OsIndications e al
# riavvio il firmware la verifica e la scrive, anche con il BIOS Lock acceso.
# Dalla v1.3.0 (vboot, docs/vboot.md) scrive solo lo slot RW che non gira e
# poi lo prova; la regione RO, le variabili UEFI, la VPD e il registro degli
# eventi restano.
#
#   sudo python3 tools/update.py status
#   sudo python3 tools/update.py stage --latest        # ultima release della variante che gira
#   sudo python3 tools/update.py stage w541-coreboot-v1.2.1-mrc.cap
#   sudo python3 tools/update.py cancel
#   python3 tools/update.py info w541-coreboot-v1.2.1-mrc.cap
#   python3 tools/update.py vboot flash.bin            # da sudo flashrom -p internal -r flash.bin
#   sudo python3 tools/update.py protection            # protezione del flash (M920x, W541), solo letture
#
# Al posto della .cap va bene anche il pacchetto fwupd della release (.cab,
# tools/fwupd-cab.py): se ne usa la capsula che contiene.
#
# Il firmware che gira deve avere la stessa mappa del flash della capsula: le
# capsule della v1.3.0 in su (con vboot) si installano su un firmware dalla
# v1.3.0, quelle della v1.2.x su un firmware v1.2.x; da v1.2.x a v1.3.0 si
# passa una volta con flashrom (docs/flashing.md). Il firmware applica solo
# capsule della sua variante (mrc o nri, un GUID ciascuna nell'ESRT), firmate
# dalla chiave di keys/capsule-signing.pem e non piu' vecchie della versione
# minima (LSV); qui si controlla prima, per non riavviare per niente.
#
# Solo la libreria standard di Python; openssl, se c'e', verifica anche la
# firma (con --cert, o keys/capsule-signing.pem accanto a questo script).
import argparse
import errno
import fcntl
import gzip
import hashlib
import json
import mmap
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

REPO = "debianita22/ourobios"

# Il GUID dell'ESRT (DRIVERS_EFI_MAIN_FW_GUID nei defconfig) di ogni variante.
# Cambia con la parte RO: una capsula scrive solo gli slot, e il firmware accetta
# solo capsule con il suo GUID, cosi' una release i cui slot vogliono un'altra
# parte RO non si installa con la capsula, ma una volta con flashrom.
#   dalla v1.3.9: la parte RO con una cache-as-RAM uguale per mrc e nri
VARIANTS = {
    "mrc": uuid.UUID("70eab79a-675a-42ef-9543-43abcad96275"),
    "nri": uuid.UUID("5379c75b-87f2-4669-8d87-6fdd92a50ed4"),
    # ThinkCentre M920x (boards/m920x), dalla sua prima release
    "m920x-fsp": uuid.UUID("2e0b05d4-27d0-4faa-929d-93989c01fee8"),
}
# La board e la variante di ogni nome di release (vX.Y.Z-<nome>): i file
# della release sono <board>-coreboot-vX.Y.Z-<variante>.cap, e l'immagine
# nella capsula e' grande quanto il flash della board
FLAVOURS = {
    "mrc": ("w541", "mrc", 12 * 1024 * 1024),
    "nri": ("w541", "nri", 12 * 1024 * 1024),
    "m920x-fsp": ("m920x", "fsp", 24 * 1024 * 1024),
}
#   v1.3.0-v1.3.8: la prima parte RO con vboot, con la cache-as-RAM della sua variante
RO1_VARIANTS = {
    "mrc": uuid.UUID("1a1d806e-1dec-436f-a428-17e010b08c58"),
    "nri": uuid.UUID("ef384a6d-1e1d-4344-abf9-b26f39d9e80a"),
}
#   v1.2.x: la mappa del flash senza vboot
LEGACY_VARIANTS = {
    "mrc": uuid.UUID("b774aa46-be0e-4ec1-bb1b-b7c0bf2722aa"),
    "nri": uuid.UUID("d945239f-4a5a-4089-8597-6bd72edd1a1f"),
}
# Le regioni che scrive una capsula: il firmware scrive lo slot che non gira
# e quello che c'e' tra le altre. REGIONS e' CAPSULE_REGIONS di tools/build.sh,
# il default (W541, update-test): anche il training della RAM, che il codice
# nuovo rifa' al primo avvio
REGIONS = ["RW_MRC_CACHE", "RW_SECTION_A", "RW_SECTION_B"]
# Quelle delle capsule di oggi, per variante (BOARD_CAPSULE_REGIONS di
# boards/<board>/board.sh): sul M920x dalla v1.4.0-rc4 il training resta, la
# sua versione dice se vale ancora (FSP-M, processore, Hyper-Threading; non
# le UPD di FSP-M che mette coreboot: il perche' in board.sh). Le controlla
# info, quindi anche tools/build.sh dopo ogni capsula
CURRENT_REGIONS = {
    "mrc": REGIONS,
    "nri": REGIONS,
    "m920x-fsp": ["RW_SECTION_A", "RW_SECTION_B"],
}
# E quelle che stage e rollback accettano ancora: le capsule del M920x dalla
# v1.4.0-rc1 alla rc3 scrivono anche RW_MRC_CACHE (si torna indietro con quelle)
ACCEPTED_REGIONS = {
    "mrc": [REGIONS],
    "nri": [REGIONS],
    "m920x-fsp": [CURRENT_REGIONS["m920x-fsp"], REGIONS],
}
LEGACY_REGIONS = ["RW_MRC_CACHE", "COREBOOT"]
# la prima release del M920x che lascia il training: gli slot di prima non
# hanno la versione con processore e Hyper-Threading (patch 0173)
KEEP_CACHE_SINCE = (1, 4, 0, 4)
MIGRATION = "docs/flashing.md, \"From v1.2.x to v1.3.0\""
RO_MIGRATION = "docs/flashing.md, \"From v1.3.x to v1.3.9\""
ROM_SIZE = 12 * 1024 * 1024

FMP_CAPSULE_GUID = uuid.UUID("6dcbd5ed-e82d-4c44-bda1-7194199ad92a")
PKCS7_CERT_GUID = uuid.UUID("4aafd29d-68df-49ee-8aa9-347d375665a7")
WIN_CERT_TYPE_EFI_GUID = 0x0EF1
FMP_PAYLOAD_SIGNATURE = b"MSS1"
CAPSULE_SUPPORT_DEPENDENCY = 0x2
RMAP_SIGNATURE = 0x50414D52  # "RMAP"
RMAP_ENTRY = 16

GLOBAL_GUID = "8be4df61-93ca-11d2-aa0d-00e098032b8c"
# W541_UPDATE_SYSROOT: un'altra radice per /sys e /proc, solo per le prove
SYSROOT = os.environ.get("W541_UPDATE_SYSROOT", "/")
EFIVARS = os.path.join(SYSROOT, "sys/firmware/efi/efivars")
ESRT = os.path.join(SYSROOT, "sys/firmware/efi/esrt/entries")
POWER_SUPPLY = os.path.join(SYSROOT, "sys/class/power_supply")
BIOS_VERSION = os.path.join(SYSROOT, "sys/class/dmi/id/bios_version")
MOUNTS = os.path.join(SYSROOT, "proc/self/mounts")
# SMBIOS: le strutture una per una (dmi_sysfs, un modulo che puo' mancare) o
# la tabella intera, che c'e' sempre (quella di dmidecode); tutte e due solo root
DMI_ENTRIES = os.path.join(SYSROOT, "sys/firmware/dmi/entries")
DMI_TABLE = os.path.join(SYSROOT, "sys/firmware/dmi/tables/DMI")
HECI_PCI = os.path.join(SYSROOT, "sys/bus/pci/devices/0000:00:16.0")
# Il controller SPI del M920x (la protezione del flash) e la memoria fisica
SPI_PCI = os.path.join(SYSROOT, "sys/bus/pci/devices/0000:00:1f.5")
DEVMEM = os.path.join(SYSROOT, "dev/mem")
FILE_CAPSULE_DELIVERY = 0x4  # EFI_OS_INDICATIONS_FILE_CAPSULE_DELIVERY_SUPPORTED
VAR_ATTRS = 0x7              # non volatile, boot service, runtime
ESP_TYPES = ("c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "0xef")
CAPSULE_DIR = os.path.join("EFI", "UpdateCapsule")
STAGED_NAME = "w541-coreboot.cap"

FS_IOC_GETFLAGS = 0x80086601
FS_IOC_SETFLAGS = 0x40086602
FS_IMMUTABLE_FL = 0x10

# LastAttemptStatus dell'ESRT (UEFI 2.10, 23.4), e i codici di
# FmpDeviceSmmLib del payload (patch edk2 0008), da 0x1800
ATTEMPT = {
    0: "riuscito",
    1: "non riuscito",
    2: "risorse insufficienti",
    3: "versione non accettata",
    4: "formato non valido",
    5: "firma non valida",
    6: "alimentatore",
    7: "batteria",
    8: "dipendenze non soddisfatte",
    0x1800: "immagine non valida (senza manifest delle regioni, o di un'altra dimensione)",
    0x1801: "mappa del flash diversa da quella del firmware che gira",
    0x1802: "scrittura del flash fallita",
}


class Error(Exception):
    pass


# L'ultimo numero nel formato di prima, (X << 24) | (Y << 16) | Z, senza le
# rc: v1.3.6-rc1. Fino a li' i numeri delle release sui portatili hanno il
# byte 1 a zero, e in quel formato si leggono; nel formato di adesso li'
# cadrebbero solo le rc di una vX.Y.1 di allora (v1.3.1-rc5 = 0x01030005),
# che non ci sono mai state
LAST_OLD_LAYOUT = 0x01030006


def old_layout(v):
    """Un numero di una release fino a v1.3.6-rc1, nel formato di prima."""
    return v <= LAST_OLD_LAYOUT and v & 0xFF00 == 0


def version_str(v):
    """La versione dell'ESRT come il tag della release: X.Y.Z.R un byte ciascuno,
    vX.Y.Z e' X.Y.Z.0 e vX.Y.Z-rcN la release prima con R = N (tools/build.sh);
    i numeri fino a v1.3.6-rc1 nel loro formato (X.Y.Z, le rc come la release)."""
    if old_layout(v):
        # in quel formato una rc aveva il numero della sua release; di v1.3.6
        # pero' c'e' stata solo la rc1, l'ultima prima del formato di adesso
        return "v1.3.6-rc1" if v == LAST_OLD_LAYOUT else "v%d.%d.%d" % (v >> 24, (v >> 16) & 0xFF, v & 0xFFFF)
    if v & 0xFF == 0:
        return "v%d.%d.%d" % (v >> 24, (v >> 16) & 0xFF, (v >> 8) & 0xFF)
    rel = (v & ~0xFF) + 0x100
    return "v%d.%d.%d-rc%d" % (rel >> 24, (rel >> 16) & 0xFF, (rel >> 8) & 0xFF, v & 0xFF)


def version_quad(v):
    """La stessa versione come la scrive fwupd (formato "quad"): X.Y.Z.R."""
    return "%d.%d.%d.%d" % (v >> 24, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def version_triplet(v):
    """Come la scrivevano i pacchetti fwupd fino a v1.3.6-rc1 ("triplet"): X.Y.Z."""
    return "%d.%d.%d" % (v >> 24, (v >> 16) & 0xFF, v & 0xFFFF)


def attempt_str(status):
    if status in ATTEMPT:
        return ATTEMPT[status]
    if 0x1000 <= status <= 0x17FF:
        return "errore 0x%x di FmpDxe" % status
    if 0x1800 <= status <= 0x1FFF:
        return "errore 0x%x di FmpDeviceSmmLib" % status
    return "errore 0x%x" % status


def variant_of(guid):
    for name, g in VARIANTS.items():
        if g == guid:
            return name
    return None


def legacy_variant_of(guid):
    for name, g in LEGACY_VARIANTS.items():
        if g == guid:
            return name
    return None


def ro1_variant_of(guid):
    for name, g in RO1_VARIANTS.items():
        if g == guid:
            return name
    return None


def any_variant_of(guid):
    return variant_of(guid) or ro1_variant_of(guid) or legacy_variant_of(guid)


# --- capsule -----------------------------------------------------------------

def parse_capsule(data):
    """Le parti di una capsula FMP firmata con una sola immagine, come la
    scrive GenerateCapsule di EDK2 (tools/build.sh)."""
    if len(data) < 28:
        raise Error("troppo corta per una capsula")
    guid = uuid.UUID(bytes_le=data[0:16])
    hdr_size, flags, size = struct.unpack_from("<III", data, 16)
    if guid != FMP_CAPSULE_GUID:
        raise Error("non e' una capsula FMP (%s)" % guid)
    if size > len(data) or hdr_size < 28 or hdr_size + 16 > size:
        raise Error("intestazione della capsula non valida")
    fmp = hdr_size
    fver, ndrivers, nitems = struct.unpack_from("<IHH", data, fmp)
    if fver != 1 or ndrivers != 0 or nitems != 1:
        raise Error("attesa una sola immagine senza driver (versione %d, %d driver, %d immagini)"
                    % (fver, ndrivers, nitems))
    item = fmp + struct.unpack_from("<Q", data, fmp + 8)[0]
    if item + 48 > size:
        raise Error("immagine fuori dalla capsula")
    iver = struct.unpack_from("<I", data, item)[0]
    if iver < 3:
        raise Error("intestazione dell'immagine versione %d, attesa 3" % iver)
    type_id = uuid.UUID(bytes_le=data[item + 4:item + 20])
    index = data[item + 20]
    isize, vsize = struct.unpack_from("<II", data, item + 24)
    support = struct.unpack_from("<Q", data, item + 40)[0]
    start = item + 48
    end = start + isize
    if end > size or vsize != 0:
        raise Error("dimensioni dell'immagine non valide")
    # EFI_FIRMWARE_IMAGE_AUTHENTICATION: contatore, WIN_CERTIFICATE_UEFI_GUID
    if start + 32 > end:
        raise Error("immagine senza firma")
    monotonic = struct.unpack_from("<Q", data, start)[0]
    length, revision, cert_type = struct.unpack_from("<IHH", data, start + 8)
    if cert_type != WIN_CERT_TYPE_EFI_GUID or revision != 0x200 or length < 24:
        raise Error("firma di tipo sconosciuto")
    if uuid.UUID(bytes_le=data[start + 16:start + 32]) != PKCS7_CERT_GUID:
        raise Error("firma non PKCS#7")
    signed = start + 8 + length
    if signed + 16 > end:
        raise Error("firma fuori dall'immagine")
    signature = data[start + 32:signed]
    pos = signed
    if support & CAPSULE_SUPPORT_DEPENDENCY:
        raise Error("capsula con dipendenze: non e' di questo progetto")
    sig, phsize, fw_version, lsv = struct.unpack_from("<4sIII", data, pos)
    if sig != FMP_PAYLOAD_SIGNATURE or phsize < 16 or pos + phsize > end:
        raise Error("intestazione FMP_PAYLOAD_HEADER non valida")
    payload = data[pos + phsize:end]
    # RMAP: le regioni da scrivere, in coda all'immagine (AppendRmapManifest.py)
    regions = []
    image = payload
    if len(payload) >= 8:
        rsig, rver, count = struct.unpack_from("<IHH", payload, len(payload) - 8)
        if rsig == RMAP_SIGNATURE and rver == 1 and len(payload) >= 8 + count * RMAP_ENTRY:
            base = len(payload) - 8 - count * RMAP_ENTRY
            for i in range(count):
                name = payload[base + i * RMAP_ENTRY:base + (i + 1) * RMAP_ENTRY]
                regions.append(name.rstrip(b"\0").decode("ascii", "replace"))
            image = payload[:base]
    return {
        "flags": flags,
        "type_id": type_id,
        "variant": variant_of(type_id),
        "index": index,
        "monotonic": monotonic,
        "signature": signature,
        "signed": data[signed:end] + struct.pack("<Q", monotonic),
        "version": fw_version,
        "lsv": lsv,
        "regions": regions,
        "image": image,
        "size": size,
    }


def openssl(*args, data=None):
    return subprocess.run(["openssl"] + list(args), input=data, capture_output=True)


def fingerprint(pem):
    """L'impronta SHA-256 di un certificato PEM, come la stampa openssl."""
    r = openssl("x509", "-noout", "-fingerprint", "-sha256", data=pem)
    m = re.search(rb"=([0-9A-F:]+)", r.stdout)
    return m.group(1).decode() if m else None


def signer_of(cap):
    """Soggetto e impronta del certificato che ha firmato, se openssl c'e'."""
    if not shutil.which("openssl"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        sig = os.path.join(tmp, "sig.der")
        with open(sig, "wb") as f:
            f.write(cap["signature"])
        r = openssl("pkcs7", "-inform", "DER", "-in", sig, "-print_certs")
    m = re.search(rb"subject=\s*(.*)", r.stdout)
    pem = re.search(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", r.stdout, re.S)
    if not m or not pem:
        return None
    return m.group(1).decode(errors="replace").strip(), fingerprint(pem.group(0))


def verify_signature(cap, cert):
    """La firma come la verifica EDK2 (Pkcs7Verify: il certificato fidato puo'
    essere quello che firma, nessuna data, qualsiasi uso)."""
    if not shutil.which("openssl"):
        raise Error("serve openssl per verificare la firma")
    with tempfile.TemporaryDirectory() as tmp:
        sig = os.path.join(tmp, "sig.der")
        content = os.path.join(tmp, "content.bin")
        with open(sig, "wb") as f:
            f.write(cap["signature"])
        with open(content, "wb") as f:
            f.write(cap["signed"])
        r = openssl("smime", "-verify", "-binary", "-inform", "DER", "-in", sig, "-content", content,
                    "-CAfile", cert, "-purpose", "any", "-partial_chain", "-no_check_time",
                    "-out", os.devnull)
        if r.returncode != 0:
            err = r.stderr.decode(errors="replace")
            m = re.search(r"Verify error:\s*(.*)", err)
            why = m.group(1).strip() if m else (err.strip().splitlines() or ["?"])[-1]
            raise Error("firma non valida per %s (%s): la chiave non e' quella di cui il firmware "
                        "si fida" % (cert, why))


def default_cert():
    here = os.path.dirname(os.path.realpath(__file__))
    cert = os.path.normpath(os.path.join(here, os.pardir, "keys", "capsule-signing.pem"))
    return cert if os.path.isfile(cert) else None


# --- il pacchetto fwupd ------------------------------------------------------

JCAT_SHA256 = 1
JCAT_PKCS7 = 3


def cab_checksum(data, seed=0):
    """CSUMCompute di [MS-CAB] (come tools/fwupd-cab.py)."""
    csum = seed
    n = len(data) // 4
    for (w,) in struct.iter_unpack("<I", data[:n * 4]):
        csum ^= w
    ul = 0
    for b in data[n * 4:]:
        ul = (ul << 8) | b
    return csum ^ ul


def read_cab(data):
    """I file di un cabinet senza compressione, come lo fa tools/fwupd-cab.py."""
    if len(data) < 36 or data[:4] != b"MSCF":
        raise Error("non e' un cabinet")
    (_, _, total, _, coff_files, _, _, _, nfolders, nfiles, flags, _, _) = \
        struct.unpack_from("<4sIIIIIBBHHHHH", data, 0)
    if flags != 0 or total != len(data):
        raise Error("cabinet multi-volume, con dati riservati o troncato")
    folders = []
    pos = 36
    for _ in range(nfolders):
        coff, ndata, comp = struct.unpack_from("<IHH", data, pos)
        pos += 8
        if comp != 0:
            raise Error("cabinet compresso: estrai firmware.bin con gcab -x")
        parts = []
        p = coff
        for _ in range(ndata):
            csum, cb, cbu = struct.unpack_from("<IHH", data, p)
            chunk = data[p + 8:p + 8 + cb]
            if len(chunk) != cb or cb != cbu:
                raise Error("blocco CFDATA non valido")
            if csum and cab_checksum(data[p + 4:p + 8], cab_checksum(chunk)) != csum:
                raise Error("checksum di un blocco CFDATA sbagliato: cabinet corrotto")
            parts.append(chunk)
            p += 8 + cb
        folders.append(b"".join(parts))
    files = {}
    pos = coff_files
    for _ in range(nfiles):
        size, off, ifolder = struct.unpack_from("<IIH", data, pos)
        pos += 16
        end = data.index(b"\0", pos)
        name = data[pos:end].decode("ascii", "replace")
        pos = end + 1
        if ifolder >= len(folders) or off + size > len(folders[ifolder]):
            raise Error("%s fuori dal cabinet" % name)
        files[name] = folders[ifolder][off:off + size]
    return files


def parse_metainfo(xml):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise Error("firmware.metainfo.xml non valido: %s" % e)
    guids = [e.text.strip().lower() for e in root.iter("firmware") if e.get("type") == "flashed" and e.text]
    rels = root.findall("releases/release")
    fmt = [e.text for e in root.iter("value") if e.get("key") == "LVFS::VersionFormat"]
    if len(guids) != 1 or len(rels) != 1:
        raise Error("metainfo: attesi un GUID e una release")
    return {"id": root.findtext("id"), "guid": uuid.UUID(guids[0]), "version": rels[0].get("version"),
            "format": fmt[0] if fmt else None}


def verify_jcat(jcat, files, cert, label="firmware.jcat"):
    """SHA-256 e firma PKCS#7 di ogni file in files ({nome: contenuto}), come
    le controlla fwupd con il certificato in /etc/pki/fwupd (anche per i
    metadati di un remote)."""
    if not shutil.which("openssl"):
        raise Error("serve openssl per verificare la firma")
    try:
        items = {i["Id"]: i["Blobs"] for i in json.loads(gzip.decompress(jcat))["Items"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Error("%s non valido: %s" % (label, e))
    for name in files:
        blobs = items.get(name, [])
        sums = [b["Data"] for b in blobs if b.get("Kind") == JCAT_SHA256]
        sigs = [b["Data"] for b in blobs if b.get("Kind") == JCAT_PKCS7]
        if sums != [hashlib.sha256(files[name]).hexdigest()]:
            raise Error("%s: SHA-256 di %s mancante o sbagliato" % (label, name))
        if len(sigs) != 1:
            raise Error("%s: %s senza firma PKCS#7" % (label, name))
        with tempfile.TemporaryDirectory() as tmp:
            sig = os.path.join(tmp, "sig.pem")
            content = os.path.join(tmp, "content.bin")
            with open(sig, "w") as f:
                f.write(sigs[0])
            with open(content, "wb") as f:
                f.write(files[name])
            r = openssl("smime", "-verify", "-binary", "-inform", "PEM", "-in", sig, "-content", content,
                        "-CAfile", cert, "-purpose", "any", "-partial_chain", "-out", os.devnull)
        if r.returncode != 0:
            raise Error("%s: firma di %s non valida per %s" % (label, name, cert))


def load_cab(path, data):
    files = read_cab(data)
    for name in ("firmware.bin", "firmware.metainfo.xml"):
        if name not in files:
            raise Error("pacchetto fwupd senza %s" % name)
    meta = parse_metainfo(files["firmware.metainfo.xml"])
    cap = parse_capsule(files["firmware.bin"])
    v = cap["version"]
    if meta["guid"] != cap["type_id"]:
        raise Error("metainfo per %s, capsula per %s" % (meta["guid"], cap["type_id"]))
    # i pacchetti fino a v1.3.6-rc1 hanno il formato "triplet", i successivi "quad"
    if meta["format"] == "quad":
        same = meta["version"] == version_quad(v)
    else:
        same = meta["format"] == "triplet" and old_layout(v) and meta["version"] == version_triplet(v)
    if not same:
        raise Error("metainfo: versione %s (%s), la capsula e' %s (quad %s)" % (meta["version"], meta["format"],
                                                                              version_str(v), version_quad(v)))
    cap["cab"] = {"files": files, "meta": meta}
    return files["firmware.bin"], cap


def load_capsule(path):
    """Una capsula, o la capsula di un pacchetto fwupd (.cab)."""
    with open(path, "rb") as f:
        data = f.read()
    try:
        if data[:4] == b"MSCF":
            return load_cab(path, data)
        return data, parse_capsule(data)
    except Error as e:
        raise Error("%s: %s" % (path, e))


def check_capsule(cap, fw=None, current_only=False):
    """Quello che il firmware fw (esrt_entry(), o nessuno: solo la capsula)
    controllerebbe a parte la firma. current_only (info): le regioni devono
    essere quelle delle capsule di oggi, non anche quelle di una release di
    prima che stage accetta ancora."""
    legacy = legacy_variant_of(cap["type_id"])
    ro1 = ro1_variant_of(cap["type_id"])
    variant = cap["variant"] or ro1 or legacy
    if variant is None:
        raise Error("capsula per un firmware sconosciuto (%s)" % cap["type_id"])
    if fw and fw["legacy"] and not legacy:
        raise Error("qui gira la %s, senza vboot: la v1.3.0 cambia la mappa del flash e si installa una "
                    "volta con flashrom (%s), poi con le capsule" % (version_str(fw["version"]), MIGRATION))
    if fw and not fw["legacy"] and legacy:
        raise Error("capsula della v1.2.x (mappa del flash senza vboot): da un firmware v1.3.0 in su "
                    "si torna alla v1.2.x solo con flashrom")
    if fw and fw.get("ro1") and cap["variant"]:
        raise Error("qui gira la %s dietro la parte RO della v1.3.0: la v1.3.9 riscrive la parte RO "
                    "(una cache-as-RAM per mrc e nri) e si installa una volta con flashrom (%s), "
                    "poi con le capsule" % (version_str(fw["version"]), RO_MIGRATION))
    if fw and not fw["legacy"] and not fw.get("ro1") and ro1:
        raise Error("capsula della v1.3.0-v1.3.8: i suoi slot non partono dietro la parte RO della "
                    "v1.3.9, indietro si va solo con flashrom (tutta l'immagine di quella release)")
    if fw and variant != fw["variant"]:
        raise Error("capsula della variante %s, qui gira la %s: per cambiare variante si usa "
                    "flashrom (docs/flashing.md)" % (variant, fw["variant"]))
    if legacy:
        accepted = [LEGACY_REGIONS]
    elif current_only:
        accepted = [CURRENT_REGIONS.get(variant, REGIONS)]
    else:
        accepted = ACCEPTED_REGIONS.get(variant, [REGIONS])
    if cap["regions"] not in accepted:
        if not legacy and cap["regions"] in ACCEPTED_REGIONS.get(variant, []):
            raise Error("la capsula scrive %s, come quelle di prima: una capsula nuova scrive %s "
                        "(stage la accetta ancora)" % (" ".join(cap["regions"]), " ".join(accepted[0])))
        raise Error("la capsula scrive %s, attese %s" % (cap["regions"] or "tutto il flash",
                                                       " o ".join(str(a) for a in accepted)))
    size = FLAVOURS[variant][2] if variant in FLAVOURS else ROM_SIZE
    if len(cap["image"]) != size:
        raise Error("immagine di %d byte, attesi %d" % (len(cap["image"]), size))


# --- il sistema --------------------------------------------------------------

def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def esrt_entry():
    """La voce dell'ESRT del firmware coreboot, se c'e'."""
    if not os.path.isdir(ESRT):
        return None
    for e in sorted(os.listdir(ESRT)):
        d = os.path.join(ESRT, e)
        try:
            guid = uuid.UUID(read_text(os.path.join(d, "fw_class")))
        except (TypeError, ValueError):
            continue
        name = variant_of(guid)
        ro1 = ro1_variant_of(guid)
        legacy = legacy_variant_of(guid)
        if name is None and ro1 is None and legacy is None:
            continue
        num = lambda f: int(read_text(os.path.join(d, f)) or "0", 0)
        return {
            "variant": name or ro1 or legacy,
            "legacy": legacy is not None,
            "ro1": ro1 is not None,
            "guid": guid,
            "version": num("fw_version"),
            "lsv": num("lowest_supported_fw_version"),
            "last_version": num("last_attempt_version"),
            "last_status": num("last_attempt_status"),
        }
    return None


def efivar_path(name):
    return os.path.join(EFIVARS, "%s-%s" % (name, GLOBAL_GUID))


def read_u64_var(name):
    try:
        with open(efivar_path(name), "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    if len(raw) != 12:
        raise Error("%s: %d byte, attesi 4 di attributi e 8 di valore" % (name, len(raw)))
    return struct.unpack("<IQ", raw)


def set_immutable(path, on):
    """efivarfs crea molte variabili immutabili (chattr +i)."""
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            flags = struct.unpack("i", fcntl.ioctl(fd, FS_IOC_GETFLAGS, struct.pack("i", 0)))[0]
        except OSError:
            return False
        was = bool(flags & FS_IMMUTABLE_FL)
        new = (flags | FS_IMMUTABLE_FL) if on else (flags & ~FS_IMMUTABLE_FL)
        if new != flags:
            fcntl.ioctl(fd, FS_IOC_SETFLAGS, struct.pack("i", new))
        return was
    finally:
        os.close(fd)


def write_os_indications(value):
    path = efivar_path("OsIndications")
    cur = read_u64_var("OsIndications")
    attrs = cur[0] if cur else VAR_ATTRS
    was = set_immutable(path, False) if cur else False
    try:
        # efivarfs vuole attributi e dati in una sola write()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            data = struct.pack("<IQ", attrs, value)
            if os.write(fd, data) != len(data):
                raise Error("OsIndications: scrittura incompleta")
        finally:
            os.close(fd)
    finally:
        if was:
            set_immutable(path, True)


def os_indications():
    cur = read_u64_var("OsIndications")
    return cur[1] if cur else 0


def cod_supported():
    cur = read_u64_var("OsIndicationsSupported")
    return bool(cur and cur[1] & FILE_CAPSULE_DELIVERY)


def mounted_vfat():
    out = {}
    with open(MOUNTS) as f:
        for line in f:
            dev, mnt, fstype = line.split()[:3]
            if fstype == "vfat":
                out[mnt.replace("\\040", " ")] = dev
    return out


def find_esp(explicit):
    if explicit:
        if not os.path.isdir(os.path.join(explicit, "EFI")):
            raise Error("%s: nessuna cartella EFI, non sembra un'ESP" % explicit)
        return explicit
    vfat = mounted_vfat()
    esps = []
    try:
        out = subprocess.run(["lsblk", "-J", "-o", "PATH,PARTTYPE,MOUNTPOINT"],
                             capture_output=True, check=True).stdout
        for dev in json.loads(out).get("blockdevices", []):
            stack = [dev]
            while stack:
                d = stack.pop()
                stack.extend(d.get("children") or [])
                if (d.get("parttype") or "").lower() in ESP_TYPES and d.get("mountpoint") in vfat:
                    esps.append(d["mountpoint"])
    except (OSError, subprocess.CalledProcessError, ValueError):
        pass
    if not esps:
        esps = [m for m in ("/boot/efi", "/efi", "/boot") if m in vfat]
    esps = [m for m in dict.fromkeys(esps) if os.path.isdir(os.path.join(m, "EFI"))]
    if len(esps) != 1:
        raise Error("ESP %s: indicala con --esp DIR" % ("non trovata" if not esps else
                                                         "ambigua (%s)" % ", ".join(esps)))
    return esps[0]


def staged_files(esp):
    d = os.path.join(esp, CAPSULE_DIR)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d)
                  if os.path.isfile(os.path.join(d, f)))


def power():
    """(alimentatore collegato o None, carica della batteria o None)"""
    ac = None
    charge = None
    base = POWER_SUPPLY
    for p in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        kind = read_text(os.path.join(base, p, "type"))
        if kind == "Mains":
            ac = (read_text(os.path.join(base, p, "online")) == "1") or bool(ac)
        elif kind == "Battery" and charge is None:
            c = read_text(os.path.join(base, p, "capacity"))
            charge = int(c) if c and c.isdigit() else None
    return ac, charge


# --- il ME: le stringhe OEM di SMBIOS ------------------------------------------
#
# Sul M920x (dalla v1.4.0-rc4) coreboot legge HFSTS1-6 dell'HECI prima di
# scrivere le tabelle, quando il ME spento non l'ha ancora nascosta, e mette
# in due stringhe di SMBIOS tipo 11 "ME: <stato>" e "ME HFSTS: <6 parole>". Qui
# si decodifica HFSTS1 (intelblocks/me_12.h, union me_hfsts1).
ME_HFS1_CWS_NORMAL = 5            # intelblocks/cse.h
ME_MODE_TEXT = {
    3: "disattivata (soft temporary disable)",
    2: "modo debug",
    4: "security override (jumper)",
    5: "security override (messaggio HECI)",
}
ME_HFSTS_RE = re.compile(r"ME HFSTS: ((?:[0-9A-F]{8} ){5}[0-9A-F]{8})")
# Sul W541 (ME 9, Lynx Point) le stesse due stringhe, da una copia dei
# registri presa all'inizio di BS_DEV_INIT, prima che me_disable nasconda
# l'HECI (mainboard/lenovo/haswell/me_status.c): HFS 0x40, HFS2 0x48 e 0x60,
# 0x64, 0x68, 0x6c. Il riassunto guarda prima HFS2: un ME fermo nel BUP non e'
# mai "acceso". Le frasi del firmware, in italiano
ME9_TEXT = (
    (r"Disabled \(AltMeDisable, BUP\)", "disattivata (AltMeDisable, BUP)"),
    (r"Stopped in BUP \(state (0x[0-9a-f]{2})\)", "ferma nel BUP (stato %s)"),
    (r"Disabled \(soft temporary disable\)", "disattivata (soft temporary disable)"),
    (r"Enabled", "attiva"),
    (r"Enabled, not ready \(state (\d+)\)", "attiva ma non pronta (stato %s)"),
    (r"Security override \(jumper\)", "security override (jumper)"),
    (r"Security override \(HECI message\)", "security override (messaggio HECI)"),
    (r"Debug", "modo debug"),
    (r"Mode (\d+)", "modo %s"),
    (r"Not available", "non letta dal firmware (HECI spenta o nascosta all'avvio)"),
)
# lynxpoint/me.h: ME_HFS2_PHASE_BUP, ME_HFS2_STATE_BUP_CHECK_STRAP
ME9_PHASE_BUP, ME9_STATE_CHECK_STRAP = 1, 0x0a
# La prima release di ogni variante che scrive le stringhe (lo slot di una
# release di prima, anche dopo un ritorno di vboot, non le ha). Sul W541 la
# release che porta mainboard/lenovo/haswell/me_status.c non ha ancora un
# tag: None finche' non esce, e il testo dice solo "la release con lo stato
# del ME"
ME_STRINGS_SINCE = {"m920x-fsp": "v1.4.0-rc4", "mrc": None, "nri": None}


def me_strings_since(variant):
    """La release dalla quale la variante scrive le stringhe del ME, per il testo."""
    return ME_STRINGS_SINCE.get(variant) or "release con lo stato del ME"


def smbios_structures(data):
    """(tipo, [stringhe]) di ogni struttura SMBIOS in data, fino alla fine
    della tabella (tipo 127)."""
    pos = 0
    while pos + 4 <= len(data):
        stype, length = data[pos], data[pos + 1]
        if length < 4 or pos + length > len(data):
            return
        end = data.find(b"\0\0", pos + length)
        if end < 0:
            return
        yield stype, [s.decode("ascii", "replace") for s in data[pos + length:end].split(b"\0") if s]
        if stype == 127:
            return
        pos = end + 2


def oem_strings():
    """Le stringhe delle strutture SMBIOS tipo 11, None se sysfs non ha le
    tabelle; PermissionError senza root."""
    if os.path.isdir(DMI_ENTRIES):
        out = []
        names = [e for e in os.listdir(DMI_ENTRIES) if re.fullmatch(r"11-\d+", e)]
        for e in sorted(names, key=lambda e: int(e[3:])):
            with open(os.path.join(DMI_ENTRIES, e, "raw"), "rb") as f:
                for _, strings in smbios_structures(f.read()):
                    out += strings
        return out
    if os.path.isfile(DMI_TABLE):
        with open(DMI_TABLE, "rb") as f:
            data = f.read()
        return [s for t, strings in smbios_structures(data) if t == 11 for s in strings]
    return None


def me_strings(strings):
    """(riassunto, [6 parole]) delle stringhe OEM del ME, None dove mancano."""
    summary = words = None
    for s in strings or []:
        m = ME_HFSTS_RE.fullmatch(s)
        if m:
            words = [int(w, 16) for w in m.group(1).split()]
        elif s.startswith("ME: "):
            summary = s[4:]
    return summary, words


def me9_summary(h1, h2):
    """Il riassunto di coreboot sul W541 (mainboard_me_summary()) da HFS e HFS2."""
    ws, err, mode = h1 & 0xF, (h1 >> 12) & 0xF, (h1 >> 16) & 0xF
    phase, state = h2 >> 28, (h2 >> 16) & 0xFF
    if phase == ME9_PHASE_BUP and state == ME9_STATE_CHECK_STRAP and err == 0:
        return "Disabled (AltMeDisable, BUP)"
    if phase == ME9_PHASE_BUP:
        return "Stopped in BUP (state 0x%02x)" % state
    if mode == 0:
        return "Enabled" if ws == ME_HFS1_CWS_NORMAL else "Enabled, not ready (state %d)" % ws
    return {3: "Disabled (soft temporary disable)", 4: "Security override (jumper)",
            5: "Security override (HECI message)", 2: "Debug"}.get(mode, "Mode %d" % mode)


def me9_text(summary, words):
    """Lo stato del ME del W541 in italiano: la frase del firmware (o, senza,
    quella che direbbe dalle parole) e i numeri di HFS e HFS2."""
    if summary is None and words:
        summary = me9_summary(words[0], words[1])
    text = summary
    for rx, it in ME9_TEXT:
        m = re.fullmatch(rx, summary or "")
        if m:
            text = it % m.groups() if m.groups() else it
            break
    if words:
        h1, h2 = words[0], words[1]
        text += ", stato di lavoro %d, modo %d, codice di errore %d, fase %d stato 0x%02x" % (
            h1 & 0xF, (h1 >> 16) & 0xF, (h1 >> 12) & 0xF, h2 >> 28, (h2 >> 16) & 0xFF)
    return text


def me_status(board=None):
    """Lo stato del ME dalle stringhe OEM di coreboot, in italiano; None se
    il firmware non le scrive. board "w541": quelle del ME 9 (me9_text()).
    PermissionError senza root."""
    summary, words = me_strings(oem_strings())
    if words is None and summary is None:
        return None
    if board == "w541":
        text = me9_text(summary, words)
    elif words:
        h1 = words[0]
        ws, err, mode = h1 & 0xF, (h1 >> 12) & 0xF, (h1 >> 16) & 0xF
        if mode == 0:
            text = "attiva" if ws == ME_HFS1_CWS_NORMAL else "attiva ma non pronta"
        else:
            text = ME_MODE_TEXT.get(mode, "modo %d" % mode)
        text += ", stato di lavoro %d, codice di errore %d" % (ws, err)
    else:
        # solo la riga riassuntiva (HECI non letta): come la scrive il firmware
        text = summary
    if not os.path.exists(HECI_PCI):
        text += "; HECI (00:16.0) nascosta al sistema"
    return text


# --- le release --------------------------------------------------------------

def http_get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "w541-coreboot-update"})
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# Il nome di una release nel tag: vX.Y.Z[-rcN]-<nome> -> <nome> (mrc,
# m920x-fsp), None se non e' un nome di FLAVOURS
def release_flavour(tag):
    m = re.match(r"^v\d+\.\d+\.\d+(?:-rc\d+)?-([a-z0-9-]+)$", tag)
    return m.group(1) if m and m.group(1) in FLAVOURS else None


def release_key(tag):
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)(-rc\d+)?-([a-z0-9-]+)$", tag)
    if not m or m.group(5) not in FLAVOURS:
        return None
    # a parita' di numeri la release vera viene dopo le -rcN; i numeri del
    # suffisso come numeri (-rc10 dopo -rc9): re.split alterna testo e cifre
    suffix = tuple(int(x) if i % 2 else x for i, x in enumerate(re.split(r"(\d+)", m.group(4) or "")))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) is None, suffix)


def download_capsule(rel, dest):
    """La capsula di una release di GitHub (la voce JSON dell'API), controllata
    con il suo SHA256SUMS."""
    tag = rel["tag_name"]
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    flavour = release_flavour(tag)
    if flavour is None:
        raise Error("%s: non e' il tag di una release di ouroBIOS" % tag)
    board, variant, _ = FLAVOURS[flavour]
    cap_name = "%s-coreboot-%s-%s.cap" % (board, tag[:-len(flavour) - 1], variant)
    if cap_name not in assets or "SHA256SUMS" not in assets:
        raise Error("%s: senza %s o SHA256SUMS (le capsule ci sono dalla v1.2.0)" % (tag, cap_name))
    print("release %s: scarico %s" % (tag, cap_name))
    sums = http_get(assets["SHA256SUMS"]).decode()
    want = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == cap_name:
            want = parts[0].lower()
    if not want:
        raise Error("SHA256SUMS di %s senza %s" % (tag, cap_name))
    data = http_get(assets[cap_name])
    if hashlib.sha256(data).hexdigest() != want:
        raise Error("%s: SHA-256 diverso da SHA256SUMS, download corrotto" % cap_name)
    path = os.path.join(dest, cap_name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def download_latest(variant, pre, dest):
    rels = json.loads(http_get("https://api.github.com/repos/%s/releases?per_page=50" % REPO,
                               "application/vnd.github+json"))
    best = None
    for r in rels:
        tag = r.get("tag_name", "")
        if r.get("draft") or release_flavour(tag) != variant or release_key(tag) is None:
            continue
        # le candidate (vX.Y.Z-rcN) solo con --pre; la nri fino alla v1.3.8
        # usciva pre-release anche come release: quelle contano come release
        candidate = not release_key(tag)[3]
        if not pre and (candidate or (r.get("prerelease") and variant != "nri")):
            continue
        if best is None or release_key(tag) > release_key(best["tag_name"]):
            best = r
    if best is None:
        raise Error("nessuna release %s con capsula su github.com/%s" % (variant, REPO))
    return download_capsule(best, dest)


def download_tag(tag, dest):
    try:
        rel = json.loads(http_get("https://api.github.com/repos/%s/releases/tags/%s" % (REPO, tag),
                                  "application/vnd.github+json"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Error("la release %s non c'e' su github.com/%s: --capsule FILE" % (tag, REPO))
        raise
    return download_capsule(rel, dest)


# --- i comandi ---------------------------------------------------------------

def need_root():
    if os.geteuid() != 0:
        raise Error("serve root (sudo): si scrivono variabili UEFI e l'ESP")


def need_firmware():
    if not os.path.isdir(EFIVARS):
        raise Error("niente %s: Linux non e' partito in UEFI" % EFIVARS)
    fw = esrt_entry()
    if fw is None or not cod_supported():
        raise Error("il firmware che gira non applica capsule (e' piu' vecchio della v1.2.0?): "
                    "la prima volta si scrive con flashrom, docs/flashing.md")
    return fw


def print_capsule(path, cap):
    if "cab" in cap:
        print("pacchetto: %s (fwupd, %s)" % (path, cap["cab"]["meta"]["id"]))
        print("           %s" % " ".join(sorted(cap["cab"]["files"])))
    print("capsula:   %s" % (path if "cab" not in cap else "firmware.bin"))
    legacy = legacy_variant_of(cap["type_id"])
    ro1 = ro1_variant_of(cap["type_id"])
    print("firmware:  ouroBIOS, variante %s%s (%s)" % (
        cap["variant"] or ro1 or legacy or "?",
        ", v1.2.x senza vboot" if legacy else ", v1.3.0-v1.3.8 (la prima parte RO)" if ro1 else "",
        cap["type_id"]))
    print("versione:  %s, minima %s" % (version_str(cap["version"]), version_str(cap["lsv"])))
    print("regioni:   %s" % (" ".join(cap["regions"]) or "tutto il flash"))
    signer = signer_of(cap)
    if signer:
        print("firmata:   %s" % signer[0])
        print("           SHA-256 %s" % signer[1])


def cmd_info(args):
    data, cap = load_capsule(args.capsule)
    print_capsule(args.capsule, cap)
    check_capsule(cap, current_only=True)
    if args.guid and cap["type_id"] != uuid.UUID(args.guid):
        raise Error("GUID %s, atteso %s" % (cap["type_id"], args.guid))
    if args.fw_version is not None and cap["version"] != args.fw_version:
        raise Error("versione %s, attesa %s" % (version_str(cap["version"]), version_str(args.fw_version)))
    if args.lsv is not None and cap["lsv"] != args.lsv:
        raise Error("versione minima %s, attesa %s" % (version_str(cap["lsv"]), version_str(args.lsv)))
    if args.rom:
        with open(args.rom, "rb") as f:
            if f.read() != cap["image"]:
                raise Error("l'immagine nella capsula non e' %s" % args.rom)
        print("immagine:  uguale a %s" % args.rom)
    if args.same_as:
        with open(args.same_as, "rb") as f:
            if f.read() != data:
                raise Error("la capsula non e' %s" % args.same_as)
        print("capsula:   uguale a %s" % args.same_as)
    cert = args.cert or default_cert()
    if cert and (args.cert or shutil.which("openssl")):
        verify_signature(cap, cert)
        print("firma:     valida per %s" % cert)
        if "cab" in cap:
            if "firmware.jcat" not in cap["cab"]["files"]:
                raise Error("pacchetto fwupd senza firmware.jcat: fwupd non lo installa")
            files = cap["cab"]["files"]
            verify_jcat(files["firmware.jcat"],
                        {n: files[n] for n in ("firmware.bin", "firmware.metainfo.xml")}, cert)
            print("fwupd:     firmware.jcat valido per %s" % cert)
    elif args.cert is None:
        print("firma:     non verificata (serve openssl e keys/capsule-signing.pem)")
    return 0


def cmd_status(args):
    fw = esrt_entry()
    bios = read_text(BIOS_VERSION)
    if fw is None:
        # i file dell'ESRT sono solo di root
        if os.geteuid() != 0 and os.path.isdir(ESRT) and os.listdir(ESRT):
            print("firmware:  %s; ESRT, ME e protezione del flash non leggibili senza root (sudo)" % (bios or "?"))
            return 0
        print("firmware:  %s, senza aggiornamento con capsula (prima della v1.2.0?)" % (bios or "?"))
        return 0
    print("firmware:  ouroBIOS, variante %s (BIOS %s)" % (fw["variant"], bios or "?"))
    if fw["legacy"]:
        print("mappa:     senza vboot (v1.2.x): la v1.3.0 si installa una volta con flashrom (%s)" % MIGRATION)
    elif fw["ro1"]:
        print("mappa:     vboot, due slot RW, la parte RO della v1.3.0: la v1.3.9 la riscrive e si "
              "installa una volta con flashrom (%s)" % RO_MIGRATION)
    else:
        print("mappa:     vboot, due slot RW (una capsula scrive quello che non gira)")
    print("versione:  %s, minima per una capsula %s" % (version_str(fw["version"]), version_str(fw["lsv"])))
    board = FLAVOURS.get(fw["variant"], (None,))[0]
    try:
        me = me_status(board)
    except PermissionError:
        me = "non leggibile senza root (sudo)"
    except OSError as e:
        me = "tabelle SMBIOS non lette: %s" % e
    if me is None and fw["variant"] in ME_STRINGS_SINCE:
        # anche lo slot di una release di prima, dopo un ritorno di vboot
        me = "non indicato da questo firmware (prima della %s)" % me_strings_since(fw["variant"])
    if me:
        print("ME:        %s" % me)
    if fw["last_version"]:
        print("ultimo:    %s, %s" % (version_str(fw["last_version"]), attempt_str(fw["last_status"])))
        # riuscito vuol dire scritto: se lo slot nuovo non si verifica o non
        # arriva al payload, vboot torna al vecchio e l'ESRT lo dice solo cosi'
        # (tools/qemu-update.py, passi 6 e 7)
        if not fw["legacy"] and fw["last_status"] == 0 and fw["last_version"] != fw["version"]:
            print("nota:      la capsula %s e' stata scritta, ma gira la %s: vboot e' tornato all'altro "
                  "slot (quello nuovo non si e' verificato o non e' partito), si e' tornati indietro dal "
                  "setup (Firmware Update), o il flash e' stato riscritto dopo. Gli slot: sudo flashrom "
                  "-p internal -r flash.bin, poi update.py vboot flash.bin"
                  % (version_str(fw["last_version"]), version_str(fw["version"])))
            if "RW_MRC_CACHE" not in CURRENT_REGIONS.get(fw["variant"], REGIONS):
                print("           Il training della RAM resta con la capsula: se la release nuova non parte "
                      "con quello salvato, update.py other-slot --retrain la riprova con un training nuovo")
    else:
        print("ultimo:    nessun aggiornamento con capsula")
    print("su disco:  %s" % ("supportato" if cod_supported() else "NON supportato da questo firmware"))
    # prima dell'ESP: senza root o senza ESP status finisce li'
    for label, text in protection_lines():
        # "protezione:" e' lunga quanto la colonna
        print("%-11s%s" % (label + ":" + (" " if len(label) >= 10 else ""), text))
    armed = bool(os_indications() & FILE_CAPSULE_DELIVERY)
    try:
        esp = find_esp(args.esp)
        files = staged_files(esp)
    except Error as e:
        print("ESP:       %s" % e)
        return 0
    except PermissionError:
        print("ESP:       non leggibile senza root (sudo)")
        return 0
    for f in files:
        try:
            _, cap = load_capsule(f)
            what = "%s %s" % (any_variant_of(cap["type_id"]), version_str(cap["version"]))
        except (Error, OSError) as e:
            what = str(e)
        print("in attesa: %s (%s)" % (f, what))
    if files and armed:
        print("           si applica al prossimo avvio")
    elif files:
        print("           NON si applica: manca il bit di OsIndications (stage di nuovo, o cancel)")
    elif armed:
        print("in attesa: nessun file, ma il bit di OsIndications e' acceso (cancel lo spegne)")
    else:
        print("in attesa: niente")
    return 0


def stage_capsule(path, data, cap, fw, args, allow_older):
    """I controlli del firmware, poi la capsula nell'ESP e il bit di
    OsIndications: si applica al prossimo avvio."""
    print_capsule(path, cap)
    check_capsule(cap, fw)
    cert = args.cert or default_cert()
    if cert and shutil.which("openssl"):
        verify_signature(cap, cert)
        print("firma:     valida")
    if cap["version"] < fw["lsv"]:
        raise Error("%s e' piu' vecchia della minima %s: il firmware la rifiuterebbe"
                    % (version_str(cap["version"]), version_str(fw["lsv"])))
    if cap["version"] <= fw["version"] and not allow_older:
        raise Error("gira gia' la %s: per reinstallare o tornare indietro --allow-older"
                    % version_str(fw["version"]))
    ac, charge = power()
    if ac is False and not args.on_battery:
        raise Error("collega l'alimentatore (o --on-battery: il firmware aspetta comunque "
                    "una carica del 25%% o l'alimentatore). Batteria: %s%%" % charge)
    esp = find_esp(args.esp)
    d = os.path.join(esp, CAPSULE_DIR)
    os.makedirs(d, exist_ok=True)
    for f in staged_files(esp):
        if os.path.basename(f) != STAGED_NAME:
            print("attenzione: c'e' anche %s, il firmware applica anche quello" % f)
    dst = os.path.join(d, STAGED_NAME)
    part = dst + ".part"
    with open(part, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(part, dst)
    os.sync()
    with open(dst, "rb") as f:
        if hashlib.sha256(f.read()).digest() != hashlib.sha256(data).digest():
            raise Error("%s: la copia nell'ESP non e' uguale" % dst)
    write_os_indications(os_indications() | FILE_CAPSULE_DELIVERY)
    if not os_indications() & FILE_CAPSULE_DELIVERY:
        raise Error("OsIndications non scritta")


def finish_stage(args):
    if args.reboot:
        subprocess.run(["systemctl", "reboot"], check=False)
    else:
        print("  sudo systemctl reboot")
    return 0


def cmd_stage(args):
    need_root()
    fw = need_firmware()
    with tempfile.TemporaryDirectory() as tmp:
        path = args.capsule
        if args.latest:
            path = download_latest(fw["variant"], args.pre, tmp)
        data, cap = load_capsule(path)
        stage_capsule(path, data, cap, fw, args, args.allow_older)
    print("\npronta: %s %s -> %s, si applica al prossimo riavvio." % (
        fw["variant"], version_str(fw["version"]), version_str(cap["version"])))
    print("Il firmware la verifica e la scrive in circa un minuto, con una barra sotto il")
    print("logo: non spegnere. Poi riparte da solo con il firmware nuovo.")
    print_training(cap)
    return finish_stage(args)


def print_training(cap):
    """Cosa succede al training della RAM con la capsula cap."""
    if "RW_MRC_CACHE" in cap["regions"]:
        print("La capsula svuota anche il training della RAM: il primo avvio lo rifa' e dura di piu'.")
    else:
        print("Il training della RAM resta: lo slot nuovo lo rifa' solo se non vale per lui (un altro")
        print("FSP-M, processore o Hyper-Threading). Se lo slot nuovo non partisse due volte di fila,")
        print("vboot torna a quello di adesso: allora update.py other-slot --retrain.")


def cmd_cancel(args):
    need_root()
    esp = find_esp(args.esp)
    for f in staged_files(esp):
        if os.path.basename(f) == STAGED_NAME or args.all:
            os.remove(f)
            print("tolta %s" % f)
        else:
            print("lasciata %s (non e' di update.py: --all per toglierla)" % f)
    if os_indications() & FILE_CAPSULE_DELIVERY:
        write_os_indications(os_indications() & ~FILE_CAPSULE_DELIVERY)
        print("bit di OsIndications spento")
    return 0


# --- vboot: lo stato in RW_NVRAM ----------------------------------------------
#
# Record V1 di vboot da 16 byte, accodati dall'inizio della regione (coreboot,
# vbnv_flash.c; il payload, FmpDeviceSmmLib); il corrente e' l'ultimo prima del
# primo cancellato. Campi da vboot_reference, 2nvstorage_fields.h.
NV_RECORD = 16
NV_RESULTS = ("-", "in prova", "confermato", "fallito")


def nv_crc8(data):
    """Il CRC-8 di vboot (x^8 + x^2 + x + 1)."""
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc ^= 0x1070 << 3
            crc = (crc << 1) & 0xffff
    return crc >> 8


def fmap_areas(data):
    """Le aree della FMAP di un'immagine del flash, {nome: (offset, size)}; None senza FMAP."""
    pos = data.find(b"__FMAP__")
    while pos >= 0:
        if pos + 56 <= len(data):
            major, _, _, _, _, n = struct.unpack_from("<BBQI32sH", data, pos + 8)
            if major == 1 and pos + 56 + 42 * n <= len(data):
                areas = {}
                for i in range(n):
                    off, size, name, _ = struct.unpack_from("<II32sH", data, pos + 56 + 42 * i)
                    areas[name.split(b"\0")[0].decode("ascii", "replace")] = (off, size)
                return areas
        pos = data.find(b"__FMAP__", pos + 1)
    return None


def nv_state(region):
    """Il record corrente di RW_NVRAM: dict con i campi, o None se non ce n'e' uno valido."""
    used = 0
    while used + NV_RECORD <= len(region) and region[used:used + NV_RECORD] != b"\xff" * NV_RECORD:
        used += NV_RECORD
    st = {"used": used // NV_RECORD, "total": len(region) // NV_RECORD, "offset": used - NV_RECORD}
    rec = region[used - NV_RECORD:used] if used else b""
    if not rec or rec[0] & 0xc3 != 0x40 or nv_crc8(rec[:15]) != rec[15]:
        st["valid"] = False
        return st
    boot, boot2 = rec[1], rec[7]
    st.update(valid=True, try_next=(boot2 >> 3) & 1, try_count=boot & 0x0f,
              tried=(boot2 >> 2) & 1, result=boot2 & 3,
              prev_tried=(boot2 >> 6) & 1, prev_result=(boot2 >> 4) & 3,
              recovery=rec[2])
    return st


def nv_coreboot_current(region):
    """L'offset del record che coreboot (vbnv_flash.c, init_vbnv) prende come corrente:
    una ricerca binaria del confine tra record usati e vuoti, che si fida che dopo il
    primo vuoto sia tutto vuoto."""
    empty = b"\xff" * NV_RECORD
    used_below, empty_above = 0, len(region) // NV_RECORD
    while used_below + 1 < empty_above:
        guess = (used_below + empty_above) // 2
        if region[guess * NV_RECORD:(guess + 1) * NV_RECORD] == empty:
            empty_above = guess
        else:
            used_below = guess
    return used_below * NV_RECORD


# La release scritta in una regione: coreboot mette la sua versione, con
# CONFIG_LOCALVERSION, nel banner del bootblock e di ogni stage. Due release
# nella stessa regione: una scrittura rimasta a meta'.
RELEASE_RE = re.compile(rb"(?:ouroBIOS|w541)-v\d+\.\d+\.\d+(?:-rc\d+)?-(?:[a-z0-9]+-)?(?:mrc|nri|fsp)")


# (X, Y, Z, rc) di una release come la scrive la build (ouroBIOS-vX.Y.Z-rcN-mrc),
# con la release finale dopo tutte le sue rc; release_key e' quella dei tag
RELEASE_KEY_RE = re.compile(r"(?:ouroBIOS|w541)-v(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?-(?:[a-z0-9]+-)?(?:mrc|nri|fsp)")


# la prima release la cui parte RO parte gli slot di tutte e due le varianti
RO_COMMON = (1, 3, 9, 0)


def build_release_key(name):
    m = RELEASE_KEY_RE.search(name or "")
    if not m:
        return None
    x, y, z, rc = m.groups()
    return (int(x), int(y), int(z), int(rc) if rc else 1 << 30)


# Le build di prova della CI (branch ci-test/**): ouroBIOS-ci-N-sha-<board>-<variante>,
# dallo stesso albero delle release. Solo other-slot le accetta, come una
# release di oggi (la cache-as-RAM di dopo la v1.3.9): status e rollback no
CI_BUILD_RE = re.compile(rb"ouroBIOS-ci-\d+-[0-9a-f]{7,}-(?:[a-z0-9]+-)?(?:mrc|nri|fsp)")


def region_builds(data, area):
    """Come region_releases(), con anche le build di prova della CI."""
    off, size = area
    found = region_releases(data, area)
    for m in CI_BUILD_RE.finditer(data[off:off + size]):
        name = m.group().decode()
        if name not in found:
            found.append(name)
    return found


def build_key_or_ci(name):
    """La chiave di build_release_key(); una build della CI vale come una di oggi."""
    key = build_release_key(name)
    if key is None and CI_BUILD_RE.search(name.encode()):
        return (1 << 30,) * 4
    return key


def region_releases(data, area):
    off, size = area
    found = []
    for m in RELEASE_RE.finditer(data[off:off + size]):
        name = m.group().decode()
        if name not in found:
            found.append(name)
    return found


# Il primo chip del flash di ogni board, il solo che flashrom legge quando passa da
# /dev/mtd0: la board, il modulo del kernel che tiene il controller SPI (sul M920x
# e' un dispositivo PCI, 00:1f.5) e il flash intero, in MiB
FIRST_CHIPS = {
    8 << 20: ("W541", "spi_intel_platform", 12),
    16 << 20: ("M920x", "spi_intel_pci", 24),
}


def need_whole_flash(path, data, areas):
    """Una copia senza FMAP grande quanto il primo chip di una board e' solo quel
    chip: flashrom e' passato da /dev/mtd0 perche' il driver del kernel teneva il
    controller SPI."""
    if areas is None and len(data) in FIRST_CHIPS:
        board, module, whole = FIRST_CHIPS[len(data)]
        raise Error("%s: %d MiB, solo il primo chip del %s: flashrom e' passato da /dev/mtd0 "
                    "(driver spi_intel caricato). sudo modprobe -r %s spi_intel, poi rileggi: "
                    "deve venire di %d MiB" % (path, len(data) >> 20, board, module, whole))


def flash_image(path):
    """L'immagine del flash di una release: il .rom, o quella in una capsula (.cap, .cab)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"MSCF" or (len(data) >= 16 and uuid.UUID(bytes_le=data[:16]) == FMP_CAPSULE_GUID):
        return load_capsule(path)[1]["image"]
    return data


def region_diff(a, b, area, block=0x1000):
    """I blocchi da 4 KiB di un'area diversi tra due immagini."""
    off, size = area
    return [o for o in range(off, off + size, block) if a[o:o + block] != b[o:o + block]]


def cmd_vboot(args):
    data = open(args.dump, "rb").read()
    areas = fmap_areas(data)
    need_whole_flash(args.dump, data, areas)
    if areas is not None:
        if "RW_NVRAM" not in areas:
            raise Error("%s: la FMAP non ha RW_NVRAM: un firmware senza vboot (prima della v1.3.0)" % args.dump)
        off, size = areas["RW_NVRAM"]
        if off + size > len(data):
            raise Error("%s: RW_NVRAM (0x%x, %d KiB) fuori dal file" % (args.dump, off, size // 1024))
        region = data[off:off + size]
    elif 0 < len(data) <= 0x100000 and len(data) % NV_RECORD == 0:
        region = data       # solo RW_NVRAM (flashrom -i RW_NVRAM:FILE)
    else:
        raise Error("%s: ne' un'immagine del flash con la FMAP ne' una copia di RW_NVRAM" % args.dump)
    slot = "AB"
    image = None
    if args.image:
        if areas is None:
            raise Error("%s: per --image serve tutto il flash (flashrom -r)" % args.dump)
        image = flash_image(args.image)
        iareas = fmap_areas(image)
        names = ("WP_RO", "RW_SECTION_A", "RW_SECTION_B")
        if len(image) != len(data) or iareas is None or any(iareas.get(n) != areas.get(n) for n in names):
            raise Error("%s: un'immagine con un'altra mappa del flash" % args.image)
    if areas is not None:
        # quale release c'e' nella parte read-only e in ciascuno slot; con
        # --image, se ogni byte e' quello della release
        head = "contenuto:"
        for label, name, whole in (("RO", "WP_RO", "WP_RO"), ("slot A", "FW_MAIN_A", "RW_SECTION_A"),
                                   ("slot B", "FW_MAIN_B", "RW_SECTION_B")):
            if name not in areas or sum(areas[name]) > len(data):
                continue
            found = region_releases(data, areas[name])
            print("%-12s%-8s%s" % (head, label, " + ".join(found) + (
                "  (mescolate: scritto a meta'?)" if len(found) > 1 else "")
                if found else "non riconosciuto: vuoto o rovinato?"))
            if image is not None:
                diff = region_diff(data, image, areas[whole])
                total = areas[whole][1] // 0x1000
                if not diff:
                    print("%20s= %s, tutti i %d blocchi da 4 KiB" % ("", os.path.basename(args.image), total))
                else:
                    print("%20s!= %s: %d blocchi da 4 KiB su %d, da 0x%06x a 0x%06x" % (
                        "", os.path.basename(args.image), len(diff), total, diff[0], diff[-1] + 0xfff))
            head = ""
    st = nv_state(region)
    print("RW_NVRAM:   %d record su %d" % (st["used"], st["total"]))
    if args.all:
        # la storia: ogni record e' lo stato dopo una scrittura (vboot dal
        # bootblock, il payload con la capsula o la conferma dello slot)
        print("            #   prossimo  tent.  corrente          precedente         byte")
        for i in range(st["used"]):
            rec = region[i * NV_RECORD:(i + 1) * NV_RECORD]
            if rec[0] & 0xc3 != 0x40 or nv_crc8(rec[:15]) != rec[15]:
                print("            %-3d record non valido                                          %s" % (i, rec.hex()))
                continue
            b1, b2 = rec[1], rec[7]
            print("            %-3d slot %s    %-5d  slot %s %-10s  slot %s %-10s  %s" % (
                i, slot[(b2 >> 3) & 1], b1 & 0x0f, slot[(b2 >> 2) & 1], NV_RESULTS[b2 & 3],
                slot[(b2 >> 6) & 1], NV_RESULTS[(b2 >> 4) & 3], rec.hex()))
        # quello che legge coreboot, e quello che c'e' oltre il primo record vuoto
        cb = nv_coreboot_current(region)
        beyond = [o for o in range(st["used"] * NV_RECORD, len(region), NV_RECORD)
                  if region[o:o + NV_RECORD] != b"\xff" * NV_RECORD]
        if st["used"] == 0 and not beyond:
            print("coreboot:   nessun record da leggere")
        else:
            print("coreboot:   legge il record a 0x%04x (#%d)%s" % (
                cb, cb // NV_RECORD, "" if cb == st["offset"] else ", NON l'ultimo prima del primo vuoto"))
        if beyond:
            print("oltre:      %d record non vuoti dopo il primo vuoto, da 0x%04x: %s" % (
                len(beyond), beyond[0], " ".join("0x%04x" % o for o in beyond[:8])))
    if not st["valid"]:
        print("stato:      nessun record valido: al prossimo avvio vboot riparte dallo slot A")
        return 0
    n = st["try_count"]
    print("prossimo:   slot %s%s" % (slot[st["try_next"]],
                                     ", %d tentativ%s" % (n, "o" if n == 1 else "i") if n else ""))
    print("corrente:   slot %s, %s" % (slot[st["tried"]], NV_RESULTS[st["result"]]))
    print("precedente: slot %s, %s" % (slot[st["prev_tried"]], NV_RESULTS[st["prev_result"]]))
    if st["recovery"]:
        print("recovery:   richiesto, motivo 0x%02x (questo firmware non ha recovery)" % st["recovery"])
    if st["prev_result"] == 3:
        print("nota:       lo slot %s non si e' verificato o non e' partito, vboot e' passato al %s"
              % (slot[st["prev_tried"]], slot[st["tried"]]))
    return 0


# --- rollback: la release dell'altro slot ----------------------------------------
#
# Dopo un aggiornamento lo slot che non gira tiene la release di prima. La sua
# capsula non vi riscrive niente (i blocchi sono gia' quelli) e chiede a vboot
# di provarlo, con due tentativi: il payload fa il resto come per ogni capsula.

TAG_RE = re.compile(r"v\d+\.\d+\.\d+(?:-rc\d+)?-(?:[a-z0-9]+-)?(?:mrc|nri|fsp)")


def rollback_plan(data, running):
    """Da una copia di tutto il flash, presa in questo avvio, e dalla release
    che gira (bios_version): lo slot che gira, l'altro e la release che c'e'
    dentro, se si puo' tornare a quella."""
    areas = fmap_areas(data)
    need = ("RW_NVRAM", "FW_MAIN_A", "FW_MAIN_B", "RW_SECTION_A", "RW_SECTION_B")
    if areas is None or any(n not in areas or sum(areas[n]) > len(data) for n in need):
        raise Error("serve tutto il flash di un firmware con vboot (v1.3.0 in su): "
                    "sudo flashrom -p internal -r FILE")
    off, size = areas["RW_NVRAM"]
    st = nv_state(data[off:off + size])
    if not st["valid"]:
        raise Error("RW_NVRAM senza un record valido: non si sa quale slot gira")
    slot = "AB"
    cur, other = st["tried"], 1 - st["tried"]
    found = {s: region_releases(data, areas["FW_MAIN_" + slot[s]]) for s in (0, 1)}
    # confrontate per tag (v1.3.1-mrc, v1.4.0-m920x-fsp): il prefisso, w541- o
    # ouroBIOS-, e' cambiato
    tag = lambda name: TAG_RE.search(name or "").group() if TAG_RE.search(name or "") else None
    if running is None or [tag(n) for n in found[cur]] != [tag(running)]:
        raise Error("nello slot %s, quello di questo avvio secondo RW_NVRAM, c'e' %s e gira %s: "
                    "una copia del flash di un altro avvio? rileggila"
                    % (slot[cur], " + ".join(found[cur]) or "altro", running or "?"))
    if len(found[other]) != 1:
        raise Error("slot %s: %s, non c'e' una release a cui tornare (vuoto, rovinato o scritto a "
                    "meta')" % (slot[other], " + ".join(found[other]) or "nessuna release"))
    back = found[other][0]
    old, new = build_release_key(back), build_release_key(running)
    if old is None or new is None or tag(back) is None:
        raise Error("slot %s: release %s non riconosciuta" % (slot[other], back))
    if tag(back).rsplit("-", 1)[1] != tag(running).rsplit("-", 1)[1]:
        raise Error("slot %s: %s, un'altra variante: si cambia variante con flashrom" % (slot[other], back))
    if old == new:
        raise Error("lo slot %s ha la stessa release che gira, %s: niente a cui tornare" % (slot[other], back))
    if old > new:
        raise Error("lo slot %s ha la %s, piu' recente di quella che gira: non e' un ritorno indietro "
                    "(vboot vi e' tornato da li'? update.py vboot). Per riprovarla: stage" % (slot[other], back))
    return {"current": slot[cur], "other": slot[other], "running": running, "back": back,
            "tag": tag(back), "areas": areas,
            "pending": st["try_count"] > 0 and st["try_next"] == other}


def cmd_rollback(args):
    need_root()
    fw = need_firmware()
    if fw["legacy"]:
        raise Error("v1.2.x: senza vboot non c'e' un altro slot")
    with open(args.dump, "rb") as f:
        flash = f.read()
    need_whole_flash(args.dump, flash, fmap_areas(flash))
    running = RELEASE_KEY_RE.search(read_text(BIOS_VERSION) or "")
    plan = rollback_plan(flash, running.group() if running else None)
    print("gira:      slot %s, %s" % (plan["current"], plan["running"]))
    print("indietro:  slot %s, %s" % (plan["other"], plan["back"]))
    if plan["pending"]:
        print("nota:      vboot ha gia' in programma di provare lo slot %s al prossimo avvio" % plan["other"])
    with tempfile.TemporaryDirectory() as tmp:
        path = args.capsule or download_tag(plan["tag"], tmp)
        data, cap = load_capsule(path)
        names = region_releases(cap["image"], plan["areas"]["FW_MAIN_" + plan["other"]])
        if names != [plan["back"]]:
            raise Error("%s: nello slot %s porta %s, non %s"
                        % (path, plan["other"], " + ".join(names) or "altro", plan["back"]))
        area = plan["areas"]["RW_SECTION_" + plan["other"]]
        diff = region_diff(flash, cap["image"], area)
        if diff:
            print("slot %s:    %d blocchi da 4 KiB su %d diversi dalla release: il firmware li riscrive"
                  % (plan["other"], len(diff), area[1] // 0x1000))
        else:
            print("slot %s:    uguale alla release: il firmware non riscrive niente, cambia solo slot"
                  % plan["other"])
        if args.dry_run:
            print("\n--dry-run: niente di preparato")
            return 0
        stage_capsule(path, data, cap, fw, args, True)
    print("\npronta: al prossimo riavvio %s -> %s (slot %s)." % (plan["running"], plan["back"], plan["other"]))
    print("Il firmware verifica la capsula e chiede a vboot lo slot %s, con due tentativi." % plan["other"])
    print("Se lo slot %s non partisse, vboot tornerebbe allo slot %s." % (plan["other"], plan["current"]))
    print_training(cap)
    return finish_stage(args)


# Un record di RW_NVRAM come lo scrive vbnv_try_other_slot() di coreboot (patch
# 0065): il record corrente con try_next sull'altro slot e i tentativi, CRC
# rifatto; appeso dopo l'ultimo (vbnv_flash.c scrive cosi' un record che
# accende bit), o da solo in una regione cancellata quando e' piena
NV_BOOT_TRY_COUNT_MASK = 0x0f
NV_BOOT2_TRIED = 0x04
NV_BOOT2_TRY_NEXT = 0x08


def nv_try_other(region, tries=2):
    """La regione RW_NVRAM con un record in piu': prova l'altro slot. (regione, slot)"""
    st = nv_state(region)
    if not st["valid"]:
        raise Error("RW_NVRAM senza un record valido: non si sa quale slot gira")
    rec = bytearray(region[st["offset"]:st["offset"] + NV_RECORD])
    if rec[7] & NV_BOOT2_TRIED:
        rec[7] &= ~NV_BOOT2_TRY_NEXT
        other = "A"
    else:
        rec[7] |= NV_BOOT2_TRY_NEXT
        other = "B"
    rec[1] = (rec[1] & ~NV_BOOT_TRY_COUNT_MASK) | (tries & NV_BOOT_TRY_COUNT_MASK)
    rec[15] = nv_crc8(rec[:15])
    new = bytearray(region)
    nxt = st["used"] * NV_RECORD
    if nxt + NV_RECORD > len(region):
        new = bytearray(b"\xff" * len(region))
        nxt = 0
    new[nxt:nxt + NV_RECORD] = rec
    return bytes(new), other


def build_flavour(name, size):
    """La variante (chiave di FLAVOURS) di una build dal suo nome
    (ouroBIOS-v1.4.0-rc4-m920x-fsp, ouroBIOS-ci-151-d0aaa35-m920x-fsp,
    ouroBIOS-v1.4.0-rc4-nri), o dalla dimensione del flash se una sola
    variante ce l'ha; None se non si sa (chi chiama usa REGIONS: rifa' il
    training, il lato sicuro)."""
    for f in sorted(FLAVOURS, key=len, reverse=True):
        if (name or "").endswith("-" + f):
            return f
    sized = [f for f, (_, _, s) in FLAVOURS.items() if s == size]
    return sized[0] if len(sized) == 1 else None


def cmd_other_slot(args):
    """Un'immagine del flash con, nello slot che non gira, lo slot di una release
    (anche dell'altra variante) e RW_NVRAM che chiede a vboot di provarlo: da
    scrivere con flashrom in quelle due regioni soltanto. RW_MRC_CACHE resta
    com'e', vuota solo con --retrain o dove la capsula della release la
    svuota (W541, M920x prima della v1.4.0-rc4)."""
    with open(args.dump, "rb") as f:
        flash = f.read()
    areas = fmap_areas(flash)
    need_whole_flash(args.dump, flash, areas)
    need = ("RW_NVRAM", "RW_MRC_CACHE", "FW_MAIN_A", "FW_MAIN_B", "RW_SECTION_A", "RW_SECTION_B")
    if areas is None or any(n not in areas or sum(areas[n]) > len(flash) for n in need):
        raise Error("serve tutto il flash di un firmware con vboot (v1.3.0 in su): "
                    "sudo flashrom -p internal -r FILE")
    image = flash_image(args.image)
    iareas = fmap_areas(image)
    if len(image) != len(flash) or iareas is None or any(iareas.get(n) != areas.get(n) for n in need):
        raise Error("%s: un'immagine con un'altra mappa del flash" % args.image)
    off, size = areas["RW_NVRAM"]
    nvram, other = nv_try_other(flash[off:off + size])
    current = "B" if other == "A" else "A"
    bios = read_text(BIOS_VERSION) or ""
    running = RELEASE_KEY_RE.search(bios) or CI_BUILD_RE.search(bios.encode())
    running = running.group() if running else None
    if isinstance(running, bytes):
        running = running.decode()
    in_cur = region_builds(flash, areas["FW_MAIN_" + current])
    tag = lambda name: (TAG_RE.search(name or "").group() if TAG_RE.search(name or "")
                       else name)
    if running and [tag(n) for n in in_cur] != [tag(running)]:
        raise Error("nello slot %s, quello di questo avvio secondo RW_NVRAM, c'e' %s e gira %s: "
                    "una copia del flash di un altro avvio? rileggila"
                    % (current, " + ".join(in_cur) or "altro", running))
    names = region_builds(image, iareas["FW_MAIN_" + other])
    if len(names) != 1:
        raise Error("%s: nello slot %s porta %s" % (args.image, other, " + ".join(names) or "nessuna release"))
    # La parte RO lascia alla romstage i dati di vboot, la console e le cache
    # agli indirizzi della cache-as-RAM della sua build (configs/ro-interface.txt):
    # uno slot che li cerca altrove non parte (POST 0x21). Fino alla v1.3.8 ogni
    # variante ha i suoi; dalla v1.3.9 sono uguali, ma diversi da prima, e solo
    # la parte RO di mrc porta mrc.bin
    ro = region_builds(flash, areas["WP_RO"]) if "WP_RO" in areas else []
    ro_variant = ro[0].rsplit("-", 1)[1] if len(ro) == 1 else None
    ro_common = len(ro) == 1 and build_key_or_ci(ro[0]) >= RO_COMMON
    variant = names[0].rsplit("-", 1)[1]
    common = build_key_or_ci(names[0]) >= RO_COMMON
    if ro and not args.force:
        if common != ro_common:
            raise Error("%s cerca nella cache-as-RAM quello che lascia la parte RO %s v1.3.9, qui c'e' "
                        "%s: non parte. Si cambia con flashrom, tutta l'immagine (%s)"
                        % (names[0], "della" if common else "di prima della", ro[0], RO_MIGRATION))
        if variant != ro_variant and not (ro_common and ro_variant == "mrc"):
            raise Error("%s e' la variante %s: non parte dopo la parte RO di questo firmware, %s (%s): "
                        "%s. Si cambia con flashrom: docs/flashing.md"
                        % (names[0], variant, ro_variant, ro[0],
                           "solo quella di mrc, dalla v1.3.9, porta mrc.bin e la cache-as-RAM di tutte "
                           "e due" if ro_common else "fino alla v1.3.8 ogni parte RO parte solo la sua "
                           "variante"))
    # il training della RAM come lo tratta la capsula di quella release: sul
    # M920x dalla v1.4.0-rc4 resta (la sua versione dice allo slot se vale);
    # sul W541 e nelle release del M920x di prima si svuota
    flavour = build_flavour(names[0], len(image))
    retrain = args.retrain or "RW_MRC_CACHE" in CURRENT_REGIONS.get(flavour, REGIONS) \
        or (build_key_or_ci(names[0]) or (0,)) < KEEP_CACHE_SINCE
    regions = ["RW_SECTION_" + other] + (["RW_MRC_CACHE"] if retrain else []) + ["RW_NVRAM"]
    check_flash_writable(areas, regions)
    print("gira:      slot %s, %s" % (current, " + ".join(in_cur) or "?"))
    print("da provare: slot %s, %s (ora: %s)" % (other, names[0],
          " + ".join(region_builds(flash, areas["FW_MAIN_" + other])) or "vuoto"))
    out = bytearray(flash)
    for name in ("RW_SECTION_" + other,):
        o, s = areas[name]
        out[o:o + s] = image[o:o + s]
    if retrain:
        o, s = areas["RW_MRC_CACHE"]
        out[o:o + s] = b"\xff" * s
    out[off:off + size] = nvram
    with open(args.out, "wb") as f:
        f.write(out)
    print("\nscritta %s: come il flash di ora, con lo slot %s della release, %s e"
          % (args.out, other, "RW_MRC_CACHE vuota" if retrain else "il training della RAM di adesso"))
    print("un record in RW_NVRAM che chiede a vboot lo slot %s con due tentativi. Da scrivere con:" % other)
    print("\n  sudo flashrom -p internal --fmap %s -w %s" % (" ".join("-i " + r for r in regions), args.out))
    print("\nSolo quelle %s regioni: parte RO, settings (SMMSTORE), VPD%s restano come sono."
          % ("tre" if retrain else "due", " e registro" if retrain else ", registro e training della RAM"))
    if not retrain:
        print("Lo slot %s rifa' il training solo se quello salvato non vale per lui; se non parte con quello,"
              % other)
        print("rifai l'immagine con --retrain.")
    print("Riavvia subito dopo flashrom, senza sospendere: RW_NVRAM chiede gia' lo slot %s, e una ripresa" % other)
    print("da S3 passerebbe da vboot. Al riavvio parte lo slot %s; se non arriva al payload per due avvii"
          % other)
    print("di fila (spegnere e riaccendere a ogni blocco), vboot torna allo slot %s. BIOS Lock deve essere"
          % current)
    print("spento.")
    return 0


# --- le variabili UEFI in SMMSTORE ---------------------------------------------
#
# Lo store di EDK2 nella regione SMMSTORE: un firmware volume
# (EFI_SYSTEM_NV_DATA_FV), poi VARIABLE_STORE_HEADER e le variabili una dopo
# l'altra, allineate a 4 byte (MdeModulePkg, VariableFormat.h). Si mostrano
# nomi, GUID, stato, attributi e dimensioni, mai i dati.
VAR_STATES = {0x3f: "valida", 0x3e: "valida (in cancellazione)", 0x3d: "cancellata",
              0x3c: "cancellata", 0x7f: "solo header", 0xff: "vuota"}
AUTH_VAR_GUID = bytes.fromhex("782cf3aa7b949a43a1802e144ec37792")


def guid_str(b):
    a, c, d = struct.unpack_from("<IHH", b, 0)
    return "%08x-%04x-%04x-%s-%s" % (a, c, d, b[8:10].hex(), b[10:16].hex())


def var_store(region):
    """Le variabili dello store: lista di dict, e i dati dello store."""
    if region[0x28:0x2c] != b"_FVH":
        raise Error("SMMSTORE: niente firmware volume")
    hlen = struct.unpack_from("<H", region, 0x30)[0]
    fv_len = struct.unpack_from("<Q", region, 0x20)[0]
    sig = region[hlen:hlen + 16]
    size, fmt, state = struct.unpack_from("<IBB", region, hlen + 16)
    auth = sig == AUTH_VAR_GUID
    hsize = 60 if auth else 32
    start = hlen + 28
    end = min(hlen + size, len(region))
    out = []
    off = start
    while off + hsize <= end:
        if struct.unpack_from("<H", region, off)[0] != 0x55aa:
            break
        st, attrs = region[off + 2], struct.unpack_from("<I", region, off + 4)[0]
        if auth:
            nsize, dsize = struct.unpack_from("<II", region, off + 36)
            guid = region[off + 44:off + 60]
        else:
            nsize, dsize = struct.unpack_from("<II", region, off + 8)
            guid = region[off + 16:off + 32]
        if nsize > end or dsize > end:
            out.append({"off": off, "state": st, "name": "?", "guid": guid, "attrs": attrs,
                        "size": dsize, "bad": True})
            break
        name = region[off + hsize:off + hsize + nsize].decode("utf-16-le", "replace").rstrip("\0")
        # data: dove cominciano i dati (li legge solo tools/qemu-smoke.py, sul
        # flash di QEMU; vars non li stampa mai)
        out.append({"off": off, "state": st, "name": name, "guid": guid, "attrs": attrs, "size": dsize,
                    "data": off + hsize + nsize})
        off = (off + hsize + nsize + dsize + 3) & ~3
    # next: dove va la prossima variabile (tools/qemu-update.py ve la scrive,
    # nel flash di QEMU)
    info = {"fv_len": fv_len, "store_size": size, "format": fmt, "health": state, "auth": auth,
            "used": off - start, "free": end - off, "next": off}
    return out, info


def cmd_vars(args):
    data = open(args.dump, "rb").read()
    areas = fmap_areas(data)
    need_whole_flash(args.dump, data, areas)
    if areas is not None and "SMMSTORE" in areas:
        o, s = areas["SMMSTORE"]
        region = data[o:o + s]
    else:
        region = data
    vars_, info = var_store(region)
    print("store:      %s, %d KiB, formato 0x%02x, stato 0x%02x%s" % (
        "autenticato" if info["auth"] else "normale", info["store_size"] // 1024, info["format"],
        info["health"], "" if info["health"] == 0xfe else " (NON sano)"))
    states = {}
    for v in vars_:
        states[VAR_STATES.get(v["state"], "0x%02x" % v["state"])] = states.get(
            VAR_STATES.get(v["state"], "0x%02x" % v["state"]), 0) + 1
    print("variabili:  %s" % ", ".join("%d %s" % (n, k) for k, n in sorted(states.items())))
    print("spazio:     %d KiB usati, %d KiB liberi" % (info["used"] // 1024, info["free"] // 1024))
    pat = re.compile(args.grep, re.I) if args.grep else None
    for v in vars_:
        if pat and not (pat.search(v["name"]) or pat.search(guid_str(v["guid"]))):
            continue
        if not args.all and v["state"] not in (0x3f, 0x3e, 0x7f) and not pat:
            continue
        a = v["attrs"]
        flags = "".join(c for b, c in ((0, "N"), (1, "B"), (2, "R"), (5, "T")) if a >> b & 1)
        print("  %06x %-26s %-4s %6d  %s  %s" % (
            v["off"], VAR_STATES.get(v["state"], "0x%02x" % v["state"]), flags, v["size"],
            guid_str(v["guid"]), v["name"]))
    return 0


# Le opzioni del setup di coreboot (drivers/efi/option.c, EficorebootNvDataGuid)
CB_OPTION_GUID = uuid.UUID("ceae4c1d-335b-4685-a4a0-fc4a94eea085").bytes_le


# Le GUID della FV e dello store che coreboot accetta (drivers/efi/efivars.c)
NV_DATA_FV_GUID = uuid.UUID("fff12b8d-7696-4c8b-a985-2747075b4f50").bytes_le
VAR_GUID = uuid.UUID("ddcf3616-3275-4164-98b6-fe85707ffe7d").bytes_le


def cb_store(region, region_size):
    """Le variabili di uno store SMMSTORE come le valida coreboot prima di
    leggere un'opzione (drivers/efi/efivars.c: validate_fv_header(),
    validate_variable_store_header(), walk_variables()): [(stato, GUID, nome
    in UTF-16 con lo 0 finale, offset dei dati, dimensione dei dati)].
    region e' l'inizio della regione SMMSTORE, almeno fino alla fine dello
    store; region_size la regione intera. Error se coreboot lo rifiuta: allora
    usa i default."""
    rotto = lambda what: Error("store di SMMSTORE rovinato (%s)" % what)
    if len(region) < 0x48 or region[0x28:0x2c] != b"_FVH":
        raise Error("SMMSTORE senza store di variabili")
    fv_len = struct.unpack_from("<Q", region, 0x20)[0]
    hlen = struct.unpack_from("<H", region, 0x30)[0]
    if region[0x37] != 2 or fv_len > region_size or hlen < 0x48 or hlen > fv_len or fv_len - hlen < 28 \
            or hlen & 1 or len(region) < hlen + 28:
        raise rotto("header della FV")
    if region[0x10:0x20] != NV_DATA_FV_GUID:
        raise rotto("GUID della FV")
    if sum(struct.unpack_from("<%dH" % (hlen // 2), region, 0)) & 0xffff:
        raise rotto("checksum della FV")
    mapped, off = 0, 0x38
    while off + 8 <= hlen:
        num, length = struct.unpack_from("<II", region, off)
        if not num and not length:
            break
        if not num or not length:
            raise rotto("block map della FV")
        mapped += num * length
        off += 8
    if off + 8 > hlen or mapped != fv_len:
        raise rotto("block map della FV")
    sig = region[hlen:hlen + 16]
    size, fmt, health = struct.unpack_from("<IBB", region, hlen + 16)
    if sig not in (VAR_GUID, AUTH_VAR_GUID):
        raise rotto("GUID dello store")
    if size <= 28 or size > fv_len - hlen or len(region) < hlen + size:
        raise rotto("dimensione dello store")
    if fmt != 0x5a or health != 0xfe:
        raise Error("store di SMMSTORE NON sano")
    hsize = 60 if sig == AUTH_VAR_GUID else 32
    out = []
    pos, end = hlen + 28, hlen + size
    while True:
        rest = end - pos
        # dopo l'ultima variabile tutto cancellato, fino alla fine dello store
        if rest < hsize or struct.unpack_from("<H", region, pos)[0] != 0x55aa:
            if region[pos:end].strip(b"\xff"):
                raise rotto("dati dopo l'ultima variabile, a 0x%x" % pos)
            return out
        st = region[pos + 2]
        nsize, dsize = struct.unpack_from("<II", region, pos + hsize - 24)
        var_size = (hsize + nsize + dsize + 3) & ~3
        if st not in VAR_STATES or var_size > rest or nsize < 2 or nsize % 2:
            raise rotto("variabile a 0x%x" % pos)
        # header scritto, nome e dati forse no: coreboot li salta
        if st not in (0xff, 0x7f):
            name = region[pos + hsize:pos + hsize + nsize]
            if name[-2:] != b"\0\0":
                raise rotto("variabile a 0x%x" % pos)
            out.append((st, region[pos + hsize - 16:pos + hsize], name, pos + hsize + nsize, dsize))
        if var_size == rest:
            return out
        pos += var_size


def cb_options(region, names, region_size=None):
    """Le opzioni names come le legge coreboot da uno store SMMSTORE
    (drivers/efi/efivars.c, option.c): {nome: valore, o None per il default},
    e None o il perche' del default per tutte. Uno store vuoto, non sano o che
    coreboot rifiuta (cb_store) vuol dire default; vale la prima copia valida
    (0x3f), senza, l'ultima in cancellazione (0x3e); una copia che non e' di
    4 byte e' il default."""
    out = dict.fromkeys(names)
    try:
        vars_ = cb_store(region, len(region) if region_size is None else region_size)
    except (struct.error, IndexError):
        return out, "store di SMMSTORE rovinato"
    except Error as e:
        return out, str(e)
    for n in names:
        want, hit = (n + "\0").encode("utf-16-le"), None
        for st, guid, name, data, dsize in vars_:
            if st in (0x3f, 0x3e) and guid == CB_OPTION_GUID and name == want:
                hit = (data, dsize)
                if st == 0x3f:
                    break
        if hit and hit[1] == 4:
            out[n] = struct.unpack_from("<I", region, hit[0])[0]
    return out, None


# --- la protezione del flash ---------------------------------------------------
#
# Solo letture, e mai flashrom: anche per leggere riscrive BIOS_CNTL e, con
# FLOCKDN spento, toglie i Protected Range. Sul M920x lo spazio PCI del
# controller SPI 00:1f.5 e alcuni registri del suo BAR0 (mmap PROT_READ di
# resource0); sul W541 lo spazio PCI dell'LPC 00:1f.0 e una pagina di /dev/mem
# a RCBA + 0x3000 (lpt_protection()). Poi su tutti e due la regione BIOS come
# la vede la CPU sotto i 4 GiB (/dev/mem): la FMAP e le opzioni in SMMSTORE.
# Registri da soc/intel/common/block/fast_spi/fast_spi_def.h e
# southbridge/intel/common/spi.c, FRACC/FRAP, FREG e GPR0 da flashrom
# (ichspi.c) e dal kernel (spi-intel.c). I file intel_spi_protected e
# intel_spi_bios_locked del kernel dicono la politica del driver, non i
# registri: non si usano. Sul W541 00:1f.5 e' un altro dispositivo.
FAST_SPI_IDS = {0xa324: "Cannon Point-H"}
SPI_BIOS_CONTROL = 0xdc
# BIOS_CNTL: i bit 0, 1 e 5 hanno lo stesso posto su Cannon Point (WPD, BLE,
# EISS) e su Lynx Point (BIOSWE, BLE, SMM_BWP); BILD e' il bit 7 solo su
# Cannon Point (su Lynx Point e' riservato, e il bit 4 e' TSS, il Top Swap)
BC_WPD, BC_BLE, BC_EISS, BC_BILD = 1 << 0, 1 << 1, 1 << 5, 1 << 7
BC_SMM_BWP, BC_TSS = BC_EISS, 1 << 4
SPIBAR_BFPREG, SPIBAR_HSFSTS, SPIBAR_DLOCK, SPIBAR_FRACC = 0x00, 0x04, 0x0c, 0x50
SPIBAR_FREG0, SPIBAR_FPR0, SPIBAR_GPR0 = 0x54, 0x84, 0x98
FREG_COUNT, FPR_COUNT = 12, 5
HSFS_FLOCKDN, HSFS_FDOPSS, HSFS_PRR34_LOCKDN, HSFS_WRSDIS = 1 << 15, 1 << 13, 1 << 12, 1 << 11
DLOCK_PR0LOCKDN = 1 << 8
FPR_RPE, FPR_WPE = 1 << 15, 1 << 31
# i soli dword letti: mai HSFC, FDATA, PTINX o PTDATA
SPIBAR_READ = ([SPIBAR_BFPREG, SPIBAR_HSFSTS, SPIBAR_DLOCK, SPIBAR_FRACC]
               + [SPIBAR_FREG0 + 4 * n for n in range(FREG_COUNT)]
               + [SPIBAR_FPR0 + 4 * n for n in range(FPR_COUNT)] + [SPIBAR_GPR0])
FREG_NAMES = ("descrittore", "BIOS", "ME", "GbE", "Platform Data")
# la finestra della regione BIOS sotto i 4 GiB e' al piu' di 16 MiB
BIOS_WINDOW_MAX = 16 << 20
# Il default delle opzioni che coreboot legge senza variabile
# (security/lockdown/lockdown.h; CONFIG_BOOTMEDIA_SMM_BWP spento sulle due board)
LOCK_OPTIONS = {"bootmedia_lock": 1, "bios_lock": 0}
# Le regioni che scrive una capsula: lo slot, il record di vboot, le variabili
CAPSULE_WRITES = ("RW_SECTION_A", "RW_SECTION_B", "RW_NVRAM", "SMMSTORE")

# Lynx Point, il W541: il controller SPI (struct ich9_spi_regs di
# southbridge/intel/common/spi.c) e' nel RCBA, che l'LPC 00:1f.0 dice a 0xf0
# (rcba.h). Gli LPC di southbridge/intel/lynxpoint/lpc.c (pci_device_ids,
# nomi da pci_ids.h), non Wildcat Point, la cui finalize e' un'altra
LPC_PCI = os.path.join(SYSROOT, "sys/bus/pci/devices/0000:00:1f.0")
LPT_LPC_IDS = {
    0x8c41: "Lynx Point mobile, sample", 0x8c42: "Lynx Point desktop, sample", 0x8c44: "Lynx Point Z87",
    0x8c46: "Lynx Point Z85", 0x8c49: "Lynx Point HM86", 0x8c4a: "Lynx Point H87", 0x8c4b: "Lynx Point HM87",
    0x8c4c: "Lynx Point Q85", 0x8c4e: "Lynx Point Q87", 0x8c4f: "Lynx Point QM87", 0x8c50: "Lynx Point B85",
    0x8c52: "Lynx Point C222", 0x8c54: "Lynx Point C224", 0x8c56: "Lynx Point C226", 0x8c5c: "Lynx Point H81",
    0x8cc1: "Lynx Point mobile, sample (9)", 0x8cc2: "Lynx Point desktop, sample (9)",
    0x8cc3: "Lynx Point HM97", 0x8cc4: "Lynx Point Z97", 0x8cc6: "Lynx Point H97",
    0x9c41: "Lynx Point-LP, sample", 0x9c43: "Lynx Point-LP premium", 0x9c45: "Lynx Point-LP mainstream",
    0x9c47: "Lynx Point-LP value",
}
LPC_RCBA, RCBA_EN, RCBA_MASK = 0xf0, 1, 0xffffc000
# CONFIG_FIXED_RCBA_MMIO_BASE, e i 16 KiB che il DSDT riserva (PDRC, PNP0C02)
RCBA_FIXED, RCBA_SIZE = 0xfed1c000, 0x4000
# La pagina letta, RCBA + 0x3000: GCS (BILD, bit 0) e BUC (Top Swap, bit 0)
# di finalize.c e di flashrom (chipset_enable.c), e i registri SPI da 0x800
RCBA_PAGE, LPT_GCS, LPT_BUC, LPT_SPIBAR = 0x3000, 0x410, 0x414, 0x800
GCS_BILD, BUC_TS = 1 << 0, 1 << 0
LPT_BFPR, LPT_HSFS, LPT_FRAP, LPT_FREG0, LPT_PR0 = 0x00, 0x04, 0x50, 0x54, 0x74
LPT_FREG_COUNT = 5
# i soli dword letti dei registri SPI: mai FDATA (0x10-0x4f), SSFS, SSFC,
# PREOP, OPTYPE e OPMENU (0x90-0x9f), FDOC e FDOD (0xb0-0xb7)
LPT_SPIBAR_READ = ([LPT_BFPR, LPT_HSFS, LPT_FRAP] + [LPT_FREG0 + 4 * n for n in range(LPT_FREG_COUNT)]
                   + [LPT_PR0 + 4 * n for n in range(FPR_COUNT)])
# Le altre opzioni del W541 che si leggono da SMMSTORE (southbridge/intel/
# lynxpoint/cfr.h: me_disable, default CONFIG_DISABLE_ME_PCI, acceso)
LPT_OPTIONS = {"me_disable": 1}
# La regione BIOS del W541 (SI_BIOS di configs/w541.fmd), per leggere le
# opzioni senza i registri SPI quando cbmem non da' la FMAP dell'avvio: vale
# solo se window_fmap() ci trova la FMAP dove deve essere
LPT_BIOS_REGION = (0x500000, 0xbfffff)
# Il driver del kernel del controller SPI di Lynx Point (lpc_ich.c, "intel-spi")
INTEL_SPI_PLATFORM = os.path.join(SYSROOT, "sys/bus/platform/devices/intel-spi")
IOMEM = os.path.join(SYSROOT, "proc/iomem")
LOCKDOWN = os.path.join(SYSROOT, "sys/kernel/security/lockdown")


def flash_range(v):
    """(inizio, fine compresa) di un registro FREG, BFPREG, FPR o GPR."""
    return (v & 0x7fff) << 12, (((v >> 16) & 0x7fff) << 12) | 0xfff


def read_dwords(path, offset, offsets):
    """I dword agli offset offsets della pagina di 4 KiB di path (resource0, o
    /dev/mem) che inizia a offset, da un mmap in sola lettura."""
    fd = os.open(path, os.O_RDONLY | os.O_SYNC)
    try:
        mm = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=offset)
    finally:
        os.close(fd)
    try:
        # letture allineate da 32 bit, come un volatile in C
        r = memoryview(mm).cast("I")
        try:
            return {off: r[off // 4] for off in offsets}
        finally:
            r.release()
    finally:
        mm.close()


def read_spibar(path):
    """I dword SPIBAR_READ del BAR0, da un mmap in sola lettura di resource0."""
    return read_dwords(path, 0, SPIBAR_READ)


def window_fmap(mm, top):
    """La FMAP nella finestra mm (la regione BIOS che finisce a top, offset del
    flash): cercata ogni 4 KiB dall'alto, valida solo se la sua area FMAP e'
    dove la si trova e la mappa e' grande quanto il flash."""
    size = len(mm)
    for woff in range(size - 0x1000, -1, -0x1000):
        if mm[woff:woff + 8] != b"__FMAP__":
            continue
        chunk = mm[woff:min(woff + 0x2000, size)]
        areas = fmap_areas(chunk)
        flash_size = struct.unpack_from("<I", chunk, 18)[0] if len(chunk) >= 22 else 0
        here = top - size + woff
        if areas and areas.get("FMAP", (None,))[0] == here and flash_size == top:
            return areas
    return None


def spi_protection(devmem=None):
    """La protezione del flash in questo avvio, letta e mai scritta: il
    controller del M920x (fast_spi_protection()) o quello del W541
    (lpt_protection()). None se non c'e' nessuno dei due; {"root": False}
    senza root. devmem: (file, indirizzo fisico del suo primo byte) al posto
    di /dev/mem."""
    p = fast_spi_protection(devmem)
    return lpt_protection(devmem) if p is None else p


def fast_spi_protection(devmem=None):
    """Cannon Point (M920x): None se 00:1f.5 non e' un controller di FAST_SPI_IDS."""
    try:
        dev = int(read_text(os.path.join(SPI_PCI, "device")) or "", 16)
    except ValueError:
        return None
    cls = read_text(os.path.join(SPI_PCI, "class")) or ""
    if read_text(os.path.join(SPI_PCI, "vendor")) != "0x8086" or not cls.startswith("0x0c80") \
            or dev not in FAST_SPI_IDS:
        return None
    try:
        with open(os.path.join(SPI_PCI, "config"), "rb") as f:
            cfg = f.read(256)
    except PermissionError:
        cfg = b""
    # senza root sysfs da' solo i primi 64 byte dello spazio PCI
    if len(cfg) < 256:
        return {"root": False}
    p = {"root": True, "ctrl": "cnp", "device": dev, "bios_cntl": cfg[SPI_BIOS_CONTROL],
         "bar": struct.unpack_from("<I", cfg, 0x10)[0] & ~0xfff, "regs": None, "areas": None,
         "fmap": None, "options": dict.fromkeys(LOCK_OPTIONS), "options_note": "non lette", "board_options": {}}
    try:
        p["regs"] = regs = read_spibar(os.path.join(SPI_PCI, "resource0"))
    except OSError as e:
        locked = read_text(os.path.join(SPI_PCI, "intel_spi_locked"))
        p["error"] = "PRx non leggibili (kernel lockdown o IO_STRICT_DEVMEM: %s)%s" % (
            e.strerror or e, "; FLOCKDN %s (intel_spi_locked)" % locked if locked in ("0", "1") else "")
        return p
    return bios_window(p, regs, devmem, ())


def iomem_entries():
    """Le righe di /proc/iomem: [(inizio, fine, nome)] (da root, se no gli
    indirizzi sono 0)."""
    out = []
    try:
        with open(IOMEM) as f:
            for line in f:
                m = re.match(r"\s*([0-9a-f]+)-([0-9a-f]+) : (.*)$", line)
                if m:
                    out.append((int(m.group(1), 16), int(m.group(2), 16), m.group(3).strip()))
    except OSError:
        pass
    return out


def lpt_rcba_ok(base):
    """Se il RCBA e' quello di coreboot, o almeno dentro una riserva PNP0C02
    (pnp/system.c) di /proc/iomem: un valore qualunque mapperebbe la pagina di
    un altro dispositivo."""
    return base == RCBA_FIXED or any(a <= base and base + RCBA_SIZE - 1 <= b and name.startswith("pnp ")
                                     for a, b, name in iomem_entries())


def lpt_devmem_error(e, page):
    """Perche' /dev/mem non da' la pagina dei registri, e cosa fare. EPERM e'
    la kernel lockdown, o IO_STRICT_DEVMEM con i driver che la tengono
    (intel-spi a RCBA + 0x3800, iTCO_wdt per GCS a RCBA + 0x3410); un altro
    errore (niente /dev/mem, CONFIG_DEVMEM spento, un mmap rifiutato) si dice
    com'e', iomem=relaxed li' non serve. Mai modprobe da qui."""
    text = "registri SPI non leggibili da /dev/mem (%s)" % (getattr(e, "strerror", None) or e)
    if getattr(e, "errno", None) == errno.EPERM:
        mode = re.search(r"\[(\w+)\]", read_text(LOCKDOWN) or "")
        claims = ["%x-%x %s" % (a, b, n) for a, b, n in iomem_entries() if page <= a <= page + 0xfff and b]
        if mode and mode.group(1) != "none":
            text += "; kernel lockdown (%s): /dev/mem resta chiusa" % mode.group(1)
        else:
            # iomem=relaxed toglie una protezione del kernel: solo per la
            # verifica, e il rimedio e' ancora da provare su un W541 vero
            text += "; kernel con IO_STRICT_DEVMEM%s: per questa sola verifica avvia una volta con " \
                "iomem=relaxed, poi toglilo (da confermare su un W541)" % (
                    " (la pagina 0x%08x e' anche di %s)" % (page, ", ".join(claims)) if claims else "")
    locked = read_text(os.path.join(INTEL_SPI_PLATFORM, "intel_spi_locked"))
    if locked in ("0", "1"):
        text += "; FLOCKDN %s (intel_spi_locked)" % locked
    return text


def lpt_protection(devmem=None):
    """Lynx Point (W541): None se 00:1f.0 non e' un LPC di LPT_LPC_IDS.
    BIOS_CNTL e RCBA dallo spazio PCI dell'LPC, poi una pagina di /dev/mem in
    sola lettura a RCBA + 0x3000: GCS, BUC e i registri SPI di LPT_SPIBAR_READ."""
    try:
        dev = int(read_text(os.path.join(LPC_PCI, "device")) or "", 16)
    except ValueError:
        return None
    cls = read_text(os.path.join(LPC_PCI, "class")) or ""
    if read_text(os.path.join(LPC_PCI, "vendor")) != "0x8086" or not cls.startswith("0x0601") \
            or dev not in LPT_LPC_IDS:
        return None
    try:
        with open(os.path.join(LPC_PCI, "config"), "rb") as f:
            cfg = f.read(256)
    except PermissionError:
        cfg = b""
    if len(cfg) < 256:
        return {"root": False}
    rcba = struct.unpack_from("<I", cfg, LPC_RCBA)[0]
    base = rcba & RCBA_MASK
    p = {"root": True, "ctrl": "lpt", "device": dev, "bios_cntl": cfg[SPI_BIOS_CONTROL], "rcba": base,
         "bar": base + RCBA_PAGE + LPT_SPIBAR, "regs": None, "areas": None, "fmap": None,
         "options": dict.fromkeys(LOCK_OPTIONS), "options_note": "non lette",
         "board_options": dict.fromkeys(LPT_OPTIONS)}
    if not rcba & RCBA_EN:
        p["error"] = "RCBA spento (0xf0 = 0x%08x)" % rcba
        return lpt_options_only(p, devmem)
    if not lpt_rcba_ok(base):
        p["error"] = "RCBA 0x%08x: non e' 0x%08x ne' in una riserva PNP0C02 di /proc/iomem, non lo leggo" % (
            base, RCBA_FIXED)
        return lpt_options_only(p, devmem)
    path, phys = devmem or (DEVMEM, 0)
    page = base + RCBA_PAGE
    try:
        w = read_dwords(path, page - phys, [LPT_GCS, LPT_BUC] + [LPT_SPIBAR + o for o in LPT_SPIBAR_READ])
    except OSError as e:
        p["error"] = lpt_devmem_error(e, page)
        return lpt_options_only(p, devmem)
    except (ValueError, OverflowError) as e:
        p["error"] = "pagina 0x%08x non leggibile da %s: %s" % (page, path, e)
        return lpt_options_only(p, devmem)
    # Sotto le chiavi del M920x, cosi' spi_verdict() e le righe valgono per
    # tutti e due: BFPR, HSFS e FRAP dove sono BFPREG, HSFSTS e FRACC, FREG0-4
    # e PR0-4 dove sono FREG0-4 e FPR0-4 (PR0 qui e' a 0x74, li' a 0x84).
    # DLOCK e GPR0 su Lynx Point non ci sono: 0, FLOCKDN blocca da solo anche
    # i PR (flashrom, ichspi.c); FREG5-11 non usati (0x7fff)
    spi = lambda off: w[LPT_SPIBAR + off]
    regs = {SPIBAR_BFPREG: spi(LPT_BFPR), SPIBAR_HSFSTS: spi(LPT_HSFS), SPIBAR_FRACC: spi(LPT_FRAP),
            SPIBAR_DLOCK: 0, SPIBAR_GPR0: 0}
    for n in range(FREG_COUNT):
        regs[SPIBAR_FREG0 + 4 * n] = spi(LPT_FREG0 + 4 * n) if n < LPT_FREG_COUNT else 0x7fff
    for n in range(FPR_COUNT):
        regs[SPIBAR_FPR0 + 4 * n] = spi(LPT_PR0 + 4 * n)
    p["regs"], p["gcs"], p["buc"] = regs, w[LPT_GCS], w[LPT_BUC]
    return bios_window(p, regs, devmem, LPT_OPTIONS)


def boot_fmap():
    """La FMAP di questo avvio da CBMEM (cbmem -r 464d4150), i suoi byte, o
    None: solo sulla macchina vera e con cbmem."""
    if SYSROOT != "/" or not shutil.which("cbmem"):
        return None
    try:
        r = subprocess.run(["cbmem", "-r", "464d4150"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def fmap_bios_region(raw):
    """(inizio, fine compresa) di SI_BIOS in una FMAP, se finisce dove finisce
    il flash come la regione BIOS che la CPU vede sotto i 4 GiB; se no None."""
    areas = fmap_areas(raw) if raw else None
    pos = raw.find(b"__FMAP__") if areas else -1
    if not areas or "SI_BIOS" not in areas or pos < 0 or pos + 22 > len(raw):
        return None
    o, s = areas["SI_BIOS"]
    return (o, o + s - 1) if s and o + s == struct.unpack_from("<I", raw, pos + 18)[0] else None


def lpt_options_only(p, devmem):
    """Lynx Point senza i registri SPI (pagina del RCBA rifiutata, RCBA spento
    o strano): le opzioni in SMMSTORE si leggono lo stesso dalla finestra della
    regione BIOS sotto i 4 GiB, che intel-spi e iTCO_wdt non tengono. La regione
    da SI_BIOS della FMAP dell'avvio, se no LPT_BIOS_REGION; p["error"] resta."""
    raw = boot_fmap()
    region = fmap_bios_region(raw)
    p["bios_from"] = "SI_BIOS della FMAP dell'avvio" if region else "SI_BIOS di configs/w541.fmd"
    return read_window(p, region or LPT_BIOS_REGION, devmem, LPT_OPTIONS, raw)


def bios_window(p, regs, devmem, board_options):
    """Per tutti e due i controller, con i registri letti: la regione BIOS
    (BFPREG), poi read_window()."""
    bf = regs[SPIBAR_BFPREG]
    base, limit = flash_range(bf)
    if bf == 0xffffffff or limit <= base:
        p["error"] = "BFPREG 0x%08x non valido: il controller non risponde?" % bf
        return p
    return read_window(p, (base, limit), devmem, board_options, boot_fmap())


def read_window(p, bios, devmem, board_options, boot_raw):
    """La finestra della regione BIOS bios (inizio, fine compresa) sotto i 4
    GiB, la FMAP (quella dell'avvio, boot_raw da boot_fmap(), o quella nel
    flash) e le opzioni in SMMSTORE: LOCK_OPTIONS in p["options"],
    board_options in p["board_options"]; p["store_read"] se lo store si e'
    guardato (allora un'opzione che manca e' davvero il suo default)."""
    base, limit = bios
    p["bios"] = (base, limit)
    size = min(limit + 1 - base, BIOS_WINDOW_MAX)
    win = (1 << 32) - size
    p["window"] = win
    path, phys = devmem or (DEVMEM, 0)
    mm = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_SYNC)
        try:
            mm = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ, offset=win - phys)
        finally:
            os.close(fd)
    except (OSError, ValueError, OverflowError) as e:
        p["fmap"] = "regione BIOS non leggibile da %s: %s" % (path, getattr(e, "strerror", None) or e)
    try:
        flash = window_fmap(mm, limit + 1) if mm else None
        # quella dell'avvio, che i PR seguono (solo sulla macchina vera)
        boot = fmap_areas(boot_raw) if boot_raw else None
        p["areas"] = boot or flash
        if boot and flash:
            p["fmap"] = "quella dell'avvio (cbmem), uguale a quella nel flash" if boot == flash else \
                "quella dell'avvio (cbmem); nel flash ce n'e' un'altra (riscritto dopo l'avvio?)"
        elif boot or flash:
            p["fmap"] = "quella dell'avvio (cbmem)" if boot else "quella nel flash (0x%07x)" % flash["FMAP"][0]
        elif mm:
            p["fmap"] = "non trovata nella regione BIOS"
        smm = (p["areas"] or {}).get("SMMSTORE")
        if mm and smm and limit + 1 - size <= smm[0] and smm[0] + smm[1] <= limit + 1:
            # solo l'header e lo store di variabili, non le aree FTW
            woff = smm[0] - (limit + 1 - size)
            head = mm[woff:woff + 0x100]
            n = smm[1]
            if head[0x28:0x2c] == b"_FVH":
                hlen = struct.unpack_from("<H", head, 0x30)[0]
                if hlen + 32 <= len(head):
                    n = min(n, hlen + struct.unpack_from("<I", head, hlen + 16)[0])
                opts, p["options_note"] = cb_options(mm[woff:woff + n], list(LOCK_OPTIONS) + list(board_options),
                                                     smm[1])
                p["options"] = {k: opts[k] for k in LOCK_OPTIONS}
                p["board_options"] = {k: opts[k] for k in board_options}
            else:
                p["options_note"] = "SMMSTORE vuota"
            # vuota, rovinata o non sana coreboot usa i default: si sanno
            p["store_read"] = True
    finally:
        if mm:
            mm.close()
    return p


def covered(lo, hi, ranges):
    """Se l'unione di ranges [(inizio, fine)] copre tutto [lo, hi]."""
    pos = lo
    for a, b in sorted(ranges):
        if a > pos:
            break
        pos = max(pos, b + 1)
        if pos > hi:
            return True
    return pos > hi


def range_names(areas, lo, hi):
    """Le aree della FMAP di un intervallo: quelle che coincidono, se no quelle
    che tocca (senza le aree che lo contengono tutto e quelle dentro un'altra)."""
    if not areas:
        return []
    exact = [n for n, (o, s) in areas.items() if s and o == lo and o + s - 1 == hi]
    if exact:
        return sorted(exact)
    ov = {n: (o, o + s - 1) for n, (o, s) in areas.items() if s and o <= hi and o + s - 1 >= lo
          and not (o <= lo and o + s - 1 >= hi)}
    return sorted((n for n, (a, b) in ov.items()
                   if not any(m != n and c <= a and b <= d and (c, d) != (a, b) for m, (c, d) in ov.items())),
                  key=lambda n: ov[n])


def bios_lock_state(p):
    """BIOS Lock in questo avvio dal solo BIOS_CNTL (anche senza i registri
    SPI): (solo SMM scrive la regione BIOS, e lo tiene l'SMI che rimette
    BIOSWE/WPD a 0). L'opzione in SMMSTORE vale dal prossimo avvio o dalla
    prossima ripresa da S3: anche li' ramstage rifa' i blocchi (lockdown.c a
    BS_DEV_RESOURCES, la finalize di lpc.c) con le opzioni che trova."""
    bc = p["bios_cntl"]
    if p.get("ctrl") == "lpt":
        # Lynx Point: SMM_BWP (R/WLO: acceso, resta fino al reset o a S3) basta da
        # solo, la regione BIOS si scrive solo con InSMM.STS; senza, BLE con BIOSWE a 0,
        # che l'SMI di BIOSWR rimette a 0 (lynxpoint/smihandler.c). coreboot
        # scrive 0x09 (spento), 0x2a (acceso)
        smm = bool(bc & BC_SMM_BWP) or (bool(bc & BC_BLE) and not bc & BC_WPD)
        return smm, smm and not bc & BC_SMM_BWP
    # Cannon Point: BLE con EISS, o BLE con WPD a 0. La finalize di SMM
    # rimette WPD a 1 (fast_spi_init(), che azzera anche EISS) e poi a 0 solo
    # se SMM applica il BIOS Lock, come l'SMI a ogni 0->1 (smihandler.c)
    smm = bool(bc & BC_BLE) and (bool(bc & BC_EISS) or not bc & BC_WPD)
    return smm, smm and not bc & BC_EISS


def spi_verdict(p, areas=None):
    """Cosa vuol dire lo stato letto da spi_protection() (con i registri)."""
    regs = p["regs"]
    areas = areas if areas is not None else (p["areas"] or {})
    hsfs, dlock, fracc = regs[SPIBAR_HSFSTS] & 0xffff, regs[SPIBAR_DLOCK], regs[SPIBAR_FRACC]
    prs = []
    for n in range(FPR_COUNT + 1):
        v = regs[SPIBAR_GPR0] if n == FPR_COUNT else regs[SPIBAR_FPR0 + 4 * n]
        if v & (FPR_WPE | FPR_RPE):
            lo, hi = flash_range(v)
            name = "GPR0" if n == FPR_COUNT else "PR%d" % n
            locked = bool(hsfs & HSFS_FLOCKDN) or (n < FPR_COUNT and bool(dlock & (DLOCK_PR0LOCKDN << n)))
            prs.append({"name": name, "value": v, "lo": lo, "hi": hi, "wpe": bool(v & FPR_WPE),
                        "rpe": bool(v & FPR_RPE), "locked": locked, "areas": range_names(areas, lo, hi)})
    wp = [(r["lo"], r["hi"]) for r in prs if r["wpe"]]
    touching = lambda o, s, kind: [r for r in prs if r[kind] and r["lo"] <= o + s - 1 and r["hi"] >= o]
    v = {"prs": prs, "flockdn": bool(hsfs & HSFS_FLOCKDN), "ro": None}
    ro = areas.get("WP_RO")
    if ro:
        mine = touching(ro[0], ro[1], "wpe")
        full = covered(ro[0], ro[0] + ro[1] - 1, wp)
        v["ro"] = "ok" if full and all(r["locked"] for r in mine) else \
            "unlocked" if full else "partial" if mine else "off"
        v["ro_by"] = [r["name"] for r in mine]
    v["smm_only"], v["smm_by_smi"] = bios_lock_state(p)
    # la regione BIOS (1) e il descrittore (0) scrivibili dalla CPU (BRWA)
    v["bios_host_write"] = bool(fracc & (1 << 9))
    v["desc_writable"] = bool(fracc & (1 << 8)) and not covered(0, 0xfff, wp)
    v["capsule_block"] = sorted({r["name"] + " " + n for n in CAPSULE_WRITES if n in areas
                                 for r in touching(areas[n][0], areas[n][1], "wpe")})
    # la capsula legge la FMAP del flash attraverso SMMSTORE
    for n in ("FMAP", "WP_RO"):
        if n in areas:
            v["capsule_block"] += sorted({r["name"] + " " + n + " (lettura)"
                                          for r in touching(areas[n][0], areas[n][1], "rpe")})
    v["flashrom_block"] = sorted({r["name"] + " " + n for n in ("RW_SECTION_A", "RW_SECTION_B", "RW_NVRAM")
                                  if n in areas for r in touching(areas[n][0], areas[n][1], "wpe")})
    # PR attivi senza una FMAP con cui confrontarli: degli slot non si sa niente
    v["unmapped"] = [r["name"] for r in prs] if not areas else []
    return v


def protection_lines(devmem=None):
    """Le righe della protezione del flash per status: [(etichetta, testo)]."""
    try:
        p = spi_protection(devmem)
    except (OSError, Error, struct.error, ValueError) as e:
        return [("protezione", "non letta: %s" % e)]
    if p is None:
        return [("protezione", "non verificabile su questa macchina (solo i controller SPI del M920x e del W541)")]
    if not p["root"]:
        return [("protezione", "serve root (sudo)")]
    if not p["regs"] or "error" in p:
        # BIOS_CNTL viene dallo spazio PCI: il BIOS Lock si sa anche cosi'
        smm, by_smi = bios_lock_state(p)
        return [("protezione", "%s; BIOS_CNTL 0x%02x" % (p.get("error"), p["bios_cntl"])),
                ("BIOS Lock", bios_lock_text(p, {"smm_only": smm, "smm_by_smi": by_smi}))]
    v = spi_verdict(p)
    return [("WP_RO", ro_text(p, v)), ("BIOS Lock", bios_lock_text(p, v)), ("slot RW", slots_text(p, v))]


def option_text(p, name):
    """Il valore di un'opzione in SMMSTORE, o il default e perche'."""
    val = p["options"].get(name)
    if val is not None:
        return "%d" % val
    return "%d (default%s)" % (LOCK_OPTIONS[name], ": " + p["options_note"] if p["options_note"] else "")


def ro_text(p, v):
    opt = p["options"].get("bootmedia_lock")
    on = opt if opt is not None else LOCK_OPTIONS["bootmedia_lock"]
    if v["ro"] is None:
        return "non trovata: FMAP non letta (%s)" % p.get("fmap")
    if v["ro"] in ("ok", "unlocked"):
        text = "protetta fino al prossimo reset o ripresa da S3 (%s)" % ", ".join(v["ro_by"])
        if v["ro"] == "unlocked":
            text += ", ma FLOCKDN e' spento: i PR si possono togliere"
        if v["desc_writable"]:
            text += "; ma il descrittore e' scrivibile dalla CPU (UNLOCK_FLASH_REGIONS): si puo' aggirare"
        if not on:
            text += "; spenta nel setup, vale dal prossimo avvio o ripresa da S3"
        return text
    text = "protetta solo in parte (%s)" % ", ".join(v["ro_by"]) if v["ro"] == "partial" else "NON protetta"
    if not on:
        return text + " (Firmware protection spenta, anche nel setup)"
    why = "accesa nel setup" if opt is not None else "al default, accesa (%s)" % (p["options_note"] or
                                                                                   "nessuna variabile")
    return text + "; Firmware protection %s: se cambiata dopo l'avvio vale dal prossimo avvio o ripresa " \
        "da S3, se no " \
        "sudo cbmem -1 | grep -E \"BM-LOCKDOWN|FPR\"" % why


def bios_lock_text(p, v):
    opt = p["options"].get("bios_lock")
    lpt = p.get("ctrl") == "lpt"
    bc = p["bios_cntl"]
    if v["smm_only"]:
        text = "acceso: scrive solo il firmware in SMM"
        if v["smm_by_smi"]:
            text += " (SMM_BWP a 0: lo tiene l'SMI che rimette BIOSWE a 0)" if lpt else \
                " (EISS a 0: lo tiene l'SMI che rimette WPD a 0)"
        if opt == 0:
            text += "; spento nel setup, vale dal prossimo avvio o ripresa da S3"
        return text
    text = "spento: il sistema puo' scrivere il flash"
    if not bc & BC_WPD:
        text += " (dopo aver acceso BIOSWE, come fa flashrom)"
    elif lpt and bc & BC_BLE:
        # BLE senza SMM_BWP: l'SMI di BIOSWR doveva rimettere BIOSWE a 0
        text += " (BLE acceso ma BIOSWE a 1: l'SMI non l'ha rimesso a 0)"
    if opt == 1:
        text += "; acceso nel setup, vale dal prossimo avvio o ripresa da S3"
    return text


UNMAPPED = "FMAP non letta (update.py protection --flash FILE)"


def slots_text(p, v):
    if v["capsule_block"]:
        return "NON scrivibili: %s; la capsula fallirebbe (0x1802 scrittura del flash fallita)" % \
            ", ".join(v["capsule_block"])
    if v["unmapped"]:
        return "non verificabili: %s attivi, %s%s" % (", ".join(v["unmapped"]), UNMAPPED,
                                                       "; flashrom no (BIOS Lock)" if v["smm_only"] else "")
    if v["flashrom_block"]:
        return "scrivibili con la capsula; flashrom no (%s)" % ", ".join(v["flashrom_block"])
    if v["smm_only"] or not v["bios_host_write"]:
        return "scrivibili con la capsula; flashrom no (%s)" % (
            "BIOS Lock" if v["smm_only"] else "il descrittore non da' alla CPU la regione BIOS")
    return "scrivibili con la capsula e con flashrom"


def check_flash_writable(areas, regions):
    """Prima di proporre flashrom (other-slot): le regioni sotto un PR non si
    scrivono. Solo da root, sui controller del M920x e del W541, e solo come
    avviso per il BIOS Lock: la copia del flash puo' venire da un'altra macchina."""
    if os.geteuid() != 0:
        return
    try:
        p = spi_protection()
    except (OSError, Error, struct.error, ValueError):
        return
    if not p or not p.get("root"):
        return
    if not p.get("regs") or "error" in p:
        # i PR no, ma BIOS_CNTL viene dallo spazio PCI: il BIOS Lock si sa
        if bios_lock_state(p)[0]:
            print(BIOS_LOCK_WARNING)
        print("nota: i Protected Range di questo avvio non si leggono (update.py protection dice perche'): "
              "se flashrom rifiuta di scrivere, e' li'")
        return
    v = spi_verdict(p, areas)
    blocked = sorted({r["name"] + " " + n for n in regions if n in areas
                      for r in v["prs"] if r["wpe"] and r["lo"] <= sum(areas[n]) - 1 and r["hi"] >= areas[n][0]})
    if blocked:
        raise Error("in questo avvio %s: flashrom non le puo' scrivere (update.py protection)" % ", ".join(blocked))
    if v["smm_only"]:
        print(BIOS_LOCK_WARNING)


BIOS_LOCK_WARNING = ("attenzione: BIOS Lock acceso, flashrom non puo' scrivere: usa la capsula, o spegnilo nel "
                     "setup (Security > Flash protection) e riavvia")


def firmware_note():
    """Una nota se il firmware che gira non e' ouroBIOS (un T440p, il firmware
    Lenovo): i registri valgono, le opzioni e i default no."""
    bios = read_text(BIOS_VERSION)
    if bios and not (RELEASE_RE.search(bios.encode()) or CI_BUILD_RE.search(bios.encode())):
        return "firmware %s, non ouroBIOS: i registri valgono, le opzioni e i loro default sono quelli di " \
            "ouroBIOS" % bios
    return None


def print_options(p):
    print("opzioni:     Firmware protection %s, BIOS Lock %s (in SMMSTORE: valgono dal prossimo avvio o "
          "ripresa da S3)" % (option_text(p, "bootmedia_lock"), option_text(p, "bios_lock")))


def unknown_ro(args, why):
    """Lo stato di WP_RO non si sa: con --expect-ro esce con 2 (mai 1, che
    con off vorrebbe dire protetta), se no e' un errore."""
    if not args.expect_ro:
        raise Error(why)
    print("errore: %s" % why, file=sys.stderr)
    print("atteso: WP_RO %s; stato di WP_RO non noto" % ("protetta" if args.expect_ro == "on" else "non protetta"))
    return 2


def cmd_protection(args):
    try:
        p = spi_protection()
    except (OSError, struct.error, ValueError) as e:
        return unknown_ro(args, "protezione non letta: %s" % e)
    if p is None:
        return unknown_ro(args, "ne' 00:1f.5 e' il controller SPI del M920x (%s) ne' 00:1f.0 un LPC Lynx Point "
                          "(W541): niente da leggere su questa macchina" % ", ".join("8086:%04x" % d
                                                                                   for d in FAST_SPI_IDS))
    if not p["root"]:
        return unknown_ro(args, "serve root (sudo): lo spazio PCI del controller SPI e /dev/mem")
    lpt = p["ctrl"] == "lpt"
    bc = p["bios_cntl"]
    if lpt:
        print("controller:  00:1f.0 (LPC), 8086:%04x (%s), RCBA 0x%08x, SPIBAR 0x%08x" % (
            p["device"], LPT_LPC_IDS[p["device"]], p["rcba"], p["bar"]))
        # il bit 7 qui e' riservato: BILD e' in GCS
        print("BIOS_CNTL:   0x%02x: BIOSWE %d, BLE %d, SMM_BWP %d, Top Swap %d (TSS)" % (
            bc, bc & BC_WPD, bc >> 1 & 1, bc >> 5 & 1, bc >> 4 & 1))
    else:
        print("controller:  00:1f.5, 8086:%04x (%s), SPIBAR 0x%08x" % (p["device"], FAST_SPI_IDS[p["device"]],
                                                                        p["bar"]))
        print("BIOS_CNTL:   0x%02x: BIOSWE %d, BLE %d, EISS %d, BILD %d" % (
            bc, bc & BC_WPD, bc >> 1 & 1, bc >> 5 & 1, bc >> 7 & 1))
    note = firmware_note()
    if note:
        print("nota:        %s" % note)
    if not p["regs"] or "error" in p:
        # BIOS_CNTL viene dallo spazio PCI e le opzioni dalla finestra della
        # regione BIOS: si dicono anche senza i registri SPI
        if p.get("store_read"):
            print_options(p)
        smm, by_smi = bios_lock_state(p)
        print("BIOS Lock:   %s" % bios_lock_text(p, {"smm_only": smm, "smm_by_smi": by_smi}))
        return unknown_ro(args, p.get("error") or "registri SPI non letti")
    regs = p["regs"]
    if lpt:
        print("GCS:         0x%08x: BILD %d; BUC 0x%02x: Top Swap %d" % (
            p["gcs"], p["gcs"] & GCS_BILD, p["buc"] & 0xff, p["buc"] & BUC_TS))
    base, limit = p["bios"]
    print("BIOS:        regione 0x%07x-0x%07x (%d MiB), sotto i 4 GiB da 0x%08x" % (
        base, limit, (limit + 1 - base) >> 20, p["window"]))
    areas = p["areas"]
    if args.flash:
        data = flash_image(args.flash)
        areas = fmap_areas(data)
        if areas is None:
            raise Error("%s: senza FMAP" % args.flash)
        print("FMAP:        da %s (solo i nomi: i PR sono nei registri di questo avvio)" % args.flash)
    else:
        print("FMAP:        %s" % p["fmap"])
    hsfs, dlock, fracc = regs[SPIBAR_HSFSTS] & 0xffff, regs[SPIBAR_DLOCK], regs[SPIBAR_FRACC]
    if lpt:
        # niente DLOCK, PRR34_LOCKDN e WRSDIS: ci sono dalla serie 100
        print("blocchi:     FLOCKDN %d (blocca anche PR0-PR4), descrittore %s" % (
            hsfs >> 15 & 1, "attivo" if hsfs & HSFS_FDOPSS else "NON attivo (FDOPSS 0)"))
    else:
        prl = [n for n in range(FPR_COUNT) if dlock & (DLOCK_PR0LOCKDN << n)]
        print("blocchi:     FLOCKDN %d, PR bloccati %s (DLOCK 0x%08x), PRR34_LOCKDN %d, WRSDIS %d, "
              "descrittore %s" % (
                  hsfs >> 15 & 1, ", ".join("PR%d" % n for n in prl) or "nessuno", dlock, hsfs >> 12 & 1,
                  hsfs >> 11 & 1, "attivo" if hsfs & HSFS_FDOPSS else "NON attivo (FDOPSS 0)"))
    used = []
    for n in range(LPT_FREG_COUNT if lpt else FREG_COUNT):
        lo, hi = flash_range(regs[SPIBAR_FREG0 + 4 * n])
        if lo <= hi:
            used.append((n, lo, hi))
    name = lambda n: FREG_NAMES[n] if n < len(FREG_NAMES) else "regione %d" % n
    print("regioni:     %s" % ", ".join("%s 0x%07x-0x%07x" % (name(n), lo, hi) for n, lo, hi in used))
    print("%-13s0x%08x: la CPU legge %s; scrive %s" % (
        "FRAP:" if lpt else "FRACC:", fracc, ", ".join(name(n) for n, _, _ in used if fracc >> n & 1) or "niente",
        ", ".join(name(n) for n, _, _ in used if fracc >> (8 + n) & 1) or "niente"))
    v = spi_verdict(p, areas)
    for r in v["prs"]:
        print("%-12s 0x%08x: 0x%07x-0x%07x %s%s%s" % (
            r["name"] + ":", r["value"], r["lo"], r["hi"],
            "/".join(k for k, on in (("scrittura", r["wpe"]), ("lettura", r["rpe"])) if on),
            " = " + " ".join(r["areas"]) if r["areas"] else "", "" if r["locked"] else ", NON bloccato"))
    if not v["prs"]:
        print("PR0-PR4:     tutti vuoti" if lpt else "PR, GPR0:    tutti vuoti")
    print_options(p)
    print("WP_RO:       %s" % ro_text(p, v))
    print("descrittore: %s" % ("scrivibile dalla CPU (%s, nessun PR su 0x0-0xfff): con WP_RO "
                               "protetta, si aggira al prossimo reset; il BIOS Lock non lo copre"
                               % ("FRAP" if lpt else "FRACC") if v["desc_writable"] else "non scrivibile dalla CPU"))
    print("BIOS Lock:   %s" % bios_lock_text(p, v))
    unmapped = "non verificabile: %s attivi, %s" % (", ".join(v["unmapped"]), UNMAPPED)
    print("capsula:     %s" % ("NO: %s" % ", ".join(v["capsule_block"]) if v["capsule_block"] else
                               unmapped if v["unmapped"] else "si': nessun PR sugli slot, RW_NVRAM e SMMSTORE"))
    fr = list(v["flashrom_block"])
    if v["smm_only"]:
        fr.append("BIOS Lock")
    if not v["bios_host_write"]:
        fr.append("il descrittore non da' alla CPU la regione BIOS")
    print("flashrom:    %s" % ("NO: %s" % ", ".join(fr) if fr else unmapped if v["unmapped"] else
                               "si' sugli slot (BIOS Lock spento, nessun PR)"))
    print("Solo la CPU: i PR non fermano gli altri master del flash (ME, GbE).")
    if args.expect_ro:
        # 2: niente da confrontare (WP_RO non nella FMAP, o FMAP non letta)
        if v["ro"] is None:
            print("atteso: WP_RO %s; stato di WP_RO non noto" % (
                "protetta" if args.expect_ro == "on" else "non protetta"))
            return 2
        if (v["ro"] == "ok") != (args.expect_ro == "on"):
            print("atteso: WP_RO %s" % ("protetta" if args.expect_ro == "on" else "non protetta"))
            return 1
    return 0


# --- vboot: cosa ha deciso verstage in questo avvio ----------------------------
#
# La workbuf di vboot resta in CBMEM ("VBOOT WORK", id 0x78007343): all'inizio
# vb2_shared_data (vboot_reference, 2struct.h), con dentro vb2_context
# (2context.h). Si legge con: sudo cbmem -r 0x78007343 > vbwork.bin
VB2_SD_MAGIC = 0x44533256
VB2_CONTEXT_FLAGS = ((0, "NVDATA_CHANGED"), (2, "RECOVERY_MODE"), (6, "FW_SLOT_B"),
                     (14, "S3_RESUME"), (18, "NVDATA_V2"), (29, "SLOT_A_ONLY"))
VB2_SD_STATUS = ((0, "NV_REINIT"), (1, "NV_INIT"), (3, "CHOSE_SLOT"), (7, "RECOVERY_DECIDED"))


def cmd_vboot_work(args):
    data = open(args.dump, "rb").read()
    if len(data) < 432 or struct.unpack_from("<I", data, 0)[0] != VB2_SD_MAGIC:
        raise Error("%s: non e' la workbuf di vboot (cbmem -r 0x78007343)" % args.dump)
    major, minor = struct.unpack_from("<HH", data, 4)
    flags = struct.unpack_from("<Q", data, 8)[0]
    nv = data[16:32]
    (wsize, wused, sdflags, recovery, last_slot, last_result, fw_slot, _, _, status) = \
        struct.unpack_from("<10I", data, 392)
    slot = "AB"
    print("workbuf:    vb2_shared_data %d.%d, %d byte usati" % (major, minor, wused))
    print("contesto:   %s" % (" ".join(n for b, n in VB2_CONTEXT_FLAGS if flags >> b & 1) or "-"))
    print("stato:      %s" % (" ".join(n for b, n in VB2_SD_STATUS if status >> b & 1) or "-"))
    print("slot:       %s (precedente: slot %s, %s)" % (
        slot[fw_slot & 1], slot[last_slot & 1], NV_RESULTS[last_result & 3]))
    if recovery:
        print("recovery:   motivo 0x%02x" % recovery)
    ok = nv[0] & 0xc3 == 0x40 and nv_crc8(nv[:15]) == nv[15]
    b1, b2 = nv[1], nv[7]
    print("nvdata:     %s  prossimo slot %s, %d tentativi; corrente slot %s %s; precedente slot %s %s%s" % (
        nv.hex(), slot[(b2 >> 3) & 1], b1 & 0x0f, slot[(b2 >> 2) & 1], NV_RESULTS[b2 & 3],
        slot[(b2 >> 6) & 1], NV_RESULTS[(b2 >> 4) & 3], "" if ok else " (NON valida)"))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Aggiornamento di ouroBIOS (W541, ThinkCentre M920x) con una "
                                             "capsula UEFI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="firmware, versione, ultimo aggiornamento, capsula in attesa")
    p.add_argument("--esp", help="dove e' montata l'ESP (default: la si cerca)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("stage", help="prepara una capsula per il prossimo avvio")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("capsule", nargs="?", help="file .cap (o .cab) di una release")
    g.add_argument("--latest", action="store_true", help="scarica l'ultima release della variante che gira")
    p.add_argument("--pre", action="store_true", help="con --latest anche le pre-release")
    p.add_argument("--allow-older", action="store_true", help="anche la stessa versione o una piu' vecchia")
    p.add_argument("--on-battery", action="store_true", help="anche senza alimentatore")
    p.add_argument("--cert", help="certificato per verificare la firma (default: keys/capsule-signing.pem)")
    p.add_argument("--esp", help="dove e' montata l'ESP (default: la si cerca)")
    p.add_argument("--reboot", action="store_true", help="riavvia subito")
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("cancel", help="toglie la capsula in attesa")
    p.add_argument("--all", action="store_true", help="anche i file di altri strumenti (fwupd)")
    p.add_argument("--esp", help="dove e' montata l'ESP (default: la si cerca)")
    p.set_defaults(func=cmd_cancel)

    num = lambda s: int(s, 0)
    p = sub.add_parser("info", help="mostra e controlla una capsula o un .cab (anche tools/build.sh)")
    p.add_argument("capsule")
    p.add_argument("--same-as", help="la capsula deve essere questo file (per un .cab)")
    p.add_argument("--cert", help="verifica la firma con questo certificato")
    p.add_argument("--rom", help="l'immagine nella capsula deve essere questa")
    p.add_argument("--guid", help="GUID atteso")
    p.add_argument("--fw-version", type=num, help="versione attesa (0x01020000)")
    p.add_argument("--lsv", type=num, help="versione minima attesa")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("vboot", help="lo stato di vboot (slot, tentativi) in una copia del flash")
    p.add_argument("dump", help="flashrom -r: tutto il flash, o -i RW_NVRAM:FILE")
    p.add_argument("--all", action="store_true", help="anche tutti i record, dal primo")
    p.add_argument("--image", help="confronta RO e slot con una release (.rom, .cap o .cab)")
    p.set_defaults(func=cmd_vboot)

    p = sub.add_parser("other-slot", help="prepara l'immagine per scrivere con flashrom lo slot di una release "
                   "nello slot che non gira, e farlo provare a vboot")
    p.add_argument("dump", help="sudo flashrom -p internal -r FILE: tutto il flash, preso in questo avvio")
    p.add_argument("image", help="la release: .rom, .cap o .cab")
    p.add_argument("--out", default="other-slot.rom", help="l'immagine da scrivere (default: other-slot.rom)")
    p.add_argument("--force", action="store_true", help="anche l'altra variante, che dopo questa parte RO non parte")
    p.add_argument("--retrain", action="store_true",
                   help="svuota anche il training della RAM (RW_MRC_CACHE): lo slot lo rifa' al primo avvio "
                        "(sul W541 e per le release del M920x prima della v1.4.0-rc4 lo si svuota sempre)")
    p.set_defaults(func=cmd_other_slot)

    p = sub.add_parser("rollback", help="torna alla release nell'altro slot, quella di prima dell'ultimo aggiornamento")
    p.add_argument("dump", help="sudo flashrom -p internal -r FILE: tutto il flash, preso in questo avvio")
    p.add_argument("--capsule", help="la capsula di quella release (default: la si scarica da GitHub)")
    p.add_argument("--dry-run", action="store_true", help="mostra cosa farebbe, senza preparare niente")
    p.add_argument("--on-battery", action="store_true", help="anche senza alimentatore")
    p.add_argument("--cert", help="certificato per verificare la firma (default: keys/capsule-signing.pem)")
    p.add_argument("--esp", help="dove e' montata l'ESP (default: la si cerca)")
    p.add_argument("--reboot", action="store_true", help="riavvia subito")
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("vars", help="le variabili UEFI di SMMSTORE in una copia del flash (nomi, mai i dati)")
    p.add_argument("dump")
    p.add_argument("--grep", help="solo le variabili con questo nome o GUID (regex)")
    p.add_argument("--all", action="store_true", help="anche quelle cancellate")
    p.set_defaults(func=cmd_vars)

    p = sub.add_parser("protection", help="la protezione del flash in questo avvio (M920x e W541): Protected "
                       "Range su WP_RO, BIOS Lock, FLOCKDN, regioni della FMAP; solo letture")
    p.add_argument("--flash", help="i nomi delle regioni da una copia del flash o da una release (.rom, .cap, .cab)")
    p.add_argument("--expect-ro", choices=("on", "off"),
                   help="esce con 1 se WP_RO non e' (on) o e' (off) protetta e bloccata, con 2 se non "
                   "si sa (WP_RO non trovata nella FMAP, registri SPI non letti, senza root)")
    p.set_defaults(func=cmd_protection)

    p = sub.add_parser("vboot-work", help="cosa ha deciso vboot in questo avvio (sudo cbmem -r 0x78007343 > FILE)")
    p.add_argument("dump")
    p.set_defaults(func=cmd_vboot_work)

    args = ap.parse_args()
    try:
        return args.func(args)
    except (Error, OSError) as e:
        print("errore: %s" % e, file=sys.stderr)
        return 1
    except (struct.error, ValueError) as e:
        # un file tagliato o non del tipo atteso (una capsula, un .cab, uno
        # store di variabili, un GUID scritto male): un errore, non un traceback
        print("errore: file o valore non valido: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
