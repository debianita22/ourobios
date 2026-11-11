#!/usr/bin/env python3
# LOCK-09 helper: writes of the test's own variable through efivarfs
# lock09.py one SIZE        one write of SIZE bytes of data
# lock09.py fill SIZE       writes of SIZE bytes until one fails; bytes counted
# lock09.py delete
import os, sys, subprocess, time
G="5b6f0a3e-7c1d-4e2a-9f10-0d0a6f726f42"; V="/sys/firmware/efi/efivars/OuroBiosLockTest-"+G
def write(size, fill):
    if os.path.exists(V): subprocess.run(["chattr","-i",V],check=True)
    t=time.monotonic()
    try:
        fd=os.open(V, os.O_WRONLY|os.O_CREAT, 0o644)
        try: os.write(fd, b"\x07\x00\x00\x00"+bytes([fill])*size)
        finally: os.close(fd)
    except OSError as e:
        return False, time.monotonic()-t, str(e)
    return True, time.monotonic()-t, ""
cmd=sys.argv[1]
if cmd=="one":
    ok,dt,err=write(int(sys.argv[2]), 0x41); print("write of %s bytes: %s in %.3f s %s" % (sys.argv[2], "ok" if ok else "FAILED", dt, err))
    sys.exit(0 if ok else 1)
if cmd=="fill":
    size=int(sys.argv[2]); n=0
    while True:
        ok,dt,err=write(size, 0x42+(n%20))
        if not ok:
            print("write %d FAILED after %.3f s: %s" % (n+1, dt, err)); break
        n+=1
    print("%d writes of %d bytes went through before one failed: %d bytes of data, %d of records" % (n,size,n*size,n*((60+34+size+3)&~3)))
if cmd=="delete":
    subprocess.run(["chattr","-i",V],check=True); os.unlink(V); print("variable deleted")
