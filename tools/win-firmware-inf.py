#!/usr/bin/env python3
# win-firmware-inf.py - un pacchetto di driver di Windows per una capsula di
# ouroBIOS (docs/hlk.md, "Firmware updates from Windows"): firmware.bin, la
# capsula com'e', e ourobios.inf, l'INF di "Authoring an update driver
# package" di Microsoft con il GUID dell'ESRT e la versione della capsula.
# Windows la passa al firmware con UpdateCapsule() prima di un riavvio a
# caldo. Il catalogo (Inf2Cat) e la sua firma li fa Windows: per le prove con
# un certificato di test, come dice quella pagina.
#
#   tools/win-firmware-inf.py [--date AAAA-MM-GG] CAPSULA CARTELLA
#
# CAPSULA: un .cap o un .cab di una release (tools/update.py li legge).
# CARTELLA: nuova o vuota. --date: la data di DriverVer (default oggi, UTC).
import argparse
import datetime
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# il pacchetto per Windows 10, version 1803 e successive (FirmwareFilename
# con il percorso nel Driver Store, DefaultDestDir 13); x64
INF = """\
; ouroBIOS: {desc}
; tools/win-firmware-inf.py, from {capsule}

[Version]
Signature   = "$WINDOWS NT$"
Provider    = %Provider%
Class       = Firmware
ClassGuid   = {{f2e7dd72-6468-4e36-b6f1-6488f42c1b52}}
DriverVer   = {date},{quad}
CatalogFile = ourobios.cat
PnpLockdown = 1

[Manufacturer]
%MfgName% = Firmware,NTamd64.10.0...17134

[Firmware.NTamd64.10.0...17134]
%FirmwareDesc% = Firmware_Install,UEFI\\RES_{{{guid}}}

[Firmware_Install.NT]
CopyFiles = Firmware_CopyFiles

[Firmware_CopyFiles]
firmware.bin

[Firmware_Install.NT.Hw]
AddReg = Firmware_AddReg

[Firmware_AddReg]
HKR,,FirmwareId,,{{{guid}}}
HKR,,FirmwareVersion,%REG_DWORD%,0x{version:08x}
HKR,,FirmwareFilename,,%13%\\firmware.bin

[SourceDisksNames]
1 = %DiskName%

[SourceDisksFiles]
firmware.bin = 1

[DestinationDirs]
DefaultDestDir = 13

[Strings]
Provider     = "ouroBIOS"
MfgName      = "ouroBIOS"
FirmwareDesc = "{desc}"
DiskName     = "ouroBIOS firmware update"
REG_DWORD    = 0x00010001
"""


def load_update():
    spec = importlib.util.spec_from_file_location("update", os.path.join(HERE, "update.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="pacchetto di driver di Windows per una capsula di ouroBIOS")
    ap.add_argument("--date", help="data di DriverVer, AAAA-MM-GG (default oggi, UTC)")
    ap.add_argument("capsule")
    ap.add_argument("out")
    args = ap.parse_args()
    upd = load_update()
    try:
        data, cap = upd.load_capsule(args.capsule)
    except upd.Error as e:
        print("win-firmware-inf: %s" % e, file=sys.stderr)
        return 1
    if cap["variant"] is None:
        print("win-firmware-inf: %s: GUID %s, non di una variante di oggi (%s)" % (
            args.capsule, cap["type_id"], ", ".join(sorted(upd.VARIANTS))), file=sys.stderr)
        return 1
    if args.date:
        day = datetime.date.fromisoformat(args.date)
    else:
        day = datetime.datetime.now(datetime.timezone.utc).date()
    if os.path.exists(args.out) and os.listdir(args.out):
        print("win-firmware-inf: %s non e' vuota" % args.out, file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)
    board, variant, _ = upd.FLAVOURS[cap["variant"]]
    desc = "ouroBIOS %s (%s %s) system firmware" % (upd.version_str(cap["version"]), board, variant)
    text = INF.format(desc=desc, capsule=os.path.basename(args.capsule),
                      date=day.strftime("%m/%d/%Y"), quad=upd.version_quad(cap["version"]),
                      guid=str(cap["type_id"]), version=cap["version"])
    # le INF di Windows: CRLF, ASCII
    with open(os.path.join(args.out, "ourobios.inf"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(text)
    with open(os.path.join(args.out, "firmware.bin"), "wb") as f:
        f.write(data)
    print("%s: %s, ESRT %s, versione 0x%08x" % (args.out, desc, cap["type_id"], cap["version"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
