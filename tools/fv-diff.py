#!/usr/bin/env python3
# fv-diff.py - due flash device di EDK2 (UEFIPAYLOAD.fd) confrontati file per
# file: i volumi (FV), i file FFS con il loro nome (la sezione USER_INTERFACE)
# e, dentro le sezioni compresse LZMA, i volumi annidati. Per un file diverso,
# le sezioni PE32 diverse e, di quelle, le sezioni del PE (.text, .data...)
# che cambiano. Per tools/build.sh edk2-parity: il payload dall'EDK2 di
# MrChromebox e quello dal package su TianoCore.
#
#   tools/fv-diff.py A.fd B.fd
#
# Esce con 0 se i file FFS sono gli stessi (anche se i due .fd non sono
# uguali byte per byte: lo dice), 1 se no.
import hashlib
import lzma
import struct
import sys
import uuid

LZMA_GUID = uuid.UUID("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
CRC32_GUID = uuid.UUID("fc1bcdb0-7d31-49aa-936a-a4600d9dd083")
SECTION_NAMES = {0x01: "COMPRESSION", 0x02: "GUID_DEFINED", 0x10: "PE32", 0x11: "PIC", 0x12: "TE",
                 0x13: "DXE_DEPEX", 0x14: "VERSION", 0x15: "USER_INTERFACE", 0x17: "FV_IMAGE",
                 0x18: "FREEFORM_SUBTYPE_GUID", 0x19: "RAW", 0x1B: "PEI_DEPEX", 0x1C: "MM_DEPEX"}


def u24(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def guid(b, o):
    return uuid.UUID(bytes_le=bytes(b[o:o + 16]))


def sections(data, path, out):
    """Le sezioni di un file FFS (o di una sezione incapsulata): torna il
    nome (USER_INTERFACE) se c'e'; i volumi annidati in out."""
    name = None
    o = 0
    while o + 4 <= len(data):
        size, typ = u24(data, o), data[o + 3]
        hdr = 4
        if size == 0xFFFFFF:
            size, hdr = struct.unpack_from("<I", data, o + 4)[0], 8
        if size < hdr or o + size > len(data):
            break
        body = data[o + hdr:o + size]
        if typ == 0x15:
            name = bytes(body).decode("utf-16-le", errors="replace").rstrip("\0")
        elif typ == 0x02:
            g = guid(body, 0)
            off = struct.unpack_from("<H", body, 16)[0] - hdr
            inner = body[off:]
            if g == LZMA_GUID:
                try:
                    inner = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(bytes(inner))
                except lzma.LZMAError as e:
                    out.setdefault("errors", []).append("%s: LZMA %s" % (path, e))
                    inner = b""
            elif g != CRC32_GUID:
                out.setdefault("errors", []).append("%s: sezione GUID %s non letta" % (path, g))
                inner = b""
            n = sections(inner, path, out)
            name = name or n
        elif typ == 0x01:
            # EFI_COMPRESSION_SECTION: solo quella senza compressione
            if body[4] == 0:
                n = sections(body[5:], path, out)
                name = name or n
            else:
                out.setdefault("errors", []).append("%s: compressione EFI non letta" % path)
        elif typ == 0x17:
            volumes(body, path + "/FV", out)
        o = (o + size + 3) & ~3
    return name


def pe_sections(data):
    """Le sezioni di un PE32: nome -> (inizio, dati)."""
    if data[:2] != b"MZ":
        return {}
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return {}
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    out = {"(header)": (0, data[:pe + 24 + opt + 40 * nsec])}
    for i in range(nsec):
        s = pe + 24 + opt + 40 * i
        nm = data[s:s + 8].rstrip(b"\0").decode(errors="replace")
        raw_size, raw_ptr = struct.unpack_from("<II", data, s + 16)
        out[nm] = (raw_ptr, data[raw_ptr:raw_ptr + raw_size])
    return out


def ffs_files(fv, path, out):
    hlen = struct.unpack_from("<H", fv, 48)[0]
    ext = struct.unpack_from("<H", fv, 52)[0]
    o = hlen
    if ext:
        o = (ext + struct.unpack_from("<I", fv, ext + 16)[0] + 7) & ~7
    end = struct.unpack_from("<Q", fv, 32)[0]
    while o + 24 <= min(end, len(fv)):
        if fv[o:o + 24] == b"\xff" * 24:
            break
        g = guid(fv, o)
        typ, attr = fv[o + 18], fv[o + 19]
        size, hdr = u24(fv, o + 20), 24
        if attr & 0x01:
            size, hdr = struct.unpack_from("<Q", fv, o + 24)[0], 32
        if size < hdr:
            break
        body = fv[o + hdr:o + size]
        if typ != 0xF0:
            key = "%s/%s" % (path, g)
            pes = []
            sub = {}
            name = None
            if typ not in (0x01, 0x02):
                name = sections(body, key, sub)
                pes = [s for s in collect_pe(body)]
            out[key] = {"name": name or "", "type": typ, "size": size,
                        "sha": hashlib.sha256(bytes(fv[o:o + size])).hexdigest(), "pe": pes}
            for k, v in sub.items():
                if k == "errors":
                    out.setdefault("errors", []).extend(v)
                else:
                    out[k] = v
        o = (o + size + 7) & ~7


def collect_pe(data):
    """Le sezioni PE32 e TE di un file FFS, anche dentro LZMA."""
    found = []
    o = 0
    while o + 4 <= len(data):
        size, typ = u24(data, o), data[o + 3]
        hdr = 4
        if size == 0xFFFFFF:
            size, hdr = struct.unpack_from("<I", data, o + 4)[0], 8
        if size < hdr or o + size > len(data):
            break
        body = data[o + hdr:o + size]
        if typ in (0x10, 0x12):
            found.append(bytes(body))
        elif typ == 0x02:
            g = guid(body, 0)
            off = struct.unpack_from("<H", body, 16)[0] - hdr
            inner = body[off:]
            if g == LZMA_GUID:
                try:
                    inner = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(bytes(inner))
                except lzma.LZMAError:
                    inner = b""
            found.extend(collect_pe(inner))
        o = (o + size + 3) & ~3
    return found


def volumes(data, path, out):
    """I volumi di un .fd o di una sezione FV_IMAGE, ognuno con i suoi file."""
    o = 0
    n = 0
    while o + 56 <= len(data):
        if data[o + 40:o + 44] == b"_FVH":
            length = struct.unpack_from("<Q", data, o + 32)[0]
            if 0 < length <= len(data) - o:
                ffs_files(memoryview(data)[o:o + length], "%s@%x" % (path, o), out)
                n += 1
                o += (length + 7) & ~7
                continue
        o += 8
    return n


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    out = {}
    volumes(data, "FV", out)
    return data, out


def main():
    if len(sys.argv) != 3:
        print("uso: fv-diff.py A.fd B.fd", file=sys.stderr)
        return 2
    (da, a), (db, b) = load(sys.argv[1]), load(sys.argv[2])
    for side, x in (("A", a), ("B", b)):
        for e in x.get("errors", []):
            print("  !!  %s: %s" % (side, e))
    keys = sorted((set(a) | set(b)) - {"errors"})
    diff = 0
    for k in keys:
        x, y = a.get(k), b.get(k)
        label = (x or y)["name"] or "tipo 0x%02x" % (x or y)["type"]
        if x is None or y is None:
            print("  NO  %s (%s): solo in %s" % (k, label, "B" if x is None else "A"))
            diff += 1
            continue
        if x["sha"] == y["sha"]:
            continue
        diff += 1
        print("  NO  %s (%s): %d e %d byte" % (k, label, x["size"], y["size"]))
        for i, (pa, pb) in enumerate(zip(x["pe"], y["pe"])):
            if pa == pb:
                continue
            sa, sb = pe_sections(pa), pe_sections(pb)
            for nm in sorted(set(sa) | set(sb)):
                ra, rb = sa.get(nm), sb.get(nm)
                if ra is None or rb is None or ra[1] != rb[1]:
                    first = next((j for j, (p, q) in enumerate(zip(ra[1], rb[1])) if p != q), None) \
                        if ra and rb else None
                    print("        PE %d %s: %s e %s byte%s" % (
                        i, nm, len(ra[1]) if ra else "-", len(rb[1]) if rb else "-",
                        ", primo byte diverso a +0x%x" % first if first is not None else ""))
        if len(x["pe"]) != len(y["pe"]):
            print("        %d e %d sezioni PE32/TE" % (len(x["pe"]), len(y["pe"])))
    same = da == db
    print("  %s  %d file FFS in A, %d in B, %d diversi; i .fd %s (%d e %d byte)" % (
        "ok" if diff == 0 else "NO", len(set(a) - {"errors"}), len(set(b) - {"errors"}), diff,
        "uguali byte per byte" if same else "diversi", len(da), len(db)))
    return 0 if diff == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
