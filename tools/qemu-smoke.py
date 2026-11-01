#!/usr/bin/env python3
# qemu-smoke.py - la prova di fumo del payload: una ROM coreboot per QEMU
# q35 con l'EDK2 del W541 (tools/build.sh smoke) avviata in QEMU, per vedere
# prima di una release che il payload parte, disegna e risponde ai tasti.
#
#   python3 tools/qemu-smoke.py [--out DIR] [--timeout S] [--setup-only]
#                               [--vga-mb N] [--size WxH] [--reloc-test EFI]
#                               [--sb-test EFI --esrt GUID:VERSIONE:LSV [--sb-only]]
#                               [--tpm EFI [--tpm2]] ROM
#
# Controlla, in ordine:
#   1. coreboot arriva al payload ("Jumping to boot code" sulla seriale);
#   2. lo schermo non e' piu' di un colore solo (il payload disegna);
#   3. con Esc, premuto durante l'avvio, il payload apre il setup, e lo
#      schermo si ferma su una pagina grafica: non la Shell UEFI, dove il
#      payload arriva senza dischi se Esc non apre il setup;
#   4. Giu' e Invio aprono un'altra pagina, Esc torna indietro: il setup
#      risponde ai tasti;
#   5. QEMU e' ancora vivo: nessun riavvio, nessun triple fault (-no-reboot);
#   6. le variabili UEFI in SMMSTORE: senza dischi il payload arriva alla
#      Shell, dove setvar scrive una variabile di prova; spenta la macchina,
#      la variabile deve essere nello store del flash, con i suoi dati. Al
#      secondo avvio la Shell la riscrive con un altro valore: il driver deve
#      trovare la copia di prima nel flash e cancellarla, e ne deve restare
#      una sola valida;
#   7. iPXE: la voce "iPXE Network Boot" (il suo numero Boot#### letto dallo
#      store) messa in BootNext dalla Shell, poi un avvio con una scheda
#      e1000 sulla rete utente di QEMU, che fa da DHCP e TFTP: iPXE deve
#      prendere l'indirizzo, scaricare lo script del DHCP (opzione 67) ed
#      eseguirlo; lo script ne chiama un altro, e la richiesta TFTP di quel
#      secondo file nel pcap del traffico (filter-dump) e' la prova;
#   8. CSMWrap: la voce "CSMWrap Legacy Boot" in BootNext, poi un avvio con
#      due CPU (CSMWrap ne tiene una per i suoi servizi BIOS) e un disco
#      SATA il cui MBR scrive una riga sulla porta seriale: il BIOS legacy
#      deve avviarlo (INT 13h di SeaBIOS, con il suo driver AHCI);
#   9. con --reloc-test, i servizi runtime spostati come li sposta boot.efi
#      di macOS senza AvoidRuntimeDefrag di OpenCore: su una copia nuova
#      della ROM, con un'ESP dalla prima accensione, il payload avvia
#      tools/efi/rt-reloc-test.c (\EFI\BOOT\BOOTX64.EFI), che dopo
#      ExitBootServices() e SetVirtualAddressMap() copia altrove il codice e
#      i dati dei servizi runtime, riempie di 0xCC le copie di prima e li
#      chiama solo dalle pagine virtuali. Ogni servizio deve rispondere,
#      nessun triple fault (un indirizzo fisico che il payload usa ancora a
#      runtime), nessun byte scritto nelle copie di prima, ResetSystem() deve
#      riavviare; le due variabili scritte devono essere nello store del
#      flash con i loro dati (SMM, che scrive il flash, non deve leggere le
#      copie di prima). v1.3.10-rc15 non passa: SetVariable() falliva
#      (EFI_DEVICE_ERROR), con gli argomenti di SMMSTORE dati dei servizi
#      runtime;
#  10. con --sb-test, l'ESRT e Secure Boot: su un'altra copia nuova della
#      ROM, con un'ESP dalla prima accensione, il payload avvia due volte
#      tools/efi/secure-boot-test.c, firmato con un certificato figlio di una
#      CA di prova. Al primo avvio (la variante fresca: EnrollDefaultKeys ha
#      messo le chiavi Microsoft, Secure Boot spento) stampa l'ESRT, carica
#      le immagini incorporate (tutte accettate), mette la CA in db in custom
#      mode come fa EnrollDefaultKeys, scrive SecureBootEnable=1 e riavvia.
#      Al secondo avvio parte solo se il payload ha verificato la sua firma
#      (la catena foglia -> CA, con l'OpenSSL di CryptoDxe): poi LoadImage()
#      deve accettare lo shim firmato da Microsoft (se c'era da incorporare)
#      e rifiutare l'immagine firmata da un certificato che non e' in db e
#      quella senza firma. L'ESRT, a ogni avvio, deve avere la sola voce
#      della variante (--esrt): e' il GUID che il payload legge dalla tabella
#      di coreboot (patches/edk2/0033). --sb-only fa questo passo soltanto:
#      tools/build.sh smoke lo usa per la variante il cui payload e' gia'
#      stato provato con l'altra (lo stesso, byte per byte);
#  11. con --tpm, il TPM 1.2 di swtpm (la ROM con CONFIG_TPM1 e
#      CONFIG_TPM_MEASURED_BOOT, come il W541): su un'altra copia nuova della
#      ROM, con un'ESP, il payload avvia tools/efi/tpm-pcr-test.c, che legge
#      dal TPM i PCR 0-7; poi la RAM via QMP e il log TCPA di coreboot, dove
#      il payload scrive le sue misure dopo quelle di coreboot. Il log deve
#      dare, rifatto evento per evento, i PCR letti dal TPM; coreboot deve
#      aver misurato in PCR 2 l'area FMAP, il bootblock, romstage, ramstage
#      e il payload, ogni file con lo SHA-1 dei suoi byte nella ROM (con il
#      log di 4 KiB di coreboot gli eventi del payload non ci stavano: la
#      patch 0200). Con --tpm2 il TPM 2.0 di swtpm con i banchi SHA-1 e
#      SHA-256, come il M920x (la ROM con CONFIG_TPM2 e
#      CONFIG_TPM_MEASURED_BOOT_SHA1_BANK): il log e' quello crypto agile di
#      EFI_TCG2_PROTOCOL, dove Tcg2Dxe mette le misure di coreboot
#      (patches/edk2/0042), ognuna con i due digest (patch 0201); i due
#      banchi rifatti devono dare i PCR del TPM. Ogni PCR 0-7 deve avere il
#      separatore, e con il TPM 1.2 in PCR 7 ci devono essere
#      le misure di SecureBoot, PK, KEK, db e dbx che il driver delle
#      variabili fa quando EnrollDefaultKeys le scrive al primo avvio, con
#      il digest SHA-1 dei dati di ogni evento. Con un TPM 1.2 quelle
#      misure si fanno solo allora: v1.3.10-rc19 le perdeva, perche' con
#      l'OpenSSL condiviso TcgDxe partiva dopo le chiavi (patches/edk2/0035).
# Le schermate di ogni passo vanno in DIR (PNG), con la console seriale.
# Un'eccezione del payload sulla seriale ("X64 Exception Type") ferma la
# prova al passo in cui arriva, con la riga dell'eccezione e l'immagine.
#
# --setup-only fa i passi 1-5 soltanto, --vga-mb da' alla VGA di QEMU piu'
# memoria (16 MiB di default: un framebuffer di 2880x1620 ne vuole 18) e
# --size controlla che il setup sia disegnato a quella risoluzione:
# tools/build.sh smoke prova cosi' anche il setup alla risoluzione del
# pannello 3K del W541 (gfx_fb_limit), dove v1.3.10-rc3 si fermava su un page
# fault di LVGL (patches/lvglpkg/0016).
#
# Il W541 non si emula: qui girano il payload (UEFIPayloadPkg, LvglPkg, le
# patch di patches/edk2) e il codice comune di coreboot, non quello della
# board. Solo la libreria standard di Python, qemu-system-x86_64 e, per il
# passo 9, mtools (l'ESP).
#
# QEMU va in TCG; OUROBIOS_QEMU_ACCEL=kvm lo mette in KVM, con la stessa CPU
# Haswell-noTSX (QEMU toglie quello che l'host non ha e lo scrive nel suo
# log). Sui runner di GitHub (virtualizzazione annidata) KVM non conviene:
# ogni SMI di SMMSTORE costa un'uscita all'hypervisor, la prova
# dell'aggiornamento, che scrive il flash a blocchi via SMM, ci mette di
# piu' che in TCG, e il setup a 2880x1620 non ha passato la prova.
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid


