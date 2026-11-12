#!/usr/bin/env python3
# hw-report.py - il controllo di una macchina con ouroBIOS che gira: per ogni
# area un esito (PASS, WARN, FAIL, o INFO e SKIP quando non c'e' una soglia)
# e i numeri che lo motivano, per accorgersi di una regressione al primo
# avvio di una build. Lo spunto: sulla ci-150 FspMemoryInit prendeva 15.2 s a
# ogni avvio con la cache del training valida, invece di 0.2-0.4 s, e per due
# avvii non se n'e' accorto nessuno.
#
#   sudo python3 -I tools/hw-report.py                      # stati C per 20 s
#   sudo python3 -I tools/hw-report.py --seconds 60 --markdown report.md
#   sudo python3 -I tools/hw-report.py --json > report.json
#   sudo python3 -I tools/hw-report.py --dump flash.bin     # anche registro degli
#                                                           # eventi, vboot e opzioni
#
# Cosa guarda: versione del firmware e slot di vboot (cbmem, ESRT), tempi di
# avvio (cbmem -t) con la RAM init rispetto alla cache del training, errori e
# avvisi del log di coreboot (cbmem -1) e quelli del kernel che riguardano il
# firmware, la memoria (SMBIOS), CPU e limiti di potenza, gli stati C del
# package e il consumo (come tools/idle-report.py), ASPM e LTR del PCIe, la
# porta PEG del riser (M920x), ventola e temperature, ME, firmware dell'EC
# (W541), TPM, protezione del flash (con la sonda di tools/update.py
# protection, sulle due board), SMBIOS e tabelle ACPI, WSMT e finestra ECAM
# (riservata nella mappa della memoria e tra le risorse della scheda madre),
# S3. Con --dump, una copia del flash presa con flashrom -r (lo script il
# flash non lo legge mai): il registro degli eventi (tools/elog.py), lo stato
# di vboot in RW_NVRAM, cosa c'e' negli slot e le opzioni del setup salvate in
# SMMSTORE (tools/update.py).
#
# Solo lettura: niente scritture su flash, MSR, /sys o /dev, nessun modulo
# caricato (il modulo msr serve per gli stati C: sudo modprobe msr, a mano).
# Numeri di serie e UUID compaiono solo con le ultime 4 cifre, la chiave di
# Windows (MSDM) mai: il rapporto si puo' allegare a una segnalazione.
#
# Uscita: 0 tutto PASS (o INFO, SKIP), 1 almeno un WARN, 2 almeno un FAIL,
# 3 se non e' partito (non root, opzioni sbagliate). I controlli e le soglie
# sono quelli di docs/testing.md, con gli stessi ID.
#
# Solo la libreria standard di Python.
import argparse
import glob
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid

TOOLS = os.path.dirname(os.path.abspath(__file__))
# gli altri strumenti come librerie, senza lasciare __pycache__ in tools/
sys.dont_write_bytecode = True
sys.path.insert(0, TOOLS)
import update  # noqa: E402  (tools/update.py)


