#!/usr/bin/env python3
# F2: the variable store of a copy of the flash (read only)
import sys, collections, importlib.util, struct
spec=importlib.util.spec_from_file_location("upd","/root/ourobios/tools/update.py"); u=importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
data=open(sys.argv[1],"rb").read(); o,s=u.fmap_areas(data)["SMMSTORE"]; region=data[o:o+s]
vars_,info=u.var_store(region)
st=collections.Counter(u.VAR_STATES.get(v["state"],hex(v["state"])) for v in vars_)
cb=[v for v in vars_ if v["state"] in (0x3f,0x3e) and v["guid"]==u.CB_OPTION_GUID]
print("store %d bytes: used %d, free %d, next record at 0x%x; records %d %s; options %d" % (info["store_size"],info["used"],info["free"],info["next"],len(vars_),dict(st),len(cb)))
# The note of the reclaim in SMM (patch 0288): why the handler refused, in the last block
note = region[s - 0x10000 + 0x800:s - 0x10000 + 0x800 + 20]
if note[:8] == b"OBRCLMNT":
    code, a, n = struct.unpack("<III", note[8:20])
    names = {1: "store not walkable", 2: "more than a quarter free", 3: "reclaims of the boot used",
             4: "other headers", 5: "image not walkable", 6: "image clears the MOR request",
             7: "image with other options", 8: "commit record not written", 9: "copy failed", 10: "unknown op"}
    print("reclaim note: %s (code %d, value %d), reclaims of that boot %d" % (names.get(code, "?"), code, a, n))
if region[s - 0x10000:s - 0x10000 + 8] == b"OBRCLM01":
    print("reclaim commit record present: the next boot finishes the swap")
