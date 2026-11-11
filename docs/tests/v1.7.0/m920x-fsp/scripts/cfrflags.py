#!/usr/bin/env python3
# The flags of every option in the live CFR record of the coreboot table
import struct, sys
t = open(sys.argv[1], "rb").read()
# struct lb_header: signature, header_bytes, header_checksum, table_bytes,
# table_checksum, table_entries
hdr_bytes, _, table_bytes, _, entries = struct.unpack_from("<IIIII", t, 4)
pos, end = hdr_bytes, hdr_bytes + table_bytes
cfr = None
for _ in range(entries):
    if pos + 8 > end:
        break
    tag, size = struct.unpack_from("<II", t, pos)
    if tag == 0x47:
        cfr = (pos, size)
    if size < 8:
        break
    pos += size
assert cfr, "no LB_TAG_CFR_ROOT"
FLAG = {1: "READONLY", 2: "INACTIVE", 4: "SUPPRESS", 8: "VOLATILE", 16: "RUNTIME", 32: "LOCK_AT_BOOT"}
opts = []
def walk(pos, end):
    while pos + 8 <= end:
        tag, size = struct.unpack_from("<II", t, pos)
        if size < 8:
            break
        if tag in (3, 4, 5, 6):
            flags, = struct.unpack_from("<I", t, pos + 24)
            fixed = 48 if tag != 6 else 28
            vt, vs, vl = struct.unpack_from("<III", t, pos + fixed)
            name = t[pos + fixed + 12:pos + fixed + 12 + vl].rstrip(b"\0").decode() if vt == 7 else "?"
            opts.append((name, flags))
        elif tag == 1:
            vt, vs, vl = struct.unpack_from("<III", t, pos + 28)
            walk(pos + 28 + vs, pos + size)
        pos += size
# the root record: tag, size, then the root form
walk(cfr[0] + 16, cfr[0] + cfr[1])
for name, flags in opts:
    print("%-26s 0x%02x %s" % (name, flags, " ".join(n for b, n in FLAG.items() if flags & b)))
lock = sum(1 for _, f in opts if f & 32)
ro = sum(1 for _, f in opts if f & 1)
print("options %d: LOCK_AT_BOOT %d, READONLY %d, neither %d" % (len(opts), lock, ro, sum(1 for _, f in opts if not f & 33)))