def load_tool(name, filename):
    """Un altro script di tools/ (con il trattino nel nome) come modulo."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


idle = load_tool("idle_report", "idle-report.py")
elog = load_tool("elog", "elog.py")

STATUS_ORDER = ("PASS", "INFO", "SKIP", "WARN", "FAIL")
STATUS_EXIT = {"PASS": 0, "INFO": 0, "SKIP": 0, "WARN": 1, "FAIL": 2}

# Le board di ouroBIOS: il nome, le soglie del tempo fino al payload (WARN,
# FAIL, in secondi, con la cache del training valida), il TPM e la sua
# tabella ACPI. Misurati: M920x 9.4 s con ci-149 al livello DEBUG e la RAM
# azzerata a ogni avvio (docs/m920x.md, Boot time), W541 3.4 s
# (docs/flashing.md, First boot and settings)
BOARDS = {
    "m920x": {"name": "ThinkCentre M920x", "boot": (12.0, 20.0), "tpm": (2, "TPM2")},
    "w541": {"name": "ThinkPad W541", "boot": (6.0, 12.0), "tpm": (1, "TCPA")},
}

# La RAM init con la cache valida (o in S3): oltre 2 s WARN, oltre 5 s FAIL
RAMINIT_LIMITS = (2.0, 5.0)
# Stati C del package a riposo: la parte in PC6 e oltre
IDLE_DEEP_LIMITS = (50.0, 10.0)
# Occupazione media dei core oltre la quale la misura non vale come riposo
IDLE_BUSY_MAX = 10.0
# Un processo che da solo usa piu' di questa parte di un core (in %): la
# macchina non e' a riposo (un browser con una pagina animata, un video)
IDLE_PROC_MAX = 5.0
# Il modo nativo del pannello 3K del W541: acceso, il package resta in PC2
W541_3K = "2880x1620"
# Temperatura del package: oltre WARN, oltre FAIL (TjMax 100 gradi su entrambe)
TEMP_LIMITS = (80.0, 95.0)

# Identificativi dei timestamp (commonlib/include/commonlib/timestamp_serialized.h)
TS_ROMSTAGE_START, TS_INITRAM_START, TS_INITRAM_END, TS_ROMSTAGE_END = 1, 2, 3, 4
TS_VBOOT_START, TS_VBOOT_END, TS_RAMSTAGE_START = 5, 6, 10
TS_LOAD_PAYLOAD, TS_SELFBOOT_JUMP = 90, 99
# "finished LZMA decompress": dopo TS_LOAD_PAYLOAD, la fine del payload compresso
TS_LZMA_END = 16
TS_FSP_MEMORY_INIT_START, TS_FSP_MEMORY_INIT_END = 950, 951
TS_FSP_SILICON_INIT_START, TS_FSP_SILICON_INIT_END = 954, 955

# Le voci di CBMEM lette con cbmem -r (commonlib/bsd/include/commonlib/bsd/cbmem_id.h)
CBMEM_ID_VBOOT_WORKBUF = 0x78007343
CBMEM_ID_FMAP = 0x464D4150

# Il log del driver della cache del training (drivers/mrc_cache/mrc_cache.c):
# niente cache o una cache che non vale, quindi FSP-M (o mrc.bin, la NRI)
# rifa' il training; "does not need update" quando i dati di questo avvio sono
# quelli salvati, cioe' la cache e' stata usata
MRC_TRAINING = re.compile(r"MRC: (version mismatch: .*|no data in '.*'|cache data '.*' needs update"
                          r"|header hash mismatch.*|data hash mismatch.*|invalid header signature"
                          r"|metadata was invalidated|couldn't read metadata|region file invalid.*)")
MRC_VALID = re.compile(r"MRC: '(.*)' does not need update")
MRC_UPDATED = re.compile(r"MRC: updated '(.*)'")

# Il livello dei messaggi nel log di CBMEM (console/printk: [EMERG] ... [SPEW ])
LOG_LEVEL = re.compile(r"^\[(EMERG|ALERT|CRIT |ERROR|WARN |NOTE |INFO |DEBUG|SPEW )\]\s+(.*)$")
LOG_BAD = {"EMERG": "FAIL", "ALERT": "FAIL", "CRIT": "FAIL", "ERROR": "FAIL", "WARN": "WARN"}

# La console seriale del M920x: COM1 del Super I/O, 115200 baud, 8N1 (10 bit
# per byte), con il prefisso e le sequenze ANSI del defconfig. Una riga al
# livello L costa la sequenza di L (bios_log_escape, commonlib/loglevel.h),
# il prefisso "[DEBUG]  " che cbmem -1 scrive uguale, il testo, il reset
# "\x1b[0m" e "\r\n" (console/printk.c, console/console.c). Il log di CBMEM ha
# ogni riga fino a DEBUG a qualsiasi livello (console_log_level(),
# CONSOLE_LOG_FAST), anche quelle degli AP, quindi da' i byte di ogni livello
SERIAL_BAUD = 115200
LEVEL_NUMBER = {"EMERG": 0, "ALERT": 1, "CRIT ": 2, "ERROR": 3, "WARN ": 4, "NOTE ": 5, "INFO ": 6,
                "DEBUG": 7, "SPEW ": 8}
LEVEL_ESCAPE = ("1;4;5;7", "1;4;7", "1;7", "7", "1;4", "1", "0", "0", "0")
LEVEL_NAME = ("Emergency", "Alert", "Critical", "Error", "Warning", "Notice", "Info", "Debug", "Spew")
STAGE_BANNER = re.compile(r"coreboot-(\S+) .* (bootblock|verstage|romstage|postcar|ramstage) starting "
                          r"\(log level: (\d+)\)")
# la tabella ACPI che coreboot scrive solo con la console seriale accesa
# (acpi_create_spcr(), console_serial_enabled(): Console > Serial Console)
SPCR_TABLE = "/sys/firmware/acpi/tables/SPCR"

# Messaggi gia' noti del log di coreboot: (regex, board o None per tutte, perche')
# (espressione, board o None, motivo[, ultima release in cui e' noto]): con il
# quarto elemento il messaggio e' noto solo su quella release e le precedenti,
# mai su una build della CI (una regressione va vista)
KNOWN_FW_LOG = (
    (r"CBFS: 'fallback/slic' not found", "w541",
     "la tabella SLIC e' facoltativa: acpi.c la cerca sempre in CBFS"),
    (r"CBFS: 'fallback/slic' not found", "m920x",
     "la tabella SLIC e' facoltativa: acpi.c la cercava sempre in CBFS; dalla patch 0287 il M920x non la "
     "cerca piu' (ACPI_SLIC_CBFS, la MSDM viene dalla VPD)", (1, 7, 0)),
    (r"SPI Transaction Error at Flash Offset [0-9a-f]+ HSFSTS = 0x0[c8]04f803", "m920x",
     "fino a v1.5.0 la protezione in scrittura del BIOS (FLOCKDN, FCERR) precede i due eventi di "
     "fine ramstage; da v1.6.0 la applica il finalize in SMM (patch 0209)", (1, 5, 0)),
    (r"ELOG: NV Write failed at 0x[0-9a-f]+, size 0x[0-9a-f]+", "m920x",
     "fino a v1.5.0 il registro perde il 'boot' e il 'System reset' di ogni avvio: vedi l'errore SPI; "
     "corretto da v1.6.0 (patch 0209)", (1, 5, 0)),
    (r"HECI: CSE device 16\.0 is disabled", "m920x",
     "alla ripresa da S3 con il ME spento (me_state): la ramstage lo cerca e lo trova nascosto; dalla "
     "patch 0286 lo dice al livello debug", (1, 7, 0)),
    (r"PMC: Duplicate GPE DW register values detected", "m920x",
     "dal bootblock di una parte RO di prima della patch 0166 (una capsula non la riscrive); "
     "il ramstage con la 0166 non lo stampa piu'"),
    # docs/flashing.md, First boot and settings: normali sul W541. Con l'MBP
    # che non arriva lynxpoint/me.c stampa anche, in CRIT, "intel_me_path: mbp
    # is not ready!". Non "ME is not ready!" della romstage della NRI
    # (early_me.c): l'attesa di 1 s dell'UMA, da vedere su un W541 vero
    (r"ME: BIOS path: Error|MBP not ready|intel_me_path: mbp is not ready!", "w541",
     "ME ridotto da me_cleaner -S"),
    (r"RO_VPD is uninitialized|DMI: Cannot read .* from VPD|No RW_VPD FMAP section", "w541",
     "VPD vuota (tools/vpd.py)"),
    (r"1c\.3: Timeout waiting for 328h", "w541", "la root port 4, non usata"),
)
# Avvisi del log di coreboot che raccontano un evento atteso: INFO, non un
# problema (drivers/efi/option.c, DRIVERS_EFI_RESET_OPTIONS_ON_RTC_FAILURE)
EVENT_FW_LOG = (
    # patch 0288: la ramstage finisce un reclaim dello store in SMM che una
    # caduta di corrente ha interrotto (drivers/smmstore/reclaim.c)
    (r"SMMSTORE: finishing a reclaim cut by a power loss", None,
     "un reclaim dello store in SMM era stato interrotto (corrente persa durante la copia): la ramstage "
     "lo ha finito dall'area di appoggio"),
    (r"Setup options: \d+ reset to defaults \(RTC power lost\)", None,
     "la RTC ha perso l'alimentazione (pila, jumper della CMOS): le opzioni del setup sono ai default, "
     "Firmware protection compresa"),
    # W541 dalla v1.6.1 (patch 0256): il bit RTC_PWR_STS acceso senza la CMOS
    # persa, che il sistema operativo puo' fare da solo: le opzioni restano
    (r"Setup options: not reset, RTC power lost but the CMOS kept the last boot|"
     r"RTC power lost: setup options not reset, the CMOS kept its contents", "w541",
     "il bit RTC_PWR_STS era acceso ma la CMOS no (il sistema operativo puo' accenderlo, o la RTC ha perso "
     "l'alimentazione lasciando il segno dei banchi valido): le opzioni del setup restano come erano"),
    # W541 nri dalla v1.7.0 (patch 0291-0297): il controllo dei margini dopo il
    # training e' un rapporto; con HASWELL_NRI_MARGIN_CHECK_RETRAIN rifarebbe
    # il training, qui no. Solo nei boot che fanno il training
    (r"\*\*\*\*\* Margin limit check failed! \*\*\*\*\*|Margins below the retrain limits, training kept",
     "w541",
     "margini della memoria sotto i limiti di retrain dell'MRC: il controllo dei margini li riporta e il "
     "training resta (la tabella in cbmem -1 dopo 'Margin: RdT', MEM-17 di docs/testing.md)"),
)

# Il kernel: messaggi che riguardano il firmware (tabelle ACPI, PCI, VT-d,
# grafica, TPM, microcode, mappa della memoria)
KERNEL_FW = re.compile(r"ACPI|firmware|BIOS|i915|\bpci|PCIe|DMAR|IOMMU|_DSM|_OSC|_CRS|HPET|TPM|MTRR|"
                       r"microcode|e820|\bMCE\b|mce:|x2apic|SMBIOS|DMI:", re.I)
KNOWN_KERNEL = (
    (r"Direct firmware load for .* failed|firmware: failed to load", None,
     "un file di linux-firmware del driver, non il BIOS"),
    (r"PCIe ACS overrides enabled", None, "pcie_acs_override sulla riga di comando del kernel"),
    (r"SGX disabled or unsupported by BIOS", None,
     "il firmware non attiva SGX (SOC_INTEL_COMMON_BLOCK_SGX_ENABLE, default n) e il kernel lo dice "
     "perche' KVM potrebbe usarlo; 'nosgx' sulla riga di comando del kernel lo toglie"),
    # drivers/char/hpet.c prende gli IRQ solo da Interrupt() e, se ne trova,
    # accende il contatore dell'HPET: dargliene sarebbe peggio del messaggio
    (r"hpet_acpi_add: no address or irqs in _CRS", "m920x",
     "il kernel spegne l'HPET perche' il processore puo' andare in PC10 ('HPET dysfunctional in PC10. "
     "Force disabled'), poi il driver di /dev/hpet prova da solo il dispositivo ACPI e non trova un "
     "Interrupt() nel _CRS: non e' il firmware; 'initcall_blacklist=hpet_init' sulla riga di comando lo "
     "toglie"),
    (r"i915 .*DPLL [0-9]+ not locked", None,
     "intermittente all'avvio con un monitor HDMI collegato (M920x: 2 avvii su 6 di ci-244, anche su ci-209, "
     "ci-211 e v1.5.x): i915 e l'init del display del firmware, da capire a parte (docs/roadmap.md)"),
    (r"TSC ADJUST differs: CPU0 0 --> [0-9]+\. Restoring", "w541",
     "a ogni resume da S3 il kernel trova IA32_TSC_ADJUST del processore 0 diverso da zero e lo rimette a "
     "zero da solo (il TSC resta coerente); non e' il firmware: misurato con una build di prova, il "
     "registro e' 0 fino al salto al wake vector e il TSC di prima della sospensione viene riscritto "
     "dopo, lato Linux (docs/tests/v1.6.0/w541-nri/diag.md); c'era anche con la v1.5.0"),
    # Sul W541 non piu' noti: GPLV ("SystemIO range ... conflicts with
    # OpRegion") e "failed to evaluate _DSM" di iwlwifi li tolgono le patch
    # 0068 e 0069; se tornano e' una regressione
)

# ME: i valori delle righe di cse_spec.c (CSME, numeri) e di
# lynxpoint/me_status.c (W541, nomi)
ME_MODES = {"Normal": 0, "Debug": 2, "Soft Temporary Disable": 3, "Security Override via Jumper": 4,
            "Security Override via MEI Message": 5}
ME_HFS1_CWS_NORMAL = 5          # intelblocks/cse.h
ME_HFS1_COM_NORMAL = 0
ME_HFS1_COM_SOFT_TEMP_DISABLE = 3
# W541: il riassunto del firmware nelle stringhe OEM (mainboard/lenovo/
# haswell/me_status.c): quelli di un ME a posto (me_cleaner -S sulle immagini
# di ouroBIOS, o il ME intero di Lenovo su un altro W541) e quelli che si
# spiegano senza un guasto
ME9_GOOD = ("Disabled (AltMeDisable, BUP)", "Enabled")
ME9_INFO = ("Not available", "Disabled (soft temporary disable)")

# MSR (Intel SDM vol. 4; cpu/intel/haswell/haswell.h)
MSR_PLATFORM_INFO = 0xCE
MSR_TEMPERATURE_TARGET = 0x1A2
MSR_TURBO_RATIO_LIMIT = 0x1AD
MSR_PKG_POWER_SKU_UNIT = 0x606
MSR_PKG_POWER_LIMIT = 0x610
# L'offset TCC: programmabile se PLATFORM_INFO bit 30; in MSR 0x1A2 i bit
# 27:24 su Haswell (il W541, dove l'SDM li da' riservati) e 29:24 sul M920x
PLATFORM_INFO_PROG_TCC = 1 << 30

# L'EC del W541 (e del W540): ECP 1.15, GMHT30WW, corregge CVE-2019-6171
# (LEN-27764, firmware Lenovo 2.40); ouroBIOS non aggiorna l'EC
EC_BUILD_RE = re.compile(r"^([0-9A-Z]{4})(\d{2})WW")
EC_MIN = {"GMHT": (30, "1.15")}
EC_STRING_RE = re.compile(r"^IBM ThinkPad Embedded Controller -\[(\S+)\s*\]-$")

# Il Protected Range che coreboot scrive (southbridge/intel/common/spi.c sul
# W541, fast_spi_flash.c sul M920x): quando i registri non si leggono
FPR_LOG = r"^(?:fast_)?spi_flash_protect: FPR (\d) is enabled for range 0x([0-9a-f]{8})-0x([0-9a-f]{8})$"

# Le opzioni di coreboot in SMMSTORE (drivers/efi/option.c, EficorebootNvDataGuid)
CB_OPTION_GUID = uuid.UUID("ceae4c1d-335b-4685-a4a0-fc4a94eea085").bytes_le


class Usage(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        die(message)


def die(msg):
    print("hw-report.py: " + msg, file=sys.stderr)
    sys.exit(3)


def rd(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def run(cmd, binary=False, timeout=60):
    """(codice di uscita, uscita) di un comando, None se non c'e' o non finisce."""
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.returncode, (p.stdout if binary else p.stdout.decode("utf-8", "replace"))


def redact(s):
    """Le sole ultime 4 cifre di un numero di serie o di un UUID."""
    s = (s or "").strip()
    return "****" + s[-4:] if len(s) > 4 else "****"


def sec(us):
    return "%.2f s" % (us / 1e6)


def serial_bytes(log):
    """I byte che gli stage dello slot (romstage, postcar, ramstage) mandano
    alla seriale per le righe di ogni livello del log di CBMEM: {stage:
    (livello dello stage dal banner, [byte dei livelli 0..8])}. Le righe prima
    della romstage non contano: bootblock e verstage sono della parte RO, con
    il suo livello. Una riga senza marcatore (vuota, o il seguito di una
    riga) va con il livello della riga prima."""
    stages, cur, last = {}, None, None
    for line in log or ():
        m = LOG_LEVEL.match(line)
        if m:
            last = LEVEL_NUMBER[m.group(1)]
            b = STAGE_BANNER.search(m.group(2))
            if b:
                cur = b.group(2) if b.group(2) in ("romstage", "postcar", "ramstage") else None
                if cur:
                    stages[cur] = (int(b.group(3)), [0] * len(LEVEL_NAME))
            if cur:
                stages[cur][1][last] += len("\x1b[%sm" % LEVEL_ESCAPE[last]) + len(line) + len("\x1b[0m\r\n")
        elif cur and last is not None:
            stages[cur][1][last] += len(line) + len("\x1b[0m\r\n")
    return stages


def serial_seconds(stages, level=None):
    """I secondi della seriale per gli stage dello slot: al livello di ognuno
    (dal banner) o, con level, a quel livello per romstage e ramstage, che
    leggono Console > Console Log Level; postcar resta al default della build
    (con le variabili UEFI non legge le opzioni)."""
    total = 0
    for stage, (lv, counts) in stages.items():
        use = lv if level is None or stage == "postcar" else level
        total += sum(counts[:use + 1])
    return total * 10 / SERIAL_BAUD


class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, title, status, summary, details=(), data=None):
        assert status in STATUS_ORDER
        self.checks.append({"id": cid, "title": title, "status": status, "summary": summary,
                            "details": list(details), "data": data or {}})

    def worst(self):
        return max((c["status"] for c in self.checks), key=lambda s: STATUS_EXIT[s] * 10 + STATUS_ORDER.index(s),
                   default="PASS")

    def exit_code(self):
        return max((STATUS_EXIT[c["status"]] for c in self.checks), default=0)

    def counts(self):
        n = {s: 0 for s in STATUS_ORDER}
        for c in self.checks:
            n[c["status"]] += 1
        return n


def worst(*statuses):
    return max(statuses, key=lambda s: STATUS_EXIT[s] * 10 + STATUS_ORDER.index(s))


# --- cosa ha lasciato il firmware ---------------------------------------------

class Firmware:
    """Il log e i timestamp di coreboot di questo avvio, e la board."""

    def __init__(self):
        self.cbmem = shutil.which("cbmem")
        self.bios = rd("/sys/class/dmi/id/bios_version", "")
        self.log, self.ts, self.total_line = None, [], None
        if self.cbmem:
            r = run([self.cbmem, "-1"])
            if r and r[0] == 0:
                self.log = r[1].splitlines()
            r = run([self.cbmem, "-T"])
            if r and r[0] == 0:
                for line in r[1].splitlines():
                    parts = line.split("\t", 3)
                    if len(parts) == 4 and parts[0].isdigit():
                        self.ts.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3].strip()))
        self.board = self.detect_board()

    @property
    def release(self):
        """(major, minor, patch) di una release, None per una build della CI."""
        m = re.search(r"-v(\d+)\.(\d+)\.(\d+)(?:-rc\d+)?-", getattr(self, "bios", "") or "")
        return tuple(int(x) for x in m.groups()) if m else None

    def detect_board(self):
        b = self.bios or ""
        if "-m920x-" in b:
            return "m920x"
        if re.search(r"-(mrc|nri)$", b):
            return "w541"
        dmi = " ".join(rd("/sys/class/dmi/id/" + f, "") for f in ("board_name", "product_version"))
        if re.search(r"M920x|M920q|M720q", dmi):
            return "m920x"
        if "W541" in dmi:
            return "w541"
        return None

    def raw(self, cbmem_id):
        """Una voce di CBMEM (cbmem -r), None se non c'e'."""
        if not self.cbmem:
            return None
        r = run([self.cbmem, "-r", "%x" % cbmem_id], binary=True)
        return r[1] if r and r[0] == 0 and r[1] else None

    def grep(self, pattern):
        """Le righe del log (senza il livello) che corrispondono, con i gruppi."""
        out = []
        rx = re.compile(pattern)
        for line in self.log or ():
            m = LOG_LEVEL.match(line)
            text = m.group(2) if m else line
            g = rx.search(text)
            if g:
                out.append(g)
        return out

    def stamp(self, ts_id, after=0):
        """Il primo timestamp con questo id (in us dal reset), dopo after."""
        for i, t, _, _ in self.ts:
            if i == ts_id and t >= after:
                return t
        return None

    def span(self, start, end):
        a = self.stamp(start)
        if a is None:
            return None
        b = self.stamp(end, a)
        return None if b is None else b - a


def known(text, table, board, release=None):
    for entry in table:
        rx, b, why = entry[:3]
        if b is not None and b != board:
            continue
        if len(entry) > 3 and (release is None or release > entry[3]):
            continue
        if re.search(rx, text):
            return why
    return None


# --- i controlli ---------------------------------------------------------------

OPTION_LOCK_VAR = "/sys/firmware/efi/efivars/OptionLockStatus-ceae4c1d-335b-4685-a4a0-fc4a94eea085"


def option_lock_status():
    """La risposta di SMM all'armamento del blocco delle opzioni come la riporta
    il payload (edk2/0057): None senza la variabile (firmware di prima, o
    senza vboot)."""
    try:
        raw = open(OPTION_LOCK_VAR, "rb").read()
    except OSError:
        return None
    if len(raw) != 12:
        return "variabile di %d byte, attesi 4 di attributi e 8 di valore" % len(raw)
    v = int.from_bytes(raw[4:], "little")
    if v == 0:
        return "armato: bios_lock e bootmedia_lock di sola lettura per l'OS"
    if v == 0x8000000000000003:
        return "non armato: EFI_UNSUPPORTED (BIOS Lock spento o firmware senza il blocco)"
    return "non armato: EFI_STATUS %#x" % v

def check_firmware(fw, rep):
    """BOOT-01: quale firmware gira, e se le parti dicono la stessa versione."""
    details, status = [], "PASS"
    bios = fw.bios
    is_release = bool(update.RELEASE_RE.search(bios.encode()))
    is_ci = bool(update.CI_BUILD_RE.search(bios.encode()))
    vendor = rd("/sys/class/dmi/id/bios_vendor", "?")
    details.append("SMBIOS: %s, %s (%s)" % (vendor, bios or "?", rd("/sys/class/dmi/id/bios_date", "?")))
    if not (is_release or is_ci):
        status = "WARN"
        details.append("la versione non e' quella di una release ne' di una build della CI di ouroBIOS")
    if fw.log is None:
        rep.add("BOOT-01", "Firmware", "WARN" if status == "PASS" else status,
                "%s; log di coreboot non letto (%s)" % (bios or "?", "cbmem non trovato" if not fw.cbmem
                                                         else "cbmem -1 non riuscito"), details)
        return
    banners = {}
    for m in fw.grep(r"coreboot-(\S+) .* (bootblock|verstage|romstage|postcar|ramstage) starting "
                     r"\(log level: (\d+)\)"):
        banners[m.group(2)] = (m.group(1), int(m.group(3)))
    for stage in ("bootblock", "romstage", "ramstage"):
        if stage in banners:
            details.append("%-9s %s, log level %d" % (stage, banners[stage][0], banners[stage][1]))
    rw = [v for s, (v, _) in banners.items() if s in ("romstage", "postcar", "ramstage")]
    # la versione senza l'identificativo nel formato Lenovo che il W541 e il
    # T440p le mettono davanti in SMBIOS ("CBET4000 ", patch 0001)
    ver = bios.split()[-1] if bios else bios
    if ver and rw and any(not v.endswith(ver) for v in rw):
        status = "WARN"
        details.append("le versioni degli stage dello slot non sono quella di SMBIOS")
    if "bootblock" not in banners:
        details.append("il banner del bootblock (parte RO) non e' nel log: la console prima di CBMEM e' "
                       "traboccata" if any("console overflowed" in l for l in fw.log) else
                       "il banner del bootblock non e' nel log")
    level = banners.get("ramstage", (None, None))[1]
    console = sum(int(m.group(3)) for m in fw.grep(r"BS: (.+?) times \(exec / console\): (.+?) / (\d+) ms"))
    if level is not None:
        # le righe BS: contano la console del solo processore di avvio: quella
        # degli AP (MP init, MTRR) finisce nella colonna exec
        details.append("console: %.1f s negli stage (righe BS:, processore di avvio), livello %d" % (
            console / 1000, level))
    serial = serial_report(fw) if fw.board == "m920x" else None
    if serial:
        details.append(serial["text"])
    kind = "release" if is_release else "build della CI" if is_ci else "?"
    rep.add("BOOT-01", "Firmware", status, "%s (%s)" % (bios or "?", kind), details,
            {"bios_version": bios, "banners": {k: v[0] for k, v in banners.items()}, "log_level": level,
             "console_ms": console, "serial": {k: v for k, v in serial.items() if k != "text"} if serial else None})


def serial_report(fw):
    """La seriale del M920x: accesa o no (la tabella SPCR), e i secondi che
    costa agli stage dello slot al livello di ora e agli altri dell'opzione,
    contati sul log (serial_bytes)."""
    stages = serial_bytes(fw.log)
    if "ramstage" not in stages:
        return None
    on = os.path.exists(SPCR_TABLE) if os.path.isdir(os.path.dirname(SPCR_TABLE)) else None
    level = stages["ramstage"][0]
    now = serial_seconds(stages)
    alt = {LEVEL_NAME[lv]: round(serial_seconds(stages, lv), 2) for lv in (6, 5, 3) if lv != level}
    if on is False:
        text = ("seriale spenta (Console > Serial Console): la COM1 non costa niente; accesa, al livello %d "
                "(%s), ~%.1f s agli stage dello slot" % (level, LEVEL_NAME[level], now))
    else:
        text = ("seriale%s, COM1 a %d baud: ~%.1f s agli stage dello slot (romstage, postcar, ramstage, AP "
                "compresi) al livello %d (%s); %s; spenta (Console > Serial Console) 0. Il log di CBMEM "
                "resta fino a DEBUG a ogni livello" % (
                    "" if on else " (tabella SPCR non letta)", SERIAL_BAUD, now, level, LEVEL_NAME[level],
                    ", ".join("a %s ~%.1f s" % (k, v) for k, v in alt.items())))
    return {"text": text, "on": on, "seconds": round(now, 2), "by_level": alt}


VB2_FW_RESULT_FAILURE = 3


def check_vboot(fw, rep):
    """VB-01: lo slot che gira e com'e' andato l'avvio prima (workbuf di vboot in CBMEM)."""
    sel = fw.grep(r"Slot ([AB]) is selected")
    log_slot = sel[-1].group(1) if sel else None
    wb = fw.raw(CBMEM_ID_VBOOT_WORKBUF)
    if not wb or len(wb) < 432 or struct.unpack_from("<I", wb, 0)[0] != update.VB2_SD_MAGIC:
        if log_slot:
            rep.add("VB-01", "vboot", "INFO", "slot %s (dal log; workbuf di vboot non letta)" % log_slot)
        else:
            rep.add("VB-01", "vboot", "SKIP", "niente workbuf di vboot ne' riga 'Slot X is selected'")
        return
    slot = "AB"
    flags = struct.unpack_from("<Q", wb, 8)[0]
    nv = wb[16:32]
    (_, _, _, recovery, last_slot, last_result, fw_slot, _, _, _) = struct.unpack_from("<10I", wb, 392)
    running = slot[fw_slot & 1]
    details = ["contesto: %s" % (" ".join(n for b, n in update.VB2_CONTEXT_FLAGS if flags >> b & 1) or "-"),
               "avvio prima: slot %s, %s" % (slot[last_slot & 1], update.NV_RESULTS[last_result & 3])]
    status, summary = "PASS", "slot %s" % running
    nv_ok = nv[0] & 0xc3 == 0x40 and update.nv_crc8(nv[:15]) == nv[15]
    if nv_ok:
        b1, b2 = nv[1], nv[7]
        n = b1 & 0x0f
        details.append("RW_NVRAM in verstage: prossimo slot %s, %d tentativ%s; corrente slot %s %s" % (
            slot[(b2 >> 3) & 1], n, "o" if n == 1 else "i", slot[(b2 >> 2) & 1], update.NV_RESULTS[b2 & 3]))
        if b1 & 0x0f:
            details.append("slot in prova (una capsula, update.py other-slot o rollback): il payload lo "
                           "conferma quando arriva alla sua console")
    else:
        details.append("i dati di RW_NVRAM nella workbuf non sono validi")
    if log_slot and log_slot != running:
        status = "WARN"
        details.append("il log dice slot %s, la workbuf slot %s" % (log_slot, running))
    if recovery or flags & (1 << 2):
        status = "FAIL"
        summary += ", RECOVERY (motivo 0x%02x): questo firmware non ha recovery" % recovery
    elif last_result == VB2_FW_RESULT_FAILURE:
        status = "WARN"
        summary += ": lo slot %s dell'avvio prima non si e' verificato o non e' partito" % slot[last_slot & 1]
    else:
        summary += ", avvio prima slot %s %s" % (slot[last_slot & 1], update.NV_RESULTS[last_result & 3])
    rep.add("VB-01", "vboot", status, summary, details,
            {"slot": running, "last_slot": slot[last_slot & 1], "last_result": last_result,
             "recovery": recovery})


def check_update(fw, rep):
    """UPD-01: l'ESRT (versione, ultimo aggiornamento) e una capsula in attesa."""
    try:
        e = update.esrt_entry()
    except (OSError, update.Error) as ex:
        rep.add("UPD-01", "Aggiornamenti", "WARN", "ESRT non letta: %s" % ex)
        return
    if e is None:
        rep.add("UPD-01", "Aggiornamenti", "WARN" if fw.board else "SKIP",
                "nessuna voce di ouroBIOS nell'ESRT: il firmware non applica capsule")
        return
    details = ["variante %s, GUID %s" % (e["variant"], e["guid"]),
               "versione %s, minima per una capsula %s" % (update.version_str(e["version"]),
                                                          update.version_str(e["lsv"]))]
    status = "PASS"
    summary = "%s, variante %s" % (update.version_str(e["version"]), e["variant"])
    if e["version"] == 0:
        details.append("versione 0: una build della CI, che nessuna capsula considera piu' vecchia")
    if e["last_version"]:
        details.append("ultimo aggiornamento: %s, %s" % (update.version_str(e["last_version"]),
                                                          update.attempt_str(e["last_status"])))
        if e["last_status"] != 0:
            status = "WARN"
            summary += "; l'ultima capsula non e' stata scritta: %s" % update.attempt_str(e["last_status"])
        elif not e["legacy"] and e["last_version"] != e["version"]:
            status = "WARN"
            summary += "; la capsula %s e' stata scritta ma gira la %s (vboot e' tornato all'altro slot?)" % (
                update.version_str(e["last_version"]), update.version_str(e["version"]))
    else:
        details.append("nessun aggiornamento con capsula")
    try:
        if not update.cod_supported():
            status = "WARN"
            details.append("capsule su disco NON supportate dal firmware (OsIndicationsSupported)")
        if update.os_indications() & update.FILE_CAPSULE_DELIVERY:
            details.append("il bit di OsIndications e' acceso: una capsula si applica al prossimo avvio "
                           "(update.py status)")
    except (OSError, update.Error) as ex:
        details.append("variabili UEFI non lette: %s" % ex)
    rep.add("UPD-01", "Aggiornamenti", status, summary, details,
            {"variant": e["variant"], "version": e["version"], "lsv": e["lsv"],
             "last_version": e["last_version"], "last_status": e["last_status"]})


def cache_state(fw):
    """Lo stato della cache del training in questo avvio: (stato, perche')."""
    if fw.grep(r"^S3 Resume$"):
        return "s3", "ripresa da S3"
    t = fw.grep(MRC_TRAINING.pattern)
    if t:
        upd = fw.grep(MRC_UPDATED.pattern)
        return "training", t[0].group(0) + ("; salvata di nuovo" if upd else "")
    v = fw.grep(MRC_VALID.pattern)
    if v:
        return "valid", "'%s' valida, usata" % v[0].group(1)
    # la NRI del W541 (raminit_native.c, INFO): il training salvato usato
    if fw.grep(r"^Using cached memory parameters$"):
        return "valid", "training salvato usato (NRI: Using cached memory parameters)"
    return "unknown", "stato della cache non nel log"


