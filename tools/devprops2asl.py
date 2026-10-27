#!/usr/bin/env python3
# devprops2asl.py - the DeviceProperties of an OpenCore configuration as the
# _DSM methods of the DSDT of the W541: src/mainboard/lenovo/haswell/acpi/
# devprops.asl (patch 0128), under macOS only and with the setup option
# macos_device_properties on.
#
#   python3 tools/devprops2asl.py config.plist > devprops.asl
#   python3 tools/devprops2asl.py configs/macos/DeviceProperties.plist \
#       --builtin configs/macos/DeviceProperties-builtin.plist > devprops.asl
#
# With --builtin, a device that has properties in both files returns those
# of the second one when Panel under macOS is on Built-in display
# (\_SB.PCI0.GFX0.DWBI, patch 0129), the others otherwise: the framebuffer
# of the Intel GPU differs between the two (desktop 0x0D220003 with the
# panel as a DisplayPort sink, laptop 0x0A260006 with con0 on DDI D).
#
# configs/macos/DeviceProperties.plist holds the DeviceProperties of patch
# 0128, configs/macos/DeviceProperties-builtin.plist those of 0133 for
# Built-in display: after a change there, the output (with --builtin) goes
# in the devprops.asl of a new patch, and the setup help of
# macos_device_properties says what they are.
#
# Reads DeviceProperties -> Add of config.plist (or of a plist that holds only
# that dictionary, or the Add dictionary itself): nothing else of the file,
# PlatformInfo included. For each device, in the order of the file, a Scope
# with a _DSM for Apple's UUID: function 0 lists function 1, which returns the
# properties as OpenCore gives them, in plist multidata form (data as is,
# strings with their NUL, integers as 32-bit little-endian data); other UUIDs,
# other OSes and the option off get Buffer () { 0 }.
import argparse
import plistlib
import re
import sys

APPLE_UUID = "a0b5b7c6-1318-441c-b0c9-fe695eaf949b"

# Device paths of the W541 and their nodes in the DSDT of ouroBIOS
NODES = {
    "PciRoot(0x0)/Pci(0x0,0x0)": r"\_SB.PCI0.MCHC",
    "PciRoot(0x0)/Pci(0x1,0x0)": r"\_SB.PCI0.PEGP",
    "PciRoot(0x0)/Pci(0x2,0x0)": r"\_SB.PCI0.GFX0",
    "PciRoot(0x0)/Pci(0x3,0x0)": r"\_SB.PCI0.HDAU",
    "PciRoot(0x0)/Pci(0x14,0x0)": r"\_SB.PCI0.XHCI",
    "PciRoot(0x0)/Pci(0x19,0x0)": r"\_SB.PCI0.GLAN",
    "PciRoot(0x0)/Pci(0x1a,0x0)": r"\_SB.PCI0.EHC2",
    "PciRoot(0x0)/Pci(0x1b,0x0)": r"\_SB.PCI0.HDEF",
    "PciRoot(0x0)/Pci(0x1d,0x0)": r"\_SB.PCI0.EHCI",
    "PciRoot(0x0)/Pci(0x1f,0x0)": r"\_SB.PCI0.LPCB",
    "PciRoot(0x0)/Pci(0x1f,0x2)": r"\_SB.PCI0.SATA",
    "PciRoot(0x0)/Pci(0x1f,0x3)": r"\_SB.PCI0.SBUS",
}
# The cards behind the root ports that have a node (RP01-RP03, RP05)
for fn in (0, 1, 2, 4):
    NODES[f"PciRoot(0x0)/Pci(0x1c,{fn:#x})/Pci(0x0,0x0)"] = rf"\_SB.PCI0.RP0{fn + 1}.PXSX"
    NODES[f"PciRoot(0x0)/Pci(0x1c,{fn:#x})"] = rf"\_SB.PCI0.RP0{fn + 1}"
# These have a _DSM of their own already
TAKEN = {r"\_SB.PCI0.PEGP.DEV0"}


def norm(path):
    """PciRoot(0x0)/Pci(0x2,0x0), whatever the case and the spaces"""
    path = re.sub(r"\s+", "", path)

    def hexnum(m):
        return hex(int(m.group(0), 0))

    path = re.sub(r"0[xX][0-9a-fA-F]+|\b\d+\b", hexnum, path)
    return re.sub(r"(?i)pciroot", "PciRoot", re.sub(r"(?i)\bpci\(", "Pci(", path))


def asl_string(s):
    if any(ord(c) < 0x20 or ord(c) > 0x7e or c in '"\\' for c in s):
        raise ValueError(f"key {s!r}: only printable ASCII without quotes and backslashes")
    return f'"{s}"'


def asl_buffer(data, indent, lead):
    """The bytes as Buffer () { ... }, on the line after lead (what comes
    before it, indented by indent tabs) when they fit in 96 columns, else
    eight to a line"""
    if not data:
        return "Buffer (Zero) {}"
    body = ", ".join(f"0x{b:02x}" for b in data)
    one = f"Buffer () {{ {body} }}"
    if 8 * indent + len(lead) + len(one) + 1 <= 96:
        return one
    pad = "\t" * (indent + 1)
    rows = [", ".join(f"0x{b:02x}" for b in data[i:i + 8]) for i in range(0, len(data), 8)]
    return "Buffer () {\n" + ",\n".join(pad + r for r in rows) + "\n" + "\t" * indent + "}"


