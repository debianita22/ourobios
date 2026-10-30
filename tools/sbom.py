#!/usr/bin/env python3
# sbom.py - la distinta dei componenti (SBOM) di una ROM di ouroBIOS, per le
# release: le versioni di coreboot, delle sue librerie (vboot, libgfxinit,
# libhwbase), di EDK2, iPXE, CSMWrap e SeaBIOS, quelle dei binari chiusi
# (FSP-M e FSP-S, microcode, VBT, ME, descrittore e GbE, mrc.bin, VBIOS),
# con licenze e SHA-256, e quanto dell'immagine e' codice aperto, codice
# chiuso, dati o flash vuota (come l'Openness Score di Dasharo).
#
#   python3 -I tools/sbom.py dist/m920x-coreboot-v1.4.0-fsp.rom
#   python3 -I tools/sbom.py --repo . --coreboot work/coreboot ROM -o ROM-sbom.md
#   python3 -I tools/sbom.py --cyclonedx ROM -o ROM.cdx.json   # CycloneDX 1.5
#   python3 -I tools/sbom.py --notes ROM                       # per le note
#
# La ROM e' l'immagine intera (24 MiB sul M920x, 12 sul W541), quella che
# la sua FMAP descrive tutta, non i file dei chip. Se ci sono accanto (lo
# stesso nome, come in dist/ e nelle release) legge anche il .config della
# build (EDK2, opzioni) e il -layout.txt (commit pinnati, numero di patch,
# compilatori); senza .config, il config dentro la ROM. In piu':
#   --repo DIR      il clone di ouroBIOS: patch di patches/, pin di
#                   tools/build.sh, provenienza dei blob (boards/*/blobs,
#                   blobs/, BOARD_REFERENCE) e chiavi di vboot (keys/vboot)
#   --coreboot DIR  un clone git di coreboot con il commit pinnato, anche
#                   senza file (git fetch --depth=1 --filter=blob:none): i
#                   commit dei submodule (vboot, libgfxinit, libhwbase, fsp,
#                   intel-microcode) con git ls-tree
#
# Legge i formati da se', senza cbfstool (non c'e' nel job release): FMAP e
# CBFS (src/commonlib/bsd/include/commonlib/bsd/fmap_serialized.h e
# cbfs_serialized.h, il giro di cbfs_walk() in cbfs_private.c), payload SELF
# (src/lib/selfboot.c), LZMA come lo scrive cbfstool (util/cbfstool/lzma/
# lzma.c: 5 byte di proprieta' e 8 di dimensione, il formato "alone"),
# FSP_INFO_HEADER (src/drivers/intel/fsp2_0/include/fsp/info_header.h),
# microcode (src/cpu/intel/microcode/microcode.c), VBT
# (src/drivers/intel/gma/intel_bios.h), descrittore e ME come
# util/ifdtool/ifdtool.c e util/me_cleaner/me_cleaner.py, GBB e VBLOCK di
# vboot (firmware/2lib/include/2struct.h). Solo lettura: non scrive che il
# file di -o.
#
# Solo la libreria standard di Python.
import argparse
import datetime
import glob
import hashlib
import json
import lzma
import os
import re
import struct
import subprocess
import sys
import uuid

REPO_URL = "https://github.com/debianita22/ourobios"

OPEN, CLOSED, DATA, EMPTY = "open", "closed", "data", "empty"
CLASS_TEXT = {
    OPEN: "open-source code",
    CLOSED: "closed binary",
    DATA: "data",
    EMPTY: "empty (erased flash, free CBFS space)",
}

# i tipi dei file CBFS, con i nomi di cbfstool (cbfs_serialized.h)
CBFS_TYPES = {
    0x00000000: "deleted", 0xffffffff: "null", 0x01: "bootblock", 0x02: "cbfs header",
    0x10: "legacy stage", 0x11: "stage", 0x20: "simple elf", 0x21: "fit_payload",
    0x30: "optionrom", 0x40: "bootsplash", 0x50: "raw", 0x51: "vsa", 0x52: "mbi",
    0x53: "microcode", 0x54: "intel_fit", 0x60: "fsp", 0x61: "mrc", 0x62: "mma",
    0x63: "efi", 0x70: "struct", 0x80: "amdfw", 0xaa: "cmos_default", 0xab: "spd",
    0xac: "mrc_cache", 0x01aa: "cmos_layout",
}
CBFS_COMPRESS = {0: "none", 1: "LZMA", 2: "LZ4", 3: "zstd"}
CBFS_ATTR_COMPRESSION = 0x42435a4c        # 'BCZL'
CBFS_ALIGNMENT = 64
CBFS_METADATA_MAX_SIZE = 256
SELF_CODE, SELF_DATA, SELF_ENTRY = 0x434F4445, 0x44415441, 0x454E5452

# le regioni del descrittore: nome, nome FMAP (util/ifdtool/ifdtool.c, region_names)
IFD_REGIONS = (
    ("Flash Descriptor", "SI_DESC"), ("BIOS", "SI_BIOS"), ("Intel ME", "SI_ME"),
    ("GbE", "SI_GBE"), ("Platform Data", "SI_PDR"), ("Device Exp1", "SI_DEVICEEXT"),
    ("Secondary BIOS", "SI_BIOS2"), ("Reserved", None), ("EC", "SI_EC"),
    ("Device Exp2", "SI_DEVICEEXT2"), ("IE", "SI_IE"), ("10GbE_0", "SI_10GBE0"),
    ("10GbE_1", "SI_10GBE1"), ("Reserved", None), ("Reserved", None), ("PTT", "SI_PTT"),
)
IFD_LABELS = {
    "Flash Descriptor": "Intel flash descriptor (IFD)",
    "Intel ME": "Intel ME firmware",
    "GbE": "Intel GbE NVM",
    "Platform Data": "platform data region",
    "EC": "EC firmware region",
}

# le licenze: SPDX dove e' certa, altrimenti il nome (CycloneDX: license.name)
LIC = {
    "coreboot": ("id", "GPL-2.0-only"),
    "vboot": ("id", "BSD-3-Clause"),
    "libgfxinit": ("id", "GPL-2.0-or-later"),
    "libhwbase": ("id", "GPL-2.0-or-later"),
    "edk2": ("id", "BSD-2-Clause-Patent"),
    "lvglpkg": ("id", "MIT"),
    "ipxe": ("id", "GPL-2.0-or-later"),
    "csmwrap": ("name", "LGPL-2.1"),
    "seabios": ("id", "LGPL-3.0-only"),
    "fsp": ("name", "Intel FSP license (3rdparty/fsp/FSP_License.pdf)"),
    "microcode": ("name", "Intel microcode license (3rdparty/intel-microcode/license)"),
    "intel": ("name", "proprietary (Intel), from the Lenovo firmware"),
    "vbt": ("name", "proprietary (Intel VBT)"),
    "mrc": ("name", "proprietary (Intel)"),
    "vbios": ("name", "proprietary (option ROM vendor)"),
}

# i nomi delle regioni di vboot e dei dati scritti dal firmware
VBOOT_AREAS = ("GBB", "VBLOCK_A", "VBLOCK_B")
ID_AREAS = ("FMAP", "RO_FRID", "RW_FWID_A", "RW_FWID_B", "RO_PADDING")


def die(msg):
    sys.exit("sbom.py: " + msg)


def warn(msg):
    print("sbom.py: attenzione: " + msg, file=sys.stderr)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        die("%s: %s" % (path, e.strerror))


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def cstr(b):
    return b.split(b"\0")[0].decode("ascii", "replace")


def bcd_date(v):
    """Una data BCD 0xAAAAMMGG (manifest della ME)."""
    s = "%08x" % v
    return "%s-%s-%s" % (s[0:4], s[4:6], s[6:8]) if s.isdigit() else "0x%08x" % v


def human(n):
    for unit, shift in (("MiB", 20), ("KiB", 10)):
        if n >= 1 << shift:
            v = n / (1 << shift)
            return ("%d %s" % (v, unit)) if v == int(v) else ("%.1f %s" % (v, unit))
    return "%d B" % n


# --- FMAP e CBFS ------------------------------------------------------------

class Area:
    def __init__(self, name, off, size, flags):
        self.name, self.off, self.size, self.flags = name, off, size, flags
        self.end = off + size


def find_fmap(rom):
    """La FMAP dell'immagine (fmap_serialized.h): intestazione di 56 byte,
    aree di 42 (offset, dimensione, nome, flag)."""
    i = rom.find(b"__FMAP__")
    while i >= 0:
        try:
            major, minor, base, size, name, nareas = struct.unpack_from("<BBQI32sH", rom, i + 8)
            if major == 1 and 0 < nareas < 256:
                areas = []
                for a in range(nareas):
                    off, sz, nm, fl = struct.unpack_from("<II32sH", rom, i + 56 + a * 42)
                    areas.append(Area(cstr(nm), off, sz, fl))
                return {"offset": i, "version": "%d.%d" % (major, minor), "base": base,
                        "size": size, "name": cstr(name), "areas": areas}
        except struct.error:
            pass
        i = rom.find(b"__FMAP__", i + 1)
    return None


def leaf_areas(areas):
    """Le aree che non ne contengono altre; di quelle uguali la prima."""
    leaves, seen = [], set()
    for a in areas:
        if (a.off, a.size) in seen or a.size == 0:
            continue
        inner = [b for b in areas if b is not a and b.size and a.off <= b.off and b.end <= a.end
                 and (b.off, b.size) != (a.off, a.size)]
        if not inner:
            leaves.append(a)
            seen.add((a.off, a.size))
    return sorted(leaves, key=lambda a: a.off)


class CbfsFile:
    def __init__(self, region, name, ftype, hdr, data, length, comp, usize):
        self.region, self.name, self.type = region, name, ftype
        self.hdr, self.data_off, self.len = hdr, data, length
        self.comp, self.usize = comp, usize
        self.end = data + length


