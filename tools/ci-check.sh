#!/bin/bash
# ci-check.sh - i controlli veloci, gli stessi della CI (check.yml e il job
# setup di build.yml). Da lanciare anche a mano prima di un push: pochi
# secondi, nessuna rete.
#
#   ./tools/ci-check.sh
#
#   1. shellcheck (livello warning) sugli script, riconosciuti dalla prima riga
#   2. Python: la sintassi dei file .py, la VPD che scrive tools/vpd.py
#      riletta uguale, una capsula letta da tools/update.py come la scrive
#      GenerateCapsule (anche del M920x, 24 MiB, con le regioni di oggi e
#      quelle di prima), il suo pacchetto fwupd e i metadati del remote
#      fwupd (tools/fwupd-cab.py), gli esiti di tools/hw-report.py su log e
#      timestamp finti (M920x e W541); su un /sys finto, la riga ME di
#      tools/update.py status (SMBIOS tipo 11) e la protezione del flash
#      (protection), sul M920x e sul W541; l'immagine di other-slot da un
#      flash finto
#   3. i workflow (actionlint, se c'e')
#   4. blobs/, assets/, legacy/ e i blob delle altre board (boards/*/blobs):
#      i file corrispondono ai loro SHA256SUMS
#   5. patches/series, patches/edk2/series e patches/lvglpkg/series: ogni
#      patch elencata c'e', ogni .patch della cartella e' elencata, ognuna e'
#      una mail di git format-patch
#   6. la chiave Optimus NVIDIA solo in blobs/opvk.inc (lista di byte con la
#      firma della chiave): non nelle patch ne' in altri file
#   7. i due defconfig del W541: diversi solo nella RAM init e nel GUID
#      dell'ESRT (cosi' mrc e nri differiscono solo li'), con IFD, ME e GbE
#      (immagine completa), EDK2 pinnato a un commit, i file in w541/ che
#      tools/build.sh copia davvero; la mappa configs/w541.fmd con le regioni
#      scrivibili nel chip da 8 MiB; i GUID e le regioni delle capsule (per
#      board) uguali in tools/update.py e tools/build.sh, il FILE_GUID di FmpDxe in
#      tools/qemu-update.py; il remote fwupd (configs/fwupd/ourobios.conf)
#      sui metadati di build.sh e ci.sh. Le altre board (boards/*/board.sh):
#      i loro defconfig con un GUID dell'ESRT ciascuno, lo stesso commit di
#      EDK2 del W541, IFD, ME e GbE, i file della loro cartella che
#      tools/build.sh copia davvero, e la mappa con le regioni scrivibili
#      nel primo chip, lo slot B e la regione RO in quello che avvia da solo
#   8. il pin di coreboot in tools/build.sh: commit intero e describe coerente,
#      lo stesso della parte RO gia' sulle macchine di ogni board
#      (configs/ro-interface.txt, BOARD_RO_INTERFACE: gli slot di una
#      capsula partono dopo quella)
#   9. le chiavi: in keys/ solo certificati e chiavi pubbliche di vboot, il
#      keyblock con la chiave dati di keys/vboot, nessuna chiave privata nei
#      file del repository
#  10. i link dei .md: i file relativi e le ancore (#titolo, come le fa
#      GitHub), anche quelli alla documentazione che tools/ci.sh mette nelle
#      note delle release (i link al ramo principale, con un'ancora)
#  11. il menu di setup delle build in work/coreboot, se ci sono (in locale,
#      dopo tools/build.sh roms; nella CI lo fa build.yml): ogni opzione in
#      una scheda sola (tools/build.sh menu)
# L'applicazione delle patch e i .config li prova check.yml (job "patches").
set -u
O="$(cd "$(dirname "$0")/.." && pwd)"
cd "${O}" || exit 1
fail=0
step() { printf '\n== %s\n' "$*"; }
bad()  { printf '  NO  %s\n' "$*"; fail=1; }
ok()   { printf '  ok  %s\n' "$*"; }

# Le board (boards/<board>/board.sh), e una variabile $2 (array: i suoi
# elementi, uno per riga) o la funzione board_defconfig $2 della board $1
boards() {
	local f
	for f in boards/*/board.sh; do
		[ -f "${f}" ] || continue
		f="${f%/board.sh}"
		echo "${f##*/}"
	done | LC_ALL=C sort
}
board_get() {
	(
		# shellcheck source=/dev/null
		. "boards/$1/board.sh" || exit 1
		if [ "$2" = defconfig ]; then
			board_defconfig "$3"
		else
			eval "printf '%s\\n' \"\${${2}[@]}\""
		fi
	)
}

# i file del repository: quelli di git se c'e', altrimenti tutto tranne .git
files() {
	if git -C "${O}" rev-parse --git-dir >/dev/null 2>&1; then
		git -C "${O}" ls-files
	else
		find . -path ./.git -prune -o -path ./work -prune -o -path ./dist -prune -o -type f -print | sed 's|^\./||'
	fi
}

step "shellcheck"
if command -v shellcheck >/dev/null 2>&1; then
	sh_files=()
	while IFS= read -r f; do
		[ -f "${f}" ] || continue
		head -1 "${f}" 2>/dev/null | grep -qE '^#!(/usr/bin/env[[:space:]]+|/bin/)(ba)?sh([[:space:]]|$)' \
			&& sh_files+=("${f}")
	done < <(files)
	if shellcheck -S warning "${sh_files[@]}"; then
		ok "${#sh_files[@]} script"
	else
		bad "shellcheck: vedi sopra"
	fi
else
	bad "shellcheck non installato (Debian/Ubuntu: apt install shellcheck)"
fi

step "Python"
if command -v python3 >/dev/null 2>&1; then
	py_files=()
	while IFS= read -r f; do
		case "${f}" in *.py) [ -f "${f}" ] && py_files+=("${f}") ;; esac
	done < <(files)
	if python3 - "${py_files[@]}" <<'EOF'
import ast
import sys
for f in sys.argv[1:]:
    with open(f, encoding="utf-8") as fh:
        ast.parse(fh.read(), f)
EOF
	then
		ok "${#py_files[@]} file .py"
	else
		bad "Python: errore di sintassi, vedi sopra"
	fi
	# La regione RO_VPD che scrive tools/vpd.py (lunghezze di uno e piu'
	# byte, UUID binario) si rilegge uguale, e una regione vuota resta vuota
	if python3 - <<'EOF'
import sys
import uuid
sys.dont_write_bytecode = True
sys.path.insert(0, "tools")
import vpd
entries = [("serial_number", b"R90ABCDE"), ("system_uuid", uuid.uuid4().bytes_le),
           ("k" * 200, b"v" * 300)]
assert vpd.parse_region(vpd.encode_region(entries, 0x4000)) == (entries, 0)
assert vpd.parse_region(b"\xff" * 0x4000) == ([], None)
EOF
	then
		ok "tools/vpd.py: VPD scritta e riletta"
	else
		bad "tools/vpd.py: la VPD scritta non si rilegge uguale"
	fi
	# --from-lenovo: le variabili DmiVar di una NVRAM AMI finta, con un numero
	# di serie cambiato dopo (voce di soli dati in fondo alla catena dei next)
	# e una voce non valida, che non conta
	if python3 - <<'EOF'
import struct
import sys
import uuid
sys.dont_write_bytecode = True
sys.path.insert(0, "tools")
import vpd
def nvar(name, data, attr=0x83, nxt=0xFFFFFF):
    body = (b"\0" + name.encode() + b"\0" if name else b"") + data
    return b"NVAR" + struct.pack("<H", 10 + len(body)) + nxt.to_bytes(3, "little") + bytes([attr]) + body
u = uuid.uuid4()
first = nvar("DmiVar0100010700", b"PC0ABCDE\0")
mtm = nvar("DmiVar0100010500", b"10S2S00V00\0")
newer = nvar(None, b"PC0XYZ12\0", attr=0x88)
serial = nvar("DmiVar0100010700", b"PC0ABCDE\0", nxt=len(first) + len(mtm))
buf = b"\xff" * 64 + serial + mtm + newer + nvar("DmiVar0100010800", u.bytes_le) \
    + nvar("DmiVar0200020700", b"BOARD\0", attr=0x03) + b"\xff" * 64
key = b"ABCDE-FGHIJ-KLMNO-PQRST-UVWXY"
oa3 = struct.pack("<5I", 1, 0, 1, 0, len(key)) + key
buf += nvar("RomHoleReplaceOA3Var", oa3)
assert vpd.lenovo_dmi(buf) == {"serial": b"PC0XYZ12\0", "mtm": b"10S2S00V00\0", "uuid": u.bytes_le,
                               "oa3": oa3}
assert vpd.lenovo_dmi(b"\xff" * 4096) == {}
EOF
	then
		ok "tools/vpd.py: --from-lenovo legge le DmiVar e la chiave OA3 di una NVRAM AMI"
	else
		bad "tools/vpd.py: --from-lenovo non legge le DmiVar come deve"
	fi
	# other-slot: le build di prova della CI accanto alle release, solo li';
	# la variante di una build, che dice se il training della RAM resta
	if python3 - <<'EOF'
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, "tools")
import update
data = b"\xff" * 16 + b"ouroBIOS-v1.4.0-rc3-m920x-fsp\0" + b"ouroBIOS-ci-143-7125dcb-m920x-fsp\0"
area = (0, len(data))
assert update.region_releases(data, area) == ["ouroBIOS-v1.4.0-rc3-m920x-fsp"]
assert update.region_builds(data, area) == ["ouroBIOS-v1.4.0-rc3-m920x-fsp", "ouroBIOS-ci-143-7125dcb-m920x-fsp"]
assert update.build_key_or_ci("ouroBIOS-ci-143-7125dcb-m920x-fsp") >= update.RO_COMMON
assert update.build_key_or_ci("ouroBIOS-v1.3.8-mrc") < update.RO_COMMON
assert update.build_flavour("ouroBIOS-ci-143-7125dcb-m920x-fsp", 0) == "m920x-fsp"
assert update.build_flavour("ouroBIOS-v1.3.8-mrc", 0) == "mrc"
assert update.build_flavour("?", 24 << 20) == "m920x-fsp" and update.build_flavour("?", 1) is None
# i nomi delle rc e della CI della nri (prima diventavano "mrc", la prima
# variante da 12 MiB), e una dimensione di due varianti: non si sa
assert update.build_flavour("ouroBIOS-v1.4.0-rc4-nri", 12 << 20) == "nri"
assert update.build_flavour("ouroBIOS-ci-150-ecbf45d-nri", 12 << 20) == "nri"
assert update.build_flavour("ouroBIOS-ci-150-ecbf45d-mrc", 12 << 20) == "mrc"
assert update.build_flavour("ouroBIOS-v1.4.0-rc4-m920x-fsp", 24 << 20) == "m920x-fsp"
assert update.build_flavour("?", 12 << 20) is None
assert "RW_MRC_CACHE" in update.CURRENT_REGIONS["nri"] and "RW_MRC_CACHE" not in update.CURRENT_REGIONS["m920x-fsp"]
EOF
	then
		ok "tools/update.py: other-slot riconosce anche le build di prova della CI e le rc della nri"
	else
		bad "tools/update.py: other-slot non riconosce le build della CI come deve"
	fi
	# other-slot su un flash finto (24 MiB, M920x; 12 MiB, W541) e una
	# release: lo slot che non gira e RW_NVRAM cambiati, RW_MRC_CACHE com'era
	# sul M920x, vuota con --retrain, sul W541 e per una release del M920x di
	# prima della rc4; il comando di flashrom con quelle regioni soltanto, e il
	# riavvio subito
	if python3 - <<'EOF'
import contextlib
import io
import os
import shutil
import struct
import sys
import tempfile
sys.dont_write_bytecode = True
root = tempfile.mkdtemp()
# senza /sys: nessun bios_version da confrontare, nessun controller SPI
os.environ["W541_UPDATE_SYSROOT"] = root
sys.path.insert(0, "tools")
import update

# le aree negli ultimi 12 MiB del flash, come sul M920x
LAYOUT = (("RW_MRC_CACHE", 0x0, 0x10000), ("SMMSTORE", 0x10000, 0x80000), ("RW_NVRAM", 0xa0000, 0x10000),
          ("RW_SECTION_A", 0xc0000, 0x520000), ("FW_MAIN_A", 0xd0000, 0x50ffc0),
          ("RW_SECTION_B", 0x5e0000, 0x520000), ("FW_MAIN_B", 0x5f0000, 0x50ffc0),
          ("WP_RO", 0xb00000, 0x100000), ("FMAP", 0xb00000, 0x800))


def flash(size, ro, a, b, cache, nvram=True):
    base = size - 0xc00000
    areas = {n: (base + o, s) for n, o, s in LAYOUT}
    img = bytearray(b"\xff" * size)
    fmap = b"__FMAP__" + struct.pack("<BBQI32sH", 1, 1, 0, size, b"FLASH", len(areas))
    fmap += b"".join(struct.pack("<II32sH", o, s, n.encode(), 0) for n, (o, s) in areas.items())
    img[areas["FMAP"][0]:areas["FMAP"][0] + len(fmap)] = fmap
    for area, name, fill in (("WP_RO", ro, 0x33), ("RW_SECTION_A", a, 0xaa), ("RW_SECTION_B", b, 0xbb)):
        o = areas[area][0] + (0x20000 if area == "WP_RO" else 0x10000)
        img[o:o + 0x1000] = bytes([fill]) * 0x1000
        img[o + 0x1000:o + 0x1000 + len(name)] = name.encode()
    o = areas["RW_MRC_CACHE"][0]
    img[o:o + len(cache)] = cache
    o = areas["SMMSTORE"][0]
    img[o:o + 8] = b"settings"
    if nvram:
        # un record: gira lo slot A
        rec = bytearray(16)
        rec[0] = 0x40
        rec[15] = update.nv_crc8(rec[:15])
        o = areas["RW_NVRAM"][0]
        img[o:o + 16] = rec
    return img, areas


def other_slot(size, fl, retrain, new=4):
    rc = lambda n: "ouroBIOS-v1.4.0-rc%d-%s" % (n, fl)
    dump, areas = flash(size, rc(3), rc(3), rc(2), b"MRCd" + bytes(range(256)) * 16)
    rel, _ = flash(size, rc(new), rc(new), rc(new), b"", nvram=False)
    paths = [os.path.join(root, n) for n in ("dump.bin", "release.rom", "out.rom")]
    for path, data in zip(paths, (dump, rel)):
        open(path, "wb").write(bytes(data))
    out = io.StringIO()
    args = type("A", (), {"dump": paths[0], "image": paths[1], "out": paths[2], "force": False,
                          "retrain": retrain})()
    with contextlib.redirect_stdout(out):
        update.cmd_other_slot(args)
    new = open(paths[2], "rb").read()
    region = lambda data, n: bytes(data[areas[n][0]:sum(areas[n])])
    assert region(new, "RW_SECTION_B") == region(rel, "RW_SECTION_B"), "slot B non dalla release"
    for n in ("RW_SECTION_A", "WP_RO", "SMMSTORE"):
        assert region(new, n) == region(dump, n), n
    st = update.nv_state(region(new, "RW_NVRAM"))
    assert st["valid"] and st["try_next"] == 1 and st["try_count"] == 2, st
    cmd = [l for l in out.getvalue().splitlines() if "flashrom -p internal" in l]
    assert len(cmd) == 1, out.getvalue()
    return (region(new, "RW_MRC_CACHE") == region(dump, "RW_MRC_CACHE"),
            not region(new, "RW_MRC_CACHE").strip(b"\xff"), cmd[0], out.getvalue())


kept, empty, cmd, text = other_slot(24 << 20, "m920x-fsp", False)
assert kept and cmd.endswith("--fmap -i RW_SECTION_B -i RW_NVRAM -w %s/out.rom" % root), cmd
assert "Riavvia subito dopo flashrom, senza sospendere" in text and "rifai l'immagine con --retrain" in text, text
kept, empty, cmd, text = other_slot(24 << 20, "m920x-fsp", True)
assert empty and "--fmap -i RW_SECTION_B -i RW_MRC_CACHE -i RW_NVRAM -w" in cmd, cmd
kept, empty, cmd, text = other_slot(12 << 20, "mrc", False)
assert empty and "--fmap -i RW_SECTION_B -i RW_MRC_CACHE -i RW_NVRAM -w" in cmd, cmd
# una release del M920x di prima della rc4: la sua capsula lo svuotava
kept, empty, cmd, text = other_slot(24 << 20, "m920x-fsp", False, new=3)
assert empty and "--fmap -i RW_SECTION_B -i RW_MRC_CACHE -i RW_NVRAM -w" in cmd, cmd
shutil.rmtree(root)
EOF
	then
		ok "tools/update.py: other-slot su un flash finto (M920x: RW_MRC_CACHE resta, vuota con --retrain o verso la rc3; W541: vuota)"
	else
		bad "tools/update.py: other-slot non prepara l'immagine come deve"
	fi
	# tools/hw-report.py senza la macchina, su log e timestamp finti: la RAM
	# init lenta con la cache valida (la ci-150) e' un FAIL, quella del
	# training no; i messaggi noti del log di coreboot non contano, un errore si';
	# le opzioni tornate ai default sono un evento (INFO), e il microcode che
	# con PRMRR il log dice di una revisione in meno e' quello del CBFS
	if python3 - <<'EOF'
import importlib.util
import sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("hw_report", "tools/hw-report.py")
hw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw)


def firmware(board, log, ts):
    fw = hw.Firmware.__new__(hw.Firmware)
    fw.cbmem, fw.bios, fw.board, fw.total_line = None, "ouroBIOS-ci-150-ecbf45d-m920x-fsp", board, None
    fw.log, fw.ts = log, ts
    return fw


def ram(fw):
    rep = hw.Report()
    hw.check_raminit(fw, rep)
    return rep.checks[0]["status"], rep.checks[0]["data"]["cache"]


ts = lambda t: [(0, 15212, 0, "1st timestamp"), (950, 765277, 0, "calling FspMemoryInit"),
                (951, 765277 + t, t, "returning from FspMemoryInit"), (99, 24439663, 0, "selfboot jump")]
valid = ["[DEBUG]  MRC: Checking cached data update for 'RW_MRC_CACHE'.",
         "[DEBUG]  MRC: 'RW_MRC_CACHE' does not need update."]