def log_level(fw):
    """Il livello del log di questo avvio, dal banner di ramstage (o di
    romstage): Setup > Console > Console Log Level lo cambia senza una build."""
    levels = {m.group(1): int(m.group(2)) for m in
              fw.grep(r"coreboot-\S+ .* (romstage|ramstage) starting \(log level: (\d+)\)")}
    return levels.get("ramstage", levels.get("romstage"))


def debug_hint(fw, what):
    """Perche' mancano righe di livello DEBUG (7), se il log e' piu' basso."""
    level = log_level(fw)
    if level is not None and level < 7:
        return "%s sono di livello DEBUG (7), il log di questo avvio e' al livello %d: Setup > Console > " \
            "Console Log Level" % (what, level)
    return None


def raminit_span(fw):
    """(durata, cosa) della RAM init: FspMemoryInit (M920x), la RAM init
    (mrc.bin, e la NRI con i timestamp di raminit_native.c), se no tutta la
    romstage (gli slot della NRI di prima: la RAM init c'e' dentro)."""
    for a, b, what in ((TS_FSP_MEMORY_INIT_START, TS_FSP_MEMORY_INIT_END, "FspMemoryInit"),
                       (TS_INITRAM_START, TS_INITRAM_END, "RAM init"),
                       (TS_ROMSTAGE_START, TS_ROMSTAGE_END, "romstage (RAM init compresa)")):
        t = fw.span(a, b)
        if t is not None:
            return t, what
    return None, None


def me_did_wait(fw, seconds, state):
    """M920x con il ME spento dal setup (patch 0191): FSP-M aspetta la risposta
    del ME al DRAM Init Done fino a 5 s, a caso per avvio o ripresa; noto,
    non un difetto della build."""
    return (fw.log is not None and state in ("valid", "s3") and 5.0 <= seconds <= 5.6 and
            bool(fw.grep(r"ME disabled: no HECI retries or MBP read in FSP-M")))


def check_raminit(fw, rep):
    """MEM-01: quanto ha preso la RAM init, rispetto alla cache del training."""
    if not fw.ts:
        rep.add("MEM-01", "RAM init", "SKIP", "timestamp di coreboot non letti (cbmem -T)")
        return
    t, what = raminit_span(fw)
    if t is None:
        rep.add("MEM-01", "RAM init", "SKIP", "nessun timestamp della RAM init")
        return
    state, why = cache_state(fw) if fw.log is not None else ("unknown", "log di coreboot non letto")
    details = ["cache del training: %s" % why]
    if what.startswith("romstage"):
        details.append("nessun timestamp della RAM init (la NRI prima dei suoi, raminit_native.c): conta "
                       "tutta la romstage")
    hint = debug_hint(fw, "le righe 'MRC:' della cache") if state == "unknown" and fw.log is not None else None
    if hint:
        details.append(hint)
    s = t / 1e6
    if state == "training":
        status = "INFO"
        summary = "%s %.2f s, avvio con il training (%s): al prossimo avvio deve stare sotto %.0f s" % (
            what, s, why.split(";")[0], RAMINIT_LIMITS[0])
    else:
        status = "PASS" if s <= RAMINIT_LIMITS[0] else "WARN" if s <= RAMINIT_LIMITS[1] else "FAIL"
        summary = "%s %.2f s con %s (soglie %.0f/%.0f s)" % (
            what, s, {"s3": "la ripresa da S3", "valid": "la cache valida"}.get(state, "cache non nota"),
            RAMINIT_LIMITS[0], RAMINIT_LIMITS[1])
        if status != "PASS" and me_did_wait(fw, s, state):
            status = "INFO"
            summary += "; noto: con il ME spento FSP-M aspetta fino a 5 s la risposta del ME al DRAM " \
                       "Init Done (patch 0191), a caso per avvio o ripresa"
        elif status != "PASS" and state == "valid":
            details.append("con la cache valida FSP-M non rifa' il training: un tempo cosi', uguale a ogni "
                           "avvio, e' un'attesa o un timeout (ci-150 e ci-151: 15.24 s)")
    rep.add("MEM-01", "RAM init", status, summary, details, {"seconds": round(s, 3), "cache": state})


SEGMENTS = (
    ("fino a romstage (bootblock, verstage)", None, TS_ROMSTAGE_START),
    ("romstage", TS_ROMSTAGE_START, TS_ROMSTAGE_END),
    ("  di cui FspMemoryInit", TS_FSP_MEMORY_INIT_START, TS_FSP_MEMORY_INIT_END),
    ("  di cui RAM init", TS_INITRAM_START, TS_INITRAM_END),
    ("postcar e caricamento di ramstage", TS_ROMSTAGE_END, TS_RAMSTAGE_START),
    ("ramstage", TS_RAMSTAGE_START, TS_LOAD_PAYLOAD),
    ("  di cui FspSiliconInit", TS_FSP_SILICON_INIT_START, TS_FSP_SILICON_INIT_END),
)


def check_boot_time(fw, rep):
    """BOOT-02: il tempo dal reset al payload, e dove va."""
    if not fw.ts:
        rep.add("BOOT-02", "Tempo di avvio", "SKIP", "timestamp di coreboot non letti (cbmem -T)")
        return
    end = fw.stamp(TS_SELFBOOT_JUMP)
    total = end if end is not None else fw.ts[-1][1]
    details = []
    for label, a, b in SEGMENTS:
        if label.endswith("RAM init") and fw.stamp(TS_FSP_MEMORY_INIT_START) is not None:
            continue
        d = (fw.stamp(b) if a is None else fw.span(a, b))
        if d is not None:
            details.append("%-38s %8s" % (label, sec(d)))
    # il payload: caricato e decompresso, poi i passi prima del salto
    # (BS_PAYLOAD_LOAD exit e BS_PAYLOAD_BOOT: la SMI di finalize, le notifiche
    # di FSP, il registro del TPM sulla console)
    load, jump = fw.stamp(TS_LOAD_PAYLOAD), fw.stamp(TS_SELFBOOT_JUMP)
    if load is not None and jump is not None:
        lz = fw.stamp(TS_LZMA_END, load)
        if lz is not None and lz <= jump:
            details.append("%-38s %8s" % ("caricamento del payload", sec(lz - load)))
            details.append("%-38s %8s" % ("dal payload caricato al salto", sec(jump - lz)))
        else:
            details.append("%-38s %8s" % ("caricamento del payload", sec(jump - load)))
    top = sorted(fw.ts[1:], key=lambda x: -x[2])[:5]
    details.append("i passi piu' lunghi: " + "; ".join("%s fino a '%s'" % (sec(d), n) for _, _, d, n in top))
    # Clear memory at power-on: dalla riga di security/memory (patch 0192),
    # Always, When the OS asks (la richiesta TCG MOR) o Never; prima, solo
    # se ha cancellato
    clear = fw.grep(r"DRAM clear: option (always|never|when the OS asks)"
                    r"(?:, request of the OS (yes|no))?: (clearing|not clearing)") \
        if fw.log is not None else []
    if clear:
        mode, req, act = clear[-1].groups()
        details.append("Clear memory at power-on: %s%s: %s" % (
            {"always": "Always", "when the OS asks": "When the OS asks", "never": "Never"}[mode],
            "" if req is None else ", richiesta del sistema operativo (MOR) %s" % ("si'" if req == "yes" else "no"),
            "memoria cancellata (~0.5 s ogni 10 GB)" if act == "clearing" else "memoria non cancellata"))
    elif fw.log is not None and fw.grep(r"clear_memory: Clearing DRAM"):
        details.append("Clear memory at power-on acceso (~0.5 s ogni 10 GB)")
    state = cache_state(fw)[0] if fw.log is not None else "unknown"
    # con il training si toglie la RAM init (sugli slot della NRI senza i suoi
    # timestamp tutta la romstage, che la contiene)
    raminit = raminit_span(fw)[0] or 0
    # e i 5 s dell'attesa nota del ME spento (me_did_wait), che non sono della build
    me_wait = state != "training" and me_did_wait(fw, raminit / 1e6, state)
    eff = total - raminit if state == "training" or me_wait else total
    b = BOARDS.get(fw.board)
    s = eff / 1e6
    if b is None:
        status, limits = "INFO", ""
    else:
        warn, fail = b["boot"]
        status = "PASS" if s <= warn else "WARN" if s <= fail else "FAIL"
        limits = " (soglie %.0f/%.0f s per %s)" % (warn, fail, b["name"])
    summary = "%.2f s dal reset %s%s%s" % (total / 1e6, "al ritorno nell'OS (ripresa da S3)" if state == "s3"
                                           else "al payload", (", %.2f s senza il training" % s)
                                           if state == "training" else (", %.2f s senza l'attesa nota del ME "
                                                                        "spento (patch 0191)" % s)
                                           if me_wait else "", limits)
    rep.add("BOOT-02", "Tempo di avvio", status, summary, details,
            {"total_s": round(total / 1e6, 3), "without_training_s": round(s, 3), "cache": state})


def check_fw_log(fw, rep):
    """BOOT-03: [ERROR] e [WARN ] del log di coreboot, senza ripetizioni."""
    if fw.log is None:
        rep.add("BOOT-03", "Log di coreboot", "SKIP", "cbmem -1 non letto")
        return
    seen = {}
    for line in fw.log:
        m = LOG_LEVEL.match(line)
        if not m:
            continue
        lvl = m.group(1).strip()
        if lvl in LOG_BAD:
            key = (lvl, m.group(2).strip())
            seen[key] = seen.get(key, 0) + 1
    status, details, new, events = "PASS", [], 0, []
    for (lvl, text), n in seen.items():
        why = known(text, KNOWN_FW_LOG, fw.board, fw.release)
        event = known(text, EVENT_FW_LOG, fw.board)
        times = " (x%d)" % n if n > 1 else ""
        if event:
            status = worst(status, "INFO")
            events.append(event.split(":")[0])
            details.append("[%-5s] %s%s  -- evento: %s" % (lvl, text, times, event))
        elif why:
            details.append("[%-5s] %s%s  -- noto: %s" % (lvl, text, times, why))
        else:
            new += 1
            status = worst(status, LOG_BAD[lvl])
            details.append("[%-5s] %s%s" % (lvl, text, times))
    for stage in ("bootblock", "verstage", "romstage"):
        if any("Pre-CBMEM %s console overflowed" % stage in l for l in fw.log):
            details.append("la console prima di CBMEM e' traboccata: l'inizio della %s non c'e'%s" % (
                stage, " (i boot che fanno il training della RAM ne scrivono di piu')"
                if stage == "romstage" else ""))
    if any("console overflowed" in l for l in fw.log) and \
            not any(re.search(r"Pre-CBMEM \w+ console overflowed", l) for l in fw.log):
        details.append("la console prima di CBMEM e' traboccata: l'inizio del bootblock non c'e'")
    errors = sum(1 for (l, _) in seen if LOG_BAD[l] == "FAIL")
    summary = "%d messaggi diversi (%d errori), %d non noti" % (len(seen), errors, new) if seen else \
        "nessun errore ne' avviso"
    if events:
        summary += "; " + "; ".join(events)
    rep.add("BOOT-03", "Log di coreboot", status, summary, details,
            {"messages": [{"level": l, "text": t, "count": n} for (l, t), n in seen.items()]})


def kernel_messages():
    """I messaggi del kernel di questo avvio da warning in su: [(priorita', testo)]."""
    if shutil.which("journalctl"):
        r = run(["journalctl", "-k", "-b", "-p", "warning", "-o", "json", "--no-pager", "-q"])
        if r and r[0] == 0:
            out = []
            for line in r[1].splitlines():
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                msg = d.get("MESSAGE", "")
                if isinstance(msg, list):
                    msg = bytes(msg).decode("utf-8", "replace")
                out.append((int(d.get("PRIORITY", 4)), msg))
            return out, "journalctl"
    r = run(["dmesg", "-x", "--level=emerg,alert,crit,err,warn"])
    if r and r[0] == 0:
        prio = {"emerg": 0, "alert": 1, "crit": 2, "err": 3, "warn": 4}
        out = []
        for line in r[1].splitlines():
            m = re.match(r"\S+\s*:(\w+)\s*: (?:\[[^\]]*\] )?(.*)$", line)
            if m:
                out.append((prio.get(m.group(1), 4), m.group(2)))
        return out, "dmesg"
    return None, None


def check_kernel_log(fw, rep):
    """BOOT-04: avvisi ed errori del kernel che riguardano il firmware."""
    msgs, src = kernel_messages()
    if msgs is None:
        rep.add("BOOT-04", "Log del kernel", "SKIP", "ne' journalctl ne' dmesg leggibili")
        return
    seen = {}
    for prio, text in msgs:
        if KERNEL_FW.search(text):
            key = text.strip()
            p, n = seen.get(key, (prio, 0))
            seen[key] = (min(p, prio), n + 1)
    status, details, new = "PASS", [], 0
    for text, (prio, n) in seen.items():
        why = known(text, KNOWN_KERNEL, fw.board)
        lvl = "err" if prio <= 3 else "warn"
        times = " (x%d)" % n if n > 1 else ""
        if why:
            details.append("[%s] %s%s  -- noto: %s" % (lvl, text, times, why))
        else:
            new += 1
            status = worst(status, "FAIL" if prio <= 3 else "WARN")
            details.append("[%s] %s%s" % (lvl, text, times))
    summary = ("%d messaggi del firmware su %d avvisi (%s), %d non noti" % (len(seen), len(msgs), src, new)
               if seen else "nessun avviso sul firmware (%d avvisi in tutto, %s)" % (len(msgs), src))
    rep.add("BOOT-04", "Log del kernel", status, summary, details,
            {"messages": [{"priority": p, "text": t, "count": n} for t, (p, n) in seen.items()]})


def dmi_blocks(dtype):
    r = run(["dmidecode", "-t", str(dtype)])
    if not r or r[0] != 0:
        return None
    out = []
    for block in r[1].split("\n\n"):
        if "DMI type %d," % dtype not in block:
            continue
        fields = {}
        for line in block.splitlines():
            m = re.match(r"^\t([^\t:][^:]*): (.*)$", line)
            if m:
                fields[m.group(1).strip()] = m.group(2).strip()
        out.append(fields)
    return out