def cbfs_walk(rom, area):
    """I file del CBFS dell'area, come cbfs_walk() (cbfs_private.c): una
    intestazione LARCHIVE (big endian) cercata ogni 64 byte dall'inizio
    dell'area, e la successiva dopo dati e allineamento."""
    files = []
    off = 0
    while True:
        off = (off + CBFS_ALIGNMENT - 1) & ~(CBFS_ALIGNMENT - 1)
        i = rom.find(b"LARCHIVE", area.off + off, area.end)
        while i >= 0 and (i - area.off) % CBFS_ALIGNMENT:
            i = rom.find(b"LARCHIVE", i + 1, area.end)
        if i < 0 or i + 24 >= area.end:
            break
        off = i - area.off
        length, ftype, attr, doff = struct.unpack_from(">IIII", rom, i + 8)
        if doff < 24 or doff > CBFS_METADATA_MAX_SIZE or off + doff + length > area.size:
            warn("%s: intestazione CBFS non valida a 0x%x" % (area.name, off))
            off += CBFS_ALIGNMENT
            continue
        name = cstr(rom[i + 24:i + (attr if attr else doff)])
        comp, usize = 0, length
        a = i + attr if attr else i + doff
        while attr and a + 8 <= i + doff:
            tag, alen = struct.unpack_from(">II", rom, a)
            if tag in (0, 0xffffffff) or alen < 8 or a + alen > i + doff:
                break
            if tag == CBFS_ATTR_COMPRESSION and alen >= 16:
                comp, usize = struct.unpack_from(">II", rom, a + 8)
            a += alen
        files.append(CbfsFile(area.name, name, ftype, i, i + doff, length, comp, usize))
        off += doff + length
    return files


def decompress(data, comp):
    """I dati di un file CBFS; None se compressi in un formato che la
    libreria standard non ha (LZ4, zstd)."""
    if comp == 0:
        return data
    if comp == 1:
        try:
            return lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(data)
        except lzma.LZMAError:
            return None
    return None


def file_data(rom, f):
    return decompress(rom[f.data_off:f.end], f.comp)


def self_segments(data):
    """I segmenti CODE e DATA di un payload SELF, decompressi
    (cbfs_serialized.h, cbfs_payload_segment: 28 byte big endian; l'offset
    e' dall'inizio del primo segmento, selfboot.c)."""
    segs = []
    off = 0
    while off + 28 <= len(data):
        stype, comp, soff, load, length, memlen = struct.unpack_from(">IIIQII", data, off)
        if stype == SELF_ENTRY:
            break
        if stype in (SELF_CODE, SELF_DATA) and soff + length <= len(data):
            seg = decompress(data[soff:soff + length], comp)
            if seg is None:
                warn("payload: segmento compresso con %s, non letto" % CBFS_COMPRESS.get(comp, comp))
            else:
                segs.append(seg)
        off += 28
    return segs


# --- descrittore, ME, GbE -----------------------------------------------------