train = ["[INFO ]  MRC: version mismatch: 7007420 vs 7007430", "[DEBUG]  MRC: updated 'RW_MRC_CACHE'."]
assert ram(firmware("m920x", valid, ts(15242599))) == ("FAIL", "valid")
assert ram(firmware("m920x", valid, ts(3000000))) == ("WARN", "valid")
assert ram(firmware("m920x", valid, ts(230000))) == ("PASS", "valid")
assert ram(firmware("m920x", train, ts(21070000))) == ("INFO", "training")
assert ram(firmware("m920x", ["[DEBUG]  S3 Resume"], ts(150000))) == ("PASS", "s3")
rep = hw.Report()
hw.check_boot_time(firmware("m920x", valid, ts(15242599)), rep)
assert rep.checks[0]["status"] == "FAIL"
rep = hw.Report()
hw.check_boot_time(firmware("m920x", valid + [
    "[INFO ]  MOR: MemoryOverwriteRequestControl = 0x00",
    "[INFO ]  DRAM clear: option when the OS asks, request of the OS no: not clearing"], ts(230000)), rep)
assert any(d.startswith("Clear memory at power-on: When the OS asks, richiesta del sistema operativo (MOR) no: "
                        "memoria non cancellata") for d in rep.checks[0]["details"]), rep.checks[0]["details"]
rep = hw.Report()
hw.check_boot_time(firmware("m920x", valid + ["[INFO ]  DRAM clear: option always: clearing"], ts(230000)), rep)
assert "Clear memory at power-on: Always: memoria cancellata (~0.5 s ogni 10 GB)" in rep.checks[0]["details"], \
    rep.checks[0]["details"]
rep = hw.Report()
hw.check_fw_log(firmware("m920x", ["[WARN ]  CBFS: 'fallback/slic' not found.",
                                   "[ERROR]  EC: the CPU fan does not turn (0 rpm): fan failure"], []), rep)
assert rep.checks[0]["status"] == "FAIL" and "noto" in rep.checks[0]["details"][0]
assert hw.separator_pcr("sha256").startswith("3D458CFE55CC03EA")
assert hw.redact("PC0ZK26") == "****ZK26" and hw.redact("ab") == "****"
rep = hw.Report()
hw.check_fw_log(firmware("m920x", ["[WARN ]  Setup options: 31 reset to defaults (RTC power lost)",
                                   "[WARN ]  CBFS: 'fallback/slic' not found."], []), rep)
assert rep.checks[0]["status"] == "INFO" and "evento" in rep.checks[0]["details"][0], rep.checks[0]


class NoMsr:
    def read(self, cpu, reg):
        return None


rep = hw.Report()
hw.check_cpu(firmware("m920x", ["[DEBUG]  microcode: sig=0x906eb pf=0x2 revision=0xf5",
                                "[INFO ]  AP: slot 1 apic_id 2, MCU rev: 0x000000f5",
                                "[DEBUG]  Skip microcode update"], []), rep, NoMsr())
assert rep.checks[0]["data"]["firmware_microcode"] == [0xf6], rep.checks[0]
assert "coreboot 0xf6 (il log dice 0xf5" in rep.checks[0]["details"][0], rep.checks[0]["details"]
EOF
	then
		ok "tools/hw-report.py: soglie della RAM init e del tempo di avvio, messaggi noti ed eventi del log, microcode con PRMRR"
	else
		bad "tools/hw-report.py: i controlli non danno gli esiti attesi"
	fi
	# tools/hw-report.py sul W541, su log costruiti con le stringhe esatte dei
	# printk dei sorgenti (nessun log vero di un W541 nel repository): la riga
	# CRIT del ME ridotto da me_cleaner e' nota, "ME is not ready!" della NRI
	# no; la RAM init della NRI con i suoi timestamp e, sugli slot di prima,
	# la romstage; il training salvato della NRI; la protezione dal log, senza
	# i registri, solo INFO; ME-01 dalle stringhe OEM del W541 e me_disable;
	# la versione dell'EC (CVE-2019-6171); l'offset TCC in CPU-01
	if python3 - <<'EOF'
import importlib.util
import os
import shutil
import struct
import sys
import tempfile
sys.dont_write_bytecode = True
root = tempfile.mkdtemp()
# prima di caricare hw-report.py, che importa update.py
os.environ["W541_UPDATE_SYSROOT"] = root
sys.path.insert(0, "tools")
spec = importlib.util.spec_from_file_location("hw_report", "tools/hw-report.py")
hw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw)
update = hw.update
MRC, NRI = "ouroBIOS-ci-150-ecbf45d-mrc", "ouroBIOS-v1.4.0-rc4-nri"


def firmware(log, ts=(), bios=MRC, board="w541", raw=None, spi=None):
    fw = hw.Firmware.__new__(hw.Firmware)
    fw.cbmem, fw.bios, fw.board, fw.total_line = None, bios, board, None
    fw.log, fw.ts = log, list(ts)
    fw.raw = lambda cbmem_id: (raw or {}).get(cbmem_id)
    if spi is not None:
        fw.spi = spi
    return fw


def run(fn, fw, *a):
    rep = hw.Report()
    fn(fw, rep, *a)
    return rep.checks[0] if rep.checks else None


banner = lambda stage, level: ("[NOTE ]  coreboot-26.09-438-g206078d6d990-%s Fri Oct 30 12:00:00 UTC 2026 x86_32 "
                               "%s starting (log level: %d)..." % (MRC, stage, level))
# mrc, training salvato: mrc_cache.c, lynxpoint/me.c:692/836/981, vpd.c:87,
# cbfs.c:84, spi.c:1072, lockdown.c:68
cached = [banner("ramstage", 7),
          "[DEBUG]  MRC: Checking cached data update for 'RW_MRC_CACHE'.",
          "[DEBUG]  MRC: 'RW_MRC_CACHE' does not need update.",
          "[CRIT ]  intel_me_path: mbp is not ready!",
          "[NOTE ]  ME: BIOS path: Error",
          "[ERROR]  ME: MBP not ready",
          "[WARN ]  RO_VPD is uninitialized.",
          "[WARN ]  CBFS: 'fallback/slic' not found.",
          "[INFO ]  spi_flash_protect: FPR 0 is enabled for range 0x00b60000-0x00bfffff",
          "[INFO ]  BM-LOCKDOWN: Enabled bootmedia protection"]
ts = lambda *t: [(i, us, 0, n) for i, us, n in t]
ts_mrc = ts((0, 0, "1st timestamp"), (1, 400000, "start of romstage"), (2, 450000, "before RAM initialization"),
            (3, 1300000, "after RAM initialization"), (4, 1500000, "end of romstage"),
            (10, 1550000, "start of ramstage"), (90, 3250000, "starting to load payload"),
            (99, 3400000, "selfboot jump"))
c = run(hw.check_fw_log, firmware(cached, ts_mrc))
assert c["status"] == "PASS" and c["summary"].endswith("0 non noti"), c
assert any("intel_me_path" in d and "noto: ME ridotto da me_cleaner" in d for d in c["details"]), c["details"]
c = run(hw.check_raminit, firmware(cached, ts_mrc))
assert (c["status"], c["data"]["cache"]) == ("PASS", "valid") and c["summary"].startswith("RAM init 0.85 s"), c
assert run(hw.check_boot_time, firmware(cached, ts_mrc))["status"] == "PASS"
# un errore non noto resta FAIL; "ME is not ready!" della NRI (early_me.c:51,
# l'attesa di 1 s dell'UMA) non e' noto finche' un W541 vero non lo mostra
for line in ("[CRIT ]  Failed to recover CBMEM in S3 resume.", "[ERROR]  ME is not ready!"):
    c = run(hw.check_fw_log, firmware(cached + [line], ts_mrc))
    assert c["status"] == "FAIL" and c["summary"].endswith("1 non noti"), (line, c)
# nri, il primo avvio dopo un aggiornamento: il training (fino a un minuto)
train = [banner("ramstage", 7), "[NOTE ]  MRC: no data in 'RW_MRC_CACHE'",
         "[NOTE ]  CPU was replaced, forcing a cold boot",
         "[DEBUG]  MRC: Checking cached data update for 'RW_MRC_CACHE'.",
         "[DEBUG]  MRC: cache data 'RW_MRC_CACHE' needs update.", "[DEBUG]  MRC: updated 'RW_MRC_CACHE'."]
ts_train = ts((0, 0, "1st timestamp"), (1, 400000, "start of romstage"), (2, 450000, "before RAM initialization"),
              (3, 29950000, "after RAM initialization"), (4, 30400000, "end of romstage"),
              (10, 30450000, "start of ramstage"), (90, 32100000, "starting to load payload"),
              (99, 32300000, "selfboot jump"))
c = run(hw.check_raminit, firmware(train, ts_train, NRI))
assert (c["status"], c["data"]["cache"]) == ("INFO", "training") and c["summary"].startswith("RAM init 29.50 s"), c
c = run(hw.check_boot_time, firmware(train, ts_train, NRI))
assert c["status"] == "PASS" and "2.80 s senza il training" in c["summary"], c
# uno slot della NRI senza i timestamp della RAM init: tutta la romstage
old = [t for t in ts_train if t[0] not in (2, 3)]
c = run(hw.check_raminit, firmware(train, old, NRI))
assert c["status"] == "INFO" and c["summary"].startswith("romstage (RAM init compresa) 30.00 s"), c
c = run(hw.check_boot_time, firmware(train, old, NRI))
assert c["status"] == "PASS" and "2.30 s senza il training" in c["summary"], c
# nri, avvio veloce con il training salvato (raminit_native.c:151)
fast = [banner("ramstage", 7), "[INFO ]  Using cached memory parameters",
        "[DEBUG]  MRC: 'RW_MRC_CACHE' does not need update."]
ts_fast = ts((0, 0, "1st timestamp"), (1, 400000, "start of romstage"), (2, 450000, "before RAM initialization"),
             (3, 700000, "after RAM initialization"), (4, 900000, "end of romstage"),
             (10, 950000, "start of ramstage"), (90, 2650000, "starting to load payload"),
             (99, 2800000, "selfboot jump"))
assert run(hw.check_raminit, firmware(fast, ts_fast, NRI))["status"] == "PASS"
# solo la riga della NRI, senza quelle DEBUG della cache (log level 6)
c = run(hw.check_raminit, firmware([banner("ramstage", 6), fast[1]], ts_fast, NRI))
assert (c["status"], c["data"]["cache"]) == ("PASS", "valid") and "NRI" in c["details"][0], c
c = run(hw.check_raminit, firmware([banner("ramstage", 6)], ts_fast, NRI))
assert c["data"]["cache"] == "unknown" and any("Console Log Level" in d for d in c["details"]), c
# TPM 1.2: il PCR0 con il solo separatore
assert hw.separator_pcr("sha1") == "B2A83B0EBF2F8374299A5B2BDFC31EA955AD7236"
# GPLV e il _DSM di iwlwifi non sono piu' noti (patch 0068 e 0069)
for msg in ("ACPI Warning: SystemIO range 0x0000000000000480-0x00000000000004AF conflicts with OpRegion "
            "0x0000000000000480-0x00000000000004EB (\\_SB.PCI0.GPLV) (20240827/utaddress-204)",
            "ACPI: \\: failed to evaluate _DSM bf0212f2-788f-c64d-a5b3-1f738e285ade (0x1001)"):
    assert hw.known(msg, hw.KNOWN_KERNEL, "w541") is None, msg

# FLASH-01 senza i registri (kernel con IO_STRICT_DEVMEM): il PR dal log
# confrontato con WP_RO della FMAP di CBMEM, INFO e non PASS (FLOCKDN non noto)
fmap_areas = (("SI_BIOS", 0x500000, 0x700000), ("WP_RO", 0xb60000, 0xa0000), ("FMAP", 0xb60000, 0x800))
fmap = b"__FMAP__" + struct.pack("<BBQI32sH", 1, 1, 0, 12 << 20, b"FLASH", len(fmap_areas))
fmap += b"".join(struct.pack("<II32sH", o, s, n.encode(), 0) for n, o, s in fmap_areas)
eperm = {"root": True, "ctrl": "lpt", "bios_cntl": 0x09, "regs": None, "options": dict.fromkeys(update.LOCK_OPTIONS),
         "options_note": "non lette", "board_options": {"me_disable": None},
         "error": "registri SPI non leggibili da /dev/mem (Operation not permitted); kernel con IO_STRICT_DEVMEM: "
                  "per questa sola verifica avvia una volta con iomem=relaxed, poi toglilo (da confermare su un "
                  "W541)"}
c = run(hw.check_flash, firmware(cached, raw={hw.CBMEM_ID_FMAP: fmap}, spi=eperm))
assert c["status"] == "INFO" and c["summary"].startswith("WP_RO protetto all'avvio secondo il log (PR0 dal log"), c
assert "BIOS Lock: spento: il sistema puo' scrivere il flash" in c["details"], c["details"]
assert c["data"] == {"wp_ro_protected": False, "wp_ro_from_log": "PR0", "option_off": False}, c["data"]
# nessun controller conosciuto: lo stesso, dal log
c = run(hw.check_flash, firmware(cached, raw={hw.CBMEM_ID_FMAP: fmap}, spi=None))
assert c["status"] == "INFO" and "PR0 dal log" in c["summary"], c
# il log senza il PR, la protezione accesa: INFO, registri non letti
c = run(hw.check_flash, firmware(cached[:-2] + cached[-1:], raw={hw.CBMEM_ID_FMAP: fmap}, spi=eperm))
assert c["status"] == "INFO" and c["summary"] == "protezione accesa secondo il log (registri non letti)", c

# ME-01 sul W541: le stringhe OEM di mainboard/lenovo/haswell (HFS e HFS2 di
# un X220 con me_cleaner, non di un W541), l'HECI nascosta da me_disable
d = os.path.join(root, "sys/firmware/dmi/entries/11-0")
os.makedirs(d)
heci = os.path.join(root, "sys/bus/pci/devices/0000:00:16.0")
ec = "IBM ThinkPad Embedded Controller -[%-17s]-" % "GMHT30WW-1.0"


def type11(*strings):
    open(os.path.join(d, "raw"), "wb").write(bytes([11, 5, 0x09, 0x00, len(strings)]) +
                                             b"".join(s.encode() + b"\0" for s in strings) + b"\0")


me = ("ME: Disabled (AltMeDisable, BUP)", "ME HFSTS: %08X %08X %08X %08X %08X %08X" % (0x00020191, 0x100A0000, 0, 0,
                                                                                      0, 0))
type11(*me + (ec,))
lpt = lambda opt: dict(eperm, board_options={"me_disable": opt})
c = run(hw.check_me, firmware(cached, spi=lpt(None)))
assert c["status"] == "PASS" and c["summary"].startswith("disattivata (AltMeDisable, BUP), stato di lavoro 1"), c
assert c["summary"].endswith("HECI nascosta, come chiede me_disable"), c
assert "opzione me_disable: 1, il default (DISABLE_ME_PCI)? SMMSTORE non letta" in c["details"], c["details"]
# HECI visibile: con SMMSTORE non letta non si sa (INFO); con me_disable a 1
# in SMMSTORE, o lo store letto senza la variabile (o vuoto: coreboot ha
# usato il default, acceso), si' (WARN)
os.makedirs(heci)
c = run(hw.check_me, firmware(cached, spi=lpt(None)))
assert c["status"] == "INFO" and "visibile con me_disable non letto (default acceso)" in c["summary"], c
assert run(hw.check_me, firmware(cached, spi=lpt(1)))["status"] == "WARN"
for note in (None, "SMMSTORE vuota"):
    c = run(hw.check_me, firmware(cached, spi=dict(lpt(None), store_read=True, options_note=note)))
    assert c["status"] == "WARN" and c["summary"].endswith("HECI 00:16.0 visibile con me_disable al default, acceso"), c
    assert "opzione me_disable: 1, il default (DISABLE_ME_PCI): non impostata in SMMSTORE%s" % (
        " (SMMSTORE vuota)" if note else "") in c["details"] and c["data"]["me_disable_known"], c["details"]
c = run(hw.check_me, firmware(cached, spi=lpt(0)))
assert c["status"] == "PASS" and c["summary"].endswith("HECI visibile, driver -"), c
# un ME fermo nel BUP per un altro motivo: WARN; HECI non letta dal firmware: INFO
type11("ME: Stopped in BUP (state 0x18)", "ME HFSTS: 00003001 10180000 00000000 00000000 00000000 00000000", ec)
c = run(hw.check_me, firmware(cached, spi=lpt(0)))
assert c["status"] == "WARN" and c["summary"].startswith("ferma nel BUP (stato 0x18)"), c
type11("ME: Not available", ec)
c = run(hw.check_me, firmware(cached, spi=lpt(0)))
assert c["status"] == "INFO" and c["summary"].startswith("non letta dal firmware"), c
# senza le stringhe (uno slot di prima): le righe del log, o SKIP con il livello
shutil.rmtree(heci)
type11(ec)
log = cached + ["[DEBUG]  ME: Current Working State   : Initializing",
                "[DEBUG]  ME: Current Operation Mode  : Debug",
                "[DEBUG]  ME: Progress Phase          : BUP Phase",
                "[DEBUG]  ME: Progress Phase State    : Check to see if straps say ME DISABLED"]
c = run(hw.check_me, firmware(log, spi=lpt(None)))
assert c["status"] == "INFO" and c["summary"].startswith("operation mode Debug, working state Initializing"), c
c = run(hw.check_me, firmware([banner("ramstage", 6)], spi=lpt(None)))
assert c["status"] == "SKIP" and any("Console Log Level" in x for x in c["details"]), c
# la riga del log della copia dei registri, senza SMBIOS
c = run(hw.check_me, firmware(cached + ["[DEBUG]  ME: HFSTS1-6: 00020191 100a0000 00000000 00000000 00000000 "
                                        "00000000"], spi=lpt(None)))
assert c["status"] == "PASS" and c["summary"].startswith("disattivata (AltMeDisable, BUP)"), c

# EC-01: GMHT30WW (1.15) dal log di h8.c, piu' vecchio dalla stringa OEM
h8 = "[INFO ]  H8: EC Firmware ID %s, Version %d.%d%d%c" % ("GMHT30WW-1.0", 1, 1, 5, "A")
c = run(hw.check_ec, firmware(cached + [h8]))
assert c["status"] == "PASS" and c["data"] == {"ec": "GMHT30WW", "min": "GMHT30WW"}, c
type11(*me + ("IBM ThinkPad Embedded Controller -[%-17s]-" % "GMHT29WW-1.0",))
c = run(hw.check_ec, firmware(cached))
assert c["status"] == "WARN" and "CVE-2019-6171" in c["summary"] and "GMHT29WW" in c["summary"], c
assert any("programmatore esterno" in x for x in c["details"]), c["details"]
type11("IBM ThinkPad Embedded Controller -[%-17s]-" % "G2HT35WW-1.0")
assert run(hw.check_ec, firmware(cached))["status"] == "INFO"
type11(*me)
assert run(hw.check_ec, firmware(cached))["status"] == "SKIP"
assert run(hw.check_ec, firmware(cached, board="m920x")) is None


# CPU-01: l'offset TCC, solo nei dettagli (bit 27:24 sul W541, 29:24 sul M920x)
class Msr:
    def __init__(self, regs):
        self.regs = regs

    def read(self, cpu, reg):
        return self.regs.get(reg)