def size_mb(s):
    """MB di una dimensione di dmidecode: "8 GB", "8192 MB", "512 kB", o con i
    prefissi binari ("8 GiB", "512 KiB"), che non tutte le versioni usano."""
    m = re.match(r"(\d+)\s*([kKMGT])i?B\b", s or "")
    if not m:
        return 0
    return int(m.group(1)) * {"k": 1 / 1024, "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}[m.group(2)]


def check_memory(fw, rep):
    """MEM-02: i moduli secondo SMBIOS, la memoria che vede Linux, i DIMM del log."""
    devs = dmi_blocks(17)
    if devs is None:
        rep.add("MEM-02", "Memoria", "SKIP", "dmidecode non trovato o non riuscito")
        return
    status, details = "PASS", []
    total, populated = 0, 0
    for d in devs:
        mb = size_mb(d.get("Size"))
        if not mb:
            continue
        populated += 1
        total += mb
        # mai Serial Number e Asset Tag
        details.append("%s: %s %s %s, %s (configurata %s), %s %s, rank %s" % (
            d.get("Locator", "?"), d.get("Size"), d.get("Type", "?"), d.get("Form Factor", ""),
            d.get("Speed", "?"), d.get("Configured Memory Speed", "?"), d.get("Manufacturer", "?"),
            d.get("Part Number", "?"), d.get("Rank", "?")))
    memtotal = 0
    for line in open("/proc/meminfo"):
        if line.startswith("MemTotal:"):
            memtotal = int(line.split()[1]) / 1024
    summary = "%d moduli, %.0f GB; Linux vede %.1f GB" % (populated, total / 1024, memtotal / 1024)
    if not populated:
        status, summary = "WARN", "SMBIOS non elenca moduli (tipo 17)"
        if devs:
            # le voci ci sono, ma nessuna dimensione letta: quelle di dmidecode
            details.append("%d voci di tipo 17, Size: %s" % (
                len(devs), ", ".join(sorted({d.get("Size", "(nessuna)") for d in devs}))))
    elif memtotal < 0.9 * total:
        status = "WARN"
        summary += ": meno del 90% di quella installata"
    found = fw.grep(r"^(\d+) DIMMs found") if fw.log is not None else []
    if found:
        n = int(found[-1].group(1))
        details.append("log di coreboot: %d DIMM trovati" % n)
        if populated and n != populated:
            status = "WARN"
            summary += "; il log dice %d DIMM" % n
    rep.add("MEM-02", "Memoria", status, summary, details,
            {"modules": populated, "installed_mb": total, "memtotal_mb": round(memtotal)})


class MsrRO:
    """Gli MSR da /dev/cpu/N/msr, in sola lettura; il modulo msr non lo carica."""

    def __init__(self):
        self.fds = {}

    def read(self, cpu, reg):
        try:
            fd = self.fds.get(cpu)
            if fd is None:
                fd = self.fds[cpu] = os.open("/dev/cpu/%d/msr" % cpu, os.O_RDONLY)
            return struct.unpack("<Q", os.pread(fd, 8, reg))[0]
        except OSError:
            return None


def check_cpu(fw, rep, msr):
    """CPU-01: microcode (firmware e Linux), rapporti, limiti di potenza."""
    model, codes = "?", set()
    for line in open("/proc/cpuinfo"):
        if line.startswith("model name") and model == "?":
            model = line.split(":", 1)[1].strip()
        elif line.startswith("microcode"):
            codes.add(int(line.split(":", 1)[1], 16))
    status, details = "PASS", []
    fwmc = [m.group(1) for m in fw.grep(r"MCU rev: (0x[0-9a-fA-F]+)")] if fw.log is not None else []
    bsp = fw.grep(r"microcode: sig=(0x[0-9a-f]+) pf=\S+ revision=(0x[0-9a-f]+)") if fw.log is not None else []
    linux = ", ".join("0x%x" % c for c in sorted(codes)) or "?"
    fwrev = sorted({int(x, 16) for x in fwmc} | {int(m.group(2), 16) for m in bsp})
    logged = ""
    # Cannon Lake con PRMRR: la patch che carica il FIT dice in MSR 0x8B la
    # sua revisione meno uno, e ramstage salta solo quella ("Skip microcode
    # update", soc_skip_ucode_update in soc/intel/cannonlake/cpu.c): quella
    # del CBFS e' la revisione del log piu' uno (0xf5 nel log, 0xf6 caricata)
    if fwrev and fw.log is not None and fw.grep(r"^Skip microcode update$"):
        logged = " (il log dice %s: con PRMRR la patch del FIT riporta la revisione meno uno, noto)" % (
            ", ".join("0x%x" % c for c in fwrev))
        fwrev = [c + 1 for c in fwrev]
    details.append("microcode: Linux %s, coreboot %s%s" % (linux, ", ".join("0x%x" % c for c in fwrev) or "?",
                                                         logged))
    if len(codes) > 1:
        status = "WARN"
        details.append("core con microcode diversi")
    elif codes and fwrev and max(codes) > max(fwrev):
        details.append("Linux ha caricato un microcode piu' nuovo di quello del firmware")
    cpu0 = 0
    unit, pl = msr.read(cpu0, MSR_PKG_POWER_SKU_UNIT), msr.read(cpu0, MSR_PKG_POWER_LIMIT)
    summary = model
    if unit is not None and pl is not None:
        pu = 1.0 / (1 << (unit & 0xF))
        pl1, pl2 = (pl & 0x7FFF) * pu, ((pl >> 32) & 0x7FFF) * pu
        summary += ", PL1 %.0f W, PL2 %.0f W" % (pl1, pl2)
        details.append("MSR 0x610: PL1 %.1f W %s, PL2 %.1f W %s%s" % (
            pl1, "attivo" if pl & (1 << 15) else "spento", pl2, "attivo" if pl & (1 << 47) else "spento",
            ", bloccato" if pl >> 63 else ""))
        if not pl & (1 << 15) or pl1 == 0:
            status = "WARN"
            details.append("PL1 spento o a 0 W")
    else:
        status = "INFO"
        details.append("MSR non leggibili (sudo modprobe msr)")
    pi, tt, tr = (msr.read(cpu0, r) for r in (MSR_PLATFORM_INFO, MSR_TEMPERATURE_TARGET, MSR_TURBO_RATIO_LIMIT))
    tcc = {}
    if pi is not None:
        details.append("rapporto base %d (%d MHz), turbo a 1 core %s, TjMax %s" % (
            (pi >> 8) & 0xFF, ((pi >> 8) & 0xFF) * 100, "%d" % (tr & 0xFF) if tr else "?",
            "%d C" % ((tt >> 16) & 0xFF) if tt is not None else "?"))
        # solo informativo: l'offset che vale (sul W541 lo scrive l'opzione del setup, dalla v1.6.0)
        bits, mask = ("29:24", 0x3F) if fw.board == "m920x" else ("27:24", 0xF)
        tcc = {"tcc_programmable": bool(pi & PLATFORM_INFO_PROG_TCC),
               "tcc_offset": (tt >> 24) & mask if tt is not None else None}
        offset = "?" if tcc["tcc_offset"] is None else "%d" % tcc["tcc_offset"]
        details.append("offset TCC programmabile: %s (PLATFORM_INFO bit 30), offset attuale %s (MSR 0x1A2 bit %s)%s"
                       % ("si'" if tcc["tcc_programmable"] else "no", offset, bits,
                          "; sul W541 l'opzione e' Energy Saver > Thermal > TCC activation offset (dalla v1.6.0)"
                          if fw.board == "w541" else ""))
    ec = fw.grep(r"EC: platform (\S+ \S+ \S+) \(PL1 (\d+) W\)") if fw.log is not None else []
    if ec:
        details.append("EC: platform %s, classe della CPU %s W" % (ec[-1].group(1), ec[-1].group(2)))
    if fw.log is not None and fw.grep(r"^Turbo is unavailable"):
        details.append("coreboot: Turbo non disponibile su questa CPU")
    rep.add("CPU-01", "CPU", status, summary, details,
            dict({"microcode": sorted(codes), "firmware_microcode": fwrev}, **tcc))


def hwmon():
    """{nome: [(etichetta, file, valore)]} da /sys/class/hwmon."""
    out = {}
    for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = rd(h + "/name", "?")
        for f in sorted(glob.glob(h + "/temp*_input") + glob.glob(h + "/fan*_input")):
            v = rd(f)
            if v is None or not v.lstrip("-").isdigit():
                continue
            label = rd(f.replace("_input", "_label"), os.path.basename(f).replace("_input", ""))
            out.setdefault(name, []).append((label, os.path.basename(f), int(v)))
    return out


def package_temp(hw):
    for label, f, v in hw.get("coretemp", ()):
        if label.startswith("Package id"):
            return v / 1000
    return None


def panels_on():
    """I pannelli interni (eDP, LVDS) che il driver grafico tiene accesi, con il
    modo nativo se c'e' (la prima riga di modes, il modo preferito del
    pannello): "eDP-1 2880x1620"."""
    on = []
    for d in sorted(glob.glob("/sys/class/drm/card*-eDP-*") + glob.glob("/sys/class/drm/card*-LVDS-*")):
        if rd(os.path.join(d, "enabled"), "") == "enabled" and rd(os.path.join(d, "dpms"), "") == "On":
            mode = rd(os.path.join(d, "modes"), "").split("\n", 1)[0].strip()
            on.append(" ".join(filter(None, (os.path.basename(d).split("-", 1)[1], mode))))
    return on


def idle_verdict(deep, avg_busy, procs, panels, board=None):
    """Esito di IDLE-01: (stato, testo). Una misura fuori dalle condizioni del
    test (core occupati, un processo attivo, il pannello acceso sotto la
    soglia: docs/testing.md la da' a schermo spento) e' INFO. Il W541 con il
    pannello 3K (W541_3K) acceso resta in PC2: lo schermo legge tutta
    l'immagine a ogni refresh (docs/flashing.md, Power at idle), e la misura
    non dice altro."""
    loud = [(c, n) for c, n in procs or () if c >= IDLE_PROC_MAX]
    if avg_busy > IDLE_BUSY_MAX:
        why = "core occupati %.0f%%" % avg_busy
    elif loud:
        why = ", ".join("%s %.0f%% di un core" % (n[:20], c) for c, n in loud[:3])
    else:
        why = None
    if why:
        return "INFO", "macchina non a riposo (%s): PC6+ %.1f%%, ripetere a riposo" % (why, deep)
    status = "PASS" if deep >= IDLE_DEEP_LIMITS[0] else "WARN" if deep >= IDLE_DEEP_LIMITS[1] else "FAIL"
    if status != "PASS" and panels:
        if board == "w541" and any(p.endswith(" " + W541_3K) for p in panels):
            return "INFO", ("pannello 3K acceso (%s): il W541 resta in PC2 (noto), PC6+ %.1f%%; "
                            "la soglia vale a schermo spento" % (", ".join(panels), deep))
        return "INFO", "pannello acceso (%s): PC6+ %.1f%%, ripetere a schermo spento" % (", ".join(panels), deep)
    return status, None


def check_idle(fw, rep, msr, seconds):
    """IDLE-01: gli stati C del package e il consumo, misurati come idle-report.py."""
    cpus = idle.cpu_list()
    if msr.read(cpus[0], idle.MSR_TSC) is None:
        rep.add("IDLE-01", "Stati C del package", "SKIP",
                "MSR non leggibili: modulo msr non caricato (sudo modprobe msr) o non root")
        return None
    print("misura degli stati C per %.0f s, non usare la macchina..." % seconds, file=sys.stderr, flush=True)
    res = idle.sample(msr, cpus, seconds)
    pkg, rapl = res["pkg"], res["rapl"]
    busy = [r["busy"] for r in res["cores"] if r["busy"] is not None]
    avg_busy = sum(busy) / len(busy) if busy else 0.0
    deep = sum(v for k, v in pkg.items() if k in ("PC6", "PC7", "PC8", "PC9", "PC10"))
    details = ["package: " + "  ".join("%s %.1f%%" % (k, v) for k, v in pkg.items()),
               "potenza (RAPL): " + (", ".join("%s %.2f W" % (k, v) for k, v in rapl.items()) or "-"),
               "core occupati in media %.1f%%; cpuidle: %s" % (avg_busy, "  ".join(
                   "%s %.1f%%" % (n, s) for _, n, s, _, _ in res["idle"] if s >= 0.1))]
    if res["irq"]:
        details.append("interrupt/s: " + ", ".join("%s %.0f" % ((lab or k)[:24], r) for r, k, lab in res["irq"][:6]))
    if res.get("procs"):
        details.append("processi (% di un core): " + ", ".join("%s %.1f" % (n[:20], c)
                                                               for c, n in res["procs"][:6] if c >= 0.1))
    if not pkg:
        rep.add("IDLE-01", "Stati C del package", "SKIP", "contatori del package non leggibili", details)
        return res
    panels = panels_on()
    if panels:
        details.append("pannello acceso durante la misura: %s (a schermo spento: docs/testing.md, IDLE-01)"
                       % ", ".join(panels))
    status, summary = idle_verdict(deep, avg_busy, res.get("procs"), panels, fw.board)
    if summary is None:
        top = max(pkg.items(), key=lambda x: x[1])
        summary = "PC6 e oltre %.1f%% (soglie %.0f/%.0f%%), il piu' frequente %s %.1f%%" % (
            deep, IDLE_DEEP_LIMITS[0], IDLE_DEEP_LIMITS[1], top[0], top[1])
    if "package" in rapl:
        summary += ", package %.2f W" % rapl["package"]
    rep.add("IDLE-01", "Stati C del package", status, summary, details,
            {"seconds": round(res["seconds"], 1), "pkg": {k: round(v, 2) for k, v in pkg.items()},
             "rapl_w": {k: round(v, 3) for k, v in rapl.items()}, "deep_pct": round(deep, 2),
             "busy_pct": round(avg_busy, 2), "panels_on": panels})
    return res


def check_fan(fw, rep):
    """FAN-01: la ventola (hwmon, o il controllo del firmware all'avvio) e le temperature."""
    hw = hwmon()
    status, details = "PASS", []
    t = package_temp(hw)
    parts = []
    if t is not None:
        tst = "PASS" if t < TEMP_LIMITS[0] else "WARN" if t < TEMP_LIMITS[1] else "FAIL"
        status = worst(status, tst)
        parts.append("CPU %.0f C (soglie %.0f/%.0f C)" % ((t,) + TEMP_LIMITS))
    for name, vals in sorted(hw.items()):
        temps = ["%s %.0f C" % (l, v / 1000) for l, f, v in vals if f.startswith("temp")]
        if temps and name != "coretemp":
            details.append("%s: %s" % (name, ", ".join(temps[:6])))
    fans = [(n, l, v) for n, vals in hw.items() for l, f, v in vals if f.startswith("fan")]
    boot = fw.grep(r"EC: CPU fan at (\d+) rpm") if fw.log is not None else []
    dead = fw.grep(r"EC: the CPU fan does not turn") if fw.log is not None else []
    if fans:
        for n, l, v in fans:
            details.append("%s %s: %d rpm" % (n, l, v))
        rpm = max(v for _, _, v in fans)
        parts.append("ventola %d rpm" % rpm)
        if rpm == 0:
            status = worst(status, "FAIL" if fw.board == "m920x" or (t or 0) >= 70 else "INFO")
    elif boot:
        parts.append("ventola %s rpm all'avvio (log del firmware)" % boot[-1].group(1))
        details.append("ventola ora: nessun hwmon (M920x: sudo modprobe nct6683)")
    elif dead:
        parts.append("ventola ferma all'avvio")
    else:
        parts.append("ventola non letta")
        if fw.board == "m920x":
            details.append("M920x: sudo modprobe nct6683, poi di nuovo")
        elif fw.board == "w541":
            details.append("W541: la legge thinkpad_acpi (hwmon thinkpad, fan1_input): il modulo c'e'?")
    if dead:
        status = "FAIL"
        details.append("il firmware ha letto 0 rpm all'avvio: guasto della ventola (ec.c)")
    if t is None and not fans and not boot:
        status = "SKIP"
    rep.add("FAN-01", "Ventola e temperature", status, ", ".join(parts), details,
            {"cpu_temp_c": t, "fans": [{"chip": n, "label": l, "rpm": v} for n, l, v in fans]})


def pci_devices():
    """Lo stato PCIe di ogni funzione, senza svegliare chi dorme (come idle-report.py)."""
    devs = []
    for dev in sorted(glob.glob("/sys/bus/pci/devices/*")):
        devs.append({"dev": dev, "name": os.path.basename(dev),
                     "parent": os.path.basename(os.path.dirname(os.path.realpath(dev))),
                     "ids": "%s:%s" % (rd(dev + "/vendor", "0x????")[2:], rd(dev + "/device", "0x????")[2:]),
                     "drv": os.path.basename(os.path.realpath(dev + "/driver")) if os.path.exists(dev + "/driver")
                     else "-",
                     "dstate": rd(dev + "/power_state", "?"), "rt": rd(dev + "/power/runtime_status", "?")})
    state = {d["name"]: d for d in devs}
    for d in devs:
        up = state.get(d["parent"])
        d["asleep"] = d["dstate"] == "D3cold" or (up is not None and (up["dstate"] != "D0" or up["rt"] != "active"))
        cfg = b""
        if not d["asleep"]:
            try:
                with open(d["dev"] + "/config", "rb") as f:
                    cfg = f.read(256)
            except OSError:
                pass
        d["cfg"] = cfg
        d["pcie"] = idle.pcie_info(cfg)
        d["children"] = [x["name"] for x in devs if x["parent"] == d["name"]]
    return devs, state


def check_pcie(fw, rep):
    """PCI-01: ASPM e LTR dei link PCIe."""
    devs, state = pci_devices()
    pol = rd("/sys/module/pcie_aspm/parameters/policy", "?")
    m = re.search(r"\[(\w+)\]", pol)
    pol = m.group(1) if m else pol
    status, details, issues = "PASS", [], []
    for d in devs:
        p = d["pcie"]
        bdf = d["name"][5:]
        if d["asleep"]:
            details.append("%-8s %s %-12s spento o sotto un ponte sospeso: non letto" % (bdf, d["ids"], d["drv"][:12]))
            continue
        if not p or p["type"] in (9, 10):
            continue
        cap, ctl = (p["lnkcap"] >> 10) & 3, p["lnkctl"] & 3
        width = (p["lnksta"] >> 4) & 0x3F
        link = "%s x%d" % (idle.LINK_SPEED.get(p["lnksta"] & 0xF, "?"), width) if width else "giu'"
        details.append("%-8s %s %-12s %-3s ASPM %s/%s LTR %s/%s %s" % (
            bdf, d["ids"], d["drv"][:12], idle.PCIE_TYPES.get(p["type"], "?"), idle.ASPM_BITS[cap],
            idle.ASPM_BITS[ctl], "+" if p["ltr_cap"] else "-", "+" if p["ltr_en"] else "-", link))
        if p["ltr_cap"] and not p["ltr_en"]:
            if d["ids"] == "1217:8520" and fw.board == "w541":
                # patch 0272: il lettore SD del W541 senza LTR, che lo teneva in PC2
                details.append("         %s: LTR spento dal firmware (noto: patch 0272)" % bdf)
            else:
                issues.append("%s: LTR supportato ma spento" % bdf)
        up = state.get(d["parent"])
        if up and up["pcie"] and p["type"] in (0, 1, 5) and width:
            ucap, uctl = (up["pcie"]["lnkcap"] >> 10) & 3, up["pcie"]["lnkctl"] & 3
            if cap & 2 and ucap & 2 and not (ctl & 2 and uctl & 2):
                issues.append("%s-%s: ASPM L1 supportato dai due lati ma spento" % (d["parent"][5:], bdf))
    if issues:
        status = "INFO" if pol == "performance" else "WARN"
        details.extend("problema: " + i for i in issues)
    summary = "%d problemi (criterio ASPM del kernel: %s)" % (len(issues), pol) if issues else \
        "ASPM L1 e LTR accesi su ogni link che li supporta (criterio del kernel: %s)" % pol
    rep.add("PCI-01", "PCIe ASPM e LTR", status, summary, details, {"policy": pol, "issues": issues})
    return devs, state


def check_peg(fw, rep, state):
    """PCI-02 (M920x): la porta PEG 00:01.0 del riser, spenta senza scheda (patch 0169)."""
    if fw.board != "m920x":
        return
    port = state.get("0000:00:01.0")
    lines = [m.group(0) for m in fw.grep(r"^PEG: .*")] if fw.log is not None else []
    details = ["log: " + l for l in lines]
    if port is None:
        status = "PASS"
        summary = "porta PEG spenta%s" % (" (nessuna scheda sul riser)" if any("no card" in l for l in lines) else "")
    elif port["children"]:
        status = "PASS"
        child = state.get(port["children"][0])
        p = child["pcie"] if child else None
        link = ""
        if p:
            link = ", link %s x%d" % (idle.LINK_SPEED.get(p["lnksta"] & 0xF, "?"), (p["lnksta"] >> 4) & 0x3F)
        summary = "scheda sul riser: %s%s" % (", ".join(port["children"]), link)
    else:
        status = "WARN"
        summary = ("porta PEG accesa senza scheda: il package resta in PC3 (ci-145); *PCIe riser slot* su "
                   "Enabled, o una build senza la patch 0169")
    if not lines:
        details.append("nessuna riga PEG: nel log (Enabled nel setup, o una build prima della 0169)")
    rep.add("PCI-02", "Porta PEG del riser", status, summary, details)


# Le classi PCI (classe e sottoclasse) dei dispositivi che i driver del payload
# raggiungono con EFI_PCI_IO_PROTOCOL: una loro BAR fuori dall'apertura del
# root bridge e' un dispositivo che l'UEFI non usa (PCI-09). La rete no: iPXE
# ha i suoi driver
PCI_UEFI_CLASSES = {0x0c03: "USB", 0x0106: "SATA", 0x0108: "NVMe", 0x0101: "IDE", 0x0805: "lettore SD"}
# I flag di /sys/bus/pci/devices/*/resource (include/linux/ioport.h)
IORESOURCE_MEM, IORESOURCE_PREFETCH = 0x200, 0x2000


def payload_aperture(funcs, reserved):
    """PCI-09 dai dati: rifa' ScanForRootBridges() di PciHostBridgeLib del
    payload (UefiPayloadPkg, con patches/tianocore/0024) sul bus 0. funcs: le
    funzioni del bus 0 in ordine di dispositivo e funzione, ognuna {"bdf",
    "mem_on", "windows": [(base, limite, prefetch)], "bars": [(indice, base,
    limite)]}; reserved: gli intervalli (inizio, fine compresa) riservati
    nella mappa della memoria. Le finestre dei bridge allargano l'apertura
    senza controlli; una BAR di memoria solo se il tratto che aggiunge, fino
    all'apertura di prima, non tocca memoria riservata
    (PcatPciRootBridgeWarnAboutBrokenFW): dalla v1.6.0 (edk2/0052) l'ECAM lo
    e'. Su queste board non succede: coreboot mette ogni BAR a 32 bit sotto
    l'ECAM (DOMAIN_RESOURCE_32BIT_LIMIT); il controllo guarda che resti
    cosi'. Torna (mem, mem4g, fuori): le due aperture [base, limite] (base
    2**64 - 1 se vuota) e le BAR lasciate fuori, (bdf, indice, base, limite,
    l'intervallo riservato)."""
    ap = {"mem": [(1 << 64) - 1, 0], "mem4g": [(1 << 64) - 1, 0]}
    out = []

    def blocked(start, limit):
        for a, b in reserved:
            if max(start, a) < min(limit, b + 1):
                return a, b
        return None

    for f in funcs:
        for base, limit, pref in f.get("windows", ()):
            if 0 < base < limit:
                a = ap["mem4g" if pref and base >= 1 << 32 else "mem"]
                a[0], a[1] = min(a[0], base), max(a[1], limit)
        if not f.get("mem_on", True):
            continue
        for idx, base, limit in f.get("bars", ()):
            if not 0 < base < limit:
                continue
            a = ap["mem" if base < 1 << 32 else "mem4g"]
            # NewBase e NewLength del payload: il tratto fino all'apertura
            r = blocked(base if a[0] > base else a[0], base if a[1] < limit else a[0])
            if r:
                out.append((f["bdf"], idx, base, limit, r))
                continue
            a[0], a[1] = min(a[0], base), max(a[1], limit)
    return tuple(ap["mem"]), tuple(ap["mem4g"]), out


def bus0_functions(devs):
    """Le funzioni del bus 0 per payload_aperture(), da pci_devices(): le BAR
    da resource; le finestre dei bridge e il bit Memory Space del comando
    dalla configurazione letta (bastano i 64 byte che si leggono anche senza
    root), se non letta le finestre da resource e il bit acceso."""
    funcs = []
    for d in devs:
        if not re.fullmatch(r"0000:00:[0-9a-f]{2}\.[0-7]", d["name"]):
            continue
        cfg = d.get("cfg") or b""
        res = []
        for line in (rd(d["dev"] + "/resource", "") or "").splitlines():
            try:
                res.append(tuple(int(x, 16) for x in line.split()[:3]))
            except ValueError:
                res.append((0, 0, 0))
        hdr = cfg[0x0e] & 0x7f if len(cfg) >= 64 else (1 if len(res) > 14 and res[14][2] else 0)
        f = {"bdf": d["name"][5:], "ids": d["ids"], "drv": d["drv"],
             "cls": int(rd(d["dev"] + "/class", "0x000000"), 16) >> 8,
             "mem_on": bool(struct.unpack_from("<H", cfg, 4)[0] & 2) if len(cfg) >= 64 else True,
             "windows": [], "bars": []}
        nbars = 2 if hdr == 1 else 6 if hdr == 0 else 0
        for i in range(min(nbars, len(res))):
            start, end, flags = res[i]
            if flags & IORESOURCE_MEM and end > start:
                f["bars"].append((i, start, end))
        if hdr == 1 and len(cfg) >= 64:
            mb, ml, pb, pl = struct.unpack_from("<HHHH", cfg, 0x20)
            f["windows"].append(((mb & 0xfff0) << 16, ((ml & 0xfff0) << 16) | 0xfffff, False))
            pbase, plim = (pb & 0xfff0) << 16, ((pl & 0xfff0) << 16) | 0xfffff
            if pb & 0xf == 1:
                hi_b, hi_l = struct.unpack_from("<II", cfg, 0x28)
                pbase, plim = pbase | hi_b << 32, plim | hi_l << 32
            f["windows"].append((pbase, plim, True))
        elif hdr == 1:
            for i in (14, 15):
                if len(res) > i and res[i][2] & IORESOURCE_MEM and res[i][1] > res[i][0]:
                    f["windows"].append((res[i][0], res[i][1], bool(res[i][2] & IORESOURCE_PREFETCH)))
        funcs.append(f)
    return funcs


def read_memmap():
    """Le voci (inizio, fine compresa, tipo) di /sys/firmware/memmap."""
    out, d = [], "/sys/firmware/memmap"
    for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        start, end, typ = (rd(os.path.join(d, n, f)) for f in ("start", "end", "type"))
        if start and end and typ:
            out.append((int(start, 16), int(end, 16), typ))
    return out


def aperture_status(funcs, memmap, ecam=()):
    """PCI-09: (esito, sommario, dettagli, dati) da payload_aperture(). FAIL
    se resta fuori una BAR di un dispositivo che il payload usa (USB, dischi,
    lettore SD): prima del sistema operativo non funziona. Le altre sono INFO:
    nessun driver del payload le usa, e la grafica nemmeno (il GOP scrive nel
    framebuffer di coreboot da solo, iPXE fa le sue mappature); ecam, le
    finestre (inizio, fine) di MCFG, per i nomi."""
    reserved = [(a, b) for a, b, t in memmap if t == "Reserved"]
    mem, mem4g, out = payload_aperture(funcs, reserved)
    byname = {f["bdf"]: f for f in funcs}

    def what(r):
        return "%s 0x%x-0x%x" % ("ECAM" if any(r[0] <= lo and hi <= r[1] for lo, hi in ecam) else
                                 "riservata", r[0], r[1])

    def ap(a):
        return "vuota" if a[0] > a[1] else "0x%x-0x%x" % a
    nbars = sum(len(f["bars"]) for f in funcs if f.get("mem_on", True))
    details = ["apertura del root bridge sotto i 4 GiB %s, sopra %s (%d BAR di memoria sul bus 0)" % (
        ap(mem), ap(mem4g), nbars)]
    for a, b in reserved:
        if mem[0] <= mem[1] and max(a, mem[0]) <= min(b, mem[1]):
            details.append("l'apertura copre %s: PciHostBridgeDxe non la registra tutta nel GCD "
                           "(in una build DEBUG si ferma su un ASSERT)" % what((a, b)))
    status, hard = "PASS", []
    for bdf, idx, base, limit, r in out:
        f = byname[bdf]
        kind = PCI_UEFI_CLASSES.get(f["cls"])
        details.append("%s %s %-12s BAR%d 0x%x-0x%x fuori: tra la BAR e l'apertura c'e' %s%s" % (
            bdf, f["ids"], f["drv"][:12], idx, base, limit, what(r),
            "; %s, che il payload usa: prima del sistema operativo non funziona" % kind if kind else
            "; la grafica, che il GOP del payload usa dal framebuffer senza l'apertura" if f["cls"] >> 8 == 0x03
            else ""))
        if kind:
            hard.append("%s (%s)" % (bdf, kind))
    data = {"mem": list(mem), "mem_above_4g": list(mem4g),
            "excluded": [{"bdf": b, "bar": i, "base": x, "limit": y, "reserved": list(r)}
                         for b, i, x, y, r in out]}
    if hard:
        return "FAIL", "BAR fuori dall'apertura del payload: %s" % ", ".join(hard), details, data
    if out:
        return "INFO", "%d BAR fuori dall'apertura del payload, di dispositivi che i suoi driver non usano" % len(
            out), details, data
    return "PASS", "ogni BAR di memoria del bus 0 nell'apertura del root bridge del payload", details, data


def check_aperture(fw, rep, devs):
    """PCI-09: le BAR del bus 0 che l'apertura del root bridge del payload
    lascia fuori (aperture_status), con le finestre ECAM di MCFG per i nomi."""
    ecam = []
    try:
        with open("/sys/firmware/acpi/tables/MCFG", "rb") as f:
            mcfg = f.read()
        for off in range(44, len(mcfg) - 15, 16):
            base, _seg, start, end = struct.unpack_from("<QHBB", mcfg, off)
            ecam.append((base + (start << 20), base + ((end + 1) << 20) - 1))
    except OSError:
        pass
    status, summary, details, data = aperture_status(bus0_functions(devs), read_memmap(), ecam)
    rep.add("PCI-09", "Aperture PCI del payload", status, summary, details, data)


def me_value(text, names=None):
    text = text.strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    if names and text in names:
        return names[text]
    return text


def spi_probe(fw):
    """update.spi_protection() una volta sola per i controlli che la usano
    (FLASH-01, e ME-01 sul W541 per me_disable in SMMSTORE)."""
    if not hasattr(fw, "spi"):
        try:
            fw.spi = update.spi_protection()
        except (OSError, update.Error, struct.error, ValueError) as e:
            fw.spi = {"root": True, "regs": None, "error": "protezione non letta: %s" % e}
    return fw.spi


def check_me_w541(fw, rep):
    """ME-01 sul W541: lo stato del ME 9 dalle stringhe OEM di SMBIOS (copia di
    HFS1-6 presa dal firmware prima di nascondere l'HECI), se no dal log; e
    l'HECI 00:16.0 rispetto all'opzione me_disable (Security > Management
    Engine > Intel ME interface, default Disabled: nascosta)."""
    heci = os.path.exists(update.HECI_PCI)
    drv = os.path.basename(os.path.realpath(update.HECI_PCI + "/driver")) \
        if os.path.exists(update.HECI_PCI + "/driver") else "-"
    details = []
    try:
        summary, words = update.me_strings(update.oem_strings())
    except OSError as e:
        summary = words = None
        details.append("stringhe OEM di SMBIOS non lette: %s" % e)
    logged = fw.grep(r"^ME: HFSTS1-6: ((?:[0-9a-f]{8} ){5}[0-9a-f]{8})$") if fw.log is not None else []
    if words is None and logged:
        words = [int(w, 16) for w in logged[-1].group(1).split()]
        details.append("HFS1-6 dal log (riga 'ME: HFSTS1-6'), non da SMBIOS")
    p = spi_probe(fw) or {}
    opt = p.get("board_options", {}).get("me_disable")
    hide = opt if opt is not None else update.LPT_OPTIONS["me_disable"]
    # store letto senza la variabile (o vuoto, o rifiutato): coreboot ha usato
    # il default, che quindi si sa; solo uno store non letto lascia il dubbio
    known = opt is not None or bool(p.get("store_read"))
    details.append("opzione me_disable: %s" % (
        "%d (in SMMSTORE)" % opt if opt is not None else
        "%d, il default (DISABLE_ME_PCI): non impostata in SMMSTORE%s" % (
            hide, " (%s)" % p["options_note"] if p.get("options_note") else "") if known else
        "%d, il default (DISABLE_ME_PCI)? SMMSTORE non letta" % hide))
    details.append("HECI 00:16.0 nel sistema: %s" % (("si', driver %s" % drv) if heci else "no"))
    status = "PASS"
    if summary is None and words is None:
        # un firmware senza le stringhe: le righe di lynxpoint/me_status.c
        g = lambda rx: (fw.grep(rx) or [None])[-1] if fw.log is not None else None
        com, cws = g(r"^ME: Current Operation Mode\s*: (.+)$"), g(r"^ME: Current Working State\s*: (.+)$")
        phase = g(r"^ME: Progress Phase\s*: (.+)$")
        if com is None:
            hint = debug_hint(fw, "le righe 'ME:'") if fw.log is not None else None
            rep.add("ME-01", "Intel ME", "SKIP", "ne' le stringhe OEM del ME (dalla %s) ne' righe 'ME: Current "
                    "Operation Mode' nel log" % update.me_strings_since("mrc"), details + ([hint] if hint else []))
            return
        text = "operation mode %s, working state %s%s (dal log)" % (
            com.group(1), cws.group(1) if cws else "?", ", %s" % phase.group(1) if phase else "")
        status = "INFO"
    else:
        text = update.me9_text(summary, words)
        if summary is None:
            summary = update.me9_summary(words[0], words[1])
        status = "PASS" if summary in ME9_GOOD else "INFO" if summary in ME9_INFO else "WARN"
        if summary == "Not available":
            details.append("il firmware non ha letto 00:16.0 all'avvio: era nascosta (un riavvio a caldo con "
                           "HECI su Disabled?) o spenta")
    if hide and heci:
        status = worst(status, "WARN" if known else "INFO")
        text += "; HECI 00:16.0 visibile con me_disable %s" % (
            "acceso" if opt is not None else "al default, acceso" if known else
            "non letto (default acceso): Enabled nel setup?")
    elif not hide and not heci:
        status = worst(status, "INFO")
        text += "; HECI 00:16.0 non c'e' con me_disable spento"
    else:
        text += "; HECI %s" % ("nascosta, come chiede me_disable" if hide else "visibile, driver %s" % drv)
    for m in fw.grep(r"^ME: (FW Partition Table\s*: BAD|Bringup Loader Failure\s*: YES|"
                     r"Progress Phase State\s*: .*)$") if fw.log is not None else []:
        details.append("log: ME: " + m.group(1))
    rep.add("ME-01", "Intel ME", status, text, details,
            {"summary": summary, "hfsts": words, "me_disable": opt, "me_disable_known": known, "heci": heci})


def check_me(fw, rep):
    """ME-01: lo stato del ME (HFSTS1 nel log) rispetto all'opzione me_state
    (M920x) o me_disable (W541, check_me_w541())."""
    if fw.board == "w541":
        check_me_w541(fw, rep)
        return
    if fw.log is None:
        rep.add("ME-01", "Intel ME", "SKIP", "log di coreboot non letto")
        return
    g = lambda rx: (fw.grep(rx) or [None])[-1]
    cws, com, err = (g(r"^ME: Current Working State\s*: (.+)$"), g(r"^ME: Current Operation Mode\s*: (.+)$"),
                     g(r"^ME: Error Code\s*: (.+)$"))
    opt = g(r"^CMOS: me_state = (\d+)")
    # il bit HAP del descrittore (me_state 2, patch 0226): hap.c lo dice a
    # ogni avvio, o quando lo scrive
    hap = g(r"^HAP: (set|clear) in the flash descriptor|^HAP: (written)|^HAP: (not written|the flash descriptor could not)")
    hap_set = bool(hap) and (hap.group(1) == "set" or (hap.group(2) == "written" and
                                                         bool(fw.grep(r"^HAP: setting the bit"))))
    heci = os.path.exists(update.HECI_PCI)
    drv = os.path.basename(os.path.realpath(update.HECI_PCI + "/driver")) \
        if os.path.exists(update.HECI_PCI + "/driver") else "-"
    if com is None and opt and int(opt.group(1)) == 2:
        rep.add("ME-01", "Intel ME", "PASS" if hap_set and not heci else "WARN",
                "spento dal bit HAP" + (", HECI nascosto" if not heci else ", ma HECI 00:16.0 e' visibile")
                if hap_set else "chiesto il bit HAP, ma il descrittore non lo ha (righe 'HAP:' del log)",
                ["opzione me_state: 2 (Disabled, HAP bit); nessuna riga 'ME: Current Operation Mode' nel log"],
                {"me_state": 2, "hap": hap_set, "heci": heci})
        return
    if com is None:
        # dopo una ripresa da S3 la console di CBMEM ricomincia e le righe
        # 'ME:' dell'avvio non ci sono piu'; le stringhe OEM di SMBIOS, scritte
        # all'avvio, dicono ancora lo stato
        try:
            oem = update.me_status(fw.board)
        except (OSError, update.Error):
            oem = None
        if oem:
            disabled = oem.startswith("disattivata")
            want = int(opt.group(1)) if opt else None
            st = "INFO" if want is None else ("PASS" if (want != 0) == disabled else "WARN")
            rep.add("ME-01", "Intel ME", st, "%s (dalle stringhe OEM di SMBIOS: nel log niente righe 'ME:', "
                    "dopo una ripresa da S3 la console ricomincia)" % oem,
                    ["opzione me_state: %s" % (want if want is not None else "non nel log")],
                    {"oem": oem, "me_state": want})
            return
        hint = debug_hint(fw, "le righe 'ME:'")
        rep.add("ME-01", "Intel ME", "SKIP", "nessuna riga 'ME: Current Operation Mode' nel log",
                [hint] if hint else [])
        return
    mode = me_value(com.group(1), ME_MODES)
    ws = me_value(cws.group(1), {"Normal": ME_HFS1_CWS_NORMAL}) if cws else None
    ec = me_value(err.group(1), {"No Error": 0}) if err else None
    want = int(opt.group(1)) if opt else None
    details = ["HFSTS1: working state %s, operation mode %s, error code %s" % (ws, mode, ec),
               "opzione me_state: %s" % ({0: "0 (Enabled)", 1: "1 (Disabled)", 2: "2 (Disabled, HAP bit)"}
                                        .get(want, want) if opt else "non nel log"),
               "HECI 00:16.0 nel sistema: %s" % (("si', driver %s" % drv) if heci else "no")]
    for m in fw.grep(r"^ME: (Version: .*|Manufacturing Mode\s*: YES|FW Partition Table\s*: BAD|"
                     r"Bringup Loader Failure\s*: YES)$"):
        details.append("log: ME: " + m.group(1))
    if not isinstance(mode, int):
        rep.add("ME-01", "Intel ME", "INFO", "operation mode %s, working state %s" % (mode, ws), details)
        return
    status = "PASS"
    if want == 2:
        details.append("bit HAP nel descrittore: %s" % ("impostato" if hap_set else "no"))
        if not hap_set:
            status, summary = "WARN", "chiesto il bit HAP, ma il descrittore non lo ha (righe 'HAP:' del log)"
        elif mode in (ME_HFS1_COM_NORMAL, ME_HFS1_COM_SOFT_TEMP_DISABLE) and \
                (ws == ME_HFS1_CWS_NORMAL or mode == ME_HFS1_COM_SOFT_TEMP_DISABLE):
            status, summary = "INFO", ("bit HAP impostato, il ME e' ancora %s: si ferma alla prossima accensione "
                                       "da spento (spina staccata 10 s)" % ("acceso" if mode == ME_HFS1_COM_NORMAL
                                                                          else "in soft disable"))
        elif heci:
            status, summary = "WARN", "spento dal bit HAP, ma HECI 00:16.0 e' visibile"
        else:
            summary = "spento dal bit HAP (working state %s, operation mode %s), HECI nascosto" % (ws, mode)
    elif want == 1 or (want is None and mode == ME_HFS1_COM_SOFT_TEMP_DISABLE):
        summary = "spento (soft temporary disable)"
        if mode != ME_HFS1_COM_SOFT_TEMP_DISABLE:
            status, summary = "WARN", "chiesto spento (me_state 1) ma operation mode %s" % mode
        elif heci:
            status, summary = "WARN", "spento, ma HECI 00:16.0 e' ancora visibile al sistema"
        else:
            summary += " come chiesto, HECI nascosto"
    else:
        summary = "acceso"
        if mode != ME_HFS1_COM_NORMAL or ws != ME_HFS1_CWS_NORMAL:
            status, summary = "WARN", "chiesto acceso ma operation mode %s, working state %s" % (mode, ws)
        elif ec:
            status, summary = "WARN", "acceso con error code %s" % ec
        elif not heci:
            status, summary = "WARN", "acceso ma HECI 00:16.0 non c'e'"
        else:
            summary += ", normale, HECI con %s" % drv
    rep.add("ME-01", "Intel ME", status, summary, details,
            {"operation_mode": mode, "working_state": ws, "error_code": ec, "me_state": want, "heci": heci,
             "hap": hap_set})


def separator_pcr(alg):
    """Il PCR esteso solo con l'EV_SEPARATOR (4 byte a zero): nessuna misura prima."""
    h = getattr(hashlib, alg)
    return h(bytes(h().digest_size) + h(bytes(4)).digest()).hexdigest().upper()


def check_tpm(fw, rep):
    """TPM-01: il TPM, la sua tabella ACPI, il registro delle misure."""
    base = "/sys/class/tpm/tpm0"
    if not os.path.isdir(base):
        rep.add("TPM-01", "TPM", "WARN" if fw.board else "SKIP", "nessun TPM per Linux (/sys/class/tpm/tpm0)")
        return
    major = rd(base + "/tpm_version_major") or ("1" if os.path.exists(base + "/device/pcrs") else "?")
    status, details = "PASS", []
    want = BOARDS.get(fw.board, {}).get("tpm")
    tables = set(os.listdir("/sys/firmware/acpi/tables")) if os.path.isdir("/sys/firmware/acpi/tables") else set()
    if want:
        if major != str(want[0]):
            status = "WARN"
            details.append("TPM %s, atteso %d.x su %s" % (major, want[0], BOARDS[fw.board]["name"]))
        if want[1] not in tables:
            status = "WARN"
            details.append("manca la tabella ACPI %s" % want[1])
    log = "/sys/kernel/security/tpm0/binary_bios_measurements"
    try:
        n = len(open(log, "rb").read())
        details.append("registro delle misure del firmware: %d byte" % n)
        if not n:
            status = "WARN"
    except OSError:
        details.append("registro delle misure non leggibile (securityfs non montato?)")
    if major == "1":
        # TPM 1.2 (W541): coreboot lo accende e lo attiva (tspi.c); owned dice
        # se il sistema ne ha preso possesso
        flags = [(n, rd("%s/%s" % (base, n)) or rd("%s/device/%s" % (base, n)))
                 for n in ("enabled", "active", "owned")]
        if any(v is not None for _, v in flags):
            details.append("TPM 1.2: " + ", ".join("%s %s" % (n, v if v is not None else "?") for n, v in flags))
        if any(v == "0" for n, v in flags if n in ("enabled", "active")):
            status = "WARN"
            details.append("TPM 1.2 spento o non attivo")
    summary = "TPM %s.x%s" % (major, ", tabella %s" % want[1] if want and want[1] in tables else "")
    rep.add("TPM-01", "TPM", status, summary, details, {"version": major})


TCG_ALGS = {0x0004: "sha1", 0x000B: "sha256", 0x000C: "sha384", 0x000D: "sha512"}
EV_NO_ACTION = 0x3


def tcg_events(data):
    """Gli eventi del registro del firmware come lo da' Linux
    (binary_bios_measurements): il formato crypto agile del TPM 2.0 se il
    primo evento e' Spec ID Event03, se no quello del TPM 1.2 (SHA-1).
    Torna [(pcr, tipo, {banco: digest}, dati)], fino al primo evento che
    non si legge."""
    events = []
    if len(data) < 32:
        return events
    size = struct.unpack_from("<I", data, 28)[0]
    spec = data[32:32 + size]
    if spec.startswith(b"Spec ID Event03"):
        n = struct.unpack_from("<I", spec, 24)[0]
        sizes = dict(struct.unpack_from("<HH", spec, 28 + 4 * i) for i in range(n))
        o = 32 + size
        while o + 12 <= len(data):
            pcr, typ, cnt = struct.unpack_from("<III", data, o)
            if cnt == 0 or cnt > len(sizes):
                break
            p, ds = o + 12, {}
            for _ in range(cnt):
                alg = struct.unpack_from("<H", data, p)[0]
                if alg not in sizes:
                    return events
                ds[TCG_ALGS.get(alg, hex(alg))] = data[p + 2:p + 2 + sizes[alg]]
                p += 2 + sizes[alg]
            if p + 4 > len(data):
                break
            es = struct.unpack_from("<I", data, p)[0]
            events.append((pcr, typ, ds, data[p + 4:p + 4 + es]))
            o = p + 4 + es
        return events
    o = 0
    while o + 32 <= len(data):
        pcr, typ = struct.unpack_from("<II", data, o)
        es = struct.unpack_from("<I", data, o + 28)[0]
        if pcr == 0xFFFFFFFF or (typ == 0 and es == 0) or o + 32 + es > len(data):
            break
        events.append((pcr, typ, {"sha1": data[o + 8:o + 28]}, data[o + 32:o + 32 + es]))
        o += 32 + es
    return events


def measured_boot(log, pcrs):
    """TPM-03 dal registro (byte) e dai PCR letti ({(banco, n): digest}):
    (stato, riassunto, dettagli, dati). Le misure di coreboot (FMAP:, CBFS:
    in PCR 2) e di vboot (VBOOT: in PCR 1) ci devono essere, e il registro
    rifatto evento per evento deve dare i PCR 0-7 di ogni banco letto."""
    events = tcg_events(log)
    names = [d.split(b"\0", 1)[0].decode("ascii", "replace") for _, _, _, d in events]
    cb = sum(1 for (pcr, _, _, _), n in zip(events, names) if pcr == 2 and n.startswith(("FMAP: ", "CBFS: ")))
    vb = sum(1 for (pcr, _, _, _), n in zip(events, names) if pcr == 1 and n.startswith("VBOOT: "))
    banks = sorted({b for b, _ in pcrs})
    differ = []
    for b in banks:
        h = getattr(hashlib, b)
        for i in range(8):
            if (b, i) not in pcrs:
                continue
            v = bytes(h().digest_size)
            for pcr, typ, ds, _ in events:
                if pcr == i and typ != EV_NO_ACTION:
                    if b not in ds:
                        v = None
                        break
                    v = h(v + ds[b]).digest()
            if v != pcrs[(b, i)]:
                differ.append("%s/%d" % (b, i))
    details = ["%d eventi nel registro; %d misure di coreboot in PCR 2, %d di vboot in PCR 1"
               % (len(events), cb, vb)]
    data = {"events": len(events), "coreboot": cb, "vboot": vb, "banks": banks, "differ": differ}
    if not events:
        return "WARN", "registro delle misure vuoto o illeggibile", details, data
    if differ:
        details.append("i PCR %s non sono quelli del registro rifatto: un evento esteso e non scritto "
                       "(registro pieno?) o scritto e non esteso" % ", ".join(differ))
        return "FAIL", "il registro non da' i PCR (%s)" % ", ".join(differ), details, data
    if not cb:
        details.append("coreboot non misura (CONFIG_TPM_MEASURED_BOOT spento, una release prima della v1.5.0)")
        return "WARN", "nessuna misura di coreboot; il registro da' i PCR 0-7 (%s)" % ", ".join(banks), details, data
    return ("PASS", "measured boot: %d misure di coreboot e %d di vboot, il registro da' i PCR 0-7 (%s)"
            % (cb, vb, ", ".join(banks)), details, data)


def check_measured_boot(fw, rep):
    """TPM-03: il registro delle misure rifatto contro i PCR del TPM."""
    base = "/sys/class/tpm/tpm0"
    try:
        log = open("/sys/kernel/security/tpm0/binary_bios_measurements", "rb").read()
    except OSError:
        rep.add("TPM-03", "Measured boot", "SKIP" if not os.path.isdir(base) else "WARN",
                "registro delle misure non leggibile (nessun TPM, securityfs non montato o senza root)")
        return
    pcrs = {}
    for b in ("sha1", "sha256", "sha384", "sha512"):
        for i in range(8):
            v = rd("%s/pcr-%s/%d" % (base, b, i))
            if v:
                pcrs[(b, i)] = bytes.fromhex(v)
    if not pcrs:
        # TPM 1.2: il file pcrs del dispositivo
        txt = rd(base + "/pcrs") or rd(base + "/device/pcrs") or ""
        for m in re.finditer(r"PCR-0([0-7]):\s*([0-9A-Fa-f ]+)", txt):
            pcrs[("sha1", int(m.group(1)))] = bytes.fromhex(m.group(2).replace(" ", ""))
    status, summary, details, data = measured_boot(log, pcrs)
    rep.add("TPM-03", "Measured boot", status, summary, details, data)


def flash_spi(p, details):
    """FLASH-01 con la sonda di tools/update.py (spi_protection), sul M920x e
    sul W541: (i PR che coprono tutta WP_RO o None, se sono bloccati, FLOCKDN
    o None, errore, lo stato di SI_ALL come spi_verdict() o None se il
    descrittore non la da' in scrittura alla CPU, i PR che la coprono)."""
    if not p["root"]:
        return None, None, None, "serve root", None, ""
    lpt = p.get("ctrl") == "lpt"
    bc = p.get("bios_cntl")
    if bc is not None:
        if lpt:
            details.append("Lynx Point 00:1f.0: BIOS_CNTL 0x%02x (BIOSWE %d, BLE %d, SMM_BWP %d)%s" % (
                bc, bc & 1, bc >> 1 & 1, bc >> 5 & 1, ", GCS 0x%08x (BILD %d)" % (p["gcs"], p["gcs"] & 1)
                if "gcs" in p else ""))
        else:
            details.append("fast SPI 00:1f.5: BIOS_CNTL 0x%02x (BIOSWE %d, BLE %d, EISS %d)" % (
                bc, bc & 1, bc >> 1 & 1, bc >> 5 & 1))
    if not p.get("regs") or "error" in p:
        if bc is not None:
            # BIOS_CNTL viene dallo spazio PCI, anche senza /dev/mem
            smm, by_smi = update.bios_lock_state(p)
            details.append("BIOS Lock: %s" % update.bios_lock_text(p, {"smm_only": smm, "smm_by_smi": by_smi}))
        return None, None, None, p.get("error") or "registri non letti", None, ""
    v = update.spi_verdict(p)
    details[-1] += ", FLOCKDN %s" % ("si'" if v["flockdn"] else "no")
    for r in v["prs"]:
        details.append("%s 0x%07x-0x%07x%s%s" % (r["name"], r["lo"], r["hi"], " scrittura protetta" if r["wpe"]
                                                 else "", (" (" + ", ".join(r["areas"][:4]) + ")") if r["areas"]
                                                 else ""))
    for label, fn in (("WP_RO", update.ro_text), ("SI_ALL", update.si_text), ("BIOS Lock", update.bios_lock_text),
                      ("slot RW", update.slots_text)):
        details.append("%s: %s" % (label, fn(p, v)))
    full = v["ro"] in ("ok", "unlocked")
    si = v["si"] if v["desc_host"] else None
    return ", ".join(v["ro_by"]) if full else None, v["ro"] == "ok", v["flockdn"], None, si, \
        ", ".join(v.get("si_by", []))


def logged_fpr(fw):
    """I Protected Range che coreboot dice di aver scritto in questo avvio,
    e WP_RO e SI_ALL della FMAP di CBMEM: ([(n, inizio, fine)], WP_RO o
    None, SI_ALL o None)."""
    prs = [(int(m.group(1)), int(m.group(2), 16), int(m.group(3), 16)) for m in fw.grep(FPR_LOG)] \
        if fw.log is not None else []
    fmap = fw.raw(CBMEM_ID_FMAP)
    areas = update.fmap_areas(fmap) if fmap else None
    return prs, (areas or {}).get("WP_RO"), (areas or {}).get("SI_ALL")


# OC_WDT_CTL, PMBASE + 0x54: Cannon Point (ACPI_BASE_ADDRESS 0x1800) e Lynx
# Point-H (DEFAULT_PMBASE 0x500)
OC_WDT_CTL_PORTS = {"m920x": 0x1854, "w541": 0x554}


def check_watchdog(fw, rep):
    """WDT-01: il firmware watchdog (dalla v1.6.1: M920x patch 0239, W541
    patch 0254): armato in romstage se l'opzione firmware_watchdog lo
    chiede, fermato in SMM quando il payload conferma lo slot; all'OS deve
    essere spento."""
    port = OC_WDT_CTL_PORTS.get(fw.board)
    if port is None:
        rep.add("WDT-01", "Firmware watchdog", "SKIP", "solo sul M920x e sul W541")
        return
    armed = fw.grep(r"^Firmware watchdog: armed, (\d+) s") if fw.log is not None else []
    off = fw.grep(r"^Firmware watchdog: off") if fw.log is not None else []
    last = fw.grep(r"^Firmware watchdog: the last reset came from the watchdog") if fw.log is not None else []
    # dalla patch 0268: tre reset del watchdog di fila senza un avvio
    # confermato, romstage non lo arma (e scrive anche la riga "off")
    capped = fw.grep(r"^Firmware watchdog: (\d+) resets in a row and no boot confirmed, not armed") \
        if fw.log is not None else []
    # la riga di romstage puo' mancare (un avvio con il training riempie la
    # console prima di CBMEM): quella del ramstage dice che il codice c'e'
    payload = fw.grep(r"^Firmware watchdog: at the payload") if fw.log is not None else []
    details = []
    try:
        with open("/dev/port", "rb") as f:
            f.seek(port)
            ctl = int.from_bytes(f.read(4), "little")
    except OSError as e:
        ctl = None
        details.append("OC_WDT_CTL non letto (/dev/port): %s" % e)
    if ctl is not None:
        details.append("OC_WDT_CTL 0x%08x: enable %d, timeout %d s, stato di reset %d" % (
            ctl, (ctl >> 14) & 1, (ctl & 0x3ff) + 1, (ctl >> 24) & 3))
    if last:
        details.append("log: l'ultimo reset l'ha fatto il watchdog")
    if not armed and not off and payload:
        running = ctl is not None and (ctl >> 14) & 1
        rep.add("WDT-01", "Firmware watchdog", "FAIL" if running else "PASS",
                "acceso all'OS: il payload non l'ha fermato" if running else
                "spento all'OS (la riga di romstage non e' nel log, quella del payload si')", details,
                {"ctl": ctl, "armed": None, "last_reset_wdt": bool(last)})
        return
    if not armed and not off:
        rep.add("WDT-01", "Firmware watchdog", "SKIP" if ctl is None else "INFO",
                "firmware senza il watchdog (nessuna riga 'Firmware watchdog:' nel log)"
                + ("" if ctl is None else ", OC_WDT_CTL 0x%08x" % ctl), details)
        return
    running = ctl is not None and (ctl >> 14) & 1
    if armed:
        t = int(armed[-1].group(1))
        status = "FAIL" if running else ("PASS" if ctl is not None else "INFO")
        summary = ("armato a %d s e ancora acceso all'OS: il payload non l'ha fermato, la macchina si "
                   "resettera'" % t) if running else "armato a %d s all'avvio, fermato alla conferma dello " \
            "slot%s" % (t, "" if ctl is not None else " (registro non letto)")
    else:
        status = "WARN" if running else "PASS"
        summary = "acceso all'OS con l'opzione spenta" if running else "spento (opzione firmware_watchdog Off)"
    if capped and not armed:
        status = "WARN" if status == "PASS" else status
        summary = "non armato: %s reset del watchdog di fila senza un avvio confermato" % capped[-1].group(1) \
            + (", ma acceso all'OS" if running else "")
    if last:
        status = "WARN" if status == "PASS" else status
        summary += "; l'ultimo reset l'ha fatto il watchdog"
    rep.add("WDT-01", "Firmware watchdog", status, summary, details,
            {"ctl": ctl, "armed": bool(armed), "last_reset_wdt": bool(last)})

def check_flash(fw, rep):
    """FLASH-01: Firmware protection (WP_RO e, dalla v1.6.1, SI_ALL in un
    Protected Range) e BIOS Lock."""
    status, details = "PASS", []
    lock = [m.group(0) for m in fw.grep(r"^BM-LOCKDOWN: (Enabled bootmedia protection.*|Boot media protection off.*|"
                                        r"Failed to enable.*|Could not find region.*)")] if fw.log is not None else []
    details.extend("log: " + l for l in lock)
    # SMMSTORE_OPTION_LOCK (dalla v1.6.1): il payload lo arma a ReadyToBoot; la
    # printk SMM arriva nella CBMEM console solo con DEBUG_SMI (le release no)
    if fw.log is not None and fw.grep(r"^Option lock: armed"):
        details.append("option lock: bios_lock e bootmedia_lock di sola lettura per l'OS (armato a ReadyToBoot)")
    # dalla v1.6.1 il payload lascia la risposta di SMM all'armamento nella
    # variabile volatile OptionLockStatus (edk2/0057): l'EFI_STATUS in 8 byte
    olk = option_lock_status()
    if olk is not None:
        details.append("option lock: %s (OptionLockStatus del payload)" % olk)
    covered, locked, flockdn, err, from_log, si, si_by = None, None, None, None, None, None, ""
    p = spi_probe(fw)
    if p is not None:
        covered, locked, flockdn, err, si, si_by = flash_spi(p, details)
    else:
        err = "nessun controller conosciuto (00:1f.5 Cannon Point, 00:1f.0 Lynx Point)"
    if err:
        details.append("registri SPI non letti: %s" % err)
        # senza i registri, il PR che coreboot ha scritto: dice cosa e' successo
        # all'avvio, non FLOCKDN ne' un PR cambiato dopo
        prs, wp, si_area = logged_fpr(fw)
        si_log = None
        for n, lo, hi in prs:
            details.append("log: PR%d 0x%07x-0x%07x" % (n, lo, hi))
            if wp and lo <= wp[0] and hi >= wp[0] + wp[1] - 1:
                from_log = "PR%d" % n
            if si_area and lo <= si_area[0] and hi >= si_area[0] + si_area[1] - 1:
                si_log = "PR%d" % n
        if prs and not wp:
            details.append("WP_RO non confrontata: FMAP di CBMEM non letta (cbmem -r %x)" % CBMEM_ID_FMAP)
        if from_log and si_area:
            details.append("SI_ALL (descrittore, GbE, ME) %s" % (
                "in %s secondo il log" % si_log if si_log else
                "senza PR nel log: firmware senza la protezione di SI_ALL (dalla v1.6.1)"))
    if flockdn is False:
        status = "WARN"
        details.append("FLOCKDN spento: i Protected Range si possono ancora cambiare")
    off = any("protection off" in l for l in lock)
    failed = any("Failed" in l or "Could not" in l for l in lock)
    if failed:
        status, summary = "FAIL", "la protezione del firmware non si e' accesa (log)"
    elif off:
        status = "WARN"
        summary = ("Firmware protection spenta (Security > Flash protection): riaccenderla dopo flashrom; "
                   "WP_RO scrivibile")
    elif covered is not None and not locked:
        # FLOCKDN spento (e sul M920x nessun PRx_LOCKDN): il PR c'e' ma si toglie
        status = "WARN"
        summary = "WP_RO in %s, ma il PR non e' bloccato (FLOCKDN spento): si puo' togliere" % covered
    elif covered is not None:
        summary = "WP_RO protetto (%s)%s%s" % (
            covered, " e SI_ALL (%s)" % si_by if si in ("ok", "unlocked") else "",
            ", registri bloccati" if flockdn else "")
        if si in ("partial", "off"):
            # il descrittore da' SI_ALL alla CPU e i PR non la coprono: un
            # firmware senza la patch 0235, o il suo lock fallito (gia' FAIL)
            status = "WARN"
            summary += "; SI_ALL (descrittore, GbE, ME) scrivibile dalla CPU: firmware senza la protezione " \
                "di SI_ALL (dalla v1.6.1)"
    elif from_log is not None:
        status = "INFO"
        summary = "WP_RO protetto all'avvio secondo il log (%s dal log; registri non letti, FLOCKDN non noto)" % \
            from_log
    elif lock:
        status = "WARN" if flockdn is not None else "INFO"
        summary = "il log dice protezione accesa, ma WP_RO non e' in un Protected Range" \
            if flockdn is not None else "protezione accesa secondo il log (registri non letti)"
    else:
        status, summary = "INFO", "nessuna riga BM-LOCKDOWN nel log"
    # il payload riporta che il blocco delle opzioni non si e' armato mentre
    # le protezioni sono accese: l'OS potrebbe spegnerle per il prossimo avvio
    if olk is not None and not olk.startswith("armato") and status == "PASS" and covered is not None:
        status = "WARN"
        summary += "; blocco delle opzioni non armato (OptionLockStatus): %s" % olk
    rep.add("FLASH-01", "Protezione del flash", status, summary, details,
            {"wp_ro_protected": covered is not None and bool(locked), "wp_ro_from_log": from_log,
             "option_off": off, "si_all_protected": si == "ok"})


EC_CVE = "CVE-2019-6171"


def ec_version(fw):
    """[(fonte, build ID)] della versione dell'EC H8: la riga di h8.c nel log
    ("H8: EC Firmware ID GMHT30WW-1.x, Version ...") e la stringa OEM di SMBIOS
    ("IBM ThinkPad Embedded Controller -[GMHT30WW-1.x]-")."""
    out = []
    for m in fw.grep(r"^H8: EC Firmware ID (\S+), Version (\S+)$") if fw.log is not None else []:
        out.append(("log, Version %s" % m.group(2), m.group(1)))
    try:
        for s in update.oem_strings() or []:
            m = EC_STRING_RE.match(s)
            if m:
                out.append(("SMBIOS tipo 11", m.group(1)))
    except OSError:
        pass
    return out


def check_ec(fw, rep):
    """EC-01: la versione del firmware dell'EC (H8, ThinkPad): sul W541 almeno
    la 1.15 (GMHT30WW), che corregge CVE-2019-6171. ouroBIOS non aggiorna l'EC."""
    found = ec_version(fw)
    if not found:
        if fw.board == "w541":
            rep.add("EC-01", "Firmware dell'EC", "SKIP",
                    "versione dell'EC non trovata (ne' 'H8: EC Firmware ID' nel log ne' la stringa OEM)")
        return
    details = ["%s: %s" % (src, ident) for src, ident in found]
    builds = {}
    for _, ident in found:
        m = EC_BUILD_RE.match(ident)
        if m:
            builds[m.group(1)] = min(builds.get(m.group(1), 99), int(m.group(2)))
    ident = found[0][1].split("-")[0]
    known = [(fam, n) for fam, n in builds.items() if fam in EC_MIN]
    if not known:
        rep.add("EC-01", "Firmware dell'EC", "INFO", "EC %s: versione minima non nota per questa famiglia" % ident,
                details)
        return
    fam, n = known[0]
    need, ecp = EC_MIN[fam]
    if n < need:
        rep.add("EC-01", "Firmware dell'EC", "WARN",
                "EC %s%02dWW piu' vecchio della %s (%s%02dWW), senza la correzione di %s" % (
                    fam, n, ecp, fam, need, EC_CVE),
                details + ["ouroBIOS non aggiorna l'EC: lo fa solo il firmware Lenovo 2.42 (GNUJ39US), cioe' "
                           "rimettere tutto il firmware originale con un programmatore esterno, aggiornare, poi "
                           "di nuovo ouroBIOS (docs/flashing.md)"],
                {"ec": "%s%02dWW" % (fam, n), "min": "%s%02dWW" % (fam, need)})
        return
    rep.add("EC-01", "Firmware dell'EC", "PASS", "EC %s%02dWW, dalla %s (%s%02dWW) in su: con la correzione di %s"
            % (fam, n, ecp, fam, need, EC_CVE), details,
            {"ec": "%s%02dWW" % (fam, n), "min": "%s%02dWW" % (fam, need)})


def check_smbios(fw, rep):
    """ID-01: l'identita' in SMBIOS (VPD); numeri di serie e UUID solo con le ultime 4 cifre."""
    if not shutil.which("dmidecode"):
        rep.add("ID-01", "SMBIOS e VPD", "SKIP", "dmidecode non trovato")
        return
    keys = ("system-manufacturer", "system-product-name", "system-version", "baseboard-product-name",
            "bios-vendor", "bios-version", "bios-release-date", "system-serial-number", "system-uuid",
            "baseboard-serial-number")
    val = {}
    for k in keys:
        r = run(["dmidecode", "-s", k])
        val[k] = r[1].strip() if r and r[0] == 0 else ""
    empty = lambda s: s in ("", "Not Specified", "Not Settable", "Not Present", "123456789", "Default string",
                            "None") or set(s.replace("-", "")) <= {"0"}
    secret = ("system-serial-number", "system-uuid", "baseboard-serial-number")
    details = ["%s: %s" % (k, ("(vuoto)" if empty(val[k]) else redact(val[k])) if k in secret else val[k] or "?")
               for k in keys]
    status, notes = "PASS", []
    if val["bios-version"] != fw.bios:
        status = "WARN"
        notes.append("bios-version diverso da /sys/class/dmi/id/bios_version")
    if empty(val["system-serial-number"]):
        status = worst(status, "WARN" if fw.board else "INFO")
        notes.append("numero di serie vuoto: la VPD non e' scritta (tools/vpd.py, docs/flashing.md)")
    if empty(val["system-uuid"]):
        status = worst(status, "WARN" if fw.board else "INFO")
        notes.append("UUID vuoto")
    summary = "%s %s, S/N %s" % (val["system-manufacturer"], val["system-product-name"],
                                 "(vuoto)" if empty(val["system-serial-number"]) else redact(val["system-serial-number"]))
    if notes:
        summary += "; " + "; ".join(notes)
    rep.add("ID-01", "SMBIOS e VPD", status, summary, details,
            {k: (redact(v) if k in secret and not empty(v) else v) for k, v in val.items()})


def check_acpi(fw, rep):
    """ID-02: le tabelle ACPI MSDM, TPM2/TCPA, DMAR e HPET (la chiave non si stampa mai)."""
    d = "/sys/firmware/acpi/tables"
    if not os.path.isdir(d):
        rep.add("ID-02", "Tabelle ACPI", "SKIP", "nessuna %s" % d)
        return
    files = {n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))}
    # le tabelle ripetute sono SSDT, SSDT1, SSDT2...: una volta sola
    names = sorted({re.sub(r"\d+$", "", n) if re.sub(r"\d+$", "", n) in files else n for n in files})
    status, details, missing = "PASS", ["tabelle: " + " ".join(names)], []
    want = ["DMAR", "HPET"]
    tpm = BOARDS.get(fw.board, {}).get("tpm")
    if tpm:
        want.append(tpm[1])
    for t in want:
        if t not in names:
            missing.append(t)
    if missing:
        status = "WARN"
        details.append("mancano: %s (DMAR: VT-d spento nel setup?)" % " ".join(missing))
    msdm = "assente (nessuna chiave Windows nella VPD: facoltativa)"
    if "MSDM" in names:
        try:
            with open(os.path.join(d, "MSDM"), "rb") as f:
                raw = f.read()
            # header ACPI (36), versione, riservato, tipo, riservato, lunghezza, chiave (29)
            ok = len(raw) >= 85 and re.fullmatch(rb"[0-9A-Z]{5}(-[0-9A-Z]{5}){4}", raw[56:85]) is not None
            del raw
            msdm = "presente, chiave nel formato giusto (non stampata)" if ok else "presente, chiave NON valida"
            if not ok:
                status = "WARN"
        except OSError as e:
            msdm = "presente, non letta: %s" % e
    details.append("MSDM: " + msdm)
    summary = ("DMAR, HPET%s presenti" % (", " + tpm[1] if tpm else "") if not missing
               else "mancano %s" % " ".join(missing)) + "; MSDM " + msdm.split(",")[0].split(" (")[0]
    rep.add("ID-02", "Tabelle ACPI", status, summary, details, {"tables": names, "missing": missing})


