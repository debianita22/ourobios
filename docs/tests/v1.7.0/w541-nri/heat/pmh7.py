#!/usr/bin/env python3
# PMH7 of the Lenovo EC (ports 0x15ec/0x15ed/0x15ee): pmh7.py REG [VALUE]; 'dgpu on|off' as pmh7_dgpu_power_enable()
import os, sys, time
fd = os.open("/dev/port", os.O_RDWR)
def rd(r):
    os.pwrite(fd, bytes([r & 0xff]), 0x15ec); os.pwrite(fd, bytes([r >> 8]), 0x15ed); return os.pread(fd, 1, 0x15ee)[0]
def wr(r, v):
    os.pwrite(fd, bytes([r & 0xff]), 0x15ec); os.pwrite(fd, bytes([r >> 8]), 0x15ed); os.pwrite(fd, bytes([v]), 0x15ee)
if sys.argv[1] == "dgpu":
    if sys.argv[2] == "on":
        wr(0x50, rd(0x50) & ~0x80); wr(0x50, rd(0x50) | 0x08); time.sleep(0.1); wr(0x50, rd(0x50) | 0x80); time.sleep(0.1)
    else:
        wr(0x50, rd(0x50) & ~0x80); time.sleep(0.001); wr(0x50, rd(0x50) & ~0x08)
    print("PMH7 0x50 = 0x%02x" % rd(0x50)); sys.exit(0)
r = int(sys.argv[1], 0)
if len(sys.argv) > 2: wr(r, int(sys.argv[2], 0))
print("PMH7 0x%02x = 0x%02x" % (r, rd(r)))