base = {0x606: 0xA0E03, 0x610: (1 << 15) | (47 * 8), 0x1AD: 38}
c = run(hw.check_cpu, firmware(cached), Msr({**base, 0xCE: 0x10002700, 0x1A2: 0x00640000}))
assert c["data"]["tcc_programmable"] is False and c["data"]["tcc_offset"] == 0, c["data"]
assert any(x.startswith("offset TCC programmabile: no (PLATFORM_INFO bit 30), offset attuale 0 (MSR 0x1A2 bit "
                        "27:24); sul W541") for x in c["details"]), c["details"]
c = run(hw.check_cpu, firmware([], board="m920x"), Msr({**base, 0xCE: 1 << 30, 0x1A2: 0x2a640000}))
assert c["data"]["tcc_programmable"] and c["data"]["tcc_offset"] == 0x2a, c["data"]
shutil.rmtree(root)
EOF
	then
		ok "tools/hw-report.py sul W541: messaggi noti del ME, RAM init della NRI (training, slot senza timestamp, cache), protezione dal log, ME-01 con me_disable e le stringhe OEM, EC 1.15, offset TCC"
	else
		bad "tools/hw-report.py: i controlli del W541 non danno gli esiti attesi"
	fi
	# Una capsula con la struttura di GenerateCapsule (firma finta) letta da
	# tools/update.py: variante, versioni, regioni del manifest RMAP, immagine.
	# Del M920x (24 MiB): info vuole le regioni di oggi, stage accetta anche
	# quelle delle v1.4.0-rc1..rc3, che scrivono anche RW_MRC_CACHE
	if python3 - <<'EOF'
import struct
import sys
import uuid
sys.dont_write_bytecode = True
sys.path.insert(0, "tools")
import update


def capsule(variant, image, regions, version=0x01020302, lsv=0x01020000):
    rmap = b"".join(r.encode().ljust(16, b"\0") for r in regions)
    rmap += struct.pack("<IHH", update.RMAP_SIGNATURE, 1, len(regions))
    payload = struct.pack("<4sIII", b"MSS1", 16, version, lsv) + image + rmap
    cert = b"\x30" * 100
    auth = struct.pack("<QIHH", 7, 24 + len(cert), 0x200, 0x0EF1) + update.PKCS7_CERT_GUID.bytes_le + cert
    item = auth + payload
    ihdr = struct.pack("<I16sB3sIIQQ", 3, update.VARIANTS[variant].bytes_le, 1, b"", len(item), 0, 0, 1)
    fmp = struct.pack("<IHHQ", 1, 0, 1, 16) + ihdr + item
    data = update.FMP_CAPSULE_GUID.bytes_le + struct.pack("<III", 32, 0x10000, 32 + len(fmp)) + bytes(4) + fmp
    return data, payload, cert


image = bytes(range(256)) * (update.ROM_SIZE // 256)
data, payload, cert = capsule("nri", image, update.REGIONS)
cap = update.parse_capsule(data)
assert (cap["variant"], cap["version"], cap["lsv"]) == ("nri", 0x01020302, 0x01020000)
assert cap["regions"] == update.REGIONS and cap["image"] == image and cap["signature"] == cert
assert cap["signed"] == payload + struct.pack("<Q", 7)
update.check_capsule(cap, {"variant": "nri", "legacy": False})
update.check_capsule(cap, current_only=True)
m920x = {"variant": "m920x-fsp", "legacy": False}
big = bytes(range(256)) * (update.FLAVOURS["m920x-fsp"][2] // 256)
mcap = update.parse_capsule(capsule("m920x-fsp", big, ["RW_SECTION_A", "RW_SECTION_B"], 0x0103ff04)[0])
assert mcap["regions"] == update.CURRENT_REGIONS["m920x-fsp"] and len(mcap["image"]) == 24 << 20
update.check_capsule(mcap, current_only=True)
update.check_capsule(mcap, m920x)
old = update.parse_capsule(capsule("m920x-fsp", big, update.REGIONS, 0x0103ff03)[0])
update.check_capsule(old, m920x)
try:
    update.check_capsule(old, current_only=True)
    raise AssertionError("info accetta una capsula del M920x con RW_MRC_CACHE")
except update.Error as e:
    assert "stage la accetta ancora" in str(e), e
for regions, size in ((["RW_SECTION_A", "RW_SECTION_B"], update.ROM_SIZE), (["RW_SECTION_A"], 24 << 20)):
    bad = update.parse_capsule(capsule("m920x-fsp", big[:size], regions)[0])
    try:
        update.check_capsule(bad, m920x)
        raise AssertionError("capsula del M920x accettata: %r, %d byte" % (regions, size))
    except update.Error:
        pass
try:
    update.check_capsule(update.parse_capsule(capsule("nri", image, update.CURRENT_REGIONS["m920x-fsp"])[0]),
                         {"variant": "nri", "legacy": False})
    raise AssertionError("capsula del W541 senza RW_MRC_CACHE accettata")
except update.Error:
    pass
assert update.version_str(0x01020302) == "v1.2.4-rc2" and update.version_quad(0x01020302) == "1.2.3.2"
assert update.version_str(0x01020300) == "v1.2.3" and update.version_str(0x0103ff01) == "v1.4.0-rc1"
# i numeri fino a v1.3.6-rc1, nel formato di prima, sono ancora sui portatili
assert update.version_str(0x01030005) == "v1.3.5" and update.version_str(0x01020003) == "v1.2.3"
assert update.version_str(0x01030006) == "v1.3.6-rc1" and update.version_str(0x01030000) == "v1.3.0"
# il pacchetto fwupd di tools/fwupd-cab.py, riletto da tools/update.py
import datetime, importlib.util
spec = importlib.util.spec_from_file_location("fwupd_cab", "tools/fwupd-cab.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)
meta = fc.metainfo("nri", str(update.VARIANTS["nri"]), "1.2.3.2", "2026-10-11", "https://example.org/")
cab = fc.make_cab([("firmware.bin", data), ("firmware.metainfo.xml", meta.encode())],
                  datetime.datetime(2026, 10, 11))
files = update.read_cab(cab)
assert files == {"firmware.bin": data, "firmware.metainfo.xml": meta.encode()}
capdata, cap2 = update.load_cab("prova.cab", cab)
assert capdata == data and cap2["version"] == 0x01020302 and cap2["cab"]["meta"]["format"] == "quad"
# un pacchetto di prima (fino a v1.3.6-rc1): "triplet", con un numero di allora
old = bytearray(data)
struct.pack_into("<I", old, old.index(b"MSS1") + 8, 0x01020003)
old_meta = meta.replace(">quad<", ">triplet<").replace('version="1.2.3.2"', 'version="1.2.3"')
_, cap3 = update.load_cab("vecchio.cab", fc.make_cab([("firmware.bin", bytes(old)), ("firmware.metainfo.xml", old_meta.encode())],
                                                    datetime.datetime(2026, 10, 11)))
assert cap3["version"] == 0x01020003 and cap3["cab"]["meta"]["format"] == "triplet"
# "triplet" con un numero di adesso: no
bad_meta = meta.replace(">quad<", ">triplet<").replace('version="1.2.3.2"', 'version="1.2.770"')
try:
    update.load_cab("misto.cab", fc.make_cab([("firmware.bin", data), ("firmware.metainfo.xml", bad_meta.encode())],
                                             datetime.datetime(2026, 10, 11)))
    raise AssertionError("triplet con un numero di adesso accettato")
except update.Error:
    pass
# i metadati del remote fwupd con quel pacchetto (e una firma finta)
import gzip, hashlib, os, tempfile
import xml.etree.ElementTree as ET
cab = fc.make_cab([("firmware.bin", data), ("firmware.metainfo.xml", meta.encode()), ("firmware.jcat", b"x")],
                  datetime.datetime(2026, 10, 11))
url = "https://github.com/o/r/releases/download/v1.2.3-nri/w541-coreboot-v1.2.3-nri.cab"
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "w541-coreboot-v1.2.3-nri.cab")
    with open(path, "wb") as f:
        f.write(cab)
    xml = fc.make_metadata([(path, url)])
    assert fc.make_metadata([(path, url)]) == xml
root = ET.fromstring(gzip.decompress(xml))
assert root.tag == "components" and len(root.findall("component")) == 1
rel = root.find("component/releases/release")
assert rel.findtext("location") == url and rel.get("version") == "1.2.3.2"
assert rel.get("timestamp") == str(int(datetime.datetime(2026, 10, 11, tzinfo=datetime.timezone.utc).timestamp()))
sums = {(c.get("type"), c.get("target"), c.get("filename")): c.text for c in rel.findall("checksum")}
assert sums == {("sha1", "container", os.path.basename(path)): hashlib.sha1(cab).hexdigest(),
                ("sha256", "container", os.path.basename(path)): hashlib.sha256(cab).hexdigest(),
                ("sha1", "content", "firmware.bin"): hashlib.sha1(data).hexdigest(),
                ("sha256", "content", "firmware.bin"): hashlib.sha256(data).hexdigest()}
assert {e.get("type"): e.text for e in rel.findall("size")} == {"download": str(len(cab)), "installed": str(len(data))}
EOF
	then
		ok "tools/update.py: capsula e pacchetto fwupd letti; tools/fwupd-cab.py: i metadati del remote"
	else
		bad "tools/update.py: la capsula di prova non si legge come atteso, o tools/fwupd-cab.py metadata sbaglia"
	fi
	# I tag di GitHub si ordinano (stage --latest), e rollback trova nello
	# slot che non gira la release a cui tornare, solo se e' piu' vecchia,
	# anche con i nomi del M920x; una copia del solo primo chip (flashrom
	# passato da /dev/mtd0) dice il modulo del kernel della sua board
	if python3 - <<'EOF'
import struct
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, "tools")
import update
assert update.release_key("v1.3.1-mrc") < update.release_key("v1.3.2-rc1-mrc") < update.release_key("v1.3.2-mrc")
assert update.release_key("v1.3.2-rc9-mrc") < update.release_key("v1.3.2-rc10-mrc") < update.release_key("v1.3.2-mrc")
assert update.build_release_key("ouroBIOS-v1.3.2-rc1-nri") < update.build_release_key("ouroBIOS-v1.3.2-nri")
areas = [("RW_NVRAM", 0x5A0000, 0x10000), ("RW_SECTION_A", 0x5C0000, 0x2D0000), ("FW_MAIN_A", 0x5D0000, 0x2C0000),
         ("RW_SECTION_B", 0x890000, 0x2D0000), ("FW_MAIN_B", 0x8A0000, 0x2C0000)]
def flash(a, b):
    img = bytearray(b"\xff" * update.ROM_SIZE)
    fmap = b"__FMAP__" + struct.pack("<BBQI32sH", 1, 1, 0, update.ROM_SIZE, b"FLASH", len(areas))
    fmap += b"".join(struct.pack("<II32sH", o, n, name.encode(), 0) for name, o, n in areas)
    img[0xB60000:0xB60000 + len(fmap)] = fmap
    img[0x5D0100:0x5D0100 + len(a)] = a
    img[0x8A0100:0x8A0100 + len(b)] = b
    rec = bytearray(16)                 # vboot: slot B provato e confermato
    rec[0], rec[7] = 0x40, (1 << 3) | (1 << 2) | 2
    rec[15] = update.nv_crc8(bytes(rec[:15]))
    img[0x5A0000:0x5A0010] = rec
    return bytes(img)
plan = update.rollback_plan(flash(b"ouroBIOS-v1.3.1-mrc", b"ouroBIOS-v1.3.2-mrc"), "ouroBIOS-v1.3.2-mrc")
assert (plan["current"], plan["other"], plan["tag"]) == ("B", "A", "v1.3.1-mrc")
for a, b in ((b"ouroBIOS-v1.3.3-mrc", b"ouroBIOS-v1.3.2-mrc"), (b"ouroBIOS-v1.3.2-mrc", b"ouroBIOS-v1.3.2-mrc"),
             (b"", b"ouroBIOS-v1.3.2-mrc"), (b"ouroBIOS-v1.3.1-nri", b"ouroBIOS-v1.3.2-mrc")):
    try:
        update.rollback_plan(flash(a, b), "ouroBIOS-v1.3.2-mrc")
    except update.Error:
        continue
    raise AssertionError("rollback accettato: %r" % a)
plan = update.rollback_plan(flash(b"ouroBIOS-v1.4.0-rc1-m920x-fsp", b"ouroBIOS-v1.4.0-rc2-m920x-fsp"),
                            "ouroBIOS-v1.4.0-rc2-m920x-fsp")
assert plan["tag"] == "v1.4.0-rc1-m920x-fsp", plan["tag"]
try:
    update.rollback_plan(flash(b"ouroBIOS-v1.4.0-rc1-m920x-fsp", b"ouroBIOS-v1.4.0-rc1-m920x-fsp"),
                         "ouroBIOS-v1.4.0-rc2-m920x-fsp")
except update.Error as e:
    assert "un altro avvio" in str(e), e
else:
    raise AssertionError("rollback accettato con un'altra release nello slot che gira")
for size, module in ((8 << 20, "spi_intel_platform"), (16 << 20, "spi_intel_pci")):
    try:
        update.need_whole_flash("dump.rom", b"\xff" * size, None)
    except update.Error as e:
        assert module in str(e), e
    else:
        raise AssertionError("copia del solo primo chip accettata: %d MiB" % (size >> 20))
EOF
	then
		ok "tools/update.py: release di GitHub in ordine, rollback verso la release dell'altro slot (W541 e M920x), copia del solo primo chip riconosciuta"
	else
		bad "tools/update.py: release_key, rollback_plan o need_whole_flash non fanno quello che devono"
	fi
	# tools/qemu-update.py senza QEMU: le variabili che scrive nello store del
	# flash (OsIndications) come le legge tools/update.py, FmpState, l'ESRT
	# della seriale e la traccia del pflash
	if python3 - <<'EOF'
import importlib.util
import os
import struct
import sys
import tempfile
import uuid
sys.dont_write_bytecode = True
sys.path.insert(0, "tools")
import update
spec = importlib.util.spec_from_file_location("qemu_update", "tools/qemu-update.py")
qu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qu)
areas = [("RW_MRC_CACHE", 0x0, 0x10000), ("SMMSTORE", 0x10000, 0x80000), ("RW_NVRAM", 0x90000, 0x10000),
         ("RW_SECTION_A", 0xA0000, 0x360000), ("FW_MAIN_A", 0xB0000, 0x34FFC0),
         ("RW_SECTION_B", 0x400000, 0x360000), ("FW_MAIN_B", 0x410000, 0x34FFC0), ("WP_RO", 0x760000, 0xA0000)]
img = bytearray(b"\xff" * 0x800000)
fmap = b"__FMAP__" + struct.pack("<BBQI32sH", 1, 1, 0, len(img), b"FLASH", len(areas))
fmap += b"".join(struct.pack("<II32sH", o, n, name.encode(), 0) for name, o, n in areas)
img[0x760000:0x760000 + len(fmap)] = fmap
st = 0x10000                       # lo store come lo formatta il payload
img[st + 0x20:st + 0x28] = struct.pack("<Q", 0x80000)
img[st + 0x28:st + 0x2C] = b"_FVH"
img[st + 0x30:st + 0x32] = struct.pack("<H", 0x48)
img[st + 0x48:st + 0x64] = update.AUTH_VAR_GUID + struct.pack("<IBBHI", 0x80000 - 0x48, 0x5A, 0xFE, 0, 0)
tmp = tempfile.TemporaryDirectory()
path = os.path.join(tmp.name, "flash.rom")
open(path, "wb").write(img)
f = qu.Flash(path)
f.set_var("OsIndications", qu.EFI_GLOBAL, 7, struct.pack("<Q", 4))
f.set_var("OsIndications", qu.EFI_GLOBAL, 7, struct.pack("<Q", 0))
f.set_var("OsIndications", qu.EFI_GLOBAL, 7, struct.pack("<Q", 4 | 1))
assert f.os_indications() == 5
found, info = update.var_store(f.region("SMMSTORE"))
states = [v["state"] for v in found if v["name"] == "OsIndications"]
assert states == [0x3D, 0x3D, 0x3F], states
guid = uuid.UUID("b195f75a-8f95-4282-950c-ee9dd1099ec9").bytes_le
f.set_var("FmpState", guid, 7, struct.pack("<4B4I", 1, 1, 1, 1, 0x01010000, 0x01000000, 0, 0x01020000))
assert f.fmp_state(guid) == {"version": 0x01010000, "lsv": 0x01000000, "status": 0, "attempt": 0x01020000}
row = ("| B195F75A-8F95-4282-950C-EE9DD1099EC9 | System FW    | 0x 1010000 | 0x 1000000 | 0x   14000 "
       "| 0x 1020000 | 0x       0 |")
assert qu.ESRT_ROW.findall(row) == [("B195F75A-8F95-4282-950C-EE9DD1099EC9", "System FW", "1010000", "1000000",
                                      "14000", "1020000", "0")]
trace = os.path.join(tmp.name, "pflash.trace")
open(trace, "w").write("pflash_data_write system.flash0: data offset:0x10010 size:1 value:0x0000\n"
                       "pflash_write_block_erase system.flash0: block erase offset:0x400000 bytes:0x1000\n"
                       "pflash_data_write system.flash0: data offset:0x90000 size:1 value:0x0040\n"
                       "pflash_data_write_block system.flash0: data offset:0xa0010 size:1 value:0x00ff "
                       "counter:0x0000000000000010\n")
hits, total = qu.traced_writes(trace, f.areas, ("WP_RO", "RW_SECTION_A", "RW_SECTION_B"))
assert total == 4 and hits == {"WP_RO": 0, "RW_SECTION_A": 1, "RW_SECTION_B": 0x1000}, (hits, total)
tmp.cleanup()
# il nome delle ROM (build.sh) e la pagina Firmware Update (edk2/0020) nella seriale
import re
assert re.fullmatch(qu.TAG_RE, "ouroBIOS-v1.3.0-mrc+update-test-D")
line = ("FirmwareUpdate: slot A runs ouroBIOS-v1.3.0-mrc+update-test-D, slot B holds "
        "ouroBIOS-v1.1.0-mrc+update-test-B\r\n")
assert qu.UpdateTest.FW_PAGE.search(line).groups() == ("A", "ouroBIOS-v1.3.0-mrc+update-test-D", "B",
                                                        "ouroBIOS-v1.1.0-mrc+update-test-B")
EOF
	then
		ok "tools/qemu-update.py: variabili scritte nello store, FmpState, ESRT, traccia del pflash e pagina Firmware Update letti"
	else
		bad "tools/qemu-update.py: le funzioni della prova dell'aggiornamento non fanno quello che devono"
	fi
	# tools/update.py status, la riga ME: dalle stringhe OEM (SMBIOS tipo 11)
	# che scrive coreboot sul M920x, da dmi_sysfs o, senza, dalla tabella
	# intera; con la sola riga riassuntiva quella com'e'
	if python3 - <<'EOF'