def check_wsmt(fw, rep):
    """CONF-01: la tabella WSMT (Windows SMM Security Mitigations Table) e i suoi
    flag: dalla release con le patch 0211-0215 tutti e tre (7); prima non c'e'."""
    p = "/sys/firmware/acpi/tables/WSMT"
    if not os.path.exists(p):
        rep.add("CONF-01", "WSMT", "INFO", "nessuna tabella WSMT (le release fino alla v1.5.x non la pubblicano)")
        return
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except OSError as e:
        rep.add("CONF-01", "WSMT", "WARN", "WSMT non letta: %s" % e)
        return
    if len(raw) < 40:
        rep.add("CONF-01", "WSMT", "FAIL", "WSMT di %d byte, ne servono 40" % len(raw))
        return
    flags = struct.unpack_from("<I", raw, 36)[0]
    names = [n for b, n in ((1, "FIXED_COMM_BUFFERS"), (2, "COMM_BUFFER_NESTED_PTR_PROTECTION"),
                            (4, "SYSTEM_RESOURCE_PROTECTION")) if flags & b]
    status = "PASS" if flags == 7 else "WARN"
    rep.add("CONF-01", "WSMT", status, "WSMT revisione %d, flag 0x%x%s" % (
        raw[8], flags, "" if flags == 7 else ": non tutti e tre"),
        ["flag: " + (" ".join(names) or "nessuno")], {"revision": raw[8], "flags": flags})


