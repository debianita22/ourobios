#!/usr/bin/env python3
# peg-report.py - il link PCIe tra il W541 e la sua GPU NVIDIA: la porta PEG
# del processore (00:01.0) e la GPU (01:00.0). Velocita' e larghezza, le fasi
# dell'equalizzazione a 8 GT/s, i preset Gen3 e le impostazioni AFE di Intel
# che il firmware programma con *NVIDIA GPU link tuning* (patch 0078-0083),
# e gli errori che le due parti del link hanno registrato.
#
#   sudo python3 tools/peg-report.py              # il rapporto
#   sudo python3 tools/peg-report.py --clear      # il rapporto, poi gli errori azzerati
#   python3 tools/peg-report.py --file lspci.txt  # da sudo lspci -xxxx -s 00:01.0
#                                                 # (e -s 01:00.0), anche di un altro PC
#
# Una prova: GPU accesa (power/control a "on" per 00:01.0 e 01:00.0), --clear,
# un carico con il pstate piu' alto di nouveau (il link passa a 8 GT/s), poi
# di nuovo il rapporto. Lo spazio di configurazione oltre i primi 256 byte si
# legge solo da root. Un dispositivo in D3cold non si legge: la lettura da
# sysfs lo riaccenderebbe. Solo la libreria standard di Python.
import argparse
import os
import re
import sys

PCI = "/sys/bus/pci/devices/0000:"
RP, GPU = "00:01.0", "01:00.0"
# Le porte PEG 0:1.0 di Haswell (come pcie.c di coreboot)
PEG_IDS = {(0x8086, d) for d in (0x0c01, 0x0c05, 0x0c09, 0x0c0d, 0x0d01, 0x0d05, 0x0d09)}

SPEED = {1: "2.5 GT/s", 2: "5 GT/s", 3: "8 GT/s"}

# I bit di stato dell'AER: errori corretti e non corretti
CE = {0: "Receiver Error", 6: "Bad TLP", 7: "Bad DLLP", 8: "REPLAY_NUM Rollover",
      12: "Replay Timer Timeout", 13: "Advisory Non-Fatal", 14: "Corrected Internal",
      15: "Header Log Overflow"}
UE = {4: "Data Link Protocol", 5: "Surprise Down", 12: "Poisoned TLP",
      13: "Flow Control Protocol", 14: "Completion Timeout", 15: "Completer Abort",
      16: "Unexpected Completion", 17: "Receiver Overflow", 18: "Malformed TLP", 19: "ECRC",
      20: "Unsupported Request", 21: "ACS Violation", 22: "Uncorrectable Internal"}
DEVSTA = {0: "CorrErr", 1: "NonFatalErr", 2: "FatalErr", 3: "UnsupReq"}

# La parte PEG della ricetta AFE di Intel, peg_dmi_recipe() di coreboot
# (src/northbridge/intel/haswell/early_pcie.c): offset, maschera, valore,
# shift, per bundle (8 bundle a 0x20 l'uno dall'altro per le 16 lane, tutti
# nello spazio di 00:01.0)
RECIPE = [
    (0xa00, 0x1f, 0x0c, 0, True), (0xa10, 0x1f, 0x0c, 0, True),
    (0x904, 0x1f, 0x02, 0, True), (0x904, 0x1f, 0x03, 5, True),
    (0x90c, 0x3f, 0x09, 5, True), (0x90c, 0x0f, 0x05, 21, True),
    (0x910, 0x0f, 0x08, 6, True), (0x910, 0x0f, 0x00, 10, True),
    (0x910, 0x07, 0x00, 18, True),
    (0xc28, 0x1f, 0x13, 18, False),
    (0xc38, 0x01, 0x00, 6, False), (0x260, 0x03, 0x02, 0, False),
    (0x900, 0x03, 0x00, 26, True), (0x904, 0x03, 0x03, 10, True),
    (0x90c, 0x1f, 0x07, 25, True), (0x91c, 0x07, 0x05, 27, True),
]

# Lo stato del link della porta PEG, 0x216[3:0]: 0 giu', 7 L0
PEG_LINK_STATE = 0x216
# Non documentato: il reference code di Intel, e il firmware dalla v1.3.7 con
# "As the Lenovo firmware", vi accende i bit 15 e 1 prima del training e i bit
# 15 e 14 dopo l'equalizzazione a 8 GT/s
PEG_EQ_DD8 = 0xdd8
# I registri d'errore dell'AER della porta PEG, fuori dalla lista delle
# capability (Linux non li vede)
PEG_UESTS, PEG_CESTS = 0x1c4, 0x1d0