import os
import shutil
import sys
import tempfile
sys.dont_write_bytecode = True
root = tempfile.mkdtemp()
# prima di import: update.py prende la radice quando lo si carica
os.environ["W541_UPDATE_SYSROOT"] = root
sys.path.insert(0, "tools")
import update


def type11(*strings):
    return bytes([11, 5, 0x09, 0x00, len(strings)]) + b"".join(s.encode() + b"\0" for s in strings) + b"\0"


me = ("ME: Disabled (soft temporary disable)",
      "ME HFSTS: 80032044 368A0106 00000030 00004000 00000000 C0000004")
assert all(len(s) <= 64 for s in me) and len(me[1]) == 63
want = ("disattivata (soft temporary disable), stato di lavoro 4, codice di errore 2; "
        "HECI (00:16.0) nascosta al sistema")
d = os.path.join(root, "sys/firmware/dmi/entries")
os.makedirs(os.path.join(d, "11-0"))
os.makedirs(os.path.join(d, "17-0"))
open(os.path.join(d, "11-0", "raw"), "wb").write(type11(*me))
open(os.path.join(d, "17-0", "raw"), "wb").write(bytes([17, 4, 0, 0]) + b"ME: no\0\0")
assert update.me_status() == want, update.me_status()
# senza dmi_sysfs: la tabella, con altre strutture prima e dopo
shutil.rmtree(d)
t = os.path.join(root, "sys/firmware/dmi/tables")
os.makedirs(t)
type0 = bytes([0, 0x18, 0, 0]) + bytes(0x14) + b"coreboot\0\0"
type1 = bytes([1, 0x1b, 1, 0]) + bytes(0x17) + b"\0\0"
end = bytes([127, 4, 0x0a, 0]) + b"\0\0"
table = lambda *mid: type0 + b"".join(mid) + type1 + end + type11("ME: dopo la fine")
open(os.path.join(t, "DMI"), "wb").write(table(type11("altro"), type11(*me)))
assert update.me_status() == want, update.me_status()
# ME acceso e HECI visibile
os.makedirs(os.path.join(root, "sys/bus/pci/devices/0000:00:16.0"))
open(os.path.join(t, "DMI"), "wb").write(table(type11(
    "ME: Enabled", "ME HFSTS: 90000245 00000000 00000030 00004000 00000000 40000004")))
assert update.me_status() == "attiva, stato di lavoro 5, codice di errore 0", update.me_status()
# solo la riga riassuntiva (HECI non letta dal firmware)
open(os.path.join(t, "DMI"), "wb").write(table(type11("ME: Not available")))
assert update.me_status() == "Not available", update.me_status()
# un firmware che non le scrive
open(os.path.join(t, "DMI"), "wb").write(table())
assert update.me_status() is None
shutil.rmtree(root)
EOF
	then
		ok "tools/update.py: la riga ME di status dalle stringhe OEM di SMBIOS (dmi_sysfs e tabella)"
	else
		bad "tools/update.py: la riga ME di status non si legge come deve dalle stringhe OEM"
	fi
	# tools/update.py status sul W541: la riga ME dalle stringhe OEM di
	# mainboard/lenovo/haswell (me_status.c, mainboard.c), tradotte; le stesse
	# regole del firmware dalle sole parole (HFS2 prima del modo: un ME fermo
	# nel BUP non e' mai "attiva"); un firmware senza le stringhe
	if python3 - <<'EOF'
import contextlib
import io
import os
import shutil
import sys
import tempfile
sys.dont_write_bytecode = True
root = tempfile.mkdtemp()
os.environ["W541_UPDATE_SYSROOT"] = root
sys.path.insert(0, "tools")
import update

# le regole di mainboard_me_summary(): HFS e HFS2 di un X220 con me_cleaner
# (HFS2 progress phase BUP, stato 0x0a, quello che coreboot ha provato)
summ = update.me9_summary
assert summ(0x00020191, 0x100A0000) == "Disabled (AltMeDisable, BUP)"
assert summ(0x00000191, 0x100A0000) == "Disabled (AltMeDisable, BUP)"      # anche col modo 0
assert summ(0x00003001, 0x10180000) == "Stopped in BUP (state 0x18)"
assert summ(0x00023191, 0x100A0000) == "Stopped in BUP (state 0x0a)"       # con un errore
assert summ(0x00000245, 0x50000000) == "Enabled"
assert summ(0x00000243, 0x50000000) == "Enabled, not ready (state 3)"
assert [summ(m << 16, 0) for m in (2, 3, 4, 5, 6)] == [
    "Debug", "Disabled (soft temporary disable)", "Security override (jumper)",
    "Security override (HECI message)", "Mode 6"]
# ogni frase del firmware ha la sua traduzione, e sta nei 64 caratteri
for s in ("Disabled (AltMeDisable, BUP)", "Stopped in BUP (state 0x18)", "Disabled (soft temporary disable)",
          "Enabled", "Enabled, not ready (state 3)", "Security override (jumper)",
          "Security override (HECI message)", "Debug", "Mode 6", "Not available"):
    assert len("ME: " + s) <= 64 and update.me9_text(s, None) != s, s
d = os.path.join(root, "sys/firmware/dmi/entries")
os.makedirs(os.path.join(d, "11-0"))


def type11(*strings):
    open(os.path.join(d, "11-0", "raw"), "wb").write(
        bytes([11, 5, 0x09, 0x00, len(strings)]) + b"".join(s.encode() + b"\0" for s in strings) + b"\0")


# come le scrive mainboard_smbios_strings(): prima dell'EC (il dispositivo
# radice viene prima), HFSTS in maiuscolo, 63 caratteri
ec = "IBM ThinkPad Embedded Controller -[%-17s]-" % "GMHT30WW-1.0"
me = ("ME: Disabled (AltMeDisable, BUP)",
      "ME HFSTS: %08X %08X %08X %08X %08X %08X" % (0x00020191, 0x100A0000, 0, 0, 0, 0))
assert all(len(s) <= 64 for s in me + (ec,)) and len(me[1]) == 63
type11(*me + (ec,))
want = ("disattivata (AltMeDisable, BUP), stato di lavoro 1, modo 2, codice di errore 0, fase 1 stato 0x0a; "
        "HECI (00:16.0) nascosta al sistema")
assert update.me_status("w541") == want, update.me_status("w541")
# il decoder del M920x non cambia
assert update.me_status().startswith("modo debug, stato di lavoro 1"), update.me_status()
type11("ME: Stopped in BUP (state 0x18)", "ME HFSTS: 00003001 10180000 00000000 00000000 00000000 00000000", ec)
assert update.me_status("w541").startswith("ferma nel BUP (stato 0x18), stato di lavoro 1, modo 0, codice di "
                                           "errore 3"), update.me_status("w541")
# HECI non letta: solo la riga riassuntiva
os.makedirs(os.path.join(root, "sys/bus/pci/devices/0000:00:16.0"))
type11("ME: Not available", ec)
assert update.me_status("w541") == "non letta dal firmware (HECI spenta o nascosta all'avvio)"
# solo le parole: la frase che direbbe il firmware
type11(me[1], ec)
assert update.me_status("w541").startswith("disattivata (AltMeDisable, BUP), stato di lavoro 1")
# status su una nri: la riga ME, e senza le stringhe la release da cui ci sono
esrt = os.path.join(root, "sys/firmware/efi/esrt/entries/entry0")
os.makedirs(esrt)
for f, v in (("fw_class", str(update.VARIANTS["nri"])), ("fw_version", "0x0103ff04"),
             ("lowest_supported_fw_version", "0x01030900"), ("last_attempt_version", "0"),
             ("last_attempt_status", "0")):
    open(os.path.join(esrt, f), "w").write(v + "\n")
os.makedirs(os.path.join(root, "sys/class/dmi/id"))
open(os.path.join(root, "sys/class/dmi/id/bios_version"), "w").write("ouroBIOS-v1.4.0-rc4-nri\n")
os.makedirs(os.path.join(root, "esp/EFI"))


def status():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        update.cmd_status(type("A", (), {"esp": os.path.join(root, "esp")})())
    return out.getvalue()


type11(*me + (ec,))
out = status()
assert "ME:        disattivata (AltMeDisable, BUP), stato di lavoro 1" in out, out
assert "protezione: non verificabile su questa macchina (solo i controller SPI del M920x e del W541)" in out, out
type11(ec)
out = status()
assert "ME:        non indicato da questo firmware (prima della v1.4.0)" in out, out
assert (update.me_strings_since("m920x-fsp"), update.me_strings_since("nri")) == (
    "v1.4.0", "v1.4.0")
assert update.me_strings_since("altro") == "release con lo stato del ME"
shutil.rmtree(root)
EOF
	then
		ok "tools/update.py: la riga ME di status sul W541 (le frasi del ME 9 tradotte, solo le parole, senza le stringhe)"
	else
		bad "tools/update.py: la riga ME di status sul W541 non si legge come deve"
	fi
	# tools/update.py protection su un /sys finto: lo spazio PCI e il BAR0 del
	# controller SPI del M920x, e la regione BIOS sotto i 4 GiB in un file da
	# 12 MiB al posto di /dev/mem, con la FMAP e le opzioni in SMMSTORE.
	# Nessun PR (com'e' la ci-151), PR0 su WP_RO, un PR su RW_SECTION_A, il
	# BIOS Lock di questo avvio e quello del setup, uno store non sano o
	# rovinato (i default), senza FMAP, i codici di --expect-ro, senza root,
	# nessun controller
	if python3 - <<'EOF'
import contextlib
import io
import os
import shutil
import struct
import sys
import tempfile
sys.dont_write_bytecode = True
root = tempfile.mkdtemp()
os.environ["W541_UPDATE_SYSROOT"] = root
sys.path.insert(0, "tools")
import update

spi = os.path.join(root, "sys/bus/pci/devices/0000:00:1f.5")
os.makedirs(spi)
for f, v in (("vendor", "0x8086"), ("device", "0xa324"), ("class", "0x0c8000")):
    open(os.path.join(spi, f), "w").write(v + "\n")
areas = [("SI_ALL", 0, 0xc00000), ("SI_DESC", 0, 0x1000), ("SI_GBE", 0x1000, 0x2000), ("SI_ME", 0x3000, 0xbfd000),
         ("SI_BIOS", 0xc00000, 0xc00000), ("RW_MRC_CACHE", 0xc00000, 0x10000), ("SMMSTORE", 0xc10000, 0x80000),
         ("RW_NVRAM", 0xca0000, 0x10000), ("RW_SECTION_A", 0xcc0000, 0x520000), ("FW_MAIN_A", 0xcd0000, 0x50ffc0),
         ("RW_SECTION_B", 0x11e0000, 0x520000), ("WP_RO", 0x1700000, 0x100000), ("FMAP", 0x1700000, 0x800),
         ("COREBOOT", 0x1720000, 0xe0000)]
base = 0xff400000                      # 4 GiB - 12 MiB: flash 0xc00000
win = os.path.join(root, "bios-window.bin")


def var(name, value, state=0x3f, guid=update.CB_OPTION_GUID, dsize=None):
    n = (name + "\0").encode("utf-16-le")
    d = struct.pack("<I", value)
    h = struct.pack("<HBBIQ16sIII16s", 0x55aa, state, 0, 3, 0, bytes(16), 0, len(n),
                    len(d) if dsize is None else dsize, guid)
    v = h + n + d
    return v + b"\xff" * (-len(v) % 4)


def fixture(prs=(), bios_cntl=0x8b, health=0xfe, options=((0, 0, 0x3f),), config=256, with_fmap=True,
            tail=b"", checksum=0):
    cfg = bytearray(256)
    cfg[0:4] = struct.pack("<HH", 0x8086, 0xa324)
    cfg[0x10:0x14] = struct.pack("<I", 0xfe010000)
    cfg[0xdc] = bios_cntl
    open(os.path.join(spi, "config"), "wb").write(bytes(cfg[:config]))
    bar = bytearray(0x1000)
    for off, v in ((0x00, 0x17ff0c00), (0x04, 0x230af801), (0x0c, 0x1f00), (0x50, 0xffff), (0x54, 0),
                   (0x58, 0x17ff0c00), (0x5c, 0x0bff0003), (0x60, 0x00020001)):
        bar[off:off + 4] = struct.pack("<I", v)
    for n in range(4, 12):
        bar[0x54 + 4 * n:0x58 + 4 * n] = struct.pack("<I", 0x7fff)
    for n, v in prs:
        bar[0x84 + 4 * n:0x88 + 4 * n] = struct.pack("<I", v)
    open(os.path.join(spi, "resource0"), "wb").write(bytes(bar))
    img = bytearray(b"\xff" * 0xc00000)
    fmap = b"__FMAP__" + struct.pack("<BBQI32sH", 1, 1, 0, 0x1800000, b"FLASH", len(areas))
    fmap += b"".join(struct.pack("<II32sH", o, n, name.encode(), 0) for name, o, n in areas)
    if with_fmap:
        img[0xb00000:0xb00000 + len(fmap)] = fmap
    # la FV come la scrive efi_fv_initialize(): 64 blocchi da 4 KiB
    st = 0x10000
    fv = bytearray(0x48)
    fv[0x10:0x20] = update.NV_DATA_FV_GUID
    fv[0x20:0x28] = struct.pack("<Q", 0x40000)
    fv[0x28:0x2c] = b"_FVH"
    fv[0x30:0x32] = struct.pack("<H", 0x48)
    fv[0x37] = 2
    fv[0x38:0x40] = struct.pack("<II", 0x40, 0x1000)
    fv[0x32:0x34] = struct.pack("<H", (checksum - sum(struct.unpack("<36H", fv))) & 0xffff)
    img[st:st + 0x48] = fv
    img[st + 0x48:st + 0x64] = update.AUTH_VAR_GUID + struct.pack("<IBBHI", 0x30000 - 0x48, 0x5a, health, 0, 0)
    vs = var("bootmedia_lock", 1, 0x3c)                   # la copia di prima, cancellata
    for bm, bl, state in options:
        vs += var("bootmedia_lock", bm, state) + var("bios_lock", bl, state)
    vs += var("bootmedia_lock", 7, guid=bytes(16)) + tail  # stesso nome, altro GUID
    img[st + 0x64:st + 0x64 + len(vs)] = vs
    open(win, "wb").write(bytes(img))


dm = (win, base)
fixture()
p = update.spi_protection(dm)
assert p["bios"] == (0xc00000, 0x17fffff) and p["window"] == base and p["fmap"].startswith("quella nel flash")
assert p["options"] == {"bootmedia_lock": 0, "bios_lock": 0}, p["options"]
v = update.spi_verdict(p)
assert v["ro"] == "off" and v["desc_writable"] and not v["smm_only"] and not v["capsule_block"]
assert update.protection_lines(dm) == [
    ("WP_RO", "NON protetta (Firmware protection spenta, anche nel setup)"),
    ("BIOS Lock", "spento: il sistema puo' scrivere il flash"),
    ("slot RW", "scrivibili con la capsula e con flashrom")], update.protection_lines(dm)
# Firmware protection: PR0 su WP_RO, come lo scrive fast_spi_flash_protect()
fixture(prs=((0, 0x97ff1700),), options=((1, 0, 0x3f),))
p = update.spi_protection(dm)
v = update.spi_verdict(p)
assert v["ro"] == "ok" and v["prs"][0]["areas"] == ["WP_RO"] and not v["capsule_block"], v
assert update.ro_text(p, v).startswith("protetta fino al prossimo reset o ripresa da S3 (PR0); ma il descrittore "
                                      "e' scrivibile")
assert update.slots_text(p, v) == "scrivibili con la capsula e con flashrom"
# WP_RO coperta da due PR insieme
fixture(prs=((0, 0x97ff1780), (1, 0x977f1700)), options=((1, 0, 0x3f),))
assert update.spi_verdict(update.spi_protection(dm))["ro"] == "ok"
# un PR su RW_SECTION_A: la capsula non lo scrive
fixture(prs=((2, 0x91df0cc0),))
p = update.spi_protection(dm)
v = update.spi_verdict(p)
assert v["capsule_block"] == ["PR2 RW_SECTION_A"] and v["prs"][0]["areas"] == ["RW_SECTION_A"], v
assert update.slots_text(p, v).startswith("NON scrivibili: PR2 RW_SECTION_A")
assert v["ro"] == "off"
# BIOS Lock in questo avvio: EISS e BLE, o EISS a 0 e WPD a 0 con BLE (SMM
# lo rimette a 0 dopo la finalize); l'opzione in SMMSTORE solo come nota
for bc, opt, by_smi in ((0xaa, 1, False), (0x8a, 1, True)):
    fixture(bios_cntl=bc, options=((0, opt, 0x3f),))
    p = update.spi_protection(dm)
    v = update.spi_verdict(p)
    assert v["smm_only"] and v["smm_by_smi"] == by_smi, (bc, v)
    assert update.slots_text(p, v) == "scrivibili con la capsula; flashrom no (BIOS Lock)"
fixture(bios_cntl=0x8a, options=((0, 0, 0x3f),))
p = update.spi_protection(dm)
assert update.bios_lock_text(p, update.spi_verdict(p)) == "acceso: scrive solo il firmware in SMM (EISS a 0: " \
    "lo tiene l'SMI che rimette WPD a 0); spento nel setup, vale dal prossimo avvio o ripresa da S3"
# acceso nel setup ma non in questo avvio: WPD resta a 1, flashrom scrive
fixture(bios_cntl=0x8b, options=((0, 1, 0x3f),))
p = update.spi_protection(dm)
v = update.spi_verdict(p)
assert not v["smm_only"] and update.slots_text(p, v) == "scrivibili con la capsula e con flashrom"
assert update.bios_lock_text(p, v) == \
    "spento: il sistema puo' scrivere il flash; acceso nel setup, vale dal prossimo avvio o ripresa da S3"
# senza BLE WPD a 0 non tiene: flashrom lo accende
fixture(bios_cntl=0x88)
p = update.spi_protection(dm)
assert update.bios_lock_text(p, update.spi_verdict(p)) == \
    "spento: il sistema puo' scrivere il flash (dopo aver acceso BIOSWE, come fa flashrom)"