def ecam_status(mcfg, memmap, iomem):
    """CONF-07 dai dati: mcfg i byte della tabella MCFG, memmap le voci
    (inizio, fine compresa, tipo) di /sys/firmware/memmap, iomem il testo di
    /proc/iomem (None se senza indirizzi: non root). Ogni finestra ECAM deve
    essere memoria riservata nella mappa della memoria, che "fwts mcfg"
    controlla (MCFGMMIONotReserved, HIGH; edk2/0052), e una risorsa della
    scheda madre (PNP0C02, PCI Firmware 3.3, 4.1.2; patch 0218 e 0219), che
    Linux mette in /proc/iomem come "pnp". Torna (esito, sommario, dettagli,
    dati)."""
    if len(mcfg) < 44 + 16:
        return "FAIL", "tabella MCFG di %d byte, senza voci" % len(mcfg), [], {}
    windows = []
    for off in range(44, len(mcfg) - 15, 16):
        base, seg, start, end = struct.unpack_from("<QHBB", mcfg, off)
        windows.append((seg, base + (start << 20), base + ((end + 1) << 20) - 1, start, end))

    def covered(lo, hi, ranges):
        # quanta parte di [lo, hi] coprono gli intervalli (inizio, fine compresa)
        n, at = 0, lo
        for a, b in sorted(ranges):
            if b < at or a > hi:
                continue
            if a > at:
                break
            n += min(b, hi) - at + 1
            at = min(b, hi) + 1
            if at > hi:
                break
        return n

    reserved = [(a, b) for a, b, t in memmap if t == "Reserved"]
    pnp = None
    if iomem is not None:
        pnp = []
        for line in iomem.splitlines():
            # "pnp 00:0a" fino a Linux 6.x; dal 7.0 il nome ACPI, "PNP0C02:00"
            m = re.match(r"\s*([0-9a-f]+)-([0-9a-f]+) : (?:pnp |PNP0C02:)", line)
            if m:
                pnp.append((int(m.group(1), 16), int(m.group(2), 16)))
    details, missing, data = [], set(), {"windows": []}
    for seg, lo, hi, start, end in windows:
        size = hi - lo + 1
        in_map = covered(lo, hi, reserved)
        in_pnp = covered(lo, hi, pnp) if pnp is not None else None
        if in_map != size:
            missing.add("map")
        if in_pnp is not None and in_pnp != size:
            missing.add("pnp")
        details.append("segmento %d, bus %02x-%02x: 0x%x-0x%x, %d MiB; riservati nella mappa della memoria "
                       "%d MiB; tra le risorse della scheda madre (pnp) %s" % (
                           seg, start, end, lo, hi, size >> 20, in_map >> 20,
                           "non visto (senza root)" if in_pnp is None else "%d MiB" % (in_pnp >> 20)))
        data["windows"].append({"segment": seg, "start": lo, "end": hi, "reserved": in_map, "pnp": in_pnp})
    if not missing:
        if pnp is None:
            return "WARN", "ECAM riservata nella mappa della memoria; le risorse della scheda madre non " \
                   "si vedono senza root", details, data
        return "PASS", "ECAM riservata nella mappa della memoria e tra le risorse della scheda madre", \
            details, data
    what = []
    if "map" in missing:
        what.append("non riservata nella mappa della memoria (fwts mcfg: MCFGMMIONotReserved)")
    if "pnp" in missing:
        what.append("non tra le risorse della scheda madre (PNP0C02)")
    return "WARN", "ECAM " + " e ".join(what) + " (fino alla v1.5.x e' cosi')", details, data