def ifd_parse(rom):
    """Le regioni del descrittore Intel, come get_region() e
    max_regions_from_fdbar() di ifdtool: FLMAP0/FLMAP1 a 0x14, le FLREG a
    FRBA, base e limite in blocchi da 4 KiB."""
    if len(rom) < 0x1000 or rom[0x10:0x14] != b"\x5a\xa5\xf0\x0f":
        return None
    flmap0, flmap1 = struct.unpack_from("<II", rom, 0x14)
    fcba = (flmap0 & 0xff) << 4
    frba = ((flmap0 >> 16) & 0xff) << 4
    fmba = (flmap1 & 0xff) << 4
    fpsba = ((flmap1 >> 16) & 0xff) << 4
    marks = sorted((fcba, fmba, frba, fpsba, 4096 - 256 - 4))
    nmax = 16
    for a, b in zip(marks, marks[1:]):
        if a == frba:
            nmax = min((b - a) // 4, 16)
            break
    regions = []
    for i in range(nmax):
        v = struct.unpack_from("<I", rom, frba + 4 * i)[0]
        base = (v & 0x7fff) << 12
        limit = ((v >> 4) & 0x7fff000) | 0xfff
        if base > limit or limit >= len(rom):
            continue
        # le FLREG oltre quelle del chipset (IFD v1: 5) non sono regioni:
        # una che si sovrappone a un'altra si scarta
        if any(base <= r["limit"] and r["base"] <= limit for r in regions):
            continue
        name, fmap_name = IFD_REGIONS[i]
        regions.append({"index": i, "name": name, "fmap": fmap_name, "base": base,
                        "limit": limit, "size": limit - base + 1})
    flmstr = struct.unpack_from("<III", rom, fmba)
    pchstrp0 = struct.unpack_from("<I", rom, fpsba)[0]
    pchstrp10 = struct.unpack_from("<I", rom, fpsba + 0x28)[0]
    return {"regions": regions, "flmstr": flmstr, "pchstrp0": pchstrp0,
            "pchstrp10": pchstrp10, "flmap0": flmap0, "flmap1": flmap1}


def me_manifest(me, off):
    """Versione e data del manifest $MN2 a off (me_cleaner: tag a +0x1c,
    major.minor.hotfix.build a +0x24; la data BCD a +0x14)."""
    if off + 0x2c > len(me) or me[off + 0x1c:off + 0x20] != b"$MN2":
        return None
    ver = struct.unpack_from("<HHHH", me, off + 0x24)
    return {"version": "%d.%d.%d.%d" % ver, "major": ver[0],
            "date": bcd_date(struct.unpack_from("<I", me, off + 0x14)[0])}


def cpd_partitions(me):
    """Le directory $CPD delle partizioni di codice (ME 11 e successive):
    16 byte di intestazione (marker, voci, versione, versione delle voci,
    lunghezza, checksum, nome), voci da 24 byte (nome di 12, offset di 3),
    come le legge me_cleaner; il manifest e' <NOME>.man."""
    parts = []
    for m in re.finditer(re.escape(b"$CPD"), me):
        off = m.start()
        if off + 0x14 > len(me):
            continue
        count, hver, ever, hlen = struct.unpack_from("<IBBB", me, off + 4)
        name = me[off + 12:off + 16]
        if hver not in (1, 2) or ever != 1 or hlen not in (0x10, 0x14) or not 0 < count < 256 \
                or not re.fullmatch(rb"[A-Z0-9]{4}", name):
            continue
        name = name.decode()
        entry = {"name": name, "offset": off, "version": None, "date": None}
        for j in range(count):
            e = off + hlen + j * 0x18
            if e + 0x18 > len(me):
                break
            ename = cstr(me[e:e + 12])
            eoff = struct.unpack("<I", me[e + 12:e + 15] + b"\0")[0]
            if ename == name + ".man":
                man = me_manifest(me, off + eoff)
                if man:
                    entry.update(man)
                break
        parts.append(entry)
    return parts


def me_parse(me):
    """La versione del firmware della ME: con la $FPT a 0x10 (ME fino alla
    11) la partizione FTPR, $MN2 o $CPD (me_cleaner); sulla CSME 12 la regione
    comincia con la tabella del layout CSE e la $FPT e' nella partizione dei
    dati: le partizioni di codice si trovano dalle loro $CPD."""
    res = {"kind": None, "version": None, "partitions": [], "fpt": None}
    if me[0x10:0x14] == b"$FPT":
        n = struct.unpack_from("<I", me, 0x14)[0]
        res["fpt"] = 0x10
        for i in range(min(n, 64)):
            e = me[0x30 + i * 0x20:0x50 + i * 0x20]
            if len(e) < 0x20:
                break
            name = e[0:4].decode("ascii", "replace")
            poff, plen = struct.unpack_from("<II", e, 8)
            p = {"name": name, "offset": poff, "length": plen, "version": None, "date": None}
            if name == "FTPR" and poff < len(me):
                if me[poff:poff + 4] == b"$CPD":
                    res["kind"] = "cse"
                else:
                    man = me_manifest(me, poff)
                    if man:
                        p.update(man)
                        res["kind"] = "me"
            res["partitions"].append(p)
    if res["kind"] != "me":
        cpd = cpd_partitions(me)
        if cpd:
            res["kind"] = "cse"
            known = {p["name"]: p for p in res["partitions"]}
            for c in cpd:
                if c["name"] in known:
                    known[c["name"]].update({k: c[k] for k in ("version", "date")})
                else:
                    res["partitions"].append(c)
    for p in res["partitions"]:
        if p["name"] == "FTPR" and p.get("version"):
            res["version"] = p["version"]
            res["date"] = p["date"]
            res["major"] = p["major"]
        if p["name"] == "PMCP" and p.get("version"):
            res["pmc"] = p["version"]
    return res


def ff_trim(data):
    """I dati senza gli 0xFF in fondo, a blocchi di 4 KiB (come me.bin di
    boards/m920x/blobs/README.md)."""
    d = data.rstrip(b"\xff")
    return d + b"\xff" * (-len(d) % 4096)


# --- FSP, microcode, VBT, option ROM, vboot ----------------------------------------

def fsp_parse(data):
    """L'FSP_INFO_HEADER (info_header.h) a FSP_HDR_OFFSET 0x94, come
    fsp_validate_component() di fsp2_0/util.c."""
    i = 0x94 if data[0x94:0x98] == b"FSPH" else data.find(b"FSPH")
    if i < 0 or i + 0x48 > len(data):
        return None
    (hlen, spec, hrev, irev) = struct.unpack_from("<I2xBBI", data, i + 4)
    image_id = data[i + 16:i + 24].decode("ascii", "replace")
    isize, ibase, iattr, cattr, cfg_off, cfg_size = struct.unpack_from("<IIHHII", data, i + 24)
    major, minor, rev, build = irev >> 24, (irev >> 16) & 0xff, (irev >> 8) & 0xff, irev & 0xff
    # FSP 2.3: i bit alti di revision e build in extended_image_revision
    # (header_display.c lo usa con CONFIG_PLATFORM_USES_FSP2_3)
    if hrev >= 7 and hlen >= 0x50:
        ext = struct.unpack_from("<H", data, i + 0x4c)[0]
        rev |= (ext >> 8) << 8
        build |= (ext & 0xff) << 8
    upd = data[cfg_off:cfg_off + 8] if cfg_off + 9 <= len(data) else b""
    return {
        # come lo stampa l'HOB della versione di FSP (hand_off_block.c, %x) e
        # come lo chiama Intel ("Coffee Lake FSP 7.0.74.20")
        "version": "%x.%x.%x.%x" % (major, minor, rev, build),
        # come lo stampa fsp_print_header_info() (header_display.c, %u)
        "decimal": "%u.%u.%u build %u" % (major, minor, rev, build),
        "spec": "%d.%d" % (spec >> 4, spec & 0xf), "header_revision": hrev,
        "image_id": image_id, "image_size": isize, "image_base": ibase,
        "component": {1: "FSP-T", 2: "FSP-M", 3: "FSP-S"}.get(cattr >> 12, "?"),
        "build_type": "%s/%s" % ("release" if cattr & 1 else "debug",
                                 "official" if cattr & 2 else "test"),
        "upd": "%s rev %d" % (upd.decode("ascii", "replace"), data[cfg_off + 8]) if upd else None,
    }


def microcode_parse(data):
    """Gli aggiornamenti del blob, uno dopo l'altro: intestazione di 48 byte
    (struct microcode di microcode.c), data_size 0 vuol dire 2000 byte e
    total_size 2048 (SDM di Intel)."""
    ups = []
    off = 0
    while off + 48 <= len(data):
        hdr, rev, date, sig, cksum, ldr, pf, dsize, tsize = struct.unpack_from("<9I", data, off)
        if hdr != 1:
            break
        if dsize == 0:
            dsize, tsize = 2000, 2048
        if tsize < 48 or off + tsize > len(data):
            warn("microcode: aggiornamento a 0x%x troncato" % off)
            break
        blob = data[off:off + tsize]
        sigs = [(sig, pf)]
        ext = 48 + dsize
        if tsize - ext >= 20:
            n = struct.unpack_from("<I", blob, ext)[0]
            for k in range(min(n, 64)):
                e = ext + 20 + 12 * k
                if e + 12 <= tsize:
                    s, p, _ = struct.unpack_from("<III", blob, e)
                    sigs.append((s, p))
        ok = sum(struct.unpack_from("<%dI" % (tsize // 4), blob)) & 0xffffffff == 0
        ups.append({
            "offset": off, "cpuids": sigs, "revision": rev,
            # come la stampa coreboot (microcode.c): anno, mese, giorno
            "date": "%04x-%02x-%02x" % (date & 0xffff, date >> 24, (date >> 16) & 0xff),
            "size": tsize, "sha256": sha256(blob), "checksum_ok": ok,
        })
        off += tsize
    rest = data[off:]
    if rest.strip(b"\xff\0"):
        warn("microcode: %d byte dopo l'ultimo aggiornamento non riconosciuti" % len(rest))
    return ups


def vbt_parse(data):
    """struct vbt_header e bdb_header (intel_bios.h)."""
    if data is None or data[:4] != b"$VBT" or len(data) < 48:
        return None
    version, hsize, vsize, cks, _, bdb_off = struct.unpack_from("<HHHBBI", data, 20)
    res = {"signature": data[:20].rstrip(b"\0 ").decode("ascii", "replace"), "version": version,
           "size": vsize, "bdb": None}
    if data[bdb_off:bdb_off + 16].startswith(b"BIOS_DATA_BLOCK") and bdb_off + 18 <= len(data):
        res["bdb"] = struct.unpack_from("<H", data, bdb_off + 16)[0]
    return res


def optionrom_parse(data):
    """Un'option ROM PCI: 55AA, la struttura PCIR (fornitore, dispositivo) e
    la versione del VBIOS NVIDIA ("Version 80.06.63.00.1D")."""
    if data is None or data[:2] != b"\x55\xaa" or len(data) < 0x1a:
        return None
    res = {"vendor": None, "device": None, "version": None}
    p = struct.unpack_from("<H", data, 0x18)[0]
    if data[p:p + 4] == b"PCIR":
        res["vendor"], res["device"] = struct.unpack_from("<HH", data, p + 4)
    m = re.search(rb"Version (\d{2}\.\d{2}\.[0-9A-F]{2}\.[0-9A-F]{2}\.[0-9A-F]{2})", data[:0x1000])
    if m:
        res["version"] = m.group(1).decode()
    return res


def packed_key(data, off):
    """vb2_packed_key a off: offset (dalla struct), dimensione, algoritmo,
    versione, e i byte della chiave."""
    if off + 32 > len(data):
        return None
    koff, ksize, algo, kver = struct.unpack_from("<I4xI4xI4xI", data, off)
    key = data[off + koff:off + koff + ksize]
    if len(key) != ksize or not ksize:
        return None
    return {"algorithm": algo, "version": kver, "size": ksize, "sha256": sha256(key)}


def gbb_parse(data):
    """vb2_gbb_header: "$GBB", versione, flag, HWID, chiave root e di recovery."""
    if data[:4] != b"$GBB" or len(data) < 128:
        return None
    major, minor, hsize, flags, hwo, hws, rko, rks, _, _, rco, rcs = \
        struct.unpack_from("<HHIIIIIIIIII", data, 4)
    return {"version": "%d.%d" % (major, minor), "flags": flags,
            "hwid": cstr(data[hwo:hwo + hws]) if hws else "",
            "root_key": packed_key(data, rko) if rks else None,
            "recovery_key": packed_key(data, rco) if rcs else None}


def vblock_parse(data):
    """vb2_keyblock ("CHROMEOS": la chiave dei dati a +80) e, dopo
    keyblock_size, vb2_fw_preamble (versione del firmware a +40, firma del
    corpo a +80: quanti byte dello slot copre)."""
    if data[:8] != b"CHROMEOS" or len(data) < 112:
        return None
    kmaj, kmin, ksize = struct.unpack_from("<III", data, 8)
    flags = struct.unpack_from("<I", data, 72)[0]
    res = {"keyblock_size": ksize, "keyblock_flags": flags, "data_key": packed_key(data, 80),
           "keyblock_sha256": sha256(data[:ksize]) if ksize <= len(data) else None,
           "firmware_version": None, "body_size": None, "preamble_flags": None}
    p = ksize
    if p + 108 <= len(data):
        hmaj, hmin, fwver = struct.unpack_from("<III", data, p + 32)
        res["firmware_version"] = fwver
        res["body_size"] = struct.unpack_from("<I", data, p + 80 + 16)[0]
        res["preamble_flags"] = struct.unpack_from("<I", data, p + 104)[0]
    return res


def vbpubk_sha256(path):
    """Lo SHA-256 dei byte della chiave di un file .vbpubk o .keyblock del
    repository, per il confronto con quelli della ROM."""
    d = read_file(path)
    if path.endswith(".keyblock"):
        k = packed_key(d, 80) if d[:8] == b"CHROMEOS" else None
    else:
        k = packed_key(d, 0)
    return k["sha256"] if k else None


# --- .config, layout, repository ----------------------------------------------

def parse_config(text):
    cfg = {}
    for line in text.splitlines():
        m = re.match(r"^(CONFIG_\w+)=(.*)$", line)
        if m:
            v = m.group(2)
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1].replace('\\"', '"')
            cfg[m.group(1)] = v
    return cfg


def parse_layout(text):
    """Le righe che tools/build.sh (collect) scrive in testa al -layout.txt."""
    lay = {"optional": []}
    for line in text.splitlines():
        m = re.match(r"^coreboot (\S+) \(([0-9a-f]{40})\) \+ (\d+) patches", line)
        if m:
            lay["coreboot_describe"], lay["coreboot_commit"], lay["coreboot_patches"] = \
                m.group(1), m.group(2), int(m.group(3))
        m = re.match(r"^EDK2 ([0-9a-f]{7,40}) \+ (\d+) patches.*?LvglPkg \+ (\d+) patches", line)
        if m:
            lay["edk2_rev"], lay["edk2_patches"], lay["lvgl_patches"] = \
                m.group(1), int(m.group(2)), int(m.group(3))
        m = re.match(r"^iPXE ([0-9a-f]{40}), CSMWrap ([0-9a-f]{40}) \(SeaBIOS ([0-9a-f]{40}|\?)\)", line)
        if m:
            lay["ipxe_commit"], lay["csmwrap_commit"] = m.group(1), m.group(2)
            if m.group(3) != "?":
                lay["seabios_commit"] = m.group(3)
        if line.startswith("toolchain: "):
            lay["toolchain"] = line[len("toolchain: "):]
        m = re.match(r"^\+ (patches/optional/\S+)", line)
        if m:
            lay["optional"].append(m.group(1))
        m = re.match(r'^CONFIG_LOCALVERSION="(.*)"$', line)
        if m:
            lay["localversion"] = m.group(1)
    return lay


def series_count(path):
    """Le patch di una serie: le righe senza commenti, come cmd_notes di
    tools/ci.sh."""
    t = read_text(path)
    if t is None:
        return None
    return sum(1 for line in t.splitlines() if re.sub(r"#.*", "", line).strip())


def shell_value(text, name):
    """NAME="..." o NAME=$((espressione semplice)) di uno script bash."""
    m = re.search(r'^%s="([^"]*)"' % name, text, re.M)
    if m:
        return m.group(1)
    m = re.search(r"^%s=\$\(\(\s*(0x[0-9a-fA-F]+|\d+)\s*(?:<<\s*(\d+))?\s*\)\)" % name, text, re.M)
    if m:
        return int(m.group(1), 0) << int(m.group(2) or 0)
    m = re.search(r"^%s=([^\s(]\S*)" % name, text, re.M)
    if m:
        return m.group(1)
    m = re.search(r"^%s=\(([^)]*)\)" % name, text, re.M)
    if m:
        return m.group(1).split()
    return None


def repo_info(repo, part_number):
    """Dal clone di ouroBIOS: patch, pin di tools/build.sh e la board con
    quel BOARD_NAME (boards/*/board.sh)."""
    info = {"dir": repo}
    for key, path in (("coreboot_patches", "patches/series"), ("edk2_patches", "patches/edk2/series"),
                      ("lvgl_patches", "patches/lvglpkg/series")):
        n = series_count(os.path.join(repo, path))
        if n is not None:
            info[key] = n
    bs = read_text(os.path.join(repo, "tools/build.sh"))
    if bs is None:
        warn("%s: non c'e' tools/build.sh, non e' il clone di ouroBIOS?" % repo)
    else:
        for key, var in (("coreboot_commit", "COREBOOT_COMMIT"), ("coreboot_describe", "COREBOOT_DESCRIBE"),
                         ("ipxe_commit", "IPXE_COMMIT"), ("csmwrap_commit", "CSMWRAP_COMMIT")):
            v = shell_value(bs, var)
            if isinstance(v, str):
                info[key] = v
    for path in sorted(glob.glob(os.path.join(repo, "boards", "*", "board.sh"))):
        t = read_text(path) or ""
        if shell_value(t, "BOARD_NAME") == part_number:
            info["board"] = os.path.basename(os.path.dirname(path))
            info["intel_size"] = shell_value(t, "BOARD_INTEL_SIZE")
            info["reference"] = shell_value(t, "BOARD_REFERENCE")
            sums = shell_value(t, "BOARD_SUMS")
            info["sums"] = [sums] if isinstance(sums, str) else (sums or [])
    if "board" not in info:
        warn("%s: nessuna boards/*/board.sh con BOARD_NAME=\"%s\"" % (repo, part_number))
    blobs = {}
    for s in info.get("sums", []):
        t = read_text(os.path.join(repo, s))
        if t is None:
            warn("%s: %s non c'e'" % (repo, s))
            continue
        for line in t.splitlines():
            m = re.match(r"^([0-9a-f]{64})\s+\*?(\S+)$", line)
            if m:
                blobs[m.group(1)] = os.path.join(os.path.dirname(s), m.group(2))
    info["blobs"] = blobs
    try:
        out = subprocess.run(["git", "-C", repo, "describe", "--always", "--dirty", "--tags"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            info["describe"] = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def submodules(cbdir, commit):
    """I commit dei submodule di coreboot in 3rdparty/ (git ls-tree)."""
    res = {}
    for rev in ([commit] if commit else []) + ["HEAD"]:
        try:
            out = subprocess.run(["git", "-C", cbdir, "ls-tree", rev, "3rdparty/"],
                                 capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            warn("%s: git ls-tree non va: %s" % (cbdir, e))
            return res
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                m = re.match(r"^160000 commit ([0-9a-f]{40})\t3rdparty/(\S+)$", line)
                if m:
                    res[m.group(2)] = m.group(1)
            if res:
                if rev == "HEAD" and commit:
                    warn("%s: il commit %s non c'e', uso HEAD" % (cbdir, commit[:12]))
                return res
    warn("%s: nessun submodule in 3rdparty/ (non e' un clone di coreboot?)" % cbdir)
    return res


# --- conteggio dell'apertura --------------------------------------------------

class Tally:
    """I byte dell'immagine per componente e classe."""

    def __init__(self, rom):
        self.rom = rom
        self.rows = {}
        self.covered = 0

    def add(self, label, cls, n):
        if n:
            self.rows[(label, cls)] = self.rows.get((label, cls), 0) + n
            self.covered += n

    def scan(self, start, end, label, cls):
        """Un tratto fuori dal CBFS: le sequenze di almeno 64 byte a 0xFF
        sono flash vuota, il resto e' della classe data."""
        empty = sum(m.end() - m.start() for m in re.finditer(rb"\xff{64,}", self.rom[start:end]))
        self.add(label, cls, end - start - empty)
        self.add("erased flash (0xff)", EMPTY, empty)

    def total(self, cls):
        return sum(n for (_, c), n in self.rows.items() if c == cls)


def cbfs_class(f):
    """Componente e classe di un file CBFS."""
    n, t = f.name, f.type
    if t in (0, 0xffffffff):
        return "free CBFS space", EMPTY
    if t == 0x53 or n == "cpu_microcode_blob.bin":
        return "Intel CPU microcode", CLOSED
    if t == 0x60 or n in ("fspm.bin", "fsps.bin", "fspt.bin"):
        return {"fspm.bin": "Intel FSP-M", "fsps.bin": "Intel FSP-S", "fspt.bin": "Intel FSP-T"}.get(
            n, "Intel FSP (%s)" % n), CLOSED
    if t == 0x61 or n == "mrc.bin":
        return "Intel MRC (mrc.bin)", CLOSED
    if n == "vbt.bin":
        return "Intel VBT", CLOSED
    if t == 0x30:
        m = re.fullmatch(r"pci([0-9a-f]{4}),([0-9a-f]{4})\.rom", n)
        return ("option ROM %s:%s" % m.groups()) if m else "option ROM %s" % n, CLOSED
    if t in (0x01, 0x10, 0x11) or n.endswith(".aml"):
        return "coreboot (stages, ACPI tables)", OPEN
    if t in (0x20, 0x21):
        return "payload (EDK II, iPXE, CSMWrap, SeaBIOS)", OPEN
    if t in (0x02, 0x54, 0x1aa, 0xaa, 0xab) or n in ("config", "revision", "build_info"):
        return "coreboot metadata (CBFS header, FIT, config, revision)", DATA
    if t == 0x40 or n.endswith(".bmp"):
        return "boot splash", DATA
    warn("file CBFS %s/%s (%s) sconosciuto: contato come binario chiuso"
         % (f.region, n, CBFS_TYPES.get(t, hex(t))))
    return "unknown CBFS file %s" % n, CLOSED


def area_class(area, ifd_kind):
    if ifd_kind:
        return IFD_LABELS.get(ifd_kind, "IFD region %s" % ifd_kind), CLOSED
    if area.name in VBOOT_AREAS:
        return "vboot keys and signatures (GBB, VBLOCK)", DATA
    if area.name in ID_AREAS:
        return "flash map and firmware IDs", DATA
    return "runtime regions (MRC cache, UEFI variables, VPD, event log, NVRAM)", DATA


# --- l'analisi --------------------------------------------------------------

def analyze(a):
    rom = read_file(a.rom)
    base = re.sub(r"\.rom$", "", a.rom)
    info = {"rom": a.rom, "name": os.path.basename(base), "size": len(rom), "sha256": sha256(rom)}

    fmap = find_fmap(rom)
    if not fmap:
        die("%s: nessuna FMAP, non e' una ROM di coreboot" % a.rom)
    if fmap["size"] != len(rom):
        die("%s: la FMAP descrive %d byte, il file ne ha %d: serve l'immagine intera (.rom), "
            "non il file di un chip" % (a.rom, fmap["size"], len(rom)))
    info["fmap"] = fmap
    areas = {x.name: x for x in fmap["areas"]}

    # i file CBFS di ogni area che ne ha uno
    leaves = leaf_areas(fmap["areas"])
    cbfs = {}
    for x in leaves:
        if rom[x.off:x.off + 8] == b"LARCHIVE":
            cbfs[x.name] = cbfs_walk(rom, x)
    if not cbfs:
        die("%s: nessun CBFS nella FMAP" % a.rom)
    info["cbfs_regions"] = list(cbfs)
    # prima il CBFS della parte RO (COREBOOT), poi gli slot
    main = "COREBOOT" if "COREBOOT" in cbfs else list(cbfs)[0]
    order = [main] + [r for r in cbfs if r != main]

    def find(name, regions=None):
        return [f for r in (regions or order) for f in cbfs.get(r, []) if f.name == name]

    # una ROM di una build ha la stessa revision in ogni CBFS; un dump del
    # flash dopo un aggiornamento puo' avere slot di build diverse
    revs = {}
    for f in find("revision"):
        revs.setdefault(file_data(rom, f), []).append(f.region)
    if len(revs) > 1:
        warn("build diverse nei CBFS (%s): versione e config sono quelli di %s"
             % ("; ".join(", ".join(r) for r in revs.values()), main))

    def first_data(name):
        for f in find(name):
            d = file_data(rom, f)
            if d is not None:
                return d
        return None

    # versione, build, board
    rev = (first_data("revision") or b"").decode("ascii", "replace")
    defs = dict(re.findall(r'#define (COREBOOT_\w+) "?([^"\n]*)"?', rev))
    binfo = dict(re.findall(r"^(\w+): (.*)$", (first_data("build_info") or b"").decode("ascii", "replace"),
                            re.M))
    info["coreboot_version"] = defs.get("COREBOOT_VERSION") or binfo.get("COREBOOT_VERSION")
    info["extra_version"] = defs.get("COREBOOT_EXTRA_VERSION", "").lstrip("-")
    info["build_time"] = None
    if defs.get("COREBOOT_VERSION_TIMESTAMP", "").isdigit():
        info["build_epoch"] = int(defs["COREBOOT_VERSION_TIMESTAMP"])
    if defs.get("COREBOOT_BUILD_EPOCH", "").isdigit():
        info["build_epoch"] = int(defs["COREBOOT_BUILD_EPOCH"])
    if "build_epoch" in info:
        info["build_time"] = datetime.datetime.fromtimestamp(info["build_epoch"], datetime.timezone.utc)
    info["vendor"] = binfo.get("MAINBOARD_VENDOR", "")
    info["part"] = binfo.get("MAINBOARD_PART_NUMBER", "")

    # .config: quello accanto o quello della ROM
    cbfs_cfg = parse_config((first_data("config") or b"").decode("ascii", "replace"))
    cfg_path = a.config or (base + ".config" if os.path.isfile(base + ".config") else None)
    if cfg_path:
        cfg = parse_config(read_text(cfg_path) or "")
        info["config_source"] = os.path.basename(cfg_path)
        for k in ("CONFIG_LOCALVERSION", "CONFIG_EDK2_TAG_OR_REV"):
            if k in cbfs_cfg and cbfs_cfg.get(k) != cfg.get(k):
                warn("%s: %s=%s, la ROM dice %s: e' il .config di un'altra build?"
                     % (cfg_path, k, cfg.get(k), cbfs_cfg[k]))
    else:
        cfg = cbfs_cfg
        info["config_source"] = "the config file in CBFS"
    info["cfg"] = cfg
    info["localversion"] = cfg.get("CONFIG_LOCALVERSION") or info["extra_version"]

    lay_path = a.layout or (base + "-layout.txt" if os.path.isfile(base + "-layout.txt") else None)
    lay = parse_layout(read_text(lay_path) or "") if lay_path else {"optional": []}
    if lay_path and "coreboot_commit" not in lay:
        warn("%s: non e' il -layout.txt di tools/build.sh" % lay_path)
    info["layout_source"] = os.path.basename(lay_path) if lay_path else None
    info["layout"] = lay

    repo = repo_info(a.repo, info["part"]) if a.repo else None
    info["repo"] = repo
    if repo:
        for k in ("coreboot_commit", "coreboot_describe", "ipxe_commit", "csmwrap_commit",
                  "coreboot_patches", "edk2_patches", "lvgl_patches"):
            if k in repo and k in lay and repo[k] != lay[k]:
                warn("%s: %s %s, il layout della ROM dice %s (descrivo la ROM)" % (a.repo, k, repo[k], lay[k]))

    def pick(k):
        return lay.get(k, repo.get(k) if repo else None)

    info["pins"] = {k: pick(k) for k in ("coreboot_commit", "coreboot_describe", "coreboot_patches",
                                         "edk2_patches", "lvgl_patches", "ipxe_commit", "csmwrap_commit",
                                         "seabios_commit", "toolchain")}
    if info["pins"]["coreboot_describe"] and info["coreboot_version"] \
            and info["pins"]["coreboot_describe"] != info["coreboot_version"]:
        warn("coreboot %s nella ROM, %s nel layout/repository" % (info["coreboot_version"],
                                                                  info["pins"]["coreboot_describe"]))
    info["submodules"] = submodules(a.coreboot, info["pins"]["coreboot_commit"]) if a.coreboot else {}

    # le ID del firmware
    info["fwid"] = {}
    for n in ("RO_FRID", "RW_FWID_A", "RW_FWID_B"):
        if n in areas:
            info["fwid"][n] = cstr(rom[areas[n].off:areas[n].end])

    # il payload: iPXE, CSMWrap e SeaBIOS dalle loro stringhe
    info["payload"] = {}
    for f in find("fallback/payload"):
        segs = self_segments(rom[f.data_off:f.end])
        blob = b"".join(segs)
        p = {"cbfs_size": f.len, "size": len(blob)}
        m = re.search(rb"iPXE\0+(\d+\.\d+\.\d+\+? \(g[0-9a-f]{4,}\))\0", blob)
        if m:
            p["ipxe"] = m.group(1).decode()
        m = re.search(rb"CSMWrap Version ([0-9A-Za-z.+-]+)", blob)
        if m:
            p["csmwrap"] = m.group(1).decode()
        m = re.search(rb"([0-9a-f]{7,40})-CSMWrap-([0-9a-f]{7,40})", blob)
        if m:
            p["seabios"] = m.group(0).decode()
        info["payload"] = p
        break

    # i binari chiusi in CBFS: uno per nome, con le copie di ogni regione
    def copies(name):
        out = []
        for f in find(name):
            d = file_data(rom, f)
            out.append((f, d))
        return out

    def same(cps, what):
        hs = {sha256(d) for _, d in cps if d is not None}
        if len(hs) > 1:
            warn("%s: copie diverse tra %s" % (what, ", ".join(f.region for f, _ in cps)))
        return hs

    mc = copies("cpu_microcode_blob.bin")
    info["microcode"] = None
    if mc and mc[0][1] is not None:
        same(mc, "cpu_microcode_blob.bin")
        info["microcode"] = {"updates": microcode_parse(mc[0][1]), "size": len(mc[0][1]),
                             "sha256": sha256(mc[0][1]), "regions": [f.region for f, _ in mc]}
    # FSP: una voce per copia diversa. FSP-M eseguito dal flash
    # (CONFIG_FSP_M_XIP) e' rilocato da cbfstool all'indirizzo di ogni
    # slot: le copie di FW_MAIN_A e FW_MAIN_B hanno ImageBase e SHA-256 loro
    info["fsp"] = []
    for name in ("fspt.bin", "fspm.bin", "fsps.bin"):
        groups = {}
        for f, d in copies(name):
            if d is None:
                warn("%s/%s: compresso con %s, non letto" % (f.region, name, CBFS_COMPRESS.get(f.comp, f.comp)))
                continue
            g = groups.setdefault(sha256(d), {"data": d, "regions": [], "stored": f.len,
                                              "comp": CBFS_COMPRESS.get(f.comp, "?")})
            g["regions"].append(f.region)
        for h, g in groups.items():
            hdr = fsp_parse(g["data"])
            if not hdr:
                warn("%s: niente FSP_INFO_HEADER" % name)
            info["fsp"].append({"name": name, "hdr": hdr, "size": len(g["data"]), "sha256": h,
                                "stored": g["stored"], "comp": g["comp"], "regions": g["regions"],
                                "split": len(groups) > 1})
    cps = copies("vbt.bin")
    info["vbt"] = None
    if cps and cps[0][1] is not None:
        same(cps, "vbt.bin")
        info["vbt"] = {"hdr": vbt_parse(cps[0][1]), "size": len(cps[0][1]), "sha256": sha256(cps[0][1]),
                       "regions": [f.region for f, _ in cps], "comp": CBFS_COMPRESS.get(cps[0][0].comp, "?")}
    info["mrc"] = None
    cps = copies("mrc.bin")
    if cps and cps[0][1] is not None:
        info["mrc"] = {"size": len(cps[0][1]), "sha256": sha256(cps[0][1]),
                       "regions": [f.region for f, _ in cps]}
    info["oproms"] = []
    for name in sorted({f.name for r in cbfs for f in cbfs[r] if f.type == 0x30}):
        cps = copies(name)
        if cps[0][1] is None:
            continue
        same(cps, name)
        info["oproms"].append({"name": name, "hdr": optionrom_parse(cps[0][1]), "size": len(cps[0][1]),
                               "sha256": sha256(cps[0][1]), "regions": [f.region for f, _ in cps]})

    # descrittore, GbE, ME
    ifd = ifd_parse(rom)
    info["ifd"] = ifd
    info["me"] = None
    if ifd:
        for r in ifd["regions"]:
            d = rom[r["base"]:r["limit"] + 1]
            r["sha256"] = sha256(d)
            r["trimmed_sha256"] = sha256(ff_trim(d))
            # i byte non vuoti, come li conta Tally.scan()
            r["used"] = len(d) - sum(m.end() - m.start() for m in re.finditer(rb"\xff{64,}", d))
            if r["fmap"] and r["fmap"] in areas and \
                    (areas[r["fmap"]].off, areas[r["fmap"]].size) != (r["base"], r["size"]):
                warn("regione %s del descrittore diversa da %s della FMAP" % (r["name"], r["fmap"]))
            if r["name"] == "Intel ME":
                info["me"] = me_parse(d)
        me = info["me"]
        v2 = me and me.get("kind") == "cse"
        v1 = me and me.get("kind") == "me"
        ifd["version"] = 2 if v2 else (1 if v1 else None)
        # HAP (IFD v2) o AltMeDisable (v1): dump_fpsba() di ifdtool
        if v2:
            ifd["me_disable"] = ("HAP", bool(ifd["pchstrp0"] & (1 << 16)))
        elif v1:
            ifd["me_disable"] = ("AltMeDisable", bool(ifd["pchstrp10"] & (1 << 7)))
        else:
            ifd["me_disable"] = None
        # accesso dell'host (FLMSTR1): i bit di scrittura delle regioni, 31:20
        # su IFD v2 e 31:24 su v1 (i valori che scrive unlock_descriptor())
        f1 = ifd["flmstr"][0]
        ifd["host_writes_all"] = ((f1 >> 20) == 0xfff) if v2 else (((f1 >> 24) == 0xff) if v1 else None)

    # vboot: GBB e i due VBLOCK
    info["gbb"] = gbb_parse(rom[areas["GBB"].off:areas["GBB"].end]) if "GBB" in areas else None
    info["vblocks"] = {}
    for n in ("VBLOCK_A", "VBLOCK_B"):
        if n in areas:
            info["vblocks"][n] = vblock_parse(rom[areas[n].off:areas[n].end])

    # provenienza dal repository: blob e riferimento dei primi byte
    info["provenance"] = {}
    info["intel_reference"] = None
    if repo:
        known = repo.get("blobs", {})
        cand = []
        if ifd:
            for r in ifd["regions"]:
                cand += [(r["name"], r["sha256"]), (r["name"], r["trimmed_sha256"])]
        for o in info["oproms"]:
            cand.append((o["name"], o["sha256"]))
        if info["mrc"]:
            cand.append(("mrc.bin", info["mrc"]["sha256"]))
        for what, h in cand:
            if h in known:
                info["provenance"].setdefault(what, known[h])
        size, ref = repo.get("intel_size"), repo.get("reference")
        if isinstance(size, int) and isinstance(ref, str) and size <= len(rom):
            rp = os.path.join(a.repo, ref)
            have = sha256(rom[:size])
            if ref.endswith(".sha256"):
                t = (read_text(rp) or "").split()
                ok = bool(t) and t[0] == have
            else:
                rd = read_file(rp) if os.path.isfile(rp) else b""
                ok = rd[:size] == rom[:size]
            info["intel_reference"] = {"size": size, "ref": ref, "ok": ok, "sha256": have}
            if not ok:
                warn("i primi %d byte (IFD, GbE, ME) non sono quelli di %s" % (size, ref))
        keys = {}
        for k, fn in (("root_key", "root_key.vbpubk"), ("recovery_key", "recovery_key.vbpubk"),
                      ("data_key", "firmware_data_key.vbpubk"), ("keyblock", "firmware.keyblock")):
            p = os.path.join(a.repo, "keys", "vboot", fn)
            if os.path.isfile(p):
                keys[k] = (os.path.join("keys", "vboot", fn), vbpubk_sha256(p),
                           sha256(read_file(p)))
        info["repo_keys"] = keys

    # l'apertura: ogni byte dell'immagine in una classe
    t = Tally(rom)
    ifd_regions = ifd["regions"] if ifd else []

    def ifd_kind(x):
        for r in ifd_regions:
            if r["name"] != "BIOS" and r["base"] <= x.off and x.end <= r["limit"] + 1:
                return r["name"]
        for name, fm in IFD_REGIONS:
            if fm and fm == x.name and name != "BIOS":
                return name
        return None

    pos = 0
    for x in leaves:
        if x.end <= pos:
            continue
        start = max(x.off, pos)
        if start > pos:
            t.scan(pos, start, "outside the flash map", DATA)
        if x.name in cbfs and start == x.off:
            cur = x.off
            for f in cbfs[x.name]:
                if f.hdr > cur:
                    t.scan(cur, f.hdr, "CBFS gaps", DATA)
                label, cls = cbfs_class(f)
                t.add(label, cls, f.end - f.hdr)
                cur = f.end
            if cur < x.end:
                t.scan(cur, x.end, "CBFS gaps", DATA)
        else:
            label, cls = area_class(x, ifd_kind(x))
            t.scan(start, x.end, label, cls)
        pos = x.end
    if pos < len(rom):
        t.scan(pos, len(rom), "outside the flash map", DATA)
    if t.covered != len(rom):
        warn("conteggio dell'apertura: %d byte contati su %d" % (t.covered, len(rom)))
    info["tally"] = t

    # i file della release accanto alla ROM
    info["release_files"] = []
    d = os.path.dirname(os.path.abspath(a.rom))
    n = os.path.basename(base)
    for p in sorted(glob.glob(os.path.join(glob.escape(d), glob.escape(n) + "*"))):
        fn = os.path.basename(p)
        if not os.path.isfile(p) or not re.fullmatch(
                re.escape(n) + r"(\.rom|-\w+-chip\.rom|\.cap|\.cab|\.config|-layout\.txt)", fn):
            continue
        data = rom if os.path.abspath(p) == os.path.abspath(a.rom) else read_file(p)
        info["release_files"].append((fn, len(data), sha256(data)))
    sums = read_text(os.path.join(d, "SHA256SUMS"))
    info["sums_file"] = None
    if sums is not None:
        listed = dict((m.group(2), m.group(1)) for m in
                      re.finditer(r"^([0-9a-f]{64})\s+\*?(\S+)$", sums, re.M))
        bad = [fn for fn, _, h in info["release_files"] if fn in listed and listed[fn] != h]
        for fn in bad:
            warn("%s: SHA-256 diverso da SHA256SUMS" % fn)
        info["sums_file"] = {"bad": bad, "listed": [fn for fn, _, _ in info["release_files"] if fn in listed]}
    return info


# --- i componenti -----------------------------------------------------------------

def short(c, n=12):
    return c[:n] if c else c


def gh(path, commit):
    return "https://github.com/%s/commit/%s" % (path, commit) if commit else "https://github.com/%s" % path


def components(info):
    """L'elenco dei componenti, per Markdown e CycloneDX."""
    pins, cfg, sub, pay = info["pins"], info["cfg"], info["submodules"], info["payload"]
    comps = []

    def add(**kw):
        kw.setdefault("props", [])
        comps.append(kw)
        return kw

    cbc = pins["coreboot_commit"]
    if not cbc:
        # senza layout e repository: il commit abbreviato del git describe
        m = re.search(r"-g([0-9a-f]{7,40})$", info["coreboot_version"] or "")
        cbc = m.group(1) if m else None
    patches = pins["coreboot_patches"]
    add(ref="coreboot", name="coreboot", type="firmware", open=True, supplier="coreboot project",
        version=info["coreboot_version"] or pins["coreboot_describe"],
        text="`%s`%s" % (info["coreboot_version"] or pins["coreboot_describe"] or "?",
                         " + %d ouroBIOS patches" % patches if patches is not None else ""),
        license=LIC["coreboot"], vcs="https://github.com/coreboot/coreboot", commit=cbc,
        url=gh("coreboot/coreboot", cbc),
        props=[("patches", patches), ("optional patches", ", ".join(info["layout"]["optional"]) or None),
               ("localversion", info["localversion"])])
    for key, name, repo, desc in (
            ("vboot", "vboot", "coreboot/vboot", "verified boot library"),
            ("libgfxinit", "libgfxinit", "coreboot/libgfxinit", "native Intel graphics init"),
            ("libhwbase", "libhwbase", "coreboot/libhwbase", "libgfxinit's hardware base library")):
        if key == "vboot" and cfg.get("CONFIG_VBOOT") != "y":
            continue
        if key != "vboot" and cfg.get("CONFIG_MAINBOARD_USE_LIBGFXINIT") != "y":
            continue
        c = sub.get(key)
        add(ref=key, name=name, type="library", open=True, version=short(c) if c else None,
            text=("`%s`" % short(c)) if c else "pinned by coreboot", license=LIC[key],
            vcs="https://github.com/" + repo, commit=c, desc=desc, supplier="coreboot project",
            url=gh(repo, c) if c else ("https://github.com/coreboot/coreboot/tree/%s/3rdparty" % cbc if cbc else None),
            label=None if c else "`3rdparty/%s` of coreboot" % key)
    if cfg.get("CONFIG_PAYLOAD_EDK2") == "y" or cfg.get("CONFIG_EDK2_TAG_OR_REV"):
        rev = cfg.get("CONFIG_EDK2_TAG_OR_REV") or info["layout"].get("edk2_rev")
        repo = cfg.get("CONFIG_EDK2_REPOSITORY", "")
        m = re.match(r"https://github\.com/([^/]+/[^/.]+)", repo)
        ep, lp = pins["edk2_patches"], pins["lvgl_patches"]
        add(ref="edk2", name="EDK II (UefiPayloadPkg)", type="firmware", open=True,
            version=rev, supplier=(m.group(1).split("/")[0] if m else None),
            text="%s `%s`%s" % (m.group(1) if m else repo, short(rev),
                                " + %d patches" % ep if ep is not None else ""),
            license=LIC["edk2"], vcs=repo or None, commit=rev,
            url=gh(m.group(1), rev) if m else repo, props=[("patches", ep)])
        # LvglPkg: un submodule di EDK2 (.gitmodules di mrchromebox/edk2);
        # i font del setup come li elenca il README (sezione License)
        if cfg.get("CONFIG_EDK2_USE_LVGL_RENDERER") == "y" or lp is not None:
            add(ref="lvglpkg", name="LvglPkg", type="library", open=True, version=None,
                text="the submodule of EDK II `%s`%s" % (short(rev), " + %d patches" % lp if lp is not None else ""),
                license=LIC["lvglpkg"], vcs="https://github.com/MrChromebox/LvglPkg", commit=None,
                url=("https://github.com/%s/tree/%s/LvglPkg" % (m.group(1), rev)) if m and rev else None,
                label="`LvglPkg` of EDK II" if m and rev else None, supplier="MrChromebox",
                desc="LVGL graphics of the setup menu, with the Montserrat (OFL-1.1) and Font Awesome Free "
                     "(CC-BY-4.0) fonts", props=[("patches", lp)])
    if cfg.get("CONFIG_EDK2_ENABLE_IPXE") == "y" or pay.get("ipxe"):
        c = pins["ipxe_commit"]
        v = pay.get("ipxe")
        if v and c:
            m = re.search(r"\(g([0-9a-f]+)\)", v)
            if m and not c.startswith(m.group(1)):
                warn("iPXE: la versione nel payload (%s) non e' del commit %s" % (v, c[:12]))
        add(ref="ipxe", name="iPXE", type="application", open=True, version=v or short(c),
            text=" ".join(x for x in ("`%s`" % v if v else None, "(`%s`)" % short(c) if c else None) if x)
            or "?",
            license=LIC["ipxe"], vcs="https://github.com/ipxe/ipxe", commit=c, url=gh("ipxe/ipxe", c),
            desc="network boot, EFI image %s" % cfg.get("CONFIG_IPXE_EFI_IMAGE", "?"),
            supplier="iPXE project")
    if cfg.get("CONFIG_EDK2_ENABLE_CSMWRAP") == "y" or pay.get("csmwrap"):
        # senza layout: i commit abbreviati che CSMWrap scrive nel binario
        c = pins["csmwrap_commit"]
        if not c and re.fullmatch(r"[0-9a-f]{7,40}", pay.get("csmwrap", "")):
            c = pay["csmwrap"]
        add(ref="csmwrap", name="CSMWrap", type="application", open=True,
            version=pay.get("csmwrap") or short(c, 7),
            text="`%s`" % (pay.get("csmwrap") or short(c, 7) or "?"),
            license=LIC["csmwrap"], vcs="https://github.com/CSMWrap/CSMWrap", commit=c,
            url=gh("CSMWrap/CSMWrap", c), desc="legacy BIOS boot", supplier="CSMWrap project")
        s = pins["seabios_commit"]
        sv = pay.get("seabios")
        if not s and sv:
            s = sv.split("-")[0]
        add(ref="seabios", name="SeaBIOS", type="firmware", open=True,
            version=sv or short(s, 7), text="`%s`" % (sv or short(s, 7) or "?"),
            license=LIC["seabios"], vcs="https://github.com/CSMWrap/seabios-csmwrap", commit=s,
            url=gh("CSMWrap/seabios-csmwrap", s), desc="the CSM inside CSMWrap", supplier="SeaBIOS project")

    # i binari
    ifd = info["ifd"]
    prov = info["provenance"]
    if ifd:
        for r in ifd["regions"]:
            if r["name"] == "BIOS":
                continue
            where = "IFD region `0x%06x-0x%06x`" % (r["base"], r["limit"])
            if r["name"] == "Flash Descriptor":
                notes = []
                if ifd.get("version"):
                    notes.append("IFD v%d" % ifd["version"])
                if ifd.get("host_writes_all") is not None:
                    notes.append("host can write every region: %s" % ("yes" if ifd["host_writes_all"] else "no"))
                if ifd.get("me_disable"):
                    notes.append("%s %s" % (ifd["me_disable"][0], "set" if ifd["me_disable"][1] else "not set"))
                add(ref="ifd", name="Intel flash descriptor", type="data", open=False, version=None,
                    text=", ".join(notes) or "-", where=where, size=r["size"], sha256=r["sha256"],
                    license=LIC["intel"], supplier="Intel Corporation", source=prov.get(r["name"]),
                    props=[("FLMSTR1", "0x%08x" % ifd["flmstr"][0]), ("FLMSTR2", "0x%08x" % ifd["flmstr"][1]),
                           ("FLMSTR3", "0x%08x" % ifd["flmstr"][2])])
            elif r["name"] == "GbE":
                add(ref="gbe", name="Intel GbE NVM", type="data", open=False, version=None,
                    text="MAC address of the machine it comes from (not printed)", where=where,
                    size=r["size"], sha256=r["sha256"], license=LIC["intel"], supplier="Intel Corporation",
                    source=prov.get(r["name"]))
            elif r["name"] == "Intel ME":
                me = info["me"] or {}
                fam = "Intel CSME" if me.get("kind") == "cse" else "Intel ME"
                v = me.get("version")
                txt = "`%s`" % v if v else "not found"
                if me.get("pmc"):
                    txt += " (PMC `%s`)" % me["pmc"]
                if me.get("date"):
                    txt += ", FTPR dated %s" % me["date"]
                if cfg.get("CONFIG_USE_ME_CLEANER") == "y":
                    txt += ", cut by me_cleaner `%s`" % cfg.get("CONFIG_ME_CLEANER_ARGS", "")
                txt += ", %s of the %s region not erased" % (human(r["used"]), human(r["size"]))
                add(ref="me", name=fam + " firmware", type="firmware", open=False, version=v, text=txt,
                    where=where, size=r["size"], sha256=r["sha256"], license=LIC["intel"],
                    supplier="Intel Corporation", source=prov.get(r["name"]),
                    props=[("PMC", me.get("pmc")), ("FTPR date", me.get("date")),
                           ("bytes not erased", r["used"]), ("sha256 without trailing 0xff", r["trimmed_sha256"])])
            else:
                add(ref="ifd-%d" % r["index"], name="IFD region " + r["name"], type="data", open=False,
                    version=None, text="-", where=where, size=r["size"], sha256=r["sha256"],
                    license=LIC["intel"], supplier=None, source=prov.get(r["name"]))
    for f in info["fsp"]:
        h = f["hdr"] or {}
        comp = h.get("component") or f["name"]
        txt = "`%s`" % h["version"] if h else "no FSP_INFO_HEADER"
        if h:
            # l'id tra apici inversi: GitHub prende $CFLFSP$ per una formula
            txt += " (`%s`, %s, FSP %s)" % (h["image_id"], h["build_type"], h["spec"])
        where = ", ".join(f["regions"]) + ": `%s`" % f["name"]
        if f["split"] and h:
            where += " (rebased to `0x%08x`)" % h["image_base"]
        ref = f["name"].replace(".bin", "") + ("-" + "-".join(f["regions"]) if f["split"] else "")
        add(ref=ref, name="Intel " + comp, type="firmware", open=False, version=h.get("version"), text=txt,
            where=where, size=f["size"], sha256=f["sha256"],
            license=LIC["fsp"], supplier="Intel Corporation",
            vcs="https://github.com/coreboot/fsp", commit=info["submodules"].get("fsp"),
            props=[("decimal revision", h.get("decimal")), ("UPD", h.get("upd")),
                   ("image base", "0x%08x" % h["image_base"] if h else None),
                   ("FSP_FD_PATH", info["cfg"].get("CONFIG_FSP_FD_PATH")),
                   ("CBFS compression", f["comp"]), ("CBFS size", f["stored"])])
    mc = info["microcode"]
    if mc:
        cpus = ", ".join("%05x" % u["cpuids"][0][0] for u in mc["updates"])
        add(ref="microcode", name="Intel CPU microcode", type="firmware", open=False,
            version=", ".join("%05x:0x%x" % (u["cpuids"][0][0], u["revision"]) for u in mc["updates"]),
            text="%d updates (CPUID %s)" % (len(mc["updates"]), cpus),
            where=", ".join(mc["regions"]) + ": `cpu_microcode_blob.bin`", size=mc["size"],
            sha256=mc["sha256"], license=LIC["microcode"], supplier="Intel Corporation",
            vcs="https://github.com/coreboot/intel-microcode", commit=info["submodules"].get("intel-microcode"))
    v = info["vbt"]
    if v:
        h = v["hdr"] or {}
        txt = ("%s, VBT %s, BDB %s" % (h["signature"], h["version"], h["bdb"])) if h else "no $VBT header"
        add(ref="vbt", name="Intel Video BIOS Table", type="data", open=False,
            version=str(h["bdb"]) if h and h.get("bdb") is not None else None, text=txt,
            where=", ".join(v["regions"]) + ": `vbt.bin`", size=v["size"], sha256=v["sha256"],
            license=LIC["vbt"], supplier="Intel Corporation",
            props=[("source", info["cfg"].get("CONFIG_INTEL_GMA_VBT_FILE"))])
    if info["mrc"]:
        m = info["mrc"]
        add(ref="mrc", name="Intel memory reference code (mrc.bin)", type="firmware", open=False,
            version=None, text="version not in the binary (coreboot reads it from MCHBAR at boot)",
            where=", ".join(m["regions"]) + ": `mrc.bin`", size=m["size"], sha256=m["sha256"],
            license=LIC["mrc"], supplier="Intel Corporation", source=prov.get("mrc.bin"))
    for o in info["oproms"]:
        h = o["hdr"] or {}
        ids = "%04x:%04x" % (h["vendor"], h["device"]) if h.get("vendor") is not None else o["name"]
        add(ref="oprom-" + o["name"], name="Option ROM " + ids, type="firmware", open=False,
            version=h.get("version"), text="`%s`" % h["version"] if h.get("version") else "-",
            where=", ".join(o["regions"]) + ": `%s`" % o["name"], size=o["size"], sha256=o["sha256"],
            license=("name", "proprietary (NVIDIA)") if h.get("vendor") == 0x10de else LIC["vbios"],
            supplier="NVIDIA Corporation" if h.get("vendor") == 0x10de else None,
            source=prov.get(o["name"]))
    return comps


# --- Markdown ----------------------------------------------------------------

def md_link(text, url):
    return "[%s](%s)" % (text, url) if url else text


def openness_rows(info):
    t = info["tally"]
    total = info["size"]
    code = t.total(OPEN) + t.total(CLOSED)
    summary = []
    for cls in (OPEN, CLOSED, DATA, EMPTY):
        n = t.total(cls)
        share = "%.1f%%" % (100.0 * n / code) if cls in (OPEN, CLOSED) and code else "-"
        summary.append((CLASS_TEXT[cls], n, "%.1f%%" % (100.0 * n / total), share))
    order = {OPEN: 0, CLOSED: 1, DATA: 2, EMPTY: 3}
    rows = sorted(t.rows.items(), key=lambda kv: (order[kv[0][1]], -kv[1]))
    return summary, rows, code


def render_markdown(info, comps, notes=False):
    out = []
    w = out.append
    ts = info["build_time"].strftime("%Y-%m-%d %H:%M:%S UTC") if info["build_time"] else "?"
    opens = [c for c in comps if c["open"]]
    closed = [c for c in comps if not c["open"]]
    summary, rows, code = openness_rows(info)
    t = info["tally"]
    pct = 100.0 * t.total(OPEN) / code if code else 0.0

    if notes:
        w("### Software bill of materials")
        w("")
        w("| Component | Version | License |")
        w("|---|---|---|")
        seen = set()
        for c in opens + closed:
            # le due copie di FSP-M (una per slot) in una riga
            if (c["name"], c["text"]) in seen:
                continue
            seen.add((c["name"], c["text"]))
            w("| %s | %s | %s |" % (md_link(c["name"], c.get("url")), c["text"], c["license"][1]))
        w("")
        w("Code in the image: **%.1f%% open source** (%s), %.1f%% closed binaries (%s); "
          "%s of data and %s empty (`tools/sbom.py`)."
          % (pct, human(t.total(OPEN)), 100 - pct if code else 0.0, human(t.total(CLOSED)),
             human(t.total(DATA)), human(t.total(EMPTY))))
        w("")
        return "\n".join(out) + "\n"

    w("# SBOM: %s" % info["name"])
    w("")
    src = ["the image itself"]
    if info.get("config_source") and info["config_source"] != "the config file in CBFS":
        src.append("`%s`" % info["config_source"])
    if info.get("layout_source"):
        src.append("`%s`" % info["layout_source"])
    if info["repo"]:
        src.append("the ouroBIOS repository%s" % (" at `%s`" % info["repo"]["describe"]
                                                  if info["repo"].get("describe") else ""))
    if info["submodules"]:
        src.append("coreboot's submodule pins")
    w("Software bill of materials of `%s.rom`, generated by `tools/sbom.py` from %s."
      % (info["name"], ", ".join(src[:-1]) + " and " + src[-1] if len(src) > 1 else src[0]))
    w("")
    w("| | |")
    w("|---|---|")
    w("| Machine | %s %s |" % (info["vendor"], info["part"]))
    w("| Firmware version | `%s` |" % info["localversion"])
    w("| coreboot version | `%s` |" % info["coreboot_version"])
    w("| Built | %s |" % ts)
    w("| Image | %d bytes (%s), SHA-256 `%s` |" % (info["size"], human(info["size"]), info["sha256"]))
    ifd = info["ifd"]
    if ifd:
        for r in ifd["regions"]:
            if r["name"] == "BIOS":
                w("| BIOS region | `0x%06x-0x%06x`, SHA-256 `%s` (what `flashrom --ifd -i bios` writes) |"
                  % (r["base"], r["limit"], r["sha256"]))
    ir = info["intel_reference"]
    if ir:
        w("| IFD, GbE, ME | first %s, SHA-256 `%s`: %s `%s` |"
          % (human(ir["size"]), ir["sha256"], "same as" if ir["ok"] else "**differs from**", ir["ref"]))
    for n, v in info["fwid"].items():
        w("| %s | `%s` |" % (n, v))
    if info["pins"]["toolchain"]:
        w("| Toolchain | %s |" % info["pins"]["toolchain"])
    w("")

    w("## Open-source components")
    w("")
    w("| Component | Version | License | Source |")
    w("|---|---|---|---|")
    for c in opens:
        src = md_link(c.get("label") or ("`%s`" % short(c["commit"]) if c.get("commit") else c.get("vcs") or "-"),
                      c.get("url"))
        w("| %s | %s | %s | %s |" % (c["name"] + (" (%s)" % c["desc"] if c.get("desc") else ""), c["text"],
                                     c["license"][1], src))
    w("")
    w("## Binary components")
    w("")
    w("| Component | Version | Where | Size | SHA-256 | License |")
    w("|---|---|---|---|---|---|")
    for c in closed:
        where = c["where"] + ("; from `%s`" % c["source"] if c.get("source") else "")
        w("| %s | %s | %s | %d | `%s` | %s |" % (c["name"], c["text"], where, c["size"], c["sha256"],
                                                 c["license"][1]))
    w("")
    packed = sorted({f["name"] for f in info["fsp"] if f["comp"] != "none"} |
                    ({"vbt.bin"} if info["vbt"] and info["vbt"]["comp"] != "none" else set()))
    note = "SHA-256 of each binary as the firmware uses it"
    if packed:
        note += ", decompressed where CBFS stores it compressed (%s)" % ", ".join("`%s`" % n for n in packed)
    if any(f["split"] for f in info["fsp"]):
        note += "; FSP-M runs from the flash and the build rebases it for the address of each slot, " \
                "so the two copies differ"
    w(note + "; the IFD regions whole, with their 0xFF padding.")
    w("")

    me = info["me"]
    if me and me.get("partitions"):
        w("### Intel ME partitions")
        w("")
        w("| Partition | Version | Date |")
        w("|---|---|---|")
        for p in me["partitions"]:
            if p.get("version") or p["name"] in ("FTPR", "NFTP", "PMCP"):
                w("| %s | %s | %s |" % (p["name"], p.get("version") or "-", p.get("date") or "-"))
        w("")
    if info["fsp"]:
        w("### Intel FSP")
        w("")
        w("| | " + " | ".join(f["name"] + (" (%s)" % ", ".join(f["regions"]) if f["split"] else "")
                              for f in info["fsp"]) + " |")
        w("|---|" + "---|" * len(info["fsp"]))
        rows_fsp = (("Version (Intel)", "version"), ("Revision (decimal)", "decimal"), ("Image ID", "image_id"),
                    ("FSP spec", "spec"), ("Build", "build_type"), ("UPD", "upd"))
        for title, k in rows_fsp:
            w("| %s | %s |" % (title, " | ".join(str((f["hdr"] or {}).get(k, "-")) for f in info["fsp"])))
        bases = ["0x%08x" % f["hdr"]["image_base"] if f["hdr"] else "-" for f in info["fsp"]]
        w("| Image base | %s |" % " | ".join(bases))
        w("| In CBFS | %s |" % " | ".join("%d bytes, %s" % (f["stored"], f["comp"]) for f in info["fsp"]))
        w("")
    mc = info["microcode"]
    if mc:
        w("### CPU microcode")
        w("")
        w("| CPUID | Platform IDs | Revision | Date | Size | SHA-256 |")
        w("|---|---|---|---|---|---|")
        for u in mc["updates"]:
            bad = "" if u["checksum_ok"] else " (bad checksum)"
            for sig, pf in u["cpuids"]:
                w("| %05x | 0x%02x | 0x%x | %s | %d | `%s`%s |"
                  % (sig, pf, u["revision"], u["date"], u["size"], u["sha256"], bad))
        w("")
    gbb, vbs = info["gbb"], info["vblocks"]
    if gbb or vbs:
        keys = info.get("repo_keys", {})

        def keymatch(k, which):
            if not k or which not in keys:
                return ""
            path, ksha, _ = keys[which]
            return ", same key as `%s`" % path if ksha == k["sha256"] else ", **not** the key of `%s`" % path

        w("### vboot")
        w("")
        w("| | |")
        w("|---|---|")
        if gbb:
            hwid = ", HWID `%s`" % gbb["hwid"] if gbb["hwid"] else ""
            w("| GBB | version %s, flags 0x%08x%s |" % (gbb["version"], gbb["flags"], hwid))
            for k, title in (("root_key", "Root key"), ("recovery_key", "Recovery key")):
                if gbb[k]:
                    w("| %s | algorithm %d, version %d, SHA-256 of the key data `%s`%s |"
                      % (title, gbb[k]["algorithm"], gbb[k]["version"], gbb[k]["sha256"], keymatch(gbb[k], k)))
        for n, vb in vbs.items():
            if not vb:
                w("| %s | no keyblock |" % n)
                continue
            dk = vb["data_key"]
            kb = ""
            if "keyblock" in keys and vb["keyblock_sha256"]:
                kb = ", keyblock %s `%s`" % ("same as" if keys["keyblock"][2] == vb["keyblock_sha256"]
                                             else "**differs from**", keys["keyblock"][0])
            w("| %s | keyblock flags 0x%x, data key version %s%s%s; firmware version %s, signature over %s "
              "bytes of the slot |" % (n, vb["keyblock_flags"], dk["version"] if dk else "?",
                                       keymatch(dk, "data_key"), kb, vb["firmware_version"], vb["body_size"]))
        w("")
    if ifd:
        w("### Flash descriptor regions")
        w("")
        w("| Region | Range | Size | SHA-256 | Source |")
        w("|---|---|---|---|---|")
        for r in ifd["regions"]:
            src = "`%s`" % info["provenance"][r["name"]] if r["name"] in info["provenance"] else "-"
            w("| %s | `0x%06x-0x%06x` | %s | `%s` | %s |"
              % (r["name"], r["base"], r["limit"], human(r["size"]), r["sha256"], src))
        w("")

    w("## Openness")
    w("")
    w("Every byte of the %s image in one class: open-source code (coreboot stages and ACPI tables, the payload "
      "with EDK II, iPXE, CSMWrap and SeaBIOS), closed binaries (Intel FSP, ME, microcode, VBT, flash "
      "descriptor and GbE, other vendors' blobs), data (flash map, vboot keys and signatures, coreboot's "
      "metadata, runtime regions) and empty (erased flash, runs of at least 64 bytes of 0xFF outside CBFS, "
      "and free CBFS space). Open source is **%.1f%%** of the code." % (human(info["size"]), pct))
    w("")
    w("| Class | Bytes | Share of the image | Share of the code |")
    w("|---|---|---|---|")
    for title, n, share, code_share in summary:
        w("| %s | %d (%s) | %s | %s |" % (title, n, human(n), share, code_share))
    w("")
    w("| Component | Class | Bytes |")
    w("|---|---|---|")
    for (label, cls), n in rows:
        w("| %s | %s | %d (%s) |" % (label, cls, n, human(n)))
    w("")

    if info["release_files"]:
        w("## Release files")
        w("")
        w("| File | Size | SHA-256 |")
        w("|---|---|---|")
        for fn, size, h in info["release_files"]:
            w("| `%s` | %d | `%s` |" % (fn, size, h))
        w("")
        sf = info["sums_file"]
        if sf is not None:
            if sf["bad"]:
                w("**Not** as in `SHA256SUMS`: %s." % ", ".join("`%s`" % fn for fn in sf["bad"]))
            else:
                w("%d of these files are in `SHA256SUMS`, all with these checksums." % len(sf["listed"]))
            w("")
        w("```sh")
        w("sha256sum -c SHA256SUMS --ignore-missing")
        w("```")
        w("")
    return "\n".join(out) + "\n"


# --- CycloneDX -----------------------------------------------------------------

def cdx_license(lic):
    kind, value = lic
    return [{"license": {"id": value}}] if kind == "id" else [{"license": {"name": value}}]


def purl(vcs, commit):
    m = re.match(r"https://github\.com/([^/]+)/([^/.]+)", vcs or "")
    if not m or not commit:
        return None
    return "pkg:github/%s/%s@%s" % (m.group(1).lower(), m.group(2).lower(), commit)


def render_cyclonedx(info, comps):
    ts = info["build_time"] or datetime.datetime.now(datetime.timezone.utc)
    out_comps = []
    for c in comps:
        o = {"type": c["type"], "bom-ref": c["ref"], "name": c["name"]}
        if c.get("supplier"):
            o["supplier"] = {"name": c["supplier"]}
        if c.get("version"):
            o["version"] = str(c["version"])
        desc = [c["desc"]] if c.get("desc") else []
        if not c["open"]:
            desc.append(re.sub(r"`", "", c["text"]))
            desc.append("in " + re.sub(r"`", "", c["where"]))
        if desc:
            o["description"] = "; ".join(desc)
        if c.get("sha256"):
            o["hashes"] = [{"alg": "SHA-256", "content": c["sha256"]}]
        o["licenses"] = cdx_license(c["license"])
        p = purl(c.get("vcs"), c.get("commit"))
        if p:
            o["purl"] = p
        refs = []
        if c.get("vcs"):
            refs.append({"type": "vcs", "url": c["vcs"]})
        if c.get("url") and c.get("url") != c.get("vcs"):
            refs.append({"type": "website", "url": c["url"]})
        if refs:
            o["externalReferences"] = refs
        props = [("ourobios:open-source", "true" if c["open"] else "false")]
        if c.get("commit"):
            props.append(("ourobios:commit", c["commit"]))
        if c.get("size") is not None:
            props.append(("ourobios:size", c["size"]))
        if c.get("source"):
            props.append(("ourobios:blob", c["source"]))
        props += [("ourobios:" + k.replace(" ", "-").lower(), v) for k, v in c["props"] if v not in (None, "")]
        o["properties"] = [{"name": k, "value": str(v)} for k, v in props]
        out_comps.append(o)
    t = info["tally"]
    props = [("ourobios:coreboot-version", info["coreboot_version"]),
             ("ourobios:localversion", info["localversion"])]
    for cls in (OPEN, CLOSED, DATA, EMPTY):
        props.append(("ourobios:openness:%s-bytes" % cls, t.total(cls)))
    for n, v in info["fwid"].items():
        props.append(("ourobios:fwid:" + n, v))
    if info["ifd"]:
        for r in info["ifd"]["regions"]:
            if r["name"] == "BIOS":
                props.append(("ourobios:bios-region-sha256", r["sha256"]))
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        # lo stesso numero per la stessa immagine: la build e' riproducibile
        "serialNumber": "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, REPO_URL + "#" + info["sha256"]),
        "version": 1,
        "metadata": {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": [{"type": "application", "name": "sbom.py", "group": "ouroBIOS",
                                      "externalReferences": [{"type": "vcs", "url": REPO_URL}]}]},
            "component": {
                "type": "firmware", "bom-ref": "ourobios", "name": "ouroBIOS",
                "version": info["localversion"] or info["coreboot_version"] or "unknown",
                "description": "coreboot and EDK II system firmware for the %s %s (%s.rom)"
                               % (info["vendor"], info["part"], info["name"]),
                "hashes": [{"alg": "SHA-256", "content": info["sha256"]}],
                "licenses": cdx_license(LIC["coreboot"]),
                "externalReferences": [{"type": "vcs", "url": REPO_URL}],
                "properties": [{"name": k, "value": str(v)} for k, v in props if v not in (None, "")],
            },
        },
        "components": out_comps,
        "dependencies": [{"ref": "ourobios", "dependsOn": [c["ref"] for c in comps]}],
    }
    return json.dumps(doc, indent=2) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="la distinta dei componenti (SBOM) di una ROM di ouroBIOS: versioni, licenze, "
                    "SHA-256 dei binari e quanto dell'immagine e' aperto")
    ap.add_argument("rom", help="l'immagine intera (.rom di dist/ o di una release)")
    ap.add_argument("--config", help="il .config della build (default: ROM.config accanto alla ROM, "
                                     "se no il config in CBFS)")
    ap.add_argument("--layout", help="il -layout.txt della build (default: quello accanto alla ROM)")
    ap.add_argument("--repo", help="il clone di ouroBIOS: patch, pin, provenienza dei blob, chiavi di vboot")
    ap.add_argument("--coreboot", help="un clone git di coreboot con il commit pinnato: i commit dei submodule")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--cyclonedx", action="store_true", help="CycloneDX 1.5 in JSON invece del Markdown")
    fmt.add_argument("--notes", action="store_true", help="solo la sezione breve per le note della release")
    ap.add_argument("-o", "--output", help="il file da scrivere (default: stdout)")
    a = ap.parse_args()

    if a.repo and not os.path.isdir(a.repo):
        die("%s: non e' una cartella" % a.repo)
    if a.coreboot and not os.path.isdir(a.coreboot):
        die("%s: non e' una cartella" % a.coreboot)
    info = analyze(a)
    comps = components(info)
    text = render_cyclonedx(info, comps) if a.cyclonedx else render_markdown(info, comps, a.notes)
    if a.output:
        try:
            with open(a.output, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            die("%s: %s" % (a.output, e.strerror))
        print("sbom.py: scritto %s" % a.output, file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