# copie in cancellazione (0x3e): vale l'ultima, se non ce n'e' una valida
fixture(options=((0, 0, 0x3e), (1, 0, 0x3e)))
assert update.spi_protection(dm)["options"] == {"bootmedia_lock": 1, "bios_lock": 0}
# store non sano: coreboot usa i default
fixture(health=0xff)
p = update.spi_protection(dm)
assert p["options"] == {"bootmedia_lock": None, "bios_lock": None}
assert update.option_text(p, "bootmedia_lock") == "1 (default: store di SMMSTORE NON sano)"
assert "al default, accesa (store di SMMSTORE NON sano)" in update.ro_text(p, update.spi_verdict(p))
# store che coreboot rifiuta, quindi i default: una variabile che va oltre la
# fine dello store, dati dopo l'ultima, il checksum della FV
for kw, why in ((dict(tail=var("x", 0, dsize=0x2ff00)), "variabile a 0x"),
                (dict(tail=b"\0" * 4), "dati dopo l'ultima variabile"),
                (dict(checksum=1), "checksum della FV")):
    fixture(**kw)
    p = update.spi_protection(dm)
    assert p["options"] == {"bootmedia_lock": None, "bios_lock": None}, (kw, p["options"])
    assert p["options_note"].startswith("store di SMMSTORE rovinato (" + why), (kw, p["options_note"])
# protection: i codici di --expect-ro (0 come atteso, 1 no, 2 non si sa)
spi_protection = update.spi_protection
update.spi_protection = lambda devmem=None: spi_protection(dm)


def protection(expect):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = update.cmd_protection(type("A", (), {"flash": None, "expect_ro": expect})())
    return rc, out.getvalue()


fixture(prs=((0, 0x97ff1700),), options=((1, 0, 0x3f),))
assert [protection(e)[0] for e in ("on", "off", None)] == [0, 1, 0]
fixture()
assert [protection(e)[0] for e in ("on", "off")] == [1, 0]
# senza FMAP (ne' nel flash ne' da cbmem) un PR non si confronta con gli slot
fixture(prs=((2, 0x91df0cc0),), with_fmap=False)
p = spi_protection(dm)
v = update.spi_verdict(p)
assert v["ro"] is None and v["unmapped"] == ["PR2"] and not v["capsule_block"], v
assert update.slots_text(p, v) == \
    "non verificabili: PR2 attivi, FMAP non letta (update.py protection --flash FILE)"
rc, out = protection("off")
assert rc == 2 and "stato di WP_RO non noto" in out, out
assert "capsula:     non verificabile: PR2 attivi" in out and "flashrom:    non verificabile: PR2" in out, out
fixture(with_fmap=False)
p = spi_protection(dm)
assert update.slots_text(p, update.spi_verdict(p)) == "scrivibili con la capsula e con flashrom"
update.spi_protection = spi_protection
# senza root sysfs da' 64 byte dello spazio PCI
fixture(config=64)
assert update.protection_lines(dm) == [("protezione", "serve root (sudo)")]
# senza il controller SPI 00:1f.5 (e senza un LPC Lynx Point, il W541)
shutil.rmtree(spi)
assert update.spi_protection(dm) is None
assert update.protection_lines(dm)[0][1].startswith("non verificabile")
shutil.rmtree(root)
EOF
	then
		ok "tools/update.py: protection su registri finti (nessun PR, PR0 su WP_RO, PR su uno slot, BIOS Lock, store non sano o rovinato, senza FMAP, --expect-ro, senza root, nessun controller)"
	else
		bad "tools/update.py: protection non legge i registri finti come deve"
	fi
	# tools/update.py protection sul W541 (Lynx Point), su un /sys finto: lo
	# spazio PCI dell'LPC 00:1f.0 (BIOS_CNTL, RCBA) e un /dev/mem finto da
	# 0xfed1c000 a 4 GiB con la pagina RCBA + 0x3000 (GCS, BUC, i registri SPI
	# a 0x3800) e la regione BIOS di 7 MiB con la FMAP della ci-150 e SMMSTORE.
	# I valori di ci-150: PR0 0x8bff0b60 su WP_RO, FLOCKDN, FRAP 0xffff
	# (FLMSTR1 0xffff0000), BIOS_CNTL 0x09 col BIOS Lock spento e 0x2a acceso.
	# Poi i casi: nessun PR, FLOCKDN spento, un PR su uno slot, BIOS_CNTL,
	# RCBA spento o strano, /dev/mem rifiutata, senza root, un altro LPC;
	# protection e --expect-ro, status, e FLASH-01 di tools/hw-report.py
	if python3 - <<'EOF'
import contextlib
import errno
import importlib.util
import io
import os
import shutil
import struct
import sys
import tempfile
sys.dont_write_bytecode = True
root = tempfile.mkdtemp()
os.environ["W541_UPDATE_SYSROOT"] = root
sys.path.insert(0, "tools")
import update

# i dword letti non toccano mai FDATA, SSFS/SSFC/PREOP/OPTYPE/OPMENU, FDOC/FDOD
assert not [o for o in update.LPT_SPIBAR_READ if 0x10 <= o < 0x50 or 0x90 <= o < 0xa0 or 0xb0 <= o < 0xb8]
assert len(update.LPT_LPC_IDS) == 24 and 0x8c4f in update.LPT_LPC_IDS and 0x8c43 not in update.LPT_LPC_IDS
lpc = os.path.join(root, "sys/bus/pci/devices/0000:00:1f.0")
sata = os.path.join(root, "sys/bus/pci/devices/0000:00:1f.5")
for d, dev, cls in ((lpc, "0x8c4f", "0x060100"), (sata, "0x8c09", "0x010185")):
    os.makedirs(d)
    for f, v in (("vendor", "0x8086"), ("device", dev), ("class", cls)):
        open(os.path.join(d, f), "w").write(v + "\n")
# la FMAP del ROM della ci-150 (W541, 12 MiB)
areas = [("SI_ALL", 0, 0x500000), ("SI_DESC", 0, 0x1000), ("SI_GBE", 0x1000, 0x2000), ("SI_ME", 0x3000, 0x4fd000),
         ("SI_BIOS", 0x500000, 0x700000), ("RW_MRC_CACHE", 0x500000, 0x10000), ("SMMSTORE", 0x510000, 0x80000),
         ("RO_VPD", 0x590000, 0x4000), ("RW_ELOG", 0x594000, 0x4000), ("RW_NVRAM", 0x5a0000, 0x10000),
         ("RW_SECTION_A", 0x5c0000, 0x2d0000), ("FW_MAIN_A", 0x5d0000, 0x2bffc0),
         ("RW_SECTION_B", 0x890000, 0x2d0000), ("FW_MAIN_B", 0x8a0000, 0x2bffc0), ("WP_RO", 0xb60000, 0xa0000),
         ("FMAP", 0xb60000, 0x800), ("COREBOOT", 0xb80000, 0x80000)]
phys = 0xfed1c000                       # il primo byte del /dev/mem finto
mem = os.path.join(root, "devmem.bin")
WIN = 0xff900000                        # 4 GiB - 7 MiB: flash 0x500000
win_off = lambda flash: WIN - phys + flash - 0x500000
with open(mem, "wb") as f:
    f.truncate((1 << 32) - phys)        # sparso, ~19 MiB
    fmap = b"__FMAP__" + struct.pack("<BBQI32sH", 1, 1, 0, 0xc00000, b"FLASH", len(areas))
    fmap += b"".join(struct.pack("<II32sH", o, n, name.encode(), 0) for name, o, n in areas)
    f.seek(win_off(0xb60000))
    f.write(fmap)


def var(name, value, state=0x3f):
    n = (name + "\0").encode("utf-16-le")
    d = struct.pack("<I", value)
    v = struct.pack("<HBBIQ16sIII16s", 0x55aa, state, 0, 3, 0, bytes(16), 0, len(n), len(d),
                    update.CB_OPTION_GUID) + n + d
    return v + b"\xff" * (-len(v) % 4)


def store(options):
    """SMMSTORE: vuota (None) o la FV di efi_fv_initialize() con le opzioni."""
    img = bytearray(b"\xff" * 0x80000)
    if options is not None:
        fv = bytearray(0x48)
        fv[0x10:0x20] = update.NV_DATA_FV_GUID
        fv[0x20:0x28] = struct.pack("<Q", 0x40000)
        fv[0x28:0x2c] = b"_FVH"
        fv[0x30:0x32] = struct.pack("<H", 0x48)
        fv[0x37] = 2
        fv[0x38:0x40] = struct.pack("<II", 0x40, 0x1000)
        fv[0x32:0x34] = struct.pack("<H", -sum(struct.unpack("<36H", fv)) & 0xffff)
        img[0:0x48] = fv
        img[0x48:0x64] = update.AUTH_VAR_GUID + struct.pack("<IBBHI", 0x30000 - 0x48, 0x5a, 0xfe, 0, 0)
        vs = b"".join(var(k, v) for k, v in options)
        img[0x64:0x64 + len(vs)] = vs
    return bytes(img)


def fixture(prs=((0, 0x8bff0b60),), bios_cntl=0x09, hsfs=0x0000e008, rcba=0xfed1c001, options=None, config=256,
            device=0x8c4f):
    cfg = bytearray(256)
    cfg[0:4] = struct.pack("<HH", 0x8086, device)
    cfg[0xdc] = bios_cntl
    cfg[0xf0:0xf4] = struct.pack("<I", rcba)
    open(os.path.join(lpc, "config"), "wb").write(bytes(cfg[:config]))
    open(os.path.join(lpc, "device"), "w").write("0x%04x\n" % device)
    page = bytearray(0x1000)
    regs = {0x410: 0x00000001, 0x414: 0x00000000,                     # GCS BILD 1, BUC Top Swap 0
            0x800: 0x0bff0500, 0x804: hsfs, 0x850: 0x0000ffff,        # BFPR, HSFS, FRAP
            0x854: 0x00000000, 0x858: 0x0bff0500, 0x85c: 0x04ff0003, 0x860: 0x00020001, 0x864: 0x00007fff}
    for n, v in prs:
        regs[0x874 + 4 * n] = v
    for off, v in regs.items():
        page[off:off + 4] = struct.pack("<I", v)
    with open(mem, "r+b") as f:
        f.seek(0x3000)
        f.write(page)
        f.seek(win_off(0x510000))
        f.write(store(options))


dm = (mem, phys)
# (a) i default di una release: PR0 su WP_RO, BIOS Lock spento, SMMSTORE vuota
fixture()
p = update.spi_protection(dm)
assert (p["ctrl"], p["device"], p["rcba"], p["bar"]) == ("lpt", 0x8c4f, 0xfed1c000, 0xfed1f800), p
assert p["bios"] == (0x500000, 0xbfffff) and p["window"] == WIN and p["fmap"] == "quella nel flash (0x0b60000)"
assert p["gcs"] & update.GCS_BILD and not p["buc"] & update.BUC_TS
v = update.spi_verdict(p)
assert v["ro"] == "ok" and v["prs"][0]["areas"] == ["WP_RO"] and v["flockdn"] and v["desc_writable"], v
assert update.option_text(p, "bootmedia_lock") == "1 (default: SMMSTORE vuota)"
assert update.protection_lines(dm) == [
    ("WP_RO", "protetta fino al prossimo reset o ripresa da S3 (PR0); ma il descrittore e' scrivibile dalla CPU "
              "(UNLOCK_FLASH_REGIONS): si puo' aggirare"),
    ("BIOS Lock", "spento: il sistema puo' scrivere il flash"),
    ("slot RW", "scrivibili con la capsula e con flashrom")], update.protection_lines(dm)
# (b) Firmware protection spenta nel setup, nessun PR; me_disable da SMMSTORE
fixture(prs=(), options=(("bootmedia_lock", 0), ("bios_lock", 0), ("me_disable", 0)))
p = update.spi_protection(dm)
assert p["options"] == {"bootmedia_lock": 0, "bios_lock": 0} and p["board_options"] == {"me_disable": 0}, p
assert update.ro_text(p, update.spi_verdict(p)) == "NON protetta (Firmware protection spenta, anche nel setup)"
# (c) FLOCKDN spento: i PR si possono togliere
fixture(hsfs=0x00006008)
p = update.spi_protection(dm)
v = update.spi_verdict(p)
assert v["ro"] == "unlocked" and "ma FLOCKDN e' spento" in update.ro_text(p, v), v
# (d) un PR su RW_SECTION_A: la capsula non lo scrive
fixture(prs=((0, 0x8bff0b60), (1, 0x888f05c0)))
p = update.spi_protection(dm)
v = update.spi_verdict(p)
assert v["capsule_block"] == ["PR1 RW_SECTION_A"] and v["ro"] == "ok", v
# (e) BIOS_CNTL: 0x2a come lo lascia coreboot col BIOS Lock acceso, 0x0a
# (SMM_BWP tolto: lo tiene l'SMI), 0x29 (SMM_BWP da solo, R/WLO: basta),
# 0x08 (BIOSWE si accende), 0x0b (l'SMI non ha rimesso BIOSWE a 0)
for bc, smm, by_smi, text in (
        (0x2a, True, False, "acceso: scrive solo il firmware in SMM"),
        (0x0a, True, True, "acceso: scrive solo il firmware in SMM (SMM_BWP a 0: lo tiene l'SMI che rimette "
                           "BIOSWE a 0)"),
        (0x29, True, False, "acceso: scrive solo il firmware in SMM"),
        (0x08, False, False, "spento: il sistema puo' scrivere il flash (dopo aver acceso BIOSWE, come fa "
                             "flashrom)"),
        (0x0b, False, False, "spento: il sistema puo' scrivere il flash (BLE acceso ma BIOSWE a 1: l'SMI non "
                             "l'ha rimesso a 0)")):
    fixture(bios_cntl=bc, options=(("bios_lock", 1),))
    p = update.spi_protection(dm)
    v = update.spi_verdict(p)
    assert (v["smm_only"], v["smm_by_smi"]) == (smm, by_smi), (bc, v)
    want = text + ("" if smm else "; acceso nel setup, vale dal prossimo avvio o ripresa da S3")
    assert update.bios_lock_text(p, v) == want, (bc, update.bios_lock_text(p, v))
    if smm:
        assert update.slots_text(p, v) == "scrivibili con la capsula; flashrom no (BIOS Lock)"
# (f) protection: le righe di Lynx Point, nessuna di Cannon Point; --expect-ro
spi_protection = update.spi_protection
update.spi_protection = lambda devmem=None: spi_protection(dm)