def rd(path, default="?"):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def r16(c, o):
    return int.from_bytes(c[o:o + 2], "little")


def r32(c, o):
    return int.from_bytes(c[o:o + 4], "little")


def names(v, table):
    s = [n for b, n in sorted(table.items()) if v >> b & 1]
    other = v & ~sum(1 << b for b in table)
    if other:
        s.append("altri bit 0x%x" % other)
    return " (" + ", ".join(s) + ")" if s else ""


def pcie_cap(c):
    p, seen = c[0x34] & 0xfc, 0
    while p and seen < 48:
        if c[p] == 0x10:
            return p
        p, seen = c[p + 1] & 0xfc, seen + 1
    return None


def ext_caps(c):
    caps, o = {}, 0x100
    for _ in range(64):
        if o < 0x100 or o + 4 > len(c):
            break
        h = r32(c, o)
        if h in (0, 0xffffffff):
            break
        caps.setdefault(h & 0xffff, o)
        o = (h >> 20) & 0xffc
    return caps


def lane_eq(c, sec, lanes):
    vals = [r16(c, sec + 0x0c + 2 * i) for i in range(lanes)]

    def f(v):
        return "porta Tx P%d hint %d, GPU Tx P%d hint %d (0x%04x)" % (
            v & 0xf, v >> 4 & 7, v >> 8 & 0xf, v >> 12 & 7, v)
    if len(set(vals)) == 1:
        return ["preset 8 GT/s, %d lane: %s" % (lanes, f(vals[0]))]
    return ["preset 8 GT/s, lane %2d: %s" % (i, f(v)) for i, v in enumerate(vals)]


def link(c, p, out):
    lcap, lsta = r32(c, p + 0x0c), r16(c, p + 0x12)
    lctl2, lsta2 = r16(c, p + 0x30), r16(c, p + 0x32)
    s = "  link %s x%d (massimo %s x%d, target %s)" % (
        SPEED.get(lsta & 0xf, "?"), lsta >> 4 & 0x3f, SPEED.get(lcap & 0xf, "?"), lcap >> 4 & 0x3f,
        SPEED.get(lctl2 & 0xf, "?"))
    if lsta >> 11 & 1:
        s += ", in training"
    if lsta >> 14 & 1:
        s += ", cambio di banda per un link inaffidabile o un retrain (LBMS)"
    if lsta >> 15 & 1:
        s += ", cambio di banda autonomo (LABS)"
    out.append(s)
    out.append("  equalizzazione 8 GT/s: %s, fase 1%s fase 2%s fase 3%s%s" % (
        "completa" if lsta2 >> 1 & 1 else "non fatta", "+" if lsta2 >> 2 & 1 else "-",
        "+" if lsta2 >> 3 & 1 else "-", "+" if lsta2 >> 4 & 1 else "-",
        ", richiesta di nuova equalizzazione" if lsta2 >> 5 & 1 else ""))
    return lcap >> 4 & 0x3f


def report(name, bdf, c, out):
    vid, did = r16(c, 0), r16(c, 2)
    out.append("%s %s (%04x:%04x)" % (bdf, name, vid, did))
    if len(c) < 0x100:
        out.append("  solo i primi %d byte: dump incompleto" % len(c))
        return
    p = pcie_cap(c)
    if p is None:
        out.append("  nessuna capability PCI Express")
        return
    lanes = link(c, p, out)
    ext = ext_caps(c) if len(c) >= 0x1000 else {}
    if len(c) < 0x1000:
        out.append("  solo i primi %d byte: niente preset, AFE ed errori (serve root)" % len(c))
    sec = ext.get(0x19)
    if sec:
        out.extend("  " + s for s in lane_eq(c, sec, min(lanes, 16)))
    if bdf == RP and len(c) >= 0x1000:
        out.append("  stato del link (0x216) %d%s" % (c[PEG_LINK_STATE] & 0xf,
                                                    " (L0)" if c[PEG_LINK_STATE] & 0xf == 7 else ""))
        same = total = 0
        for off, mask, val, shift, per_bundle in RECIPE:
            for i in range(8 if per_bundle else 1):
                total += 1
                same += (r32(c, off + 0x20 * i) >> shift & mask) == val
        out.append("  AFE: %d campi su %d come la ricetta di Intel%s" % (
            same, total, " (programmata)" if same == total else ""))
        dd8 = r32(c, PEG_EQ_DD8)
        out.append("  registro 0xdd8 0x%08x: sequenza del firmware Lenovo %s" % (
            dd8, "completata" if dd8 & 0xc002 == 0xc002 else "non eseguita"))
    devsta = r16(c, p + 0x0a) & 0xf
    out.append("  DevSta errori 0x%x%s" % (devsta, names(devsta, DEVSTA)))
    aer = PEG_UESTS - 4 if bdf == RP else ext.get(0x1)
    if aer and len(c) >= 0x1000:
        ue, ce = r32(c, aer + 4), r32(c, aer + 0x10)
        out.append("  AER non corretti 0x%08x%s" % (ue, names(ue, UE)))
        out.append("  AER corretti     0x%08x%s" % (ce, names(ce, CE)))
    if sec:
        le = r32(c, sec + 8)
        out.append("  errori per lane  0x%08x%s" % (
            le, " (lane " + " ".join(str(i) for i in range(32) if le >> i & 1) + ")" if le else ""))