def accel():
    return "kvm" if os.environ.get("OUROBIOS_QEMU_ACCEL") == "kvm" else "tcg"


ACCEL = accel()


class Fail(Exception):
    pass


class Qmp:
    def __init__(self, path, timeout=30):
        end = time.monotonic() + timeout
        while True:
            try:
                self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.s.connect(path)
                break
            except OSError:
                self.s.close()
                if time.monotonic() > end:
                    raise Fail("QMP: niente socket %s" % path)
                time.sleep(0.2)
        # una risposta che non arriva (QEMU fermo) non blocca la prova oltre
        # il suo timeout: socket.timeout e' un OSError, che halt() tratta
        # come QEMU che non risponde
        self.s.settimeout(timeout)
        self.f = self.s.makefile("rwb")
        self.read()                     # il saluto
        self.cmd("qmp_capabilities")

    def read(self):
        line = self.f.readline()
        if not line:
            raise Fail("QMP: QEMU ha chiuso la connessione")
        return json.loads(line)

    def cmd(self, name, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        self.f.write(json.dumps(msg).encode() + b"\n")
        self.f.flush()
        while True:
            r = self.read()
            if "return" in r:
                return r["return"]
            if "error" in r:
                raise Fail("QMP %s: %s" % (name, r["error"].get("desc")))
            # gli eventi (RESET, SHUTDOWN...) si saltano qui: li vede alive()


def ppm(path):
    """(larghezza, altezza, byte RGB) di uno screendump PPM (P6)."""
    with open(path, "rb") as f:
        data = f.read()
    fields, pos = [], 0
    # un file vuoto o tagliato (QEMU ucciso a meta' screendump, disco pieno)
    # finisce qui, non in un ciclo senza fine
    while len(fields) < 4:
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.find(b"\n", pos)
            if pos < 0:
                raise Fail("screendump: PPM tagliato")
            continue
        end = pos
        while end < len(data) and not data[end:end + 1].isspace():
            end += 1
        if end == pos or end >= len(data):
            raise Fail("screendump: PPM tagliato")
        fields.append(data[pos:end])
        pos = end
    if fields[0] != b"P6" or fields[3] != b"255":
        raise Fail("screendump: non e' un PPM P6")
    try:
        w, h = int(fields[1]), int(fields[2])
    except ValueError:
        raise Fail("screendump: PPM senza dimensioni") from None
    if len(data) < pos + 1 + 3 * w * h:
        raise Fail("screendump: PPM tagliato (%d byte per %dx%d)" % (len(data), w, h))
    return w, h, data[pos + 1:pos + 1 + 3 * w * h]


class Screen:
    """Una schermata, campionata: abbastanza per contare i colori e
    confrontarne due senza leggere ogni pixel di un 1920x1080."""

    def __init__(self, w, h, rgb, step=7):
        self.size = (w, h)
        self.px = [rgb[i:i + 3] for i in range(0, len(rgb) - 2, 3 * step)]

    def colors(self):
        return len(set(self.px))

    def diff(self, other):
        if other is None or other.size != self.size:
            return 1.0
        return sum(a != b for a, b in zip(self.px, other.px)) / max(1, len(self.px))


class Smoke:
    """Le macchine QEMU di una prova: una per fase, tutte sulla stessa copia
    della ROM, che il payload scrive (SMMSTORE)."""

    def __init__(self, rom, out, timeout, vga_mb=16):
        self.out, self.timeout, self.vga_mb = out, timeout, vga_mb
        self.tmp = tempfile.mkdtemp(prefix="qemu-smoke-")
        self.flash = os.path.join(self.tmp, "flash.rom")
        shutil.copyfile(rom, self.flash)
        self.sock = os.path.join(self.tmp, "qmp.sock")
        self.n = 0
        self.proc = self.qmp = self.log = None

    def boot(self, tag, extra=()):
        """Accende la macchina: extra sono altre opzioni di QEMU (dischi,
        traccia: tools/qemu-update.py). QEMU parte fermo (-S) e la CPU va
        solo dopo il saluto di QMP: un avvio che finisce subito, come un
        reset di vboot nel bootblock, non chiude QEMU prima del socket."""
        self.halt()
        self.serial = os.path.join(self.out, "serial-%s.log" % tag)
        cmd = ["qemu-system-x86_64", "-M", "q35,acpi=off", "-accel", ACCEL,
               "-cpu", "Haswell-noTSX,stepping=3",
               "-smp", "1", "-m", "2048", "-drive", "if=pflash,format=raw,file=" + self.flash,
               "-serial", "file:" + self.serial, "-qmp", "unix:%s,server=on,wait=off" % self.sock,
               "-display", "none", "-vga", "std", "-no-reboot", "-S"]
        if self.vga_mb != 16:
            cmd += ["-global", "VGA.vgamem_mb=%d" % self.vga_mb]
        cmd += list(extra)
        self.log = open(os.path.join(self.out, "qemu-%s.log" % tag), "w")
        self.proc = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT)
        self.qmp = Qmp(self.sock)
        self.qmp.cmd("cont")

    def cut(self):
        """Toglie la corrente: QEMU ucciso senza chiudere niente. Il flash
        emulato e' quello che il firmware ha scritto fin li' (QEMU scrive
        ogni byte nel file appena il firmware lo programma)."""
        if self.proc is None:
            return
        self.proc.kill()
        self.proc.wait()
        self.log.close()
        self.proc = None

    def halt(self):
        if self.proc is None:
            return
        # senza QMP (il socket non e' mai arrivato) resta kill()
        if self.proc.poll() is None and self.qmp is not None:
            try:
                self.qmp.cmd("quit")
            except (Fail, OSError):
                pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()
        self.proc = None

    def close(self):
        self.halt()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def type(self, text):
        """Scrive text sulla tastiera PS/2, maiuscole con Shift."""
        names = {" ": "spc", "-": "minus", "=": "equal", "\n": "ret", ".": "dot", "/": "slash"}
        for ch in text:
            self.alive()
            if ch.isalpha() and ch.isupper():
                keys = ["shift", ch.lower()]
            elif ch.isalnum():
                keys = [ch]
            else:
                keys = [names[ch]]
            self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in keys])
            time.sleep(0.08)

    def alive(self):
        if self.proc.poll() is not None:
            raise Fail("QEMU e' uscito (codice %s): un riavvio o un triple fault, con -no-reboot"
                       % self.proc.returncode)

    def serial_text(self):
        try:
            with open(self.serial, "rb") as f:
                return f.read().decode("utf-8", "replace")
        except OSError:
            return ""

    def shot(self, name=None):
        self.alive()
        p = os.path.join(self.tmp, "s.ppm")
        self.qmp.cmd("screendump", filename=p)
        s = Screen(*ppm(p))
        if name:
            self.n += 1
            png = os.path.join(self.out, "%02d-%s.png" % (self.n, name))
            try:
                self.qmp.cmd("screendump", filename=png, format="png")
            except Fail:
                shutil.copyfile(p, png[:-4] + ".ppm")   # QEMU prima della 7.1: niente PNG
        return s

    def key(self, *names):
        for k in names:
            self.alive()
            self.qmp.cmd("send-key", keys=[{"type": "qcode", "data": k}])
            time.sleep(0.15)

    def exception(self):
        """La riga di un'eccezione del payload sulla seriale, con l'immagine
        in cui e' avvenuta, o None."""
        text = self.serial_text()
        at = text.find("Exception Type")
        if at < 0:
            return None
        lines = text[text.rfind("\n", 0, at) + 1:].splitlines()
        image = [x for x in lines if "Find image" in x]
        return " ".join(x.strip(" !") for x in lines[:1] + image[:1])

    def wait(self, what, test, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.proc is not None and self.exception():
                raise Fail("%s: eccezione del payload: %s" % (what, self.exception()))
            r = test()
            if r:
                return r
            time.sleep(0.5)
        raise Fail("dopo %d s: %s" % (seconds, what))

    def stable(self, what, seconds, keys=(), frames=3):
        """Aspetta una schermata ferma: frames schermate di fila, a 1 s, che
        differiscono per meno dell'1% (l'orologio del setup cambia ogni
        secondo), premendo keys prima di ognuna."""
        seen = []

        def test():
            if keys:
                self.key(*keys)
            time.sleep(1.0)
            seen.append(self.shot())
            del seen[:-frames]
            if len(seen) == frames and all(a.diff(b) < 0.01 for a, b in zip(seen, seen[1:])):
                return seen[-1]
            return None
        return self.wait(what, test, seconds)


# La variabile di prova: un GUID del fornitore tutto suo, mai usato dal
# firmware; due valori di lunghezza diversa, cosi' il secondo e' un record
# nuovo e quello vecchio va cancellato
VAR_NAME = "OuroSmoke"
VAR_GUID = "2c1a8e3f-6d5b-4f1e-9a37-0b6e5f4d2c11"
VAR_DATA = ("4F55524F", "424F4F5432")      # "OURO", "BOOT2"
VAR_VALID = (0x3F, 0x3E)                   # VAR_ADDED, e in cancellazione


def store_vars(flash):
    """Le variabili dello store di SMMSTORE della ROM e la regione, per i
    dati: ([record di update.var_store], regione)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import update                           # noqa: E402 (tools/update.py)
    with open(flash, "rb") as f:
        data = f.read()
    areas = update.fmap_areas(data)
    if not areas or "SMMSTORE" not in areas:
        raise Fail("la ROM non ha una regione SMMSTORE")
    off, size = areas["SMMSTORE"]
    region = data[off:off + size]
    found, _ = update.var_store(region)
    return found, region


def boot_option_number(flash, description):
    """Il numero della voce Boot#### dello store con quella descrizione
    (UCS-2 dopo gli 6 byte di attributi e lunghezza del device path)."""
    found, region = store_vars(flash)
    want = description.encode("utf-16-le") + b"\0\0"
    for v in found:
        if v["state"] == VAR_VALID[0] and len(v["name"]) == 8 and v["name"].startswith("Boot") \
                and v["name"][4:].isalnum() and v["guid"] == GLOBAL_GUID:
            if region[v["data"] + 6:v["data"] + 6 + len(want)] == want:
                return int(v["name"][4:], 16)
    return None


def boot_next_number(flash):
    """Il valore di BootNext (UINT16) nello store della ROM, None se non c'e'."""
    found, region = store_vars(flash)
    for v in found:
        if v["name"] == "BootNext" and v["guid"] == GLOBAL_GUID and v["state"] in VAR_VALID \
                and v["size"] == 2:
            return int.from_bytes(region[v["data"]:v["data"] + 2], "little")
    return None


# Lo script che il DHCP di QEMU indica a iPXE (bootfile), e il secondo che
# questo chiama: la richiesta TFTP del secondo nel pcap prova che il primo
# e' stato scaricato ed eseguito
IPXE_SCRIPT = "smoke.ipxe"
IPXE_SCRIPT_2 = "smoke-ok.ipxe"
# Quello che l'MBR di prova scrive sulla seriale quando il BIOS legacy lo avvia
CSM_MARK = b"OUROBIOS-CSM-SMOKE"
GLOBAL_GUID = uuid.UUID("8be4df61-93ca-11d2-aa0d-00e098032b8c").bytes_le


def mbr_image(path):
    """Un disco di 1 MiB con un MBR che scrive CSM_MARK sulla porta seriale
    COM1 (0x3f8, senza inizializzarla: QEMU la accetta cosi') e si ferma."""
    code = bytearray()
    code += b"\xfa"                                  # cli
    code += b"\x31\xc0"                              # xor ax, ax
    code += b"\x8e\xd8"                              # mov ds, ax
    code += b"\xbe" + (0x7c00 + 0x20).to_bytes(2, "little")  # mov si, msg
    code += b"\xba\xf8\x03"                          # mov dx, 0x3f8
    # loop: lodsb; test al, al; jz halt; out dx, al; jmp loop
    code += b"\xac\x84\xc0\x74\x03\xee\xeb\xf8"
    code += b"\xf4\xeb\xfd"                          # halt: hlt; jmp halt
    assert len(code) <= 0x20
    code += b"\0" * (0x20 - len(code))
    code += CSM_MARK + b"\r\n\0"
    sector = bytes(code) + b"\0" * (510 - len(code)) + b"\x55\xaa"
    with open(path, "wb") as f:
        f.write(sector + b"\0" * (1024 * 1024 - 512))


def tftp_requests(pcap):
    """I file chiesti in TFTP (RRQ) nel pcap di filter-dump."""
    with open(pcap, "rb") as f:
        data = f.read()
    names = []
    off = 24                                        # il global header
    while off + 16 <= len(data):
        incl = int.from_bytes(data[off + 8:off + 12], "little")
        pkt = data[off + 16:off + 16 + incl]
        off += 16 + incl
        # Ethernet, IPv4, UDP, poi TFTP: opcode 1 (RRQ), nome, 0, modo
        if len(pkt) > 42 and pkt[12:14] == b"\x08\x00" and pkt[23] == 17:
            ihl = (pkt[14] & 0xf) * 4
            udp = pkt[14 + ihl:]
            end = udp.find(b"\0", 10) if len(udp) > 10 and udp[8:10] == b"\x00\x01" else -1
            if end > 10:                # un pacchetto scritto a meta' si salta
                names.append(udp[10:end].decode("ascii", "replace"))
    return names


def store_copies(flash, name=VAR_NAME, guid=VAR_GUID):
    """Le copie di una variabile (quella di prova, se non si dice) nello
    store di SMMSTORE della ROM: [(stato, attributi, dati)]."""
    found, region = store_vars(flash)
    guid = uuid.UUID(guid).bytes_le
    return [(v["state"], v["attrs"], region[v["data"]:v["data"] + v["size"]].hex().upper())
            for v in found if v["name"] == name and v["guid"] == guid]


# Il passo 9: le variabili che tools/efi/rt-reloc-test.c scrive, con i loro
# dati, e il prefisso delle sue righe sulla seriale
RELOC_GUID = "98fd63b7-d585-401b-9ad3-7bf5be115a84"
RELOC_VARS = (("OuroRelocA", bytes(0x40 + i for i in range(16))),
              ("OuroRelocB", bytes((7 * i + 3) & 0xFF for i in range(3000))))
RELOC_MARK = "ouroBIOS reloc test: "
# L'ESP del passo 9, come in tools/qemu-update.py: la partizione a 1 MiB,
# 32 MiB, FAT16
ESP_OFFSET = 1 << 20
ESP_SECTORS = 65536


def esp_image(path, efi):
    """Un disco con una sola partizione, di sistema EFI (MBR, tipo 0xEF),
    con efi come \\EFI\\BOOT\\BOOTX64.EFI: il payload lo avvia (mtools)."""
    env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
    part = path + ".part"
    for cmd in (["mformat", "-C", "-i", part, "-T", str(ESP_SECTORS), "-h", "64", "-s", "32",
                 "-v", "ESP", "::"],
                ["mmd", "-i", part, "::/EFI", "::/EFI/BOOT"],
                ["mcopy", "-i", part, efi, "::/EFI/BOOT/BOOTX64.EFI"]):
        r = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0:
            raise Fail("%s: %s" % (cmd[0], r.stdout.strip()))
    mbr = bytearray(512)
    mbr[446:462] = struct.pack("<B3sB3sII", 0, b"\xfe\xff\xff", 0xEF, b"\xfe\xff\xff",
                               ESP_OFFSET // 512, ESP_SECTORS)
    mbr[510:512] = b"\x55\xaa"
    with open(path, "wb") as f, open(part, "rb") as p:
        f.write(mbr)
        f.write(bytes(ESP_OFFSET - len(mbr)))
        shutil.copyfileobj(p, f)
    os.remove(part)


def reloc_test(rom, efi, out, timeout):
    """Il passo 9, su una copia nuova della ROM: con l'ESP dalla prima
    accensione, la voce di boot del disco e' la prima, e il payload avvia
    efi senza passare dalla Shell. Torna la riga del riassunto."""
    sm = Smoke(rom, out, timeout)
    try:
        disk = os.path.join(sm.tmp, "esp.img")
        esp_image(disk, efi)
        # con -no-reboot QEMU esce sia per ResetSystem() sia per un triple
        # fault: -d cpu_reset (TCG) scrive "Triple fault" nel log
        cpu = os.path.join(out, "qemu-reloc-cpu.log")
        sm.boot("reloc", ["-drive", "file=%s,format=raw,if=none,id=esp" % disk,
                          "-device", "ide-hd,drive=esp,bus=ide.0", "-d", "cpu_reset", "-D", cpu])
        sm.wait("rt-reloc-test.efi non ha finito con un reset (serial-reloc.log)",
                lambda: sm.proc.poll() is not None, timeout)
        sm.halt()
        lines = [line.split(RELOC_MARK, 1)[1].strip() for line in sm.serial_text().splitlines()
                 if RELOC_MARK in line]
        with open(cpu, errors="replace") as f:
            triple = "Triple fault" in f.read()
        last = lines[-1] if lines else "nessuna riga di rt-reloc-test.efi"
        if "RESULT OK" not in lines:
            failed = [line for line in lines if "FAIL" in line and not line.startswith("RESULT")]
            raise Fail("servizi runtime spostati come da boot.efi di macOS: %s (serial-reloc.log)"
                       % ("; ".join(failed) if failed else "triple fault dopo \"%s\"" % last if triple
                          else "fermo dopo \"%s\"" % last))
        if triple or last != "ResetSystem()":
            raise Fail("ResetSystem() dalle pagine virtuali: %s (serial-reloc.log, qemu-reloc-cpu.log)"
                       % ("triple fault" if triple else "\"%s\"" % last))
        moved = [m for m in (re.match(r"moved (\d+) ranges of runtime code and data \((\d+) pages\), "
                                      r"(\d+) other", line) for line in lines) if m]
        if not moved or int(moved[0].group(1)) == 0:
            raise Fail("rt-reloc-test.efi non ha spostato il codice e i dati dei servizi runtime")
        for name, data in RELOC_VARS:
            valid = [c for c in store_copies(sm.flash, name, RELOC_GUID) if c[0] in VAR_VALID]
            if len(valid) != 1 or valid[0][2] != data.hex().upper() or valid[0][1] & 0x7 != 0x7:
                raise Fail("%s non e' nello store del flash, una copia valida con i suoi %d byte "
                           "(NV+BS+RT): SMM ha letto le copie di prima?" % (name, len(data)))
        return ("servizi runtime spostati come da boot.efi di macOS senza AvoidRuntimeDefrag: %s aree di "
                "codice e dati (%s pagine) copiate altrove e a 0xCC le copie di prima, %s MMIO al loro "
                "posto; i servizi rispondono, %s nel flash con i loro dati, nessun byte nelle copie di "
                "prima, ResetSystem() riavvia"
                % (moved[0].group(1), moved[0].group(2), moved[0].group(3),
                   " e ".join(n for n, _ in RELOC_VARS)))
    finally:
        sm.close()


# Il passo 10: le righe di tools/efi/secure-boot-test.c sulla seriale
SB_MARK = "ouroBIOS sb test: "


def secure_boot_test(rom, efi, out, timeout, esrt):
    """Il passo 10, su una copia nuova della ROM, con un'ESP dalla prima
    accensione: il payload avvia efi due volte sullo stesso flash. Il primo
    avvio mette la CA di prova in db e accende Secure Boot, il secondo parte
    solo se la firma di efi passa, e prova LoadImage() delle immagini
    incorporate. esrt e' (guid, versione, lsv) attesi nell'ESRT, che efi
    stampa a ogni avvio. Torna la riga del riassunto."""
    sm = Smoke(rom, out, timeout)
    try:
        disk = os.path.join(sm.tmp, "esp.img")
        esp_image(disk, efi)
        drive = ["-drive", "file=%s,format=raw,if=none,id=esp" % disk,
                 "-device", "ide-hd,drive=esp,bus=ide.0"]

        def marks():
            return [line.split(SB_MARK, 1)[1].strip() for line in sm.serial_text().splitlines()
                    if SB_MARK in line]

        # il primo avvio finisce con ResetSystem(): -no-reboot chiude QEMU
        sm.boot("sb-1", drive)
        sm.wait("secure-boot-test.efi non ha finito il primo avvio con un reset (serial-sb-1.log)",
                lambda: sm.proc.poll() is not None or any(l.startswith("RESULT") for l in marks()),
                timeout)
        sm.halt()
        lines = marks()
        if not lines:
            raise Fail("il payload non ha avviato secure-boot-test.efi dall'ESP (serial-sb-1.log)")
        if lines[-1] != "reset":
            raise Fail("secure-boot-test.efi al primo avvio: %s (serial-sb-1.log)" % lines[-1])
        sm.boot("sb-2", drive)
        sm.wait("secure-boot-test.efi non ha finito il secondo avvio (serial-sb-2.log): la sua "
                "firma non passa con Secure Boot acceso?",
                lambda: (sm.alive(), any(l.startswith("RESULT") for l in marks()))[1], timeout)
        second = marks()
        sm.halt()
        lines += second
        wrong = [l for l in lines if "WRONG" in l or (l.startswith("SetVariable") and "SUCCESS" not in l)]
        if second[-1] != "RESULT OK" or wrong:
            raise Fail("Secure Boot: %s (serial-sb-*.log)" % ("; ".join(wrong) if wrong else second[-1]))
        loads = [l for l in second if l.startswith("LoadImage")]
        # l'ESRT: una voce, quella della variante, a tutti e due gli avvii
        guid, version, lsv = esrt
        want = "esrt %s type 1 version 0x%08x lsv 0x%08x" % (guid.lower(), version, lsv)
        got = [l for l in lines if l.startswith("esrt ") and not l.startswith("esrt entries")]
        if ([l for l in lines if l.startswith("esrt entries")] != ["esrt entries 1"] * 2
                or len(got) != 2 or not all(l.startswith(want) for l in got)):
            raise Fail("ESRT: attesa una voce \"%s\" a ogni avvio, trovate: %s"
                       % (want, "; ".join(got) or "nessuna"))
        # il protocollo crypto di CryptoDxe: SHA-256 e il PBKDF2 della password
        # del setup (UserAuthenticationDxe), calcolati qui per confronto
        expected = {"sha256 abc": hashlib.sha256(b"abc").hexdigest(),
                    "pbkdf2 sha256 ouroBIOS salt 0..31 1000":
                        hashlib.pbkdf2_hmac("sha256", b"ouroBIOS", bytes(range(32)), 1000, 32).hex()}
        version = [l for l in lines if l.startswith("crypto protocol: version ")]
        if len(version) != 1:
            raise Fail("il protocollo crypto di CryptoDxe: %s (serial-sb-1.log)"
                       % ("; ".join(l for l in lines if l.startswith("crypto protocol")) or "nessuna riga"))
        for what, want in expected.items():
            got = [l.split(" = ", 1)[1] for l in lines if l.startswith(what + " = ")]
            if got != [want]:
                raise Fail("%s dal protocollo crypto: %s, atteso %s" % (what, got[0] if got else "assente", want))
        skipped = [l.split()[1] for l in loads if "skipped" in l]
        verdicts = ", ".join("%s %s" % (l.split()[1], l.split(": ")[1].split(",")[0])
                             for l in loads if "skipped" not in l)
        return ("ESRT con la voce della variante (%s, 0x%08x); il protocollo crypto di CryptoDxe "
                "(%s): SHA-256 e il PBKDF2 della password del setup giusti; Secure Boot: la CA di prova "
                "messa in db in custom mode e SecureBootEnable=1 scritti, al riavvio SecureBoot=1 e il "
                "payload ha avviato secure-boot-test.efi, firmato da un certificato figlio della CA; %s%s"
                % (guid, esrt[1], version[0].split(": ", 1)[1], verdicts,
                   "" if not skipped else " (%s senza immagine, saltato)" % ", ".join(skipped)))
    finally:
        sm.close()


# Il passo 11: il TPM 1.2 di swtpm e il log TCPA del payload. Il tipo e il
# PCR degli eventi (TCG PC Client, TPM 1.2), e le variabili che il driver
# delle variabili misura in PCR 7 quando vengono scritte
EV_NO_ACTION = 0x3
EV_SEPARATOR = 0x4
EV_EFI_VARIABLE_DRIVER_CONFIG = 0x80000001
TPM_POLICY_VARS = ("SecureBoot", "PK", "KEK", "db", "dbx")
# Le misure di coreboot (security/tpm/tspi/crtm.c, TPM_MEASURED_BOOT): in
# PCR 2 (PCR_SRTM), ognuna con il nome nei dati dell'evento; quelle che ci
# devono essere, comunque sia fatta la ROM
CB_PCR = 2
CB_MEASURED = ("FMAP: FMAP", "CBFS: bootblock", "CBFS: fallback/romstage", "CBFS: fallback/ramstage",
               "CBFS: fallback/payload")
# Il prefisso delle righe di tools/efi/tpm-pcr-test.c sulla seriale
TPM_MARK = "ouroBIOS tpm test: "


def rom_digests(rom, algo="sha1"):
    """Il digest (algo di hashlib) di quello che coreboot misura, dai byte della ROM: le aree
    dell'FMAP ("FMAP: nome") e i file di ogni CBFS ("CBFS: nome", i dati
    come sono nel flash, compressi o no: cbfs.c li misura prima di
    decomprimerli). Un nome puo' avere piu' digest (un file in piu' CBFS)."""
    digests = {}
    # la firma e' anche, come stringa, nel codice che cerca l'FMAP: quello
    # vero e' la versione 1, grande quanto la ROM
    o = rom.find(b"__FMAP__")
    while o >= 0 and not (rom[o + 8] == 1 and struct.unpack_from("<I", rom, o + 18)[0] == len(rom)):
        o = rom.find(b"__FMAP__", o + 1)
    if o < 0:
        raise Fail("nessun FMAP nella ROM")
    nareas = struct.unpack_from("<H", rom, o + 0x36)[0]
    for i in range(nareas):
        off, size, name = struct.unpack_from("<II32s", rom, o + 0x38 + 42 * i)
        name = name.split(b"\0", 1)[0].decode()
        digests.setdefault("FMAP: " + name, set()).add(hashlib.new(algo, rom[off:off + size]).digest())
    o = 0
    while True:
        o = rom.find(b"LARCHIVE", o)
        if o < 0:
            break
        size, _, _, data = struct.unpack_from(">IIII", rom, o + 8)
        name = rom[o + 24:o + data].split(b"\0", 1)[0]
        if data >= 24 and name and o + data + size <= len(rom):
            digests.setdefault("CBFS: " + name.decode("ascii", "replace"), set()).add(
                hashlib.new(algo, rom[o + data:o + data + size]).digest())
        o += 8
    return digests


# Il log crypto agile di EFI_TCG2_PROTOCOL (TCG PC Client Platform Firmware
# Profile): gli algoritmi dei banchi che il passo 11 rifa'
TPM2_ALGS = {0x0004: "sha1", 0x000B: "sha256"}


def tcg2_events(dump, base, location, last):
    """Gli eventi del log crypto agile che parte a location, fino a quello a
    last compreso, in un dump della RAM che parte da base: (pcr, tipo,
    {banco: digest}, dati). Il primo evento (Spec ID Event03, formato TPM
    1.2) da' la lunghezza dei digest di ogni algoritmo."""
    o = location - base
    if o < 0 or last < location or last - base >= len(dump):
        raise Fail("il log di EFI_TCG2_PROTOCOL (0x%x-0x%x) e' fuori dal dump della RAM" % (location, last))
    size = struct.unpack_from("<I", dump, o + 28)[0]
    spec = dump[o + 32:o + 32 + size]
    if not spec.startswith(b"Spec ID Event03"):
        raise Fail("il log di EFI_TCG2_PROTOCOL non comincia con Spec ID Event03")
    count = struct.unpack_from("<I", spec, 24)[0]
    sizes = dict(struct.unpack_from("<HH", spec, 28 + 4 * i) for i in range(count))
    events = []
    o += 32 + size
    while o <= last - base:
        pcr, typ, n = struct.unpack_from("<III", dump, o)
        o += 12
        digests = {}
        for _ in range(n):
            alg = struct.unpack_from("<H", dump, o)[0]
            if alg not in sizes:
                raise Fail("evento del log TCG2 a 0x%x: algoritmo 0x%x non nello Spec ID" % (o + base, alg))
            digests[TPM2_ALGS.get(alg, "0x%x" % alg)] = dump[o + 2:o + 2 + sizes[alg]]
            o += 2 + sizes[alg]
        data_size = struct.unpack_from("<I", dump, o)[0]
        events.append((pcr, typ, digests, dump[o + 4:o + 4 + data_size]))
        o += 4 + data_size
    return sorted(TPM2_ALGS[a] for a in sizes if a in TPM2_ALGS), events


def replay_bank(events, bank):
    """I PCR 0-7 di un banco del TPM 2.0 rifatti dal log TCG2 (EV_NO_ACTION
    non estende)."""
    pcrs = {i: bytes(hashlib.new(bank).digest_size) for i in range(8)}
    for pcr, typ, digests, _ in events:
        if typ != EV_NO_ACTION and pcr in pcrs:
            if bank not in digests:
                return None
            pcrs[pcr] = hashlib.new(bank, pcrs[pcr] + digests[bank]).digest()
    return pcrs


def replay(events):
    """I PCR 0-7 rifatti dal log TCPA: ogni evento estende il suo PCR,
    SHA-1 (vecchio || digest), salvo EV_NO_ACTION."""
    pcrs = {i: bytes(20) for i in range(8)}
    for pcr, typ, digest, _ in events:
        if typ != EV_NO_ACTION and pcr in pcrs:
            pcrs[pcr] = hashlib.sha1(pcrs[pcr] + digest).digest()
    return pcrs


def tcpa_events(dump, base):
    """Gli eventi del log TCPA (tabella ACPI TCPA, LAML e LASA) in un dump
    della RAM che parte dall'indirizzo base: (pcr, tipo, digest, dati)."""
    found = None
    o = 0
    while True:
        o = dump.find(b"TCPA", o)
        if o < 0:
            break
        length = struct.unpack_from("<I", dump, o + 4)[0]
        if 50 <= length <= 100 and o + length <= len(dump) and sum(dump[o:o + length]) & 0xFF == 0:
            _, laml, lasa = struct.unpack_from("<HIQ", dump, o + 36)
            found = (laml, lasa)
        o += 4
    if not found:
        raise Fail("nessuna tabella ACPI TCPA nella RAM: coreboot non ha visto il TPM 1.2 di swtpm?")
    laml, lasa = found
    if lasa < base or lasa + laml > base + len(dump):
        raise Fail("il log TCPA (%#x, %d byte) e' fuori dal dump della RAM" % (lasa, laml))
    log = dump[lasa - base:lasa - base + laml]
    events, off = [], 0
    while off + 32 <= len(log):
        pcr, typ = struct.unpack_from("<II", log, off)
        digest = log[off + 8:off + 28]
        size = struct.unpack_from("<I", log, off + 28)[0]
        if pcr == 0xFFFFFFFF or (typ == 0 and size == 0) or off + 32 + size > len(log):
            break
        events.append((pcr, typ, digest, log[off + 32:off + 32 + size]))
        off += 32 + size
    return events


def variable_name(data):
    """Il nome in UEFI_VARIABLE_DATA: GUID, lunghezza del nome, dei dati, il
    nome in UCS-2, i dati."""
    if len(data) < 32:
        return None
    name_len, data_len = struct.unpack_from("<QQ", data, 16)
    if 32 + 2 * name_len + data_len != len(data):
        return None
    return data[32:32 + 2 * name_len].decode("utf-16-le", "replace")


def tpm2_check(sm, rom, got, out):
    """Il passo 11 con il TPM 2.0 (--tpm2, la ROM con CONFIG_TPM2 e
    CONFIG_TPM_MEASURED_BOOT_SHA1_BANK, come il M920x): il log crypto agile
    di EFI_TCG2_PROTOCOL, all'indirizzo che tpm-pcr-test.efi ha scritto,
    deve avere le misure di coreboot in PCR 2 (patches/edk2/0042), ognuna
    con lo SHA-1 e lo SHA-256 dei byte della ROM (patch 0201), i separatori
    dei PCR 0-7, e rifatto deve dare i PCR dei due banchi letti dal TPM."""
    m = next((re.fullmatch(r"log 0x([0-9a-f]+) last 0x([0-9a-f]+) truncated (\d+)", line) for line in got
              if line.startswith("log ")), None)
    if not m:
        raise Fail("tpm-pcr-test.efi non ha scritto l'indirizzo del log TCG2 (serial-tpm.log)")
    location, last, truncated = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3))
    if truncated:
        raise Fail("il log di EFI_TCG2_PROTOCOL e' troncato")
    tpm_pcrs = {}
    for line in got:
        p = re.fullmatch(r"pcr (\d+) (sha1|sha256) ([0-9a-f]+)", line)
        if p:
            tpm_pcrs[(p.group(2), int(p.group(1)))] = bytes.fromhex(p.group(3))
    base = location & ~0xFFF
    size = (last - base + 0x10000) & ~0xFFF
    dump = os.path.join(sm.tmp, "tcg2.bin")
    sm.qmp.cmd("stop")
    sm.qmp.cmd("pmemsave", val=base, size=size, filename=dump)
    with open(dump, "rb") as f:
        banks, events = tcg2_events(f.read(), base, location, last)
    sm.halt()
    with open(os.path.join(out, "tcg2-log.txt"), "w") as f:
        for pcr, typ, digests, data in events:
            f.write("PCR %d type %#x %s %s\n" % (pcr, typ, " ".join("%s:%s" % (b, d.hex()) for b, d in
                                                                      sorted(digests.items())),
                                                 data[:64].split(b"\0", 1)[0].decode("ascii", "replace")))
    if banks != ["sha1", "sha256"]:
        raise Fail("il log TCG2 ha i banchi %s, attesi sha1 e sha256 (swtpm_setup --pcr-banks)" % banks)
    with open(rom, "rb") as f:
        image = f.read()
    digests = {b: rom_digests(image, b) for b in banks}
    cb, bad = [], []
    for pcr, typ, ds, data in events:
        name = data.split(b"\0", 1)[0].decode("ascii", "replace")
        if not name.startswith(("FMAP: ", "CBFS: ")):
            continue
        if pcr != CB_PCR:
            bad.append("%s in PCR %d" % (name, pcr))
        for b in banks:
            if ds.get(b) not in digests[b].get(name, ()):
                bad.append("%s: il digest %s non e' quello dei byte nella ROM" % (name, b))
        cb.append(name)
    if bad:
        raise Fail("misure di coreboot nel log TCG2 sbagliate: %s (tcg2-log.txt)" % "; ".join(bad))
    missing = [n for n in CB_MEASURED if n not in cb]
    if missing:
        raise Fail("nel log TCG2 mancano le misure di coreboot di %s (tcg2-log.txt): Tcg2Dxe non le ha "
                   "prese dal log di coreboot (patches/edk2/0042)?" % ", ".join(missing))
    separators = sorted(pcr for pcr, typ, _, _ in events if typ == EV_SEPARATOR)
    if separators != list(range(8)):
        raise Fail("separatori nel log TCG2 per i PCR %s, attesi 0-7" % separators)
    differ = []
    for b in banks:
        logged = replay_bank(events, b)
        if logged is None:
            differ.append("%s (eventi senza il digest %s)" % (b, b))
            continue
        differ += ["%s %d" % (b, i) for i in range(8) if tpm_pcrs.get((b, i)) != logged[i]]
    if differ:
        raise Fail("i PCR %s del TPM non sono quelli del log TCG2 rifatto (serial-tpm.log, tcg2-log.txt)"
                   % ", ".join(differ))
    return ("TPM 2.0 (swtpm, SHA-1 e SHA-256): %d eventi nel log di EFI_TCG2_PROTOCOL, che rifatto da' i PCR "
            "0-7 dei due banchi letti dal TPM; in PCR 2 le %d misure di coreboot (%s), con lo SHA-1 e lo SHA-256 "
            "dei byte della ROM; i separatori dei PCR 0-7"
            % (len(events), len(cb), ", ".join(n.split(": ", 1)[1] for n in cb)))


def tpm_test(rom, efi, out, timeout, tpm2=False):
    """Il passo 11: su una copia nuova della ROM, con il TPM 1.2 di swtpm e
    un'ESP, il payload avvia efi (tools/efi/tpm-pcr-test.c), che scrive i
    PCR 0-7 sulla seriale; poi la RAM via QMP e il log TCPA. Le misure di
    coreboot in PCR 2 devono essere quelle dei byte della ROM; il driver
    delle variabili deve aver misurato in PCR 7 le chiavi di Secure Boot
    che EnrollDefaultKeys scrive al primo avvio (il TPM 1.2 le misura solo
    allora: v1.3.10-rc19 le perdeva, con TcgDxe avviato dopo), con i
    digest giusti; ogni PCR deve avere il separatore, e il log rifatto
    deve dare i PCR del TPM. Con tpm2, il TPM 2.0 (tpm2_check). Torna la
    riga del riassunto."""
    if not shutil.which("swtpm") or (tpm2 and not shutil.which("swtpm_setup")):
        raise Fail("serve swtpm per il passo 11 (Debian/Ubuntu: apt install swtpm swtpm-tools)")
    os.makedirs(out, exist_ok=True)
    sm = Smoke(rom, out, timeout)
    swtpm = None
    try:
        # un TPM 1.2 (il default di swtpm) con lo stato nuovo, che swtpm crea
        # da solo: niente swtpm_setup, le misure non vogliono l'EK. Il TPM
        # 2.0 invece con swtpm_setup, per i banchi del M920x, SHA-1 e
        # SHA-256 (libtpms da solo allocherebbe anche SHA-384 e SHA-512)
        state = os.path.join(sm.tmp, "tpm20" if tpm2 else "tpm12")
        os.makedirs(state)
        if tpm2:
            r = subprocess.run(["swtpm_setup", "--tpm2", "--tpmstate", state, "--pcr-banks", "sha1,sha256",
                                "--config", "/dev/null"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if r.returncode != 0:
                raise Fail("swtpm_setup: %s" % r.stdout.strip().splitlines()[-1:])
        sock = os.path.join(sm.tmp, "swtpm.sock")
        swtpm = subprocess.Popen(["swtpm", "socket"] + (["--tpm2"] if tpm2 else []) + ["--tpmstate", "dir=" + state,
                                  "--ctrl", "type=unixio,path=" + sock,
                                  "--log", "file=%s,level=1" % os.path.join(out, "swtpm.log")])
        end = time.monotonic() + 10
        while not os.path.exists(sock):
            if swtpm.poll() is not None or time.monotonic() > end:
                raise Fail("swtpm non ha aperto %s (swtpm.log)%s"
                           % (sock, "" if swtpm.poll() is None else ": uscito con %d" % swtpm.returncode))
            time.sleep(0.1)
        disk = os.path.join(sm.tmp, "esp.img")
        esp_image(disk, efi)
        sm.boot("tpm", ["-chardev", "socket,id=chrtpm,path=" + sock, "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
                        "-device", "tpm-tis,tpmdev=tpm0",
                        "-drive", "file=%s,format=raw,if=none,id=esp" % disk, "-device", "ide-hd,drive=esp,bus=ide.0"])
        sm.wait("coreboot non e' arrivato al payload con il TPM (serial-tpm.log)",
                lambda: (sm.alive(), "Jumping to boot code" in sm.serial_text())[1], timeout)

        # le righe di tpm-pcr-test.efi, che dopo l'ultima aspetta: dopo
        # ReadyToBoot, quando il log ha anche le misure delle variabili di
        # boot e i separatori
        def lines():
            return [line.split(TPM_MARK, 1)[1].strip() for line in sm.serial_text().splitlines()
                    if TPM_MARK in line]
        sm.wait("tpm-pcr-test.efi non ha finito (serial-tpm.log): il payload non l'ha avviato dall'ESP?",
                lambda: (sm.alive(), any(line.startswith("RESULT") for line in lines()))[1], timeout)
        got = lines()
        if "RESULT OK" not in got:
            raise Fail("tpm-pcr-test.efi: %s (serial-tpm.log)"
                       % "; ".join(line for line in got if "FAIL" in line))
        want = "tpm 2.0" if tpm2 else "tpm 1.2"
        if want not in got:
            raise Fail("tpm-pcr-test.efi non ha trovato %s: %s"
                       % ("EFI_TCG2_PROTOCOL" if tpm2 else "EFI_TCG_PROTOCOL", got[0]))
        sm.shot("tpm")
        if tpm2:
            return tpm2_check(sm, rom, got, out)
        tpm_pcrs = {}
        for line in got:
            m = re.fullmatch(r"pcr (\d+) sha1 ([0-9a-f]{40})", line)
            if m:
                tpm_pcrs[int(m.group(1))] = bytes.fromhex(m.group(2))
        # la RAM alta di q35 con 2 GiB: la tabella TCPA e il log (cbmem) sono li'
        base, size = 0x70000000, 0x10000000
        dump = os.path.join(sm.tmp, "ram.bin")
        sm.qmp.cmd("stop")
        sm.qmp.cmd("pmemsave", val=base, size=size, filename=dump)
        with open(dump, "rb") as f:
            events = tcpa_events(f.read(), base)
        sm.halt()
        if not events:
            raise Fail("il log TCPA e' vuoto")
        with open(os.path.join(out, "tcpa-log.txt"), "w") as f:
            for pcr, typ, digest, data in events:
                f.write("PCR %d type %#x %s %s\n" % (pcr, typ, digest.hex(),
                                                     data[:64].split(b"\0", 1)[0].decode("ascii", "replace")))
        # le misure di coreboot: il nome nei dati dell'evento (50 byte, una
        # stringa), il digest quello dei byte nella ROM
        with open(rom, "rb") as f:
            digests = rom_digests(f.read())
        cb, bad = [], []
        for pcr, typ, digest, data in events:
            name = data.split(b"\0", 1)[0].decode("ascii", "replace")
            if not name.startswith(("FMAP: ", "CBFS: ")):
                continue
            if pcr != CB_PCR:
                bad.append("%s in PCR %d" % (name, pcr))
            elif digest not in digests.get(name, ()):
                bad.append("%s: il digest non e' lo SHA-1 dei byte nella ROM" % name)
            cb.append(name)
        if bad:
            raise Fail("misure di coreboot sbagliate: %s (tcpa-log.txt)" % "; ".join(bad))
        missing = [n for n in CB_MEASURED if n not in cb]
        if missing:
            raise Fail("nel log TCPA mancano le misure di coreboot di %s (tcpa-log.txt): la ROM ha "
                       "CONFIG_TPM_MEASURED_BOOT?" % ", ".join(missing))
        separators = sorted(pcr for pcr, typ, _, _ in events if typ == EV_SEPARATOR)
        if separators != list(range(8)):
            raise Fail("separatori nel log TCPA per i PCR %s, attesi 0-7" % separators)
        measured, wrong = [], []
        for pcr, typ, digest, data in events:
            if typ != EV_EFI_VARIABLE_DRIVER_CONFIG:
                continue
            name = variable_name(data)
            if pcr != 7 or name is None:
                wrong.append("PCR %d, tipo %#x, %d byte" % (pcr, typ, len(data)))
            elif hashlib.sha1(data).digest() != digest:
                wrong.append("%s: il digest non e' lo SHA-1 dei dati" % name)
            else:
                measured.append(name)
        if wrong:
            raise Fail("misure delle variabili in PCR 7 sbagliate: %s" % "; ".join(wrong))
        missing = [v for v in TPM_POLICY_VARS if v not in measured]
        if missing:
            raise Fail("in PCR 7 mancano le misure di %s (misurate: %s): il driver delle variabili ha "
                       "scritto le chiavi di Secure Boot senza il driver del TPM (v1.3.10-rc19)"
                       % (", ".join(missing), ", ".join(measured) or "nessuna"))
        # il log, rifatto, deve dare i PCR del TPM: un evento esteso ma non
        # scritto (il log pieno) o scritto ma non esteso non passa
        logged = replay(events)
        differ = [str(i) for i in range(8) if tpm_pcrs.get(i) != logged[i]]
        if differ:
            raise Fail("i PCR %s del TPM non sono quelli del log TCPA rifatto (serial-tpm.log, tcpa-log.txt)"
                       % ", ".join(differ))
        return ("TPM 1.2 (swtpm): %d eventi nel log TCPA, che rifatto da' i PCR 0-7 letti dal TPM; in PCR 2 "
                "le %d misure di coreboot (%s), con lo SHA-1 dei byte della ROM; i separatori dei PCR 0-7; "
                "in PCR 7 le %d misure delle chiavi di Secure Boot scritte al primo avvio (%s) con i digest giusti"
                % (len(events), len(cb), ", ".join(n.split(": ", 1)[1] for n in cb), len(measured),
                   ", ".join(measured)))
    finally:
        sm.close()
        if swtpm is not None:
            swtpm.terminate()
            try:
                swtpm.wait(timeout=10)
            except subprocess.TimeoutExpired:
                swtpm.kill()


def run(rom, out, timeout, setup_only=False, vga_mb=16, size=None, reloc_efi=None, sb_efi=None,
        esrt=None, sb_only=False, tpm=None, tpm2=False):
    os.makedirs(out, exist_ok=True)
    if sb_only:
        t0 = time.monotonic()
        line = secure_boot_test(rom, sb_efi, out, timeout, esrt)
        return ["%3.0f s  %s" % (time.monotonic() - t0, line)]
    sm = Smoke(rom, out, timeout, vga_mb)
    steps = []
    t0 = time.monotonic()
    at = lambda: "%3.0f s" % (time.monotonic() - t0)

    def to_payload():
        sm.wait("coreboot non e' arrivato al payload (\"Jumping to boot code\" nella seriale)",
                lambda: (sm.alive(), "Jumping to boot code" in sm.serial_text())[1], timeout)

    try:
        # 1. il setup: Esc durante l'avvio lo apre (BOOT_MANAGER_ESCAPE); la
        # pagina principale lo ignora, cosi' si puo' premere finche' non c'e'
        sm.boot("setup")
        to_payload()
        steps.append("%s  coreboot -> payload" % at())

        def drawn():
            sm.key("esc")
            s = sm.shot()
            return s if s.colors() >= 2 else None
        first = sm.wait("il payload non ha disegnato niente (schermo di un colore solo)", drawn, timeout)
        sm.shot("payload")
        steps.append("%s  il payload disegna (%d colori)" % (at(), first.colors()))

        home = sm.stable("il setup non si e' fermato su una pagina", timeout, keys=("esc",))
        sm.shot("setup")
        if home.colors() <= 8:
            raise Fail("lo schermo si e' fermato con %d colori: la Shell UEFI o la console di testo, "
                       "non il setup (Esc non l'ha aperto)" % home.colors())
        if size and home.size != size:
            raise Fail("il setup e' a %dx%d, non a %dx%d" % (home.size + size))
        steps.append("%s  setup, pagina principale (%d colori, %dx%d)" % ((at(), home.colors()) + home.size))

        sm.key("down", "ret")
        page = sm.stable("dopo Giu' e Invio lo schermo non si e' fermato", timeout)
        sm.shot("pagina")
        changed = page.diff(home)
        if changed < 0.03:
            raise Fail("Giu' e Invio non hanno aperto una pagina (%.1f%% dello schermo cambiato)"
                       % (100 * changed))
        steps.append("%s  Giu' + Invio: un'altra pagina (%.0f%% dello schermo)" % (at(), 100 * changed))

        sm.key("esc")
        back = sm.stable("dopo Esc lo schermo non si e' fermato", timeout)
        sm.shot("indietro")
        if back.diff(page) < 0.03:
            raise Fail("Esc non ha lasciato la pagina")
        steps.append("%s  Esc: di nuovo la pagina principale" % at())
        sm.alive()
        boots = sm.serial_text().count("bootblock starting")
        if boots > 1:
            raise Fail("coreboot e' partito %d volte" % boots)
        steps.append("%s  QEMU vivo, un solo avvio" % at())
        if setup_only:
            return steps

        # 2. le variabili UEFI in SMMSTORE: senza dischi il payload arriva
        # alla Shell, dove setvar scrive la variabile di prova e reset -s
        # spegne; la si cerca poi nello store del flash. Al secondo avvio la
        # Shell la riscrive: il driver delle variabili deve trovare la copia
        # di prima nel flash e cancellarla, e ne deve restare una sola
        for i, value in enumerate(VAR_DATA):
            sm.boot("shell-%d" % (i + 1))
            to_payload()
            shell = sm.stable("il payload non e' arrivato alla Shell UEFI", timeout)
            if shell.colors() > 8:
                raise Fail("senza dischi il payload non si e' fermato nella Shell (%d colori)"
                           % shell.colors())
            sm.type("setvar %s -guid %s -bs -rt -nv =%s\n" % (VAR_NAME, VAR_GUID, value))
            # QEMU scrive il flash emulato su disco appena il firmware lo
            # programma: si aspetta la variabile li', non una schermata ferma
            # (la Shell lo e' anche prima di setvar). Poi si chiude QEMU.
            # Niente reset -s: il PM di ICH9 in QEMU spegne con SLP_TYP 0,
            # coreboot da' a S5 il 7 dei PCH Intel
            sm.wait("setvar non ha scritto %s nel flash" % VAR_NAME,
                    lambda: (sm.alive(), any(c[0] in VAR_VALID and c[2] == value
                                             for c in store_copies(sm.flash)))[1], timeout)
            sm.shot("shell-%d" % (i + 1))
            sm.halt()
            copies = store_copies(sm.flash)
            valid = [c for c in copies if c[0] in VAR_VALID]
            if len(valid) != 1 or valid[0][2] != value:
                raise Fail("nello store %d copie valide di %s (%s), attesa una con %s"
                           % (len(valid), VAR_NAME, ", ".join(c[2] for c in valid) or "nessuna", value))
            if valid[0][1] & 0x7 != 0x7:
                raise Fail("%s con attributi 0x%x, attesi NV+BS+RT (0x7)" % (VAR_NAME, valid[0][1]))
            if i == 0:
                steps.append("%s  Shell: setvar scrive %s in SMMSTORE (NV+BS+RT)" % (at(), VAR_NAME))
            else:
                if len(copies) < 2:
                    raise Fail("la copia di prima di %s non c'e' piu' nello store" % VAR_NAME)
                steps.append("%s  dopo un riavvio: riscritta, la copia di prima cancellata, una sola "
                             "valida" % at())

        # 3. iPXE e CSMWrap: le voci della FV che il boot manager registra.
        # Senza dischi il payload va alla Shell: da li' BootNext sceglie la
        # voce per l'avvio dopo (setvar sul nome, letto dallo store)
        def boot_next(tag, description):
            n = boot_option_number(sm.flash, description)
            if n is None:
                raise Fail("nello store nessuna voce Boot#### \"%s\": il boot manager non l'ha registrata"
                           % description)
            sm.boot(tag)
            to_payload()
            shell = sm.stable("il payload non e' arrivato alla Shell UEFI", timeout)
            if shell.colors() > 8:
                raise Fail("senza dischi il payload non si e' fermato nella Shell (%d colori)" % shell.colors())
            sm.type("setvar BootNext -guid %s -bs -rt -nv =%02X%02X\n"
                    % (str(uuid.UUID(bytes_le=GLOBAL_GUID)), n & 0xFF, n >> 8))
            sm.wait("setvar non ha scritto BootNext nel flash",
                    lambda: (sm.alive(), boot_next_number(sm.flash) == n)[1], timeout)
            sm.halt()
            return n

        n = boot_next("shell-ipxe", "iPXE Network Boot")
        tftp = os.path.join(sm.tmp, "tftp")
        os.makedirs(tftp, exist_ok=True)
        with open(os.path.join(tftp, IPXE_SCRIPT), "w") as f:
            f.write("#!ipxe\necho ouroBIOS smoke: ${net0/ip} from ${next-server}\nchain tftp://${next-server}/%s\n"
                    % IPXE_SCRIPT_2)
        with open(os.path.join(tftp, IPXE_SCRIPT_2), "w") as f:
            f.write("#!ipxe\necho ouroBIOS smoke: second script\nexit\n")
        pcap = os.path.join(out, "ipxe.pcap")
        sm.boot("ipxe", ["-netdev", "user,id=n0,tftp=%s,bootfile=%s" % (tftp, IPXE_SCRIPT),
                         "-device", "e1000,netdev=n0", "-object", "filter-dump,id=d0,netdev=n0,file=" + pcap])
        to_payload()
        sm.wait("iPXE non ha chiesto in TFTP %s, poi %s (pcap in %s)" % (IPXE_SCRIPT, IPXE_SCRIPT_2, pcap),
                lambda: (sm.alive(), IPXE_SCRIPT_2 in tftp_requests(pcap))[1], timeout)
        sm.shot("ipxe")
        sm.halt()
        steps.append("%s  iPXE (Boot%04X): DHCP dalla rete di QEMU, %s scaricato in TFTP ed eseguito, "
                     "che ha chiesto %s" % (at(), n, IPXE_SCRIPT, IPXE_SCRIPT_2))

        n = boot_next("shell-csm", "CSMWrap Legacy Boot")
        disk = os.path.join(sm.tmp, "legacy.img")
        mbr_image(disk)
        # due CPU: CSMWrap ne tiene una, logica, per i suoi servizi BIOS (il "BIOS
        # proxy": senza un AP si ferma, "BIOS proxy initialization failed")
        sm.boot("csmwrap", ["-smp", "2", "-drive", "file=%s,format=raw,if=ide" % disk])
        to_payload()
        sm.wait("CSMWrap non ha avviato l'MBR del disco (niente %s sulla seriale)" % CSM_MARK.decode(),
                lambda: (sm.alive(), CSM_MARK.decode() in sm.serial_text())[1], timeout)
        sm.shot("csmwrap")
        sm.halt()
        steps.append("%s  CSMWrap (Boot%04X): il BIOS legacy ha avviato l'MBR del disco SATA, che ha scritto "
                     "sulla seriale" % (at(), n))

        # 4. i servizi runtime spostati, come da boot.efi di macOS
        if reloc_efi:
            line = reloc_test(rom, reloc_efi, out, timeout)
            steps.append("%s  %s" % (at(), line))
        # 5. l'ESRT e Secure Boot, su un'altra copia nuova della ROM
        if sb_efi:
            line = secure_boot_test(rom, sb_efi, out, timeout, esrt)
            steps.append("%s  %s" % (at(), line))
        # 6. il TPM 1.2 e il log delle misure, su un'altra copia nuova
        if tpm:
            line = tpm_test(rom, tpm, out, timeout, tpm2)
            steps.append("%s  %s" % (at(), line))
        return steps
    finally:
        sm.close()


def main():
    ap = argparse.ArgumentParser(description="Prova di fumo del payload EDK2 in QEMU q35")
    ap.add_argument("rom", help="ROM coreboot per QEMU q35 (tools/build.sh smoke)")
    ap.add_argument("--out", default="smoke", help="dove salvare schermate e seriale (default: smoke/)")
    ap.add_argument("--timeout", type=float, default=180, help="secondi per ogni passo (default 180)")
    ap.add_argument("--setup-only", action="store_true", help="solo il setup (passi 1-5)")
    ap.add_argument("--vga-mb", type=int, default=16, help="MiB della VGA di QEMU (default 16)")
    ap.add_argument("--size", help="la risoluzione attesa del setup, LxA (es. 2880x1620)")
    ap.add_argument("--reloc-test", metavar="EFI",
                    help="tools/efi/rt-reloc-test.c compilato: il passo 9 (tools/build.sh smoke)")
    ap.add_argument("--sb-test", metavar="EFI",
                    help="tools/efi/secure-boot-test.c compilato e firmato: il passo 10 (tools/build.sh smoke)")
    ap.add_argument("--esrt", metavar="GUID:VERSIONE:LSV",
                    help="la voce attesa nell'ESRT al passo 10 (versione e LSV esadecimali)")
    ap.add_argument("--sb-only", action="store_true", help="solo il passo 10 (con --sb-test e --esrt)")
    ap.add_argument("--tpm", metavar="EFI",
                    help="tools/efi/tpm-pcr-test.c compilato: il passo 11, il TPM 1.2 di swtpm e il log "
                    "TCPA (ROM con CONFIG_TPM1 e CONFIG_TPM_MEASURED_BOOT)")
    ap.add_argument("--tpm2", action="store_true",
                    help="il passo 11 con il TPM 2.0 di swtpm, banchi SHA-1 e SHA-256, e il log di "
                    "EFI_TCG2_PROTOCOL (ROM con CONFIG_TPM2 e CONFIG_TPM_MEASURED_BOOT_SHA1_BANK)")
    args = ap.parse_args()
    esrt = None
    if args.sb_test:
        if not os.path.isfile(args.sb_test):
            sys.exit("--sb-test: %s non c'e'" % args.sb_test)
        try:
            guid, version, lsv = args.esrt.split(":")
            esrt = (str(uuid.UUID(guid)), int(version, 16), int(lsv, 16))
        except (AttributeError, ValueError):
            ap.error("--sb-test vuole --esrt GUID:VERSIONE:LSV, per esempio "
                     "70eab79a-675a-42ef-9543-43abcad96275:0x01030a14:0x01030900")
    elif args.sb_only:
        ap.error("--sb-only vuole --sb-test")
    size = None
    if args.size:
        try:
            size = tuple(int(x) for x in args.size.lower().split("x"))
            assert len(size) == 2
        except (ValueError, AssertionError):
            ap.error("--size: LxA, per esempio 2880x1620")
    if not shutil.which("qemu-system-x86_64"):
        sys.exit("serve qemu-system-x86_64 (Debian/Ubuntu: apt install qemu-system-x86)")
    if args.reloc_test:
        if not os.path.isfile(args.reloc_test):
            sys.exit("--reloc-test: %s non c'e'" % args.reloc_test)
    if args.tpm2 and not args.tpm:
        ap.error("--tpm2 vuole --tpm")
    if args.tpm and not os.path.isfile(args.tpm):
        sys.exit("--tpm: %s non c'e'" % args.tpm)
    if args.reloc_test or args.sb_test or args.tpm:
        for tool in ("mformat", "mmd", "mcopy"):
            if not shutil.which(tool):
                sys.exit("serve %s per i passi 9, 10 e 11 (Debian/Ubuntu: apt install mtools)" % tool)
    try:
        steps = run(args.rom, args.out, args.timeout, args.setup_only, args.vga_mb, size,
                    args.reloc_test, args.sb_test, esrt, args.sb_only, args.tpm, args.tpm2)
    except Fail as e:
        print("smoke: FALLITO (%s): %s (schermate e seriale in %s)" % (ACCEL.upper(), e, args.out))
        return 1
    for s in steps:
        print("  ok  %s" % s)
    print("smoke: passato (%s; schermate in %s)" % (ACCEL.upper(), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