def protection(expect):
    """cmd_protection come lo chiama main(): (codice d'uscita, stdout e stderr)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            rc = update.cmd_protection(type("A", (), {"flash": None, "expect_ro": expect})())
        except update.Error as e:
            print("errore: %s" % e, file=sys.stderr)
            rc = 1
    return rc, out.getvalue()


fixture()
rc, out = protection(None)
for s in ("controller:  00:1f.0 (LPC), 8086:8c4f (Lynx Point QM87), RCBA 0xfed1c000, SPIBAR 0xfed1f800",
          "BIOS_CNTL:   0x09: BIOSWE 1, BLE 0, SMM_BWP 0, Top Swap 0 (TSS)",
          "GCS:         0x00000001: BILD 1; BUC 0x00: Top Swap 0",
          "BIOS:        regione 0x0500000-0x0bfffff (7 MiB), sotto i 4 GiB da 0xff900000",
          "blocchi:     FLOCKDN 1 (blocca anche PR0-PR4), descrittore attivo",
          "regioni:     descrittore 0x0000000-0x0000fff, BIOS 0x0500000-0x0bfffff, ME 0x0003000-0x04fffff, "
          "GbE 0x0001000-0x0002fff",
          "FRAP:        0x0000ffff: la CPU legge descrittore, BIOS, ME, GbE; scrive descrittore, BIOS, ME, GbE",
          "PR0:         0x8bff0b60: 0x0b60000-0x0bfffff scrittura = WP_RO"):
    assert s in out.splitlines(), (s, out)
assert rc == 0 and not any(w in out for w in ("DLOCK", "EISS", "GPR0", "PRR34", "WRSDIS", "FRACC")), out
assert [protection(e)[0] for e in ("on", "off")] == [0, 1]
fixture(prs=())
rc, out = protection("on")
assert rc == 1 and "PR0-PR4:     tutti vuoti" in out, out
assert protection("off")[0] == 0
# status: le stesse tre righe del M920x
fixture()
assert [l for l, _ in update.protection_lines()] == ["WP_RO", "BIOS Lock", "slot RW"]
update.spi_protection = spi_protection
# (g) RCBA spento, o fuori dalla riserva di ACPI: la pagina non si mappa;
# BIOS_CNTL viene dallo spazio PCI, il BIOS Lock si sa lo stesso
fixture(rcba=0xfed1c000)
assert update.protection_lines(dm) == [
    ("protezione", "RCBA spento (0xf0 = 0xfed1c000); BIOS_CNTL 0x09"),
    ("BIOS Lock", "spento: il sistema puo' scrivere il flash")], update.protection_lines(dm)
fixture(rcba=0xfe000001)
assert "non e' 0xfed1c000 ne' in una riserva PNP0C02" in update.spi_protection(dm)["error"]
os.makedirs(os.path.join(root, "proc"))
open(os.path.join(root, "proc/iomem"), "w").write(
    "fe000000-fe003fff : pnp 00:01\nfed1c000-fed1ffff : pnp 00:01\n  fed1f410-fed1f414 : iTCO_wdt.0.auto\n"
    "  fed1f800-fed1f9ff : intel-spi\n")
assert update.spi_protection(dm)["error"].startswith("pagina 0xfe003000 non leggibile da ")
# (h) /dev/mem rifiutata (IO_STRICT_DEVMEM con i driver sulla pagina, o la
# kernel lockdown): perche', e FLOCKDN dal driver intel-spi; le opzioni in
# SMMSTORE si leggono lo stesso dalla finestra della regione BIOS (SI_BIOS di
# configs/w541.fmd senza cbmem, se no quello della FMAP dell'avvio);
# protection dice il BIOS Lock ed esce con 2 con --expect-ro (mai 1: con off
# vorrebbe dire protetta); other-slot avvisa del BIOS Lock lo stesso
read_dwords = update.read_dwords


def eperm(path, offset, offsets):
    raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))


update.read_dwords = eperm
os.makedirs(update.INTEL_SPI_PLATFORM)
open(os.path.join(update.INTEL_SPI_PLATFORM, "intel_spi_locked"), "w").write("1\n")
fixture(bios_cntl=0x2a)
p = update.spi_protection(dm)
assert p["error"] == ("registri SPI non leggibili da /dev/mem (Operation not permitted); kernel con "
                      "IO_STRICT_DEVMEM (la pagina 0xfed1f000 e' anche di fed1f410-fed1f414 iTCO_wdt.0.auto, "
                      "fed1f800-fed1f9ff intel-spi): per questa sola verifica avvia una volta con iomem=relaxed, "
                      "poi toglilo (da confermare su un W541); FLOCKDN 1 (intel_spi_locked)"), p["error"]
assert update.protection_lines(dm)[1] == ("BIOS Lock", "acceso: scrive solo il firmware in SMM")
fixture(bios_cntl=0x2a, options=(("me_disable", 0), ("bios_lock", 0)))
p = update.spi_protection(dm)
assert p["regs"] is None and p["error"].startswith("registri SPI non leggibili") and p["store_read"], p
assert p["options"] == {"bootmedia_lock": None, "bios_lock": 0} and p["board_options"] == {"me_disable": 0}, p
assert (p["bios_from"], p["fmap"]) == ("SI_BIOS di configs/w541.fmd", "quella nel flash (0x0b60000)"), p
assert update.protection_lines(dm)[1] == (
    "BIOS Lock", "acceso: scrive solo il firmware in SMM; spento nel setup, vale dal prossimo avvio o ripresa da S3")
boot_fmap = update.boot_fmap
update.boot_fmap = lambda: fmap
p = update.spi_protection(dm)
assert (p["bios_from"], p["fmap"]) == ("SI_BIOS della FMAP dell'avvio",
                                       "quella dell'avvio (cbmem), uguale a quella nel flash"), p
assert p["board_options"] == {"me_disable": 0}
update.boot_fmap = boot_fmap
# SI_BIOS deve finire dove finisce il flash (la dimensione nell'header)
assert update.fmap_bios_region(fmap) == (0x500000, 0xbfffff)
assert update.fmap_bios_region(fmap[:18] + struct.pack("<I", 0x1000000) + fmap[22:]) is None
assert update.fmap_bios_region(b"") is None
update.spi_protection = lambda devmem=None: spi_protection(dm)
fixture(bios_cntl=0x2a, options=(("bios_lock", 1),))
rc, out = protection(None)
assert rc == 1 and "errore: registri SPI non leggibili da /dev/mem (Operation not permitted)" in out, out
for s in ("opzioni:     Firmware protection 1 (default), BIOS Lock 1 (in SMMSTORE: valgono dal prossimo avvio o "
          "ripresa da S3)", "BIOS Lock:   acceso: scrive solo il firmware in SMM"):
    assert s in out.splitlines(), (s, out)
for e in ("on", "off"):
    rc, out = protection(e)
    assert rc == 2 and "atteso: WP_RO %s; stato di WP_RO non noto" % (
        "protetta" if e == "on" else "non protetta") in out.splitlines(), (e, rc, out)
# other-slot: il BIOS Lock si dice anche senza i registri, e che i PR non si sono visti
geteuid = update.os.geteuid
update.os.geteuid = lambda: 0
for bc, warn in ((0x2a, True), (0x09, False)):
    fixture(bios_cntl=bc)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        update.check_flash_writable({"RW_SECTION_A": (0x5c0000, 0x2d0000)}, ["RW_SECTION_A"])
    lines = out.getvalue().splitlines()
    assert lines[:-1] == ([update.BIOS_LOCK_WARNING] if warn else []), (bc, lines)
    assert lines[-1].startswith("nota: i Protected Range di questo avvio non si leggono"), lines
update.os.geteuid = geteuid
update.spi_protection = spi_protection
os.makedirs(os.path.join(root, "sys/kernel/security"))
open(os.path.join(root, "sys/kernel/security/lockdown"), "w").write("none [integrity] confidentiality\n")
assert "kernel lockdown (integrity): /dev/mem resta chiusa" in update.spi_protection(dm)["error"]
update.read_dwords = read_dwords
# un errore che non e' EPERM (niente /dev/mem): com'e', senza iomem=relaxed
# ne' lockdown; niente finestra, le opzioni non lette
nomem = (os.path.join(root, "nessuna"), phys)
p = update.spi_protection(nomem)
assert p["error"] == "registri SPI non leggibili da /dev/mem (No such file or directory); FLOCKDN 1 " \
    "(intel_spi_locked)", p["error"]
assert not p.get("store_read") and p["options_note"] == "non lette", p
# (i) senza root sysfs da' 64 byte dello spazio PCI
fixture(config=64)
assert update.protection_lines(dm) == [("protezione", "serve root (sudo)")]
update.spi_protection = lambda devmem=None: spi_protection(dm)
assert [protection(e)[0] for e in (None, "on", "off")] == [1, 2, 2]
update.spi_protection = spi_protection
# (j) un LPC che non e' di Lynx Point (0x8c43 non c'e', Wildcat Point 0x9cc3 no)
for dev in (0x8c43, 0x9cc3):
    fixture(device=dev)
    assert update.spi_protection(dm) is None, dev
    assert update.protection_lines(dm)[0][1].startswith("non verificabile")
update.spi_protection = lambda devmem=None: spi_protection(dm)
rc, out = protection("off")
assert rc == 2 and "niente da leggere su questa macchina" in out, out
update.spi_protection = spi_protection
# (l) FLASH-01 di tools/hw-report.py con la stessa sonda: registri bloccati
spec = importlib.util.spec_from_file_location("hw_report", "tools/hw-report.py")
hw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw)
assert hw.update is update
fixture()
update.spi_protection = lambda devmem=None: spi_protection(dm)
fw = hw.Firmware.__new__(hw.Firmware)
fw.cbmem, fw.bios, fw.board, fw.total_line, fw.ts = None, "ouroBIOS-v1.4.0-rc4-mrc", "w541", None, []
fw.log = ["[INFO ]  spi_flash_protect: FPR 0 is enabled for range 0x00b60000-0x00bfffff",
          "[INFO ]  BM-LOCKDOWN: Enabled bootmedia protection"]
rep = hw.Report()
hw.check_flash(fw, rep)
c = rep.checks[0]
assert (c["status"], c["summary"]) == ("PASS", "WP_RO protetto (PR0), registri bloccati"), c
assert "Lynx Point 00:1f.0: BIOS_CNTL 0x09 (BIOSWE 1, BLE 0, SMM_BWP 0), GCS 0x00000001 (BILD 1), FLOCKDN si'" \
    in c["details"], c["details"]


def report(check, log, probe):
    """Un controllo di hw-report.py con un Firmware nuovo (spi_probe() ricorda la sonda)."""
    update.spi_protection = lambda devmem=None: probe()
    fw = hw.Firmware.__new__(hw.Firmware)
    fw.cbmem, fw.bios, fw.board, fw.total_line, fw.ts, fw.log = None, "ouroBIOS-v1.4.0-rc4-mrc", "w541", None, [], log
    rep = hw.Report()
    check(fw, rep)
    update.spi_protection = spi_protection
    return rep.checks[0]


# PR0 su WP_RO con FLOCKDN spento: c'e' ma si toglie, WARN (non "WP_RO non e' in un PR")
fixture(hsfs=0x00006008)
c = report(hw.check_flash, fw.log, lambda: spi_protection(dm))
assert (c["status"], c["summary"]) == ("WARN", "WP_RO in PR0, ma il PR non e' bloccato (FLOCKDN spento): si puo' "
                                               "togliere"), c
assert not c["data"]["wp_ro_protected"], c
# ME-01 con la sonda vera: pagina rifiutata, SMMSTORE letta senza me_disable
# e l'HECI visibile: il default si sa, WARN; con SMMSTORE non letta, INFO
os.makedirs(update.HECI_PCI)
hfsts = ["[DEBUG]  ME: HFSTS1-6: 00020191 100a0000 00000000 00000000 00000000 00000000"]
update.read_dwords = eperm
fixture(options=(("bootmedia_lock", 1),))
c = report(hw.check_me, hfsts, lambda: spi_protection(dm))
assert c["status"] == "WARN" and c["summary"].endswith("HECI 00:16.0 visibile con me_disable al default, acceso"), c
update.read_dwords = read_dwords
c = report(hw.check_me, hfsts, lambda: spi_protection(nomem))
assert c["status"] == "INFO" and c["summary"].endswith("non letto (default acceso): Enabled nel setup?"), c
shutil.rmtree(root)
EOF
	then
		ok "tools/update.py: protection sul W541 (Lynx Point: PR0 su WP_RO, FLOCKDN, PR su uno slot, BIOS_CNTL, RCBA, /dev/mem rifiutata con le opzioni lette lo stesso, senza root, altri LPC, --expect-ro anche senza registri, other-slot; FLASH-01 e ME-01)"
	else
		bad "tools/update.py: protection non legge i registri finti di Lynx Point come deve"
	fi
else
	bad "python3 non installato"
fi

step "workflow (actionlint)"
if command -v actionlint >/dev/null 2>&1; then
	if actionlint .github/workflows/*.yml; then ok "workflow"; else bad "actionlint: vedi sopra"; fi
else
	echo "  (actionlint non installato: salto. pip install actionlint-py)"
fi

# I nomi dei file che tools/build.sh mette nella cartella della board $1
# nell'albero: BOARD_TREE_FILES ("sorgente[:nome]"), COMMON_TREE_FILES, le
# chiavi di vboot in vboot/, la chiave privata degli slot e csmwrap.efi
tree_names() {
	local p
	{
		board_get "$1" BOARD_TREE_FILES
		sed -n '/^COMMON_TREE_FILES=(/,/)/p' tools/build.sh | tr ' \t()' '\n\n\n\n' | grep /
	} | while read -r p; do
		[ -n "${p}" ] || continue
		case "${p}" in *:*) echo "${p#*:}" ;; *) basename "${p}" ;; esac
	done
	sed -n '/^VBOOT_KEYS=(/,/)/p' tools/build.sh | tr ' \t()' '\n\n\n\n' | sed -n 's|^keys/vboot/|vboot/|p'
	sed -n 's|^VBOOT_PRIVKEY_NAME=||p' tools/build.sh
	sed -n 's|^CSMWRAP_NAME=||p' tools/build.sh
}

step "SHA256SUMS"
board_blob_dirs=()
for b in $(boards); do
	while read -r f; do
		[ "${f}" = blobs/SHA256SUMS ] || board_blob_dirs+=("$(dirname "${f}")")
	done < <(board_get "${b}" BOARD_SUMS)
done
for d in blobs assets legacy/coreboot-4.22 "${board_blob_dirs[@]}"; do
	if [ ! -f "${d}/SHA256SUMS" ]; then bad "${d}/SHA256SUMS non c'e'"; continue; fi
	if (cd "${d}" && sha256sum --quiet -c SHA256SUMS); then
		ok "${d}: $(wc -l < "${d}/SHA256SUMS") file"
	else
		bad "${d}: i file non corrispondono a SHA256SUMS"
	fi
	# ogni file della cartella (tranne i README) e' elencato
	for f in "${d}"/*; do
		case "${f##*/}" in SHA256SUMS|README*) continue ;; esac
		grep -q "  ${f##*/}\$" "${d}/SHA256SUMS" || bad "${f}: non e' in ${d}/SHA256SUMS"
	done
done

# Una serie: la cartella $1 (patches, patches/edk2, ...) con il suo series
check_series() {
	local d="$1" p n=0 dups
	local -a listed
	if [ ! -f "${d}/series" ]; then bad "${d}/series non c'e'"; return; fi
	mapfile -t listed < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "${d}/series" | sed '/^$/d')
	for p in "${listed[@]}"; do
		n=$((n + 1))
		if [ ! -f "${d}/${p}" ]; then bad "${p}: in ${d}/series ma non in ${d}/"; continue; fi
		head -1 "${d}/${p}" | grep -q '^From [0-9a-f]\{40\} ' || bad "${d}/${p}: non e' una mail di git format-patch"
		grep -q '^Subject: \[PATCH' "${d}/${p}" || bad "${d}/${p}: senza Subject: [PATCH"
		grep -q '^diff --git ' "${d}/${p}" || bad "${d}/${p}: senza diff"
	done
	for p in "${d}"/*.patch; do
		[ -e "${p}" ] || continue
		printf '%s\n' "${listed[@]}" | grep -qxF "${p#"${d}/"}" || bad "${p}: non e' in ${d}/series"
	done
	dups="$(printf '%s\n' "${listed[@]}" | sort | uniq -d)"
	[ -z "${dups}" ] || bad "${d}/series: ripetute ${dups}"
	ok "${d}: ${n} patch in series"
}

step "serie di patch"
check_series patches
check_series patches/edk2
check_series patches/lvglpkg
n=0
for p in patches/optional/*.patch; do
	[ -e "${p}" ] || continue
	head -1 "${p}" | grep -q '^From [0-9a-f]\{40\} ' || bad "${p}: non e' una mail di git format-patch"
	n=$((n + 1))
done
ok "${n} patch opzionali"
# la bozza per una release che riscrive la parte RO: in nessuna serie
for p in patches/ro-next/*.patch; do
	[ -e "${p}" ] || continue
	{ head -1 "${p}" | grep -q '^From [0-9a-f]\{40\} ' && grep -q '^diff --git ' "${p}"; } \
		|| bad "${p}: non e' una mail di git format-patch"
done
# la patch per q35 della prova dell'aggiornamento (build.sh update-test):
# solo nel worktree di quella prova, quindi in nessuna serie
t="$(sed -n 's/^UPDATE_TEST_PATCH=\(.*\)$/\1/p' tools/build.sh)"
if [ -n "${t}" ] && [ -f "${t}" ] && grep -q '^diff --git ' "${t}"; then
	ok "${t}: la patch della prova dell'aggiornamento"
else
	bad "tools/build.sh: UPDATE_TEST_PATCH '${t}' non c'e' o non e' una patch"
fi
# e quella delle schermate del setup, che usa tools/q35-cfr-rom.sh
for p in patches/test/*.patch; do
	[ "${p}" = "${t}" ] && continue
	grep -qF "${p}" tools/q35-cfr-rom.sh \
		|| bad "${p}: in patches/test ma non usata da tools/build.sh o tools/q35-cfr-rom.sh"
done
# i comandi SMMSTORE dei due slot di vboot: lo stesso numero in coreboot
# (src/include/smmstore.h), in SmmStoreLib di EDK2 e nell'applicazione della
# prova che fa da sistema operativo
for c in SMMSTORE_CMD_VBOOT_SLOT_GOOD SMMSTORE_CMD_VBOOT_TRY_OTHER SMMSTORE_CMD_VBOOT_LOCK; do
	v="$(cat patches/*.patch patches/edk2/*.patch tools/efi/*.c \
		| sed -n "s/^[+]\{0,1\}#define[[:space:]]\{1,\}${c}[[:space:]]\{1,\}\([0-9]\{1,\}\)[[:space:]]*\$/\1/p" \
		| tr -d '\r' | sort -u)"
	n="$(printf '%s\n' "${v}" | grep -c .)"
	if [ "${n}" = 1 ]; then ok "${c} = ${v} in coreboot, EDK2 e tools/efi"; else bad "${c}: numeri diversi o assente (${v//$'\n'/ })"; fi
done

step "chiave Optimus NVIDIA"
# blobs/opvk.inc ha la chiave che il driver NVIDIA di Windows chiede alla dGPU
# (NVOP 0x10), estratta dal DSDT del firmware Lenovo: byte separati da
# virgola, che il DSDT include (patch 0036). Deve esserci solo li': non nelle
# patch e in nessun altro file, sotto nessun nome.
if [ ! -f blobs/opvk.inc ]; then
	bad "blobs/opvk.inc non c'e'"
elif ! tr -d ' \t\r\n' < blobs/opvk.inc | grep -Eqx '(0x[0-9a-fA-F]{2},)*0x[0-9a-fA-F]{2},?'; then
	bad "blobs/opvk.inc: non e' una lista di byte 0x.. separati da virgola"
else
	ok "blobs/opvk.inc: $(tr -d ' \t\r\n' < blobs/opvk.inc | tr ',' '\n' | grep -c .) byte"
fi
k="$(files | grep -i 'opvk' | grep -vx 'blobs/opvk.inc' || true)"
if [ -n "${k}" ]; then bad "altri file della chiave nel repository: ${k}"; else ok "nessun altro opvk.inc"; fi
if grep -q '^+++ b/.*opvk\.inc' patches/optional/*.patch patches/*.patch patches/edk2/*.patch patches/lvglpkg/*.patch \
	patches/test/*.patch 2>/dev/null; then
	bad "una patch crea opvk.inc"
else
	ok "nessuna patch crea opvk.inc"
fi
# e il contenuto, come byte in esadecimale: "NVIDIA Certified" e' nel testo
# della chiave (la sequenza si costruisce qui, cosi' non compare in questo
# file)
sig="$(printf 'NVIDIA Certified' | od -An -tx1 | tr -s ' \n' ' ' | sed -e 's/^ //' -e 's/ $//' -e 's/ /,0x/g' -e 's/^/0x/')"
if [ -f blobs/opvk.inc ] && ! tr -d ' \t\r\n+' < blobs/opvk.inc | grep -qiF "${sig}"; then
	bad "blobs/opvk.inc: non contiene la firma della chiave"
fi
k=""
while IFS= read -r f; do
	[ -f "${f}" ] || continue
	[ "${f}" = blobs/opvk.inc ] && continue
	grep -Iq . "${f}" 2>/dev/null || continue
	if tr -d ' \t\r\n+' < "${f}" | grep -qiF "${sig}"; then
		k+=" ${f}"
	fi
done < <(files)
if [ -n "${k}" ]; then bad "byte della chiave fuori da blobs/opvk.inc:${k}"; else ok "byte della chiave solo in blobs/opvk.inc"; fi

step "defconfig"
ram='^CONFIG_(HAVE_MRC|MRC_FILE|HASWELL_HIDE_PEG_FROM_MRC|USE_NATIVE_RAMINIT|HASWELL_NRI_MEMORY_TEST|HASWELL_NRI_ROUND_TRIP|DRIVERS_EFI_MAIN_FW_GUID)='
for v in mrc nri; do
	[ -f "configs/w541-${v}.defconfig" ] || bad "configs/w541-${v}.defconfig non c'e'"
done
if [ -f configs/w541-mrc.defconfig ] && [ -f configs/w541-nri.defconfig ]; then
	d="$(diff <(grep '^CONFIG_' configs/w541-mrc.defconfig | grep -Ev "${ram}") \
		<(grep '^CONFIG_' configs/w541-nri.defconfig | grep -Ev "${ram}"))"
	if [ -z "${d}" ]; then ok "mrc e nri uguali tranne la RAM init e il GUID"; else bad "mrc e nri diversi fuori dalla RAM init e dal GUID:"; echo "${d}"; fi
	# il GUID dell'ESRT di ogni variante: diverso, e quello di tools/update.py
	g_mrc="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_GUID="\(.*\)"$/\1/p' configs/w541-mrc.defconfig)"
	g_nri="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_GUID="\(.*\)"$/\1/p' configs/w541-nri.defconfig)"
	guid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
	if [[ "${g_mrc}" =~ ${guid_re} ]] && [[ "${g_nri}" =~ ${guid_re} ]] && [ "${g_mrc}" != "${g_nri}" ]; then
		ok "GUID dell'ESRT: mrc ${g_mrc}, nri ${g_nri}"
	else
		bad "CONFIG_DRIVERS_EFI_MAIN_FW_GUID: due GUID diversi, minuscoli (mrc '${g_mrc}', nri '${g_nri}')"
	fi
	for v in mrc nri; do
		g="g_${v}"
		grep -qE "^ +\"${v}\": uuid\.UUID\(\"${!g}\"\),$" tools/update.py \
			|| bad "tools/update.py: VARIANTS[\"${v}\"] non e' ${!g}"
	done
	# il FILE_GUID di FmpDxe (patch 0135): uno solo, non quello di una
	# variante, e quello sotto cui tools/qemu-update.py legge FmpState
	g_fmp="$(sed -n 's/^CONFIG_EDK2_CAPSULE_MAIN_FW_GUID="\(.*\)"$/\1/p' configs/w541-mrc.defconfig)"
	if [[ "${g_fmp}" =~ ${guid_re} ]] && [ "${g_fmp}" != "${g_mrc}" ] && [ "${g_fmp}" != "${g_nri}" ]; then
		ok "FILE_GUID di FmpDxe ${g_fmp}"
	else
		bad "CONFIG_EDK2_CAPSULE_MAIN_FW_GUID: un GUID minuscolo, non quello di una variante ('${g_fmp}')"
	fi
	grep -qE "^FMP_DXE_GUID = uuid\.UUID\(\"${g_fmp}\"\)\.bytes_le$" tools/qemu-update.py \
		|| bad "tools/qemu-update.py: FMP_DXE_GUID non e' ${g_fmp}"
	# La versione minima (LSV) fino a v1.3.0 o da v1.3.6 in su: in mezzo i
	# numeri del formato di prima (fino a v1.3.6-rc1, 0x0103000Z) e quelli
	# X.Y.Z.R si mescolano, e con 0x01030500 (v1.3.5) la v1.3.5 di prima,
	# 0x01030005, sarebbe rifiutata (docs/update.md#versions-variants-downgrades)
	lsv="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_LSV=\(0x[0-9a-fA-F]\{1,8\}\)$/\1/p' configs/w541-mrc.defconfig)"
	if [ -n "${lsv}" ] && { [ $((lsv)) -le $((0x01030000)) ] || [ $((lsv)) -ge $((0x01030600)) ]; }; then
		ok "LSV ${lsv}"
	else
		bad "CONFIG_DRIVERS_EFI_MAIN_FW_LSV '${lsv}': fino a 0x01030000 (v1.3.0) o da 0x01030600 (v1.3.6), non in mezzo"
	fi
	r_build="$(sed -n 's/^CAPSULE_REGIONS=(\(.*\))$/\1/p' tools/build.sh)"
	r_upd="$(sed -n 's/^REGIONS = \[\(.*\)\]$/\1/p' tools/update.py | tr -d '",')"
	if [ -n "${r_build}" ] && [ "${r_build}" = "${r_upd}" ]; then
		ok "regioni delle capsule (il default, W541 e update-test): ${r_build}"
	else
		bad "regioni delle capsule: tools/build.sh '${r_build}', tools/update.py '${r_upd}'"
	fi
	# il remote fwupd scarica dalla release latest i metadati che build.sh
	# fa e ci.sh pubblica nella release mrc
	m_build="$(sed -n 's/^FWUPD_METADATA=\([A-Za-z0-9._-]*\)$/\1/p' tools/build.sh)"
	m_ci="$(sed -n 's/^FWUPD_METADATA=\([A-Za-z0-9._-]*\)$/\1/p' tools/ci.sh)"
	m_uri="https://github.com/debianita22/ourobios/releases/latest/download/${m_build}"
	if [ -n "${m_build}" ] && [ "${m_build}" = "${m_ci}" ] \
		&& [ "$(grep -c '^\[fwupd Remote\]$' configs/fwupd/ourobios.conf)" = 1 ] \
		&& [ "$(grep -c '^MetadataURI=' configs/fwupd/ourobios.conf)" = 1 ] \
		&& grep -qxF "MetadataURI=${m_uri}" configs/fwupd/ourobios.conf \
		&& grep -qx 'Enabled=true' configs/fwupd/ourobios.conf; then
		ok "remote fwupd: ${m_uri}"
	else
		bad "remote fwupd: FWUPD_METADATA di tools/build.sh '${m_build}' e tools/ci.sh '${m_ci}', MetadataURI di configs/fwupd/ourobios.conf: atteso ${m_uri}"
	fi
	# il remote testing scarica gli stessi metadati dalla release fissa
	# TESTING_TAG di ci.sh, spento finche' non lo si accende
	t_ci="$(sed -n 's/^TESTING_TAG=\([A-Za-z0-9._-]*\)$/\1/p' tools/ci.sh)"
	t_uri="https://github.com/debianita22/ourobios/releases/download/${t_ci}/${m_build}"
	if [ -n "${t_ci}" ] && [ -n "${m_build}" ] \
		&& [ "$(grep -c '^\[fwupd Remote\]$' configs/fwupd/ourobios-testing.conf)" = 1 ] \
		&& [ "$(grep -c '^MetadataURI=' configs/fwupd/ourobios-testing.conf)" = 1 ] \
		&& grep -qxF "MetadataURI=${t_uri}" configs/fwupd/ourobios-testing.conf \
		&& grep -qx 'Enabled=false' configs/fwupd/ourobios-testing.conf; then
		ok "remote fwupd testing: ${t_uri}, spento"
	else
		bad "remote fwupd testing: TESTING_TAG di tools/ci.sh '${t_ci}', MetadataURI di configs/fwupd/ourobios-testing.conf: atteso ${t_uri}, Enabled=false"
	fi
	# il certificato di cui si fida il payload: relativo all'albero di EDK2,
	# e' w541/<file> dell'albero di coreboot, copiato da tools/build.sh
	for v in mrc nri; do
		grep -qx 'CONFIG_DRIVERS_EFI_CAPSULE_TRUSTED_PUBLIC_CERT="../../../../../w541/capsule-signing.pem"' \
			"configs/w541-${v}.defconfig" || bad "w541-${v}: CONFIG_DRIVERS_EFI_CAPSULE_TRUSTED_PUBLIC_CERT non e' w541/capsule-signing.pem"
	done
	grep -qxF capsule-signing.pem <<< "$(sed -n '/^COMMON_TREE_FILES=(/,/)/p' tools/build.sh | tr ' \t()' '\n\n\n\n' | sed -n 's|^.*/||p')" \
		|| bad "keys/capsule-signing.pem non e' in COMMON_TREE_FILES di tools/build.sh"
	grep -qx 'CONFIG_HAVE_MRC=y' configs/w541-mrc.defconfig || bad "w541-mrc: senza CONFIG_HAVE_MRC=y"
	grep -qx 'CONFIG_USE_NATIVE_RAMINIT=y' configs/w541-nri.defconfig || bad "w541-nri: senza CONFIG_USE_NATIVE_RAMINIT=y"
	grep -q '^CONFIG_HAVE_MRC=y' configs/w541-nri.defconfig && bad "w541-nri: con CONFIG_HAVE_MRC=y"
	for v in mrc nri; do
		for sym in HAVE_IFD_BIN HAVE_ME_BIN HAVE_GBE_BIN; do
			grep -qx "CONFIG_${sym}=y" "configs/w541-${v}.defconfig" \
				|| bad "w541-${v}: senza CONFIG_${sym}=y (l'immagine deve essere completa)"
		done
	done
	grep -q '^CONFIG_LOCALVERSION=' configs/*.defconfig boards/*/*.defconfig && bad "CONFIG_LOCALVERSION nel defconfig: la mette tools/build.sh"
	if grep -Eq '^CONFIG_EDK2_TAG_OR_REV="[0-9a-f]{40}"$' configs/w541-mrc.defconfig; then
		ok "EDK2 pinnato a un commit"
	else
		bad "CONFIG_EDK2_TAG_OR_REV: un commit intero, non un ramo"
	fi
	# i file che i defconfig cercano in w541/ sono quelli che build.sh copia
	# (BOARD_TREE_FILES di boards/w541/board.sh e COMMON_TREE_FILES in w541/,
	# VBOOT_KEYS in w541/vboot/) o vi scrive (la chiave privata degli slot,
	# il CSMWrap compilato)
	tree_files="$(tree_names w541)"
	for f in $(sed -n 's/^CONFIG_[A-Z0-9_]*="w541\/\([^"]*\)"$/\1/p' configs/w541-*.defconfig | sort -u); do
		grep -qxF "${f}" <<< "${tree_files}" || bad "w541/${f} nei defconfig ma tools/build.sh non lo mette in w541/"
	done
	ok "file in w541/: $(sed -n 's/^CONFIG_[A-Z0-9_]*="w541\/\([^"]*\)"$/\1/p' configs/w541-*.defconfig | sort -u | tr '\n' ' ')"
	# la mappa del flash: le regioni scritte a ogni avvio nel chip da 8 MiB
	# (0x500000-0x7FFFFF, in SI_BIOS sotto 0x300000), lo slot B e la regione
	# RO nel chip da 4 MiB, la RO in fondo a SI_BIOS (il vettore di reset)
	grep -qx 'CONFIG_FMDFILE="w541/w541.fmd"' configs/w541-mrc.defconfig || bad "w541-mrc: senza CONFIG_FMDFILE=\"w541/w541.fmd\""
	if [ -f configs/w541.fmd ]; then
		fmd() { sed -n "s/^[[:space:]]*${1}@\(0x[0-9a-f]*\) \(0x[0-9a-f]*\).*/\1 \2/p" configs/w541.fmd; }
		for r in RW_MRC_CACHE SMMSTORE RO_VPD RW_ELOG RW_NVRAM RECOVERY_MRC_CACHE; do
			read -r off size <<< "$(fmd "${r}")"
			[ -n "${off}" ] && [ $(( off + size )) -le $(( 0x300000 )) ] || bad "w541.fmd: ${r} non nel chip da 8 MiB"
		done
		read -r off size <<< "$(fmd RW_NVRAM)"
		[ -n "${off}" ] && [ $(( off % 0x10000 )) = 0 ] && [ $(( size % 0x10000 )) = 0 ] \
			|| bad "w541.fmd: RW_NVRAM non in blocchi da 64 KiB tutti suoi"
		read -r off size <<< "$(fmd RW_SECTION_B)"
		[ -n "${off}" ] && [ $(( off )) -ge $(( 0x300000 )) ] || bad "w541.fmd: RW_SECTION_B non nel chip da 4 MiB"
		read -r off size <<< "$(fmd WP_RO)"
		[ -n "${off}" ] && [ $(( off + size )) = $(( 0x700000 )) ] && [ $(( off % 0x1000 )) = 0 ] \
			|| bad "w541.fmd: WP_RO non in fondo a SI_BIOS o non allineata a 4 KiB"
		ok "w541.fmd: regioni scrivibili nel chip da 8 MiB, slot B e regione RO nel chip da 4 MiB"
	else
		bad "configs/w541.fmd non c'e'"
	fi
fi

step "le altre board"
# boards/<board>/board.sh oltre al W541 (che ha i controlli qui sopra): i
# defconfig, i GUID, i file nella cartella dell'albero e la mappa del flash
guid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
edk2_w541="$(sed -n 's/^CONFIG_EDK2_TAG_OR_REV="\(.*\)"$/\1/p' configs/w541-mrc.defconfig)"
fmp_w541="$(sed -n 's/^CONFIG_EDK2_CAPSULE_MAIN_FW_GUID="\(.*\)"$/\1/p' configs/w541-mrc.defconfig)"
all_guids="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_GUID="\(.*\)"$/\1/p' configs/w541-*.defconfig)"
for b in $(boards); do
	[ "${b}" = w541 ] && continue
	tree="$(board_get "${b}" BOARD_TREE)"
	prefix="$(board_get "${b}" BOARD_FLAVOUR_PREFIX)"
	[ -n "${tree}" ] && [ -n "${prefix}" ] || { bad "boards/${b}/board.sh: senza BOARD_TREE o BOARD_FLAVOUR_PREFIX"; continue; }
	tree_files="$(tree_names "${b}")"
	for v in $(board_get "${b}" BOARD_VARIANTS); do
		dc="$(board_get "${b}" defconfig "${v}")"
		if [ ! -f "${dc}" ]; then bad "${b}-${v}: ${dc} non c'e'"; continue; fi
		g="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_GUID="\(.*\)"$/\1/p' "${dc}")"
		if [[ "${g}" =~ ${guid_re} ]] && ! grep -qxF "${g}" <<< "${all_guids}"; then
			ok "${b}-${v}: GUID dell'ESRT ${g}"
		else
			bad "${b}-${v}: CONFIG_DRIVERS_EFI_MAIN_FW_GUID '${g}': un GUID minuscolo, diverso da quello di ogni altra variante"
		fi
		all_guids+=$'\n'"${g}"
		grep -qE "^ +\"${prefix}${v}\": uuid\.UUID\(\"${g}\"\),$" tools/update.py \
			|| bad "tools/update.py: VARIANTS[\"${prefix}${v}\"] non e' ${g}"
		[ "$(sed -n 's/^CONFIG_EDK2_TAG_OR_REV="\(.*\)"$/\1/p' "${dc}")" = "${edk2_w541}" ] \
			|| bad "${b}-${v}: CONFIG_EDK2_TAG_OR_REV non e' quello del W541 (${edk2_w541:0:12})"
		[ "$(sed -n 's/^CONFIG_EDK2_CAPSULE_MAIN_FW_GUID="\(.*\)"$/\1/p' "${dc}")" = "${fmp_w541}" ] \
			|| bad "${b}-${v}: CONFIG_EDK2_CAPSULE_MAIN_FW_GUID non e' il FILE_GUID di FmpDxe del W541 (${fmp_w541})"
		lsv="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_LSV=\(0x[0-9a-fA-F]\{1,8\}\)$/\1/p' "${dc}")"
		{ [ -n "${lsv}" ] && { [ $((lsv)) -le $((0x01030000)) ] || [ $((lsv)) -ge $((0x01030600)) ]; }; } \
			|| bad "${b}-${v}: CONFIG_DRIVERS_EFI_MAIN_FW_LSV '${lsv}': fino a 0x01030000 o da 0x01030600"
		for sym in HAVE_IFD_BIN HAVE_ME_BIN HAVE_GBE_BIN; do
			grep -qx "CONFIG_${sym}=y" "${dc}" || bad "${b}-${v}: senza CONFIG_${sym}=y (l'immagine deve essere completa)"
		done
		grep -qx "CONFIG_DRIVERS_EFI_CAPSULE_TRUSTED_PUBLIC_CERT=\"../../../../../${tree}/capsule-signing.pem\"" "${dc}" \
			|| bad "${b}-${v}: CONFIG_DRIVERS_EFI_CAPSULE_TRUSTED_PUBLIC_CERT non e' ${tree}/capsule-signing.pem"
		for f in $(sed -n "s/^CONFIG_[A-Z0-9_]*=\"${tree}\/\([^\"]*\)\"$/\1/p" "${dc}" | sort -u); do
			grep -qxF "${f}" <<< "${tree_files}" || bad "${b}-${v}: ${tree}/${f} nel defconfig ma tools/build.sh non lo mette in ${tree}/"
		done
		ok "${b}-${v}: $(basename "${dc}"), EDK2 ${edk2_w541:0:12}, file in ${tree}/: $(sed -n "s/^CONFIG_[A-Z0-9_]*=\"${tree}\/\([^\"]*\)\"$/\1/p" "${dc}" | sort -u | tr '\n' ' ')"
	done
	# la mappa: le regioni scritte a ogni avvio nel primo chip, lo slot B e
	# la regione RO nel chip che avvia da solo, la RO in fondo alla regione
	# BIOS (il vettore di reset), RW_NVRAM in blocchi da 64 KiB
	fmdfile="$(board_get "${b}" BOARD_TREE_FILES | sed -n 's/^\([^:]*\.fmd\)\(:.*\)\{0,1\}$/\1/p' | head -n 1)"
	intel="$(board_get "${b}" BOARD_INTEL_SIZE)"
	romsize="$(board_get "${b}" BOARD_ROM_SIZE)"
	bootchip="$(board_get "${b}" BOARD_BOOT_CHIP)"
	read -r _ c0off c0size <<< "$(board_get "${b}" BOARD_CHIPS | head -n 1)"
	read -r _ boff bsize <<< "$(board_get "${b}" BOARD_CHIPS | awk -v n="${bootchip}" '$1 == n')"
	if [ -z "${fmdfile}" ] || [ ! -f "${fmdfile}" ] || [ -z "${boff}" ]; then
		bad "${b}: la mappa (.fmd in BOARD_TREE_FILES) o il chip ${bootchip} non ci sono"
		continue
	fi
	fmd() { sed -n "s/^[[:space:]]*${1}@\(0x[0-9a-f]*\) \(0x[0-9a-f]*\).*/\1 \2/p" "${fmdfile}"; }
	read -r off size <<< "$(fmd SI_BIOS)"
	[ $(( off )) = $(( intel )) ] && [ $(( off + size )) = $(( romsize )) ] \
		|| bad "${fmdfile}: SI_BIOS non $(printf '0x%x' "${intel}")-fine del flash"
	for r in RW_MRC_CACHE SMMSTORE RO_VPD RW_ELOG RW_NVRAM RECOVERY_MRC_CACHE; do
		read -r off size <<< "$(fmd "${r}")"
		[ -n "${off}" ] && [ $(( intel + off + size )) -le $(( c0off + c0size )) ] || bad "${fmdfile}: ${r} non nel primo chip"
	done
	read -r off size <<< "$(fmd RW_NVRAM)"
	[ -n "${off}" ] && [ $(( off % 0x10000 )) = 0 ] && [ $(( size % 0x10000 )) = 0 ] \
		|| bad "${fmdfile}: RW_NVRAM non in blocchi da 64 KiB tutti suoi"
	for r in RW_SECTION_B WP_RO; do
		read -r off size <<< "$(fmd "${r}")"
		[ -n "${off}" ] && [ $(( intel + off )) -ge $(( boff )) ] && [ $(( intel + off + size )) -le $(( boff + bsize )) ] \
			|| bad "${fmdfile}: ${r} non nel chip ${bootchip}"
	done
	read -r off size <<< "$(fmd WP_RO)"
	[ -n "${off}" ] && [ $(( intel + off + size )) = $(( romsize )) ] && [ $(( off % 0x1000 )) = 0 ] \
		|| bad "${fmdfile}: WP_RO non in fondo alla regione BIOS o non allineata a 4 KiB"
	ok "${b}: ${fmdfile}, regioni scrivibili nel primo chip, slot B e regione RO nel chip ${bootchip}"
done

step "le board negli strumenti"
# tools/update.py (FLAVOURS e VARIANTS: board, variante, dimensione del
# flash, GUID dell'ESRT; CURRENT_REGIONS: le regioni delle capsule,
# BOARD_CAPSULE_REGIONS o CAPSULE_REGIONS di tools/build.sh) e
# tools/fwupd-cab.py (BOARDS, VARIANTS) devono conoscere ogni variante di
# ogni board, e nient'altro
rows="$(mktemp)"
r_default="$(sed -n 's/^CAPSULE_REGIONS=(\(.*\))$/\1/p' tools/build.sh | tr ' ' ',')"
for b in $(boards); do
	prefix="$(board_get "${b}" BOARD_FLAVOUR_PREFIX)"
	size="$(board_get "${b}" BOARD_ROM_SIZE)"
	regions="$(board_get "${b}" BOARD_CAPSULE_REGIONS | sed '/^$/d' | paste -sd, -)"
	# la prima versione con la board, se non c'e' da sempre: vX.Y.Z
	since="$(board_get "${b}" BOARD_SINCE)"
	if [ -n "${since}" ]; then
		if [[ "${since}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
			ok "${b}: nelle release dalla ${since}"
		else
			bad "boards/${b}/board.sh: BOARD_SINCE '${since}', non vX.Y.Z"
		fi
	fi
	for v in $(board_get "${b}" BOARD_VARIANTS); do
		g="$(sed -n 's/^CONFIG_DRIVERS_EFI_MAIN_FW_GUID="\(.*\)"$/\1/p' "$(board_get "${b}" defconfig "${v}")" 2>/dev/null)"
		echo "${b} ${v} ${prefix}${v} $((size)) ${g:--} ${regions:-${r_default}}" >> "${rows}"
	done
done
if out="$(python3 -I - "${O}/tools" "${rows}" 2>&1 <<'PY'
import importlib.util
import sys

tools, rows = sys.argv[1], sys.argv[2]
sys.path.insert(0, tools)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


upd = load("update", tools + "/update.py")
cab = load("fwupd_cab", tools + "/fwupd-cab.py")
bad, seen = [], set()
for line in open(rows):
    b, v, fl, size, g, regions = line.split()
    seen.add(fl)
    if upd.CURRENT_REGIONS.get(fl) != regions.split(","):
        bad.append("tools/update.py: CURRENT_REGIONS[%r] e' %r, la capsula di tools/build.sh scrive %s"
                   % (fl, upd.CURRENT_REGIONS.get(fl), regions.replace(",", " ")))
    if upd.CURRENT_REGIONS.get(fl) not in upd.ACCEPTED_REGIONS.get(fl, []):
        bad.append("tools/update.py: ACCEPTED_REGIONS[%r] senza le regioni di oggi" % fl)
    if upd.FLAVOURS.get(fl) != (b, v, int(size)):
        bad.append("tools/update.py: FLAVOURS[%r] e' %r, non (%r, %r, %s)" % (fl, upd.FLAVOURS.get(fl), b, v, size))
    if str(upd.VARIANTS.get(fl)) != g:
        bad.append("tools/update.py: VARIANTS[%r] e' %s, non il GUID del defconfig %s" % (fl, upd.VARIANTS.get(fl), g))
    if b not in cab.BOARDS:
        bad.append("tools/fwupd-cab.py: la board %s non e' in BOARDS" % b)
    if v not in cab.VARIANTS:
        bad.append("tools/fwupd-cab.py: la variante %s non e' in VARIANTS" % v)
for fl in sorted(set(upd.FLAVOURS) - seen):
    bad.append("tools/update.py: FLAVOURS[%r] di nessuna board" % fl)
for fl in sorted((set(upd.CURRENT_REGIONS) | set(upd.ACCEPTED_REGIONS)) - seen):
    bad.append("tools/update.py: CURRENT_REGIONS o ACCEPTED_REGIONS[%r] di nessuna board" % fl)
print("\n".join(bad) if bad else ", ".join(sorted(seen)))
sys.exit(1 if bad else 0)
PY
)"; then
	ok "tools/update.py e tools/fwupd-cab.py: ${out}"
else
	while IFS= read -r line; do [ -n "${line}" ] && bad "${line}"; done <<< "${out}"
fi
rm -f "${rows}"

step "chiavi"
if [ -f keys/capsule-signing.pem ]; then
	if ! command -v openssl >/dev/null 2>&1; then
		echo "  (openssl non installato: certificato non controllato)"
	elif openssl x509 -in keys/capsule-signing.pem -noout 2>/dev/null; then
		ok "keys/capsule-signing.pem: $(openssl x509 -in keys/capsule-signing.pem -noout -fingerprint -sha256 | sed 's/^.*=//' | cut -c1-23)..."
	else
		bad "keys/capsule-signing.pem non e' un certificato"
	fi
else
	bad "keys/capsule-signing.pem non c'e'"
fi
# solo certificati e chiavi pubbliche in keys/, e nessuna chiave privata in
# nessun file: niente PEM privati, niente .vbprivk
for f in $(files | grep '^keys/'); do
	case "${f}" in
		keys/README.md|keys/*.pem|keys/vboot/*.vbpubk|keys/vboot/firmware.keyblock) ;;
		*) bad "${f}: in keys/ solo certificati .pem, chiavi pubbliche di vboot e il README" ;;
	esac
done
if files | grep -q '\.vbprivk$'; then bad "chiavi private di vboot nel repository: $(files | grep '\.vbprivk$')"; fi
# il keyblock porta la chiave dati di keys/vboot/firmware_data_key.vbpubk
if [ -f keys/vboot/firmware.keyblock ] && [ -f keys/vboot/firmware_data_key.vbpubk ] && python3 - <<'EOF'
import struct, sys
kb = open("keys/vboot/firmware.keyblock", "rb").read()
pub = open("keys/vboot/firmware_data_key.vbpubk", "rb").read()
# vb2_keyblock: "CHROMEOS", versioni, dimensione, firma, hash, flag, poi la
# chiave dati (vb2_packed_key) a 0x50 con i suoi dati a key_offset
off, _, size = struct.unpack_from("<III", kb, 0x50)
koff, _, ksize = struct.unpack_from("<III", pub, 0)
sys.exit(0 if kb[:8] == b"CHROMEOS" and kb[0x50 + off:0x50 + off + size] == pub[koff:koff + ksize] else 1)
EOF
then
	ok "keys/vboot: il keyblock porta firmware_data_key.vbpubk"
else
	bad "keys/vboot: firmware.keyblock non porta firmware_data_key.vbpubk (o mancano)"
fi
k="$(files | while IFS= read -r f; do
	[ -f "${f}" ] && grep -lE -- '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----' "${f}" 2>/dev/null
done)"
if [ -n "${k}" ]; then bad "chiavi private nel repository: ${k}"; else ok "nessuna chiave privata nei file del repository"; fi

step "pin di coreboot"
commit="$(sed -n 's/^COREBOOT_COMMIT="\([^"]*\)".*/\1/p' tools/build.sh)"
desc="$(sed -n 's/^COREBOOT_DESCRIBE="\([^"]*\)".*/\1/p' tools/build.sh)"
if [[ "${commit}" =~ ^[0-9a-f]{40}$ ]] && [[ "${desc}" =~ -g([0-9a-f]+)$ ]] && [ "${commit:0:${#BASH_REMATCH[1]}}" = "${BASH_REMATCH[1]}" ]; then
	ok "coreboot ${desc}"
else
	bad "COREBOOT_COMMIT '${commit}' e COREBOOT_DESCRIBE '${desc}' non coerenti"
fi
# iPXE (lo stesso commit di STABLE_COMMIT_ID nel Makefile di coreboot: lo
# controlla prepare) e CSMWrap, pinnati a un commit intero
for p in IPXE_COMMIT CSMWRAP_COMMIT; do
	c="$(sed -n "s/^${p}=\"\([^\"]*\)\".*/\1/p" tools/build.sh)"
	if [[ "${c}" =~ ^[0-9a-f]{40}$ ]]; then ok "${p} ${c:0:12}"; else bad "${p} in tools/build.sh: '${c}', non un commit intero"; fi
done
for b in $(boards); do
	iface="$(board_get "${b}" BOARD_RO_INTERFACE)"
	ro_cb="$(awk '$1 == "coreboot" { print $2 }' "${iface}" 2>/dev/null)"
	if [ "${ro_cb}" = "${desc}" ]; then
		ok "${b}: la parte RO sulle macchine e' della stessa coreboot (${iface})"
	elif awk -v d="${desc}" '$1 == "rw-ok" && $2 == d { f = 1 } END { exit !f }' "${iface}" 2>/dev/null; then
		ok "${b}: pin ${desc}, slot controllati sulla parte RO ${ro_cb} (rw-ok in ${iface})"
	else
		bad "${b}: il pin e' ${desc}, la parte RO sulle macchine ${ro_cb:-?}: gli slot devono ancora leggere quello che lascia (${iface:-BOARD_RO_INTERFACE}, docs/vboot.md#limits)"
	fi
done

step "commit pinnati dal mirror (pinned_commit di tools/build.sh)"
# Un repository "upstream" che non ha piu' il commit pinnato (riscritto) e
# un mirror con il suo tag pin-<12 cifre>, in locale: pinned_commit lo deve
# prendere dal mirror, in un clone intero e in uno parziale (i file dal
# mirror promisor), e dire di no per un commit che non c'e' da nessuna parte
fn="$(sed -n '/^pinned_commit() {$/,/^}$/p' tools/build.sh)"
if [ -z "${fn}" ]; then
	bad "tools/build.sh: nessuna funzione pinned_commit"
else
	out="$(
		set -e
		t="$(mktemp -d)"
		trap 'rm -rf "${t}"' EXIT
		eval "${fn}"
		g() { git -c user.name=ci -c user.email=ci@ci -c init.defaultBranch=main -c protocol.file.allow=always "$@"; }
		g init -q "${t}/work"
		echo uno > "${t}/work/f"; g -C "${t}/work" add f; g -C "${t}/work" commit -q -m uno
		g init -q --bare "${t}/up.git"; g -C "${t}/up.git" config uploadpack.allowfilter true
		g -C "${t}/work" push -q "file://${t}/up.git" main
		echo due > "${t}/work/f"; g -C "${t}/work" commit -q -am due
		pin="$(g -C "${t}/work" rev-parse HEAD)"
		g init -q --bare "${t}/mirror.git"; g -C "${t}/mirror.git" config uploadpack.allowfilter true
		g -C "${t}/work" push -q "file://${t}/mirror.git" "HEAD:refs/tags/pin-${pin:0:12}"
		for kind in intero parziale; do
			if [ "${kind}" = parziale ]; then
				g clone -q --filter=blob:none --no-checkout "file://${t}/up.git" "${t}/${kind}"
			else
				g clone -q --no-checkout "file://${t}/up.git" "${t}/${kind}"
			fi
			git() { command git -c protocol.file.allow=always "$@"; }
			pinned_commit "${t}/${kind}" "${pin}" "file://${t}/mirror.git" > /dev/null
			unset -f git
			# nel clone parziale i file vengono dal mirror promisor, dopo un no
			# di upstream ("not our ref")
			g -C "${t}/${kind}" checkout -q --detach "${pin}" 2> /dev/null
			[ "$(cat "${t}/${kind}/f")" = due ] || { echo "clone ${kind}: il file del commit pinnato non e' quello"; exit 1; }
			git() { command git -c protocol.file.allow=always "$@"; }
			if pinned_commit "${t}/${kind}" 0123456789abcdef0123456789abcdef01234567 "file://${t}/mirror.git" > /dev/null; then
				echo "clone ${kind}: un commit che non c'e' da nessuna parte risulta trovato"; exit 1
			fi
			unset -f git
		done
		# il commit c'e' gia' nel clone parziale ma i suoi file no, e upstream
		# non li ha piu' (ramo riscritto, gc): arrivano dal mirror promisor
		echo tre > "${t}/work/f"; g -C "${t}/work" commit -q -am tre
		third="$(g -C "${t}/work" rev-parse HEAD)"
		g -C "${t}/work" push -q -f "file://${t}/up.git" HEAD:main
		g -C "${t}/work" push -q "file://${t}/mirror.git" "HEAD:refs/tags/pin-${third:0:12}"
		g clone -q --filter=blob:none --no-checkout "file://${t}/up.git" "${t}/presente"
		g -C "${t}/work" push -q -f "file://${t}/up.git" "${pin}:main"
		g -C "${t}/up.git" reflog expire --expire=now --all; g -C "${t}/up.git" gc -q --prune=now
		git() { command git -c protocol.file.allow=always "$@"; }
		pinned_commit "${t}/presente" "${third}" "file://${t}/mirror.git" > /dev/null
		unset -f git
		g -C "${t}/presente" checkout -q --detach "${third}" 2> /dev/null
		[ "$(cat "${t}/presente/f")" = tre ] || { echo "commit gia' presente: i file non vengono dal mirror"; exit 1; }
		# senza il tag, per hash da un ramo del mirror
		echo quattro > "${t}/work/f"; g -C "${t}/work" commit -q -am quattro
		fourth="$(g -C "${t}/work" rev-parse HEAD)"
		g -C "${t}/mirror.git" config uploadpack.allowReachableSHA1InWant true
		g -C "${t}/work" push -q "file://${t}/mirror.git" HEAD:refs/heads/copia
		git() { command git -c protocol.file.allow=always "$@"; }
		pinned_commit "${t}/intero" "${fourth}" "file://${t}/mirror.git" > /dev/null \
			|| { echo "senza il tag: il commit non arriva per hash"; exit 1; }
		unset -f git
		echo ok
	)" 2>&1 || true
	if [ "$(tail -n 1 <<< "${out}")" = ok ]; then
		ok "dal mirror: per tag (clone intero e parziale), per hash, i file di un commit gia' presente"
	else
		while IFS= read -r line; do [ -n "${line}" ] && bad "pinned_commit: ${line}"; done <<< "${out}"
	fi
fi
for p in EDK2_MIRROR LVGLPKG_MIRROR; do
	m="$(sed -n "s/^${p}=\"\([^\"]*\)\".*/\1/p" tools/build.sh)"
	if [[ "${m}" =~ ^https://github\.com/debianita22/[A-Za-z0-9_.-]+$ ]]; then ok "${p} ${m}"; else bad "${p} in tools/build.sh: '${m}'"; fi
done
# configs/edk2-pins.txt: le righe "commit-edk2 commit-lvglpkg release", e il
# pin dei defconfig fra quelle (tools/upstream.sh mirror ne controlla i tag)
pins=configs/edk2-pins.txt
if [ ! -f "${pins}" ]; then
	bad "${pins} non c'e'"
else
	n=0
	while read -r e l r; do
		case "${e}" in ''|'#'*) continue ;; esac
		n=$((n + 1))
		[[ "${e}" =~ ^[0-9a-f]{40}$ ]] && [[ "${l}" =~ ^[0-9a-f]{40}$ ]] && [ -n "${r}" ] \
			|| bad "${pins}: riga '${e} ${l} ${r}': due commit interi e le release"
	done < "${pins}"
	for f in configs/*.defconfig boards/*/*.defconfig; do
		rev="$(sed -n 's/^CONFIG_EDK2_TAG_OR_REV="\(.*\)"$/\1/p' "${f}")"
		[ -n "${rev}" ] || continue
		if awk -v r="${rev}" '$1 == r { f = 1 } END { exit !f }' "${pins}"; then
			ok "${f}: EDK2 ${rev:0:12} in ${pins}"
		else
			bad "${f}: EDK2 ${rev} manca in ${pins} (e nei mirror: tools/upstream.sh mirror)"
		fi
	done
	ok "${pins}: ${n} commit pinnati"
fi

step "link nei documenti"
if out="$(files | python3 -c '
import os, re, sys
files = sys.stdin.read().split()
md = [f for f in files if f.endswith(".md")]

def slug(title):
    """L ancora di un titolo come la fa GitHub."""
    t = re.sub(r"`([^`]*)`", r"\1", title.strip())
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[^\w\- ]", "", t.lower())
    return t.replace(" ", "-")

def lines(f):
    fence = False
    for no, line in enumerate(open(f, encoding="utf-8"), 1):
        if line.startswith("```"):
            fence = not fence
        elif not fence:
            yield no, line

anchors = {}
for f in md:
    seen, out = {}, set()
    for _, line in lines(f):
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            s = slug(m.group(1))
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if n == 0 else "%s-%d" % (s, n))
    anchors[f] = out

bad = []
for f in md:
    for no, line in lines(f):
        for target in re.findall(r"\]\(([^)\s]+)\)", line):
            if re.match(r"^[a-z]+:", target):
                continue
            path, _, anchor = target.partition("#")
            dest = os.path.normpath(os.path.join(os.path.dirname(f), path)) if path else f
            if path and not os.path.exists(dest):
                bad.append("%s:%d: %s non c\x27e" % (f, no, target))
            elif anchor and dest.endswith(".md") and anchor not in anchors.get(dest, set()):
                bad.append("%s:%d: #%s non e\x27 un titolo di %s" % (f, no, anchor, dest))
for f in files:
    if f.startswith("tools/") and not f.endswith((".md", ".pyc")):
        try:
            text = open(f, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        for path, anchor in re.findall(r"blob/main/([A-Za-z0-9_./-]+[.]md)#([A-Za-z0-9_-]+)", text):
            if anchor not in anchors.get(path, set()):
                bad.append("%s: %s#%s non c\x27e" % (f, path, anchor))
print("\n".join(bad))
sys.exit(1 if bad else 0)
' 2>&1)"; then
	ok "$(files | grep -c '\.md$') file .md: link relativi e ancore, anche nelle note delle release"
else
	while IFS= read -r line; do [ -n "${line}" ] && bad "${line}"; done <<< "${out}"
fi

step "menu del setup"
# solo con le build in work/coreboot (tools/build.sh roms); le stesse
# eccezioni di tools/build.sh menu
n=0
for v in $(for bd in $(boards); do p="$(board_get "${bd}" BOARD_FLAVOUR_PREFIX)"; board_get "${bd}" BOARD_VARIANTS | sed "s/^/${p}/"; done); do
	b="${O}/work/coreboot/build-${v}"
	[ -f "${b}/config.h" ] && [ -f "${b}/build.h" ] || continue
	n=$((n + 1))
	x=(-x ec_version)
	grep -q '^#define CONFIG_INTEL_OC_MAILBOX_ENABLE_UNDERVOLTING 1$' "${b}/config.h" \
		|| x+=(-x 'oc_undervolt_*')
	tmp="$(mktemp)"
	if out="$("${O}/tools/cfr-dump.sh" -q -o "${tmp}" "${x[@]}" "${O}/work/coreboot" "${b}" 2>&1)"; then
		ok "${v}: $(tail -n 1 <<< "${out}")"
	else
		while IFS= read -r line; do [ -n "${line}" ] && bad "${v}: ${line}"; done <<< "${out}"
	fi
	rm -f "${tmp}"
done
[ "${n}" -gt 0 ] || ok "nessuna build in work/coreboot: lo controlla build.yml (tools/build.sh menu)"

echo
if [ "${fail}" = 0 ]; then
	echo "tutti i controlli passano"
else
	echo "qualche controllo NON passa (righe NO qui sopra)" >&2
fi
exit "${fail}"