# La tabella HSTI del payload (edk2/0063, PlatformHstiDxe): la copia che il
# driver lascia nella variabile volatile HstiTable del GUID della tabella, con
# i bit nell'ordine di HSTI_FEATURE
HSTI_VAR = "/sys/firmware/efi/efivars/HstiTable-6be272c7-1320-4ccd-9017-d4612c012b25"
HSTI_FEATURES = ("configurazione del flash bloccata (FLOCKDN)", "regione BIOS protetta (BIOS_CNTL)",
                 "Protected Range bloccato", "descrittore non scrivibile dall'host",
                 "regione ME non scrivibile dall'host", "TSEG bloccato", "interfaccia di debug bloccata",
                 "microcode caricato", "Secure Boot", "TPM", "lock delle opzioni del setup", "lock MOR",
                 "protezione DMA prima dell'avvio")
# i limiti noti delle due board (README): descrittore e ME sbloccati con
# ifdtool, nessuna protezione DMA prima del sistema; Secure Boot e' una scelta
HSTI_KNOWN = {3: "regioni sbloccate (ifdtool)", 4: "regioni sbloccate (ifdtool)",
              8: "una scelta del proprietario", 12: "l'FSP-M non ha i dati dei PMR"}


def check_hsti(fw, rep):
    """CONF-08: la tabella HSTI che il payload pubblica all'avvio di un boot."""
    if not os.path.exists(HSTI_VAR):
        rep.add("CONF-08", "HSTI", "INFO", "nessuna tabella HSTI (le release prima della patch edk2/0063)")
        return
    try:
        with open(HSTI_VAR, "rb") as f:
            raw = f.read()[4:]
    except OSError as e:
        rep.add("CONF-08", "HSTI", "WARN", "HstiTable non letta: %s" % e)
        return
    head = 4 + 4 + 512 + 4
    if len(raw) < head:
        rep.add("CONF-08", "HSTI", "FAIL", "HstiTable di %d byte" % len(raw))
        return
    size = struct.unpack_from("<I", raw, head - 4)[0]
    if len(raw) < head + 3 * size:
        rep.add("CONF-08", "HSTI", "FAIL", "HstiTable piu' corta dei suoi tre campi di bit")
        return
    req, impl, ver = (raw[head + i * size:head + (i + 1) * size] for i in range(3))
    bit = lambda a, n: n // 8 < len(a) and bool(a[n // 8] & (1 << (n % 8)))
    details, unknown, passed = [], 0, 0
    for n, name in enumerate(HSTI_FEATURES):
        if not bit(req, n):
            continue
        if bit(ver, n):
            passed += 1
            details.append("si': %s" % name)
        elif n in HSTI_KNOWN:
            details.append("no: %s  -- noto: %s" % (name, HSTI_KNOWN[n]))
        else:
            unknown += 1
            details.append("NO: %s%s" % (name, "" if bit(impl, n) else " (non verificabile)"))
    errors = raw[head + 3 * size:].decode("utf-16-le", "replace").split("\0")[0]
    details += ["errore: %s" % l.strip() for l in errors.splitlines() if l.strip()]
    status = "WARN" if unknown else "PASS"
    rep.add("CONF-08", "HSTI", status, "%d di %d test superati, %d mancati non noti" % (
        passed, sum(bit(req, n) for n in range(len(HSTI_FEATURES))), unknown), details)