def printable(data):
    """data is a NUL-terminated string of printable ASCII, without quotes
    and backslashes: an ASL string, which a Buffer takes with its NUL"""
    return (len(data) > 1 and data[-1] == 0 and
            all(0x20 <= b <= 0x7e and b not in b'"\\' for b in data[:-1]))


def value_bytes(key, value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("ascii") + b"\0"
    if isinstance(value, bool):
        raise ValueError(f"{key}: a boolean, which OpenCore does not inject")
    if isinstance(value, int):
        return (value & 0xffffffff).to_bytes(4, "little")
    raise ValueError(f"{key}: type {type(value).__name__} not supported")


def load_add(path):
    """DeviceProperties -> Add of the plist at path"""
    with open(path, "rb") as f:
        add = plistlib.load(f)
    if "DeviceProperties" in add:
        add = add["DeviceProperties"]
    if "Add" in add:
        add = add["Add"]
    return add


def package(props, indent, path):
    """The properties as the lines of a Return (Package () { ... }), indented
    by indent tabs, and the number of errors"""
    lines = ["\t" * indent + "Return (Package () {"]
    errors = 0
    for key in props:
        try:
            data = value_bytes(key, props[key])
            lead = f"{asl_string(key)}, "
            if printable(data):
                value = 'Buffer () { "%s" }' % data[:-1].decode("ascii")
            else:
                value = asl_buffer(data, indent + 1, lead)
            lines.append("\t" * (indent + 1) + f"{lead}{value},")
        except ValueError as e:
            print(f"devprops2asl: {path}: {e}", file=sys.stderr)
            errors += 1
    lines.append("\t" * indent + "})")
    return lines, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plist")
    ap.add_argument("--builtin", metavar="PLIST",
                    help="the properties of the devices that differ with Panel "
                         "under macOS on Built-in display (\\_SB.PCI0.GFX0.DWBI)")
    args = ap.parse_args()
    add = load_add(args.plist)
    builtin = {norm(p): v for p, v in load_add(args.builtin).items()} if args.builtin else {}
    out = [
        "/* SPDX-License-Identifier: GPL-2.0-only */",
        "",
        "/*",
        " * The device properties of macOS on this W541, as DeviceProperties of an",
        " * OpenCore configuration gives them, through the _DSM of each device for",
        " * Apple's UUID: function 0 lists function 1, which returns them. Written",
        " * by tools/devprops2asl.py of ouroBIOS from that DeviceProperties.",
    ]
    if builtin:
        out += [
            " * With Panel under macOS on Built-in display (\\_SB.PCI0.GFX0.DWBI,",
            " * patch 0129), a device that has properties in the DeviceProperties",
            " * for it gets those instead.",
        ]
    out += [
        " */",
        "",
        "External (\\_SB.PCI0.DPRP, IntObj)",
        "",
        "/*",
        " * Whether a _DSM gives the properties: for Apple's UUID (Arg0), under",
        " * macOS, with the setup option macos_device_properties on (DPRP, from",
        " * the SSDT; off without it).",
        " */",
        "Method (\\_SB.PCI0.DPON, 1, Serialized)",
        "{",
        f'\tIf (Arg0 != ToUUID ("{APPLE_UUID}")) {{',
        "\t\tReturn (0)",
        "\t}",
        "\tIf (\\ISDW () && CondRefOf (\\_SB.PCI0.DPRP)) {",
        "\t\tReturn (\\_SB.PCI0.DPRP)",
        "\t}",
        "\tReturn (0)",
        "}",
    ]
    errors = 0
    for path in add:
        node = NODES.get(norm(path))
        if node is None or node in TAKEN:
            print(f"devprops2asl: {path}: no node of the DSDT for it", file=sys.stderr)
            errors += 1
            continue
        props = add[path]
        if not props:
            continue
        out += ["", f"Scope ({node})", "{", "\tMethod (_DSM, 4, Serialized)", "\t{"]
        out += [
            "\t\tIf (!\\_SB.PCI0.DPON (Arg0)) {",
            "\t\t\tReturn (Buffer (One) { 0x00 })",
            "\t\t}",
            "\t\tIf (Arg2 == Zero) {",
            "\t\t\tReturn (Buffer (One) { 0x03 })",
            "\t\t}",
        ]
        # The properties for Built-in display first, when the device has them
        other = builtin.pop(norm(path), None)
        if other:
            lines, n = package(other, 3, path)
            out += ["\t\tIf (\\_SB.PCI0.GFX0.DWBI ()) {"] + lines + ["\t\t}"]
            errors += n
        lines, n = package(props, 2, path)
        out += lines
        errors += n
        out += ["\t}", "}"]
    for path in builtin:
        print(f"devprops2asl: {path}: in --builtin only, not in {args.plist}", file=sys.stderr)
        errors += 1
    print("\n".join(out))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
