#!/usr/bin/env python3
# qemu-smoke.py - la prova di fumo del payload: una ROM coreboot per QEMU
# q35 con l'EDK2 del W541 (tools/build.sh smoke) avviata in QEMU, per vedere
# prima di una release che il payload parte, disegna e risponde ai tasti.
#
#   python3 tools/qemu-smoke.py [--out DIR] [--timeout S] [--setup-only]
#                               [--vga-mb N] [--size WxH] [--reloc-test EFI] ROM
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
#      runtime.
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
# QEMU va con KVM se c'e' (/dev/kvm leggibile e scrivibile: i runner di
# GitHub ce l'hanno, con i permessi che build.yml da'), se no con TCG, come
# in un container o su un'altra architettura; la prova e' la stessa, in KVM
# dura un quarto. OUROBIOS_QEMU_ACCEL=tcg (o kvm) lo impone: tools/build.sh
# rifa' in TCG una prova fallita in KVM, per dire se e' il firmware o KVM.
# La CPU resta Haswell-noTSX anche in KVM: QEMU toglie quello che l'host
# non ha e lo scrive nel suo log.
import argparse
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
    want = os.environ.get("OUROBIOS_QEMU_ACCEL", "")
    if want in ("kvm", "tcg"):
        return want
    return "kvm" if os.access("/dev/kvm", os.R_OK | os.W_OK) else "tcg"


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


def run(rom, out, timeout, setup_only=False, vga_mb=16, size=None, reloc_efi=None):
    os.makedirs(out, exist_ok=True)
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
    args = ap.parse_args()
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
        for tool in ("mformat", "mmd", "mcopy"):
            if not shutil.which(tool):
                sys.exit("serve %s per il passo 9 (Debian/Ubuntu: apt install mtools)" % tool)
    try:
        steps = run(args.rom, args.out, args.timeout, args.setup_only, args.vga_mb, size,
                    args.reloc_test)
    except Fail as e:
        print("smoke: FALLITO (%s): %s (schermate e seriale in %s)" % (ACCEL.upper(), e, args.out))
        return 1
    for s in steps:
        print("  ok  %s" % s)
    print("smoke: passato (%s; schermate in %s)" % (ACCEL.upper(), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
