#!/usr/bin/env python3
# F2: the variable store of a copy of the flash (read only)
import sys, collections, importlib.util
spec=importlib.util.spec_from_file_location("upd","/root/ourobios/tools/update.py"); u=importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
data=open(sys.argv[1],"rb").read(); o,s=u.fmap_areas(data)["SMMSTORE"]; region=data[o:o+s]
vars_,info=u.var_store(region)
st=collections.Counter(u.VAR_STATES.get(v["state"],hex(v["state"])) for v in vars_)
cb=[v for v in vars_ if v["state"] in (0x3f,0x3e) and v["guid"]==u.CB_OPTION_GUID]
print("store %d bytes: used %d, free %d, next record at 0x%x; records %d %s; options %d" % (info["store_size"],info["used"],info["free"],info["next"],len(vars_),dict(st),len(cb)))
