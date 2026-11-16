#!/usr/bin/env python3
# The variable store of a copy of the flash (read only), and the commit block
# of the reclaims in SMM (patches 0288, 0314): storeinfo.py FLASH.bin
#
# From v1.8.0 the first 2 KiB of the commit block are 32 slots of 64 bytes
# for the commit record (one that ended has zeros over its magic), and the
# rest slots of 32 bytes for the notes of the refusals, the last the latest.
# Up to v1.7.0 there was one record at the start of the block and one note
# at 0x800, the block erased by every reclaim: read here the same way.
import collections, importlib.util, os, struct, sys
tools = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools", "update.py")
spec = importlib.util.spec_from_file_location("upd", tools); u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
data = open(sys.argv[1], "rb").read(); o, s = u.fmap_areas(data)["SMMSTORE"]; region = data[o:o + s]
vars_, info = u.var_store(region)
st = collections.Counter(u.VAR_STATES.get(v["state"], hex(v["state"])) for v in vars_)
cb = [v for v in vars_ if v["state"] in (0x3f, 0x3e) and v["guid"] == u.CB_OPTION_GUID]
print("store %d bytes: used %d, free %d, next record at 0x%x; records %d %s; options %d"
      % (info["store_size"], info["used"], info["free"], info["next"], len(vars_), dict(st), len(cb)))

BLOCK, NOTES, RECORD, NOTE = 0x10000, 0x800, 64, 32
commit = region[s - BLOCK:]
names = {1: "store not walkable", 2: "more than a quarter free", 3: "reclaims of the boot used",
         4: "other headers", 5: "image not walkable", 6: "image clears the MOR request",
         7: "image with other options", 8: "commit record not written", 9: "copy failed", 10: "unknown op"}
slots = [commit[i:i + RECORD] for i in range(0, NOTES, RECORD)]
live = [i for i, r in enumerate(slots) if r[:8] == b"OBRCLM01"]
used = [i for i, r in enumerate(slots) if r != b"\xff" * RECORD]
free = len(slots) - (max(used) + 1 if used else 0)
print("commit block: %d record slots used, %d free%s"
      % (len(used), free, "" if free >= 4 else " (fewer than four: the next boot erases the block)"))
for i in live:
    print("reclaim commit record present in slot %d: the next boot finishes the swap" % i)
notes = []
for i in range(NOTES, BLOCK, NOTE):
    n = commit[i:i + NOTE]
    if n == b"\xff" * NOTE:
        break
    notes.append(n)
print("reclaim notes: %d" % len(notes))
for k, n in enumerate(notes[-8:], len(notes) - len(notes[-8:]) + 1):
    if n[:8] != b"OBRCLMNT":
        print("  %d: not a note (%s)" % (k, n[:8].hex()))
        continue
    code, a, r = struct.unpack("<III", n[8:20])
    print("  %d: %s (code %d, value %d), reclaims of that boot %d" % (k, names.get(code, "?"), code, a, r))
