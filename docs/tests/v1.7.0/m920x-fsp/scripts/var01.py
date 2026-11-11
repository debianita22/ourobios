#!/usr/bin/env python3
# LOCK-02 / VAR-01: twenty writes of Timeout, MSR_SMI_COUNT around each
import os, struct, subprocess, time, statistics
def smi():
    fd=os.open("/dev/cpu/0/msr",os.O_RDONLY); v=struct.unpack("<Q",os.pread(fd,8,0x34))[0]; os.close(fd); return v
subprocess.run(["modprobe","msr"])
ts=[]; ss=[]
for i in range(20):
    v="4" if i%2==0 else "3"
    a=smi(); t=time.monotonic(); r=subprocess.run(["efibootmgr","-q","-t",v]); ts.append(time.monotonic()-t); ss.append(smi()-a)
    assert r.returncode==0, "write %d failed" % i
print("median %.3f s, worst %.3f s, best %.3f s; SMI per write %s, total SMI %d" % (statistics.median(ts),max(ts),min(ts),sorted(set(ss)),sum(ss)))
print("ms per SMI: %.1f" % (1000*sum(ts)/sum(ss)))
print([l for l in subprocess.run(["efibootmgr"],capture_output=True,text=True).stdout.splitlines() if l.startswith("Timeout")][0])