def check_ecam(fw, rep):
    """CONF-07: la finestra ECAM della tabella MCFG riservata nella mappa della
    memoria e tra le risorse della scheda madre (ecam_status)."""
    p = "/sys/firmware/acpi/tables/MCFG"
    if not os.path.exists(p):
        rep.add("CONF-07", "ECAM", "INFO", "nessuna tabella MCFG")
        return
    try:
        with open(p, "rb") as f:
            mcfg = f.read()
    except OSError as e:
        rep.add("CONF-07", "ECAM", "WARN", "MCFG non letta: %s" % e)
        return
    memmap = read_memmap()
    iomem = rd("/proc/iomem")
    if iomem is not None and not re.search(r"^\s*0*[1-9a-f][0-9a-f]*-", iomem, re.M):
        iomem = None        # senza root gli indirizzi sono tutti 0
    status, summary, details, data = ecam_status(mcfg, memmap, iomem)
    rep.add("CONF-07", "ECAM", status, summary, details, data)


def check_s3(fw, rep):
    """S3-01: se il sistema offre S3 e come sono andate le sospensioni di questo avvio."""
    ms = rd("/sys/power/mem_sleep")
    if ms is None:
        rep.add("S3-01", "Sospensione", "SKIP", "/sys/power/mem_sleep non c'e'")
        return
    st = "/sys/power/suspend_stats/"
    ok, fail = int(rd(st + "success", "0") or 0), int(rd(st + "fail", "0") or 0)
    details = ["mem_sleep: %s" % ms, "sospensioni riuscite %d, fallite %d" % (ok, fail)]
    if "deep" not in ms:
        status, summary = "WARN", "S3 (deep) non offerto dal firmware: solo %s" % ms
    elif fail:
        status = "WARN"
        summary = "%d sospensioni fallite in questo avvio (ultimo: %s, %s)" % (
            fail, rd(st + "last_failed_dev", "?") or "?", rd(st + "last_failed_step", "?") or "?")
    else:
        status = "PASS" if ok else "INFO"
        summary = "S3 offerto%s; %s" % (" (default)" if "[deep]" in ms else "",
                                        "%d sospensioni riuscite" % ok if ok else
                                        "nessuna sospensione in questo avvio (prova: systemctl suspend)")
    rep.add("S3-01", "Sospensione", status, summary, details, {"mem_sleep": ms, "success": ok, "fail": fail})


# --- da una copia del flash -----------------------------------------------------

def read_elog(data):
    """Gli eventi di RW_ELOG, come li legge tools/elog.py."""
    try:
        base = elog.find_elog(data)
    except SystemExit:
        return None, 0
    p, end = base + data[base + 5], min(len(data), base + 0x4000)
    events = []
    while p + 9 <= end and data[p] != 0xFF:
        etype, length = data[p], data[p + 1]
        if length < 9 or p + length > end:
            break
        ev = data[p:p + length]
        y, mo, dd, h, mi, s = (elog.bcd(b) for b in ev[2:8])
        events.append({"type": etype, "name": elog.EVENTS.get(etype, "tipo 0x%02x" % etype),
                       "time": "20%02d-%02d-%02d %02d:%02d:%02d" % (y, mo, dd, h, mi, s),
                       "desc": elog.describe(etype, ev[8:-1]), "ok": sum(ev) & 0xFF == 0})
        p += length
    return events, p - base


def saved_options(region):
    """Le opzioni di coreboot salvate dal setup in SMMSTORE: {nome: valore} (solo interi da 4 byte)."""
    vars_, info = update.var_store(region)
    out = {}
    for v in vars_:
        if v["guid"] == CB_OPTION_GUID and v["state"] in (0x3F, 0x3E) and v["size"] == 4 and "data" in v:
            out[v["name"]] = struct.unpack_from("<I", region, v["data"])[0]
    return out, info



def same_build(bios, build):
    """La versione SMBIOS (il W541 la scrive con l'ID Lenovo davanti, 'CBET4000
    ouroBIOS-...') e' quella di una build trovata in uno slot."""
    return bios == build or bios.endswith(" " + build) or build.endswith(bios)

def check_dump(fw, rep, path):
    """ELOG-01, VB-02, OPT-01: registro degli eventi, RW_NVRAM e opzioni da una copia del flash."""
    if not path:
        rep.add("ELOG-01", "Registro degli eventi", "SKIP",
                "nessuna copia del flash (--dump, da sudo flashrom -p internal -r flash.bin)")
        return
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        rep.add("ELOG-01", "Registro degli eventi", "WARN", "%s: %s" % (path, e))
        return
    uptime = float((rd("/proc/uptime", "0") or "0").split()[0])
    stale = os.path.getmtime(path) < time.time() - uptime
    note = "; copia presa prima di questo avvio" if stale else ""
    events, used = read_elog(data)
    if events is None:
        rep.add("ELOG-01", "Registro degli eventi", "WARN", "RW_ELOG non trovata in %s" % path)
    else:
        boots = [i for i, e in enumerate(events) if e["type"] == 0x17]
        recent = events[boots[-5]:] if len(boots) >= 5 else events
        status, details = "PASS", []
        counts = {}
        for e in events:
            counts[e["name"]] = counts.get(e["name"], 0) + 1
        details.append("conteggi: " + ", ".join("%s %d" % (k, n) for k, n in sorted(counts.items(), key=lambda x: -x[1])))
        bad = [e for e in recent if e["type"] in (0xA3, 0xAB) or not e["ok"] or
               (e["type"] == 0xAA and "failed" in e["desc"])]
        for e in bad:
            status = "WARN"
            details.append("negli ultimi 5 avvii: %s %s %s%s" % (e["time"], e["name"], e["desc"],
                                                                  "" if e["ok"] else " [checksum errato]"))
        details.append("gli ultimi eventi:")
        details.extend("  %s  %-24s %s" % (e["time"], e["name"], e["desc"]) for e in events[-8:])
        summary = "%d eventi, %d avvii, %d byte su 16384%s%s" % (
            len(events), len(boots), used, "; hang, surriscaldamento o cache non scritta negli ultimi avvii"
            if bad else "", note)
        rep.add("ELOG-01", "Registro degli eventi", status, summary, details,
                {"events": len(events), "boots": len(boots), "bytes": used, "stale": stale})
    areas = update.fmap_areas(data)
    try:
        update.need_whole_flash(path, data, areas)
    except update.Error as e:
        rep.add("VB-02", "vboot nella copia del flash", "SKIP", str(e))
        return
    if not areas or "RW_NVRAM" not in areas:
        rep.add("VB-02", "vboot nella copia del flash", "SKIP", "nessuna FMAP con RW_NVRAM in %s" % path)
        return
    o, s = areas["RW_NVRAM"]
    st = update.nv_state(data[o:o + s])
    slot = "AB"
    details = []
    for label, name in (("RO", "WP_RO"), ("slot A", "FW_MAIN_A"), ("slot B", "FW_MAIN_B")):
        if name in areas:
            found = update.region_builds(data, areas[name])
            details.append("%-7s %s" % (label, " + ".join(found) or "non riconosciuto"))
    if not st["valid"]:
        status, summary = "WARN", "nessun record valido in RW_NVRAM: vboot riparte dallo slot A"
    else:
        status = "WARN" if st["prev_result"] == 3 else "PASS"
        summary = "prossimo slot %s%s; corrente %s %s, precedente %s %s%s" % (
            slot[st["try_next"]], ", %d tentativi" % st["try_count"] if st["try_count"] else "",
            slot[st["tried"]], update.NV_RESULTS[st["result"]], slot[st["prev_tried"]],
            update.NV_RESULTS[st["prev_result"]], note)
        running = [n for n in ("FW_MAIN_A", "FW_MAIN_B") if n in areas and fw.bios and
                   any(same_build(fw.bios, b) for b in update.region_builds(data, areas[n]))]
        if fw.bios and not running:
            # una copia di prima di questo avvio puo' essere di prima dell'aggiornamento
            status = worst(status, "INFO" if stale else "WARN")
            details.append("%s non e' in nessuno slot della copia" % fw.bios)
    details.append("RW_NVRAM: %d record su %d" % (st["used"], st["total"]))
    rep.add("VB-02", "vboot nella copia del flash", status, summary, details)
    if "SMMSTORE" in areas:
        o, s = areas["SMMSTORE"]
        try:
            opts, info = saved_options(data[o:o + s])
        except (update.Error, struct.error, IndexError) as e:
            rep.add("OPT-01", "Opzioni salvate", "WARN", "SMMSTORE non letto: %s" % e)
            return
        healthy = info["health"] == 0xFE
        details = ["store: %d KiB, %d KiB usati, %d liberi, stato 0x%02x%s" % (
            info["store_size"] // 1024, info["used"] // 1024, info["free"] // 1024, info["health"],
            "" if healthy else " (NON sano)")]
        details.append(", ".join("%s=%d" % kv for kv in sorted(opts.items())) or "nessuna opzione salvata")
        status = "PASS" if healthy else "WARN"
        if info["free"] < 4096:
            status = "WARN"
            details.append("store quasi pieno")
        rep.add("OPT-01", "Opzioni salvate", status, "%d opzioni di coreboot in SMMSTORE%s%s" % (
            len(opts), "" if healthy else ", store NON sano", note), details, {"options": opts})


# --- uscita --------------------------------------------------------------------

def header():
    up = float((rd("/proc/uptime", "0") or "0").split()[0])
    return {"date": time.strftime("%Y-%m-%d %H:%M"), "kernel": platform.release(),
            "uptime_min": round(up / 60), "product": rd("/sys/class/dmi/id/product_version") or
            rd("/sys/class/dmi/id/product_name", "?")}


def print_text(rep, fw, head):
    print("ouroBIOS hw-report - %s (board %s), %s" % (head["product"], fw.board or "non riconosciuta",
                                                       head["date"]))
    print("firmware %s, kernel %s, acceso da %d min" % (fw.bios or "?", head["kernel"], head["uptime_min"]))
    print()
    for c in rep.checks:
        print("[%s] %-8s %s: %s" % (c["status"], c["id"], c["title"], c["summary"]))
        for d in c["details"]:
            print("         " + d)
    n = rep.counts()
    print()
    print("Esito: %s - %s (uscita %d)" % (rep.worst(), ", ".join("%d %s" % (n[s], s) for s in
                                                               ("FAIL", "WARN", "PASS", "INFO", "SKIP") if n[s]),
                                        rep.exit_code()))


def write_markdown(rep, fw, head, path):
    esc = lambda s: s.replace("|", "\\|")
    n = rep.counts()
    out = ["# ouroBIOS hw-report", "",
           "- Macchina: %s (board %s)" % (head["product"], fw.board or "non riconosciuta"),
           "- Firmware: `%s`" % (fw.bios or "?"),
           "- Kernel: %s, acceso da %d min" % (head["kernel"], head["uptime_min"]),
           "- Data: %s" % head["date"],
           "- Esito: **%s** (%s; uscita %d)" % (rep.worst(), ", ".join(
               "%d %s" % (n[s], s) for s in ("FAIL", "WARN", "PASS", "INFO", "SKIP") if n[s]), rep.exit_code()),
           "", "| ID | Esito | Controllo | Riepilogo |", "|---|---|---|---|"]
    for c in rep.checks:
        out.append("| %s | %s | %s | %s |" % (c["id"], c["status"], esc(c["title"]), esc(c["summary"])))
    for c in rep.checks:
        if c["details"]:
            out += ["", "## %s %s: %s" % (c["id"], c["title"], c["status"]), "", "```"] + c["details"] + ["```"]
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def main():
    ap = Usage(description="Controllo di una macchina con ouroBIOS: firmware, avvio, memoria, stati C, "
                           "PCIe, ventola, ME, TPM, protezione del flash (solo lettura)")
    ap.add_argument("--seconds", type=float, default=20, help="durata della misura degli stati C (default 20)")
    ap.add_argument("--markdown", metavar="FILE", help="scrive anche il rapporto in Markdown in FILE")
    ap.add_argument("--json", action="store_true", help="stampa il rapporto in JSON invece che in testo")
    ap.add_argument("--dump", metavar="FILE", help="una copia del flash (sudo flashrom -p internal -r FILE): "
                                                   "registro degli eventi, RW_NVRAM e opzioni salvate")
    args = ap.parse_args()
    if args.seconds <= 0:
        die("--seconds deve essere positivo")
    if os.geteuid() != 0:
        die("serve root (cbmem, MSR, dmidecode): sudo python3 -I %s" % sys.argv[0])
    fw = Firmware()
    rep = Report()
    msr = MsrRO()
    pcie_state = {}

    def guard(fn, cid, title, *a):
        """un controllo che si rompe non ferma gli altri"""
        try:
            return fn(*a)
        except Exception as e:  # noqa: BLE001
            rep.add(cid, title, "WARN", "controllo non riuscito: %s: %s" % (type(e).__name__, e))
            return None

    guard(check_firmware, "BOOT-01", "Firmware", fw, rep)
    guard(check_boot_time, "BOOT-02", "Tempo di avvio", fw, rep)
    guard(check_fw_log, "BOOT-03", "Log di coreboot", fw, rep)
    guard(check_kernel_log, "BOOT-04", "Log del kernel", fw, rep)
    guard(check_raminit, "MEM-01", "RAM init", fw, rep)
    guard(check_memory, "MEM-02", "Memoria", fw, rep)
    guard(check_cpu, "CPU-01", "CPU", fw, rep, msr)
    guard(check_idle, "IDLE-01", "Stati C del package", fw, rep, msr, args.seconds)
    guard(check_s3, "S3-01", "Sospensione", fw, rep)
    r = guard(check_pcie, "PCI-01", "PCIe ASPM e LTR", fw, rep)
    if r:
        pcie_state = r[1]
        guard(check_peg, "PCI-02", "Porta PEG del riser", fw, rep, pcie_state)
        guard(check_aperture, "PCI-09", "Aperture PCI del payload", fw, rep, r[0])
    guard(check_fan, "FAN-01", "Ventola e temperature", fw, rep)
    guard(check_tpm, "TPM-01", "TPM", fw, rep)
    guard(check_measured_boot, "TPM-03", "Measured boot", fw, rep)
    guard(check_me, "ME-01", "Intel ME", fw, rep)
    guard(check_ec, "EC-01", "Firmware dell'EC", fw, rep)
    guard(check_vboot, "VB-01", "vboot", fw, rep)
    guard(check_update, "UPD-01", "Aggiornamenti", fw, rep)
    guard(check_flash, "FLASH-01", "Protezione del flash", fw, rep)
    guard(check_watchdog, "WDT-01", "Firmware watchdog", fw, rep)
    guard(check_dump, "ELOG-01", "Registro degli eventi", fw, rep, args.dump)
    guard(check_smbios, "ID-01", "SMBIOS e VPD", fw, rep)
    guard(check_acpi, "ID-02", "Tabelle ACPI", fw, rep)
    guard(check_wsmt, "CONF-01", "WSMT", fw, rep)
    guard(check_ecam, "CONF-07", "ECAM", fw, rep)
    guard(check_hsti, "CONF-08", "HSTI", fw, rep)
    head = header()
    if args.json:
        print(json.dumps({"tool": "hw-report", "format": 1, "board": fw.board, "firmware": fw.bios,
                          "header": head, "result": rep.worst(), "exit": rep.exit_code(), "checks": rep.checks},
                         indent=1, sort_keys=False))
    else:
        print_text(rep, fw, head)
    if args.markdown:
        write_markdown(rep, fw, head, args.markdown)
    return rep.exit_code()


if __name__ == "__main__":
    sys.exit(main())