def clear(bdf, c):
    """Azzera i bit RW1C d'errore: DevSta, LnkSta[15:14], AER, errori per lane"""
    p = pcie_cap(c)
    w = [(p + 0x0a, 2, 0x000f), (p + 0x12, 2, 0xc000)]
    ext = ext_caps(c)
    aer = PEG_UESTS - 4 if bdf == RP else ext.get(0x1)
    if aer:
        w += [(aer + 4, 4, 0xffffffff), (aer + 0x10, 4, 0xffffffff)]
    if ext.get(0x19):
        w.append((ext[0x19] + 8, 4, 0xffffffff))
    with open(PCI + bdf + "/config", "r+b", buffering=0) as f:
        for off, size, val in w:
            f.seek(off)
            f.write(val.to_bytes(size, "little"))


def from_sysfs(bdf):
    path = PCI + bdf
    if not os.path.exists(path):
        return None, "non c'e' (GPU spenta nel setup?)"
    if rd(path + "/power_state") == "D3cold":
        return None, "in D3cold, non letta: echo on > %s/power/control" % path
    with open(path + "/config", "rb") as f:
        return f.read(4096), None


def from_file(path):
    devs, cur = {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^(?:[0-9a-f]{4}:)?([0-9a-f]{2}:[0-9a-f]{2}\.[0-7]) ", line)
        if m:
            cur = devs.setdefault(m.group(1), bytearray())
            continue
        m = re.match(r"^([0-9a-f]{2,3}):((?: [0-9a-f]{2}){16})\s*$", line)
        if m and cur is not None:
            off = int(m.group(1), 16)
            if len(cur) < off:
                cur.extend(bytes(off - len(cur)))
            cur[off:off + 16] = bytes(int(b, 16) for b in m.group(2).split())
    return {k: bytes(v) for k, v in devs.items()}


def main():
    ap = argparse.ArgumentParser(description="Il link PCIe tra la porta PEG e la GPU NVIDIA")
    ap.add_argument("--clear", action="store_true", help="dopo il rapporto, azzera gli errori registrati")
    ap.add_argument("--file", help="un dump di lspci -xxxx al posto di sysfs")
    a = ap.parse_args()

    out = []
    if a.file:
        devs = from_file(a.file)
        out.append("dump: %s" % a.file)
    else:
        if os.geteuid() != 0:
            sys.exit("serve root, per lo spazio di configurazione esteso: sudo python3 %s" % sys.argv[0])
        out.append("firmware %s, kernel %s" % (rd("/sys/class/dmi/id/bios_version"), os.uname().release))
        devs = {}
        for bdf in (RP, GPU):
            data, why = from_sysfs(bdf)
            if data is None:
                out.append("%s %s" % (bdf, why))
            else:
                devs[bdf] = data
        if RP in devs and (r16(devs[RP], 0), r16(devs[RP], 2)) not in PEG_IDS:
            sys.exit("%s non e' la porta PEG di un Haswell: niente da leggere" % RP)
    for bdf, name in ((RP, "porta PEG"), (GPU, "GPU")):
        if bdf in devs:
            report(name, bdf, devs[bdf], out)
    print("\n".join(out))

    if a.clear:
        if a.file:
            sys.exit("--clear legge e scrive sysfs: non con --file")
        if os.geteuid() != 0:
            sys.exit("--clear: serve root")
        for bdf in devs:
            clear(bdf, devs[bdf])
        print("errori azzerati: %s" % " ".join(devs) if devs else "niente da azzerare")


if __name__ == "__main__":
    main()
