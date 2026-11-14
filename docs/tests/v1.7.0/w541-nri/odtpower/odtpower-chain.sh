#!/bin/bash
# The power of the read ODT window of patch 0310: the same saved training with the trained
# window of each byte, or with the wide one of before (-2/7) written into RW_MRC_CACHE;
# warm reboots (fast boots restore it), RAPL package and DRAM energy at rest and under
# stress-ng --stream. A B A B A.
X=/home/domenico/ourobios-test-v1.6.3/w541-nri/xmp/odtpower; J=/home/domenico/ourobios-test-v1.6.3/w541-nri/STATE.md
ST=$X/chain.step; step=$(cat $ST 2>/dev/null || echo none); sleep 60
note() { echo "- $(date -Is) odtpower chain: $1" >> $J; logger "ourobios-test: odtpower $1"; sync; }
E() { cat /sys/class/powercap/intel-rapl:0/energy_uj /sys/class/powercap/intel-rapl:0:2/energy_uj | tr '\n' ' '; }
win() { python3 - <<'PY'
import mmap,os,struct
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC); m=mmap.mmap(fd,0x8000,mmap.MAP_SHARED,mmap.PROT_READ,offset=0xfed10000)
out=[]
for ch in (0,1):
    for b in range(8):
        v=struct.unpack_from('<I',m,0x60+0x100*ch+0x200*b)[0]; d=(v>>13)&0xf; d=d-16 if d>7 else d
        out.append("%d/%d"%(d,(v>>17)&7))
print(' '.join(out))
PY
}
measure() {  # $1 = label
  local f=$X/$1.txt; { echo "# $1 $(date -Is) $(cat /sys/class/dmi/id/bios_version)"; echo "window: $(win)"; cbmem -1 | grep -cE 'Using cached memory parameters' | sed 's/^/cached: /'; } > $f
  for r in 1 2 3; do
    read -ra a <<< "$(E)"; t0=$(date +%s.%N); sleep 60; read -ra b <<< "$(E)"; t1=$(date +%s.%N)
    echo "rest $r pkg $(echo "(${b[0]}-${a[0]})/($t1-$t0)/1000000" | bc -l | cut -c1-6) dram $(echo "(${b[1]}-${a[1]})/($t1-$t0)/1000000" | bc -l | cut -c1-6)" >> $f
    stress-ng --stream 4 -t 75 > /dev/null 2>&1 & sp=$!; sleep 8
    read -ra a <<< "$(E)"; t0=$(date +%s.%N); sleep 60; read -ra b <<< "$(E)"; t1=$(date +%s.%N); wait $sp
    echo "load $r pkg $(echo "(${b[0]}-${a[0]})/($t1-$t0)/1000000" | bc -l | cut -c1-6) dram $(echo "(${b[1]}-${a[1]})/($t1-$t0)/1000000" | bc -l | cut -c1-6)" >> $f
  done
  chown domenico: $f
}
flashcache() {  # $1 = image
  modprobe -r spi_intel_platform spi_intel spi_intel_pci 2>/dev/null
  flashrom -p internal --fmap -i RW_MRC_CACHE -w $1 > $X/flash-$step.log 2>&1
  grep -q VERIFIED $X/flash-$step.log
}
case $step in
w0) measure w0-trained; flashcache $X/mrc-wide.bin && { echo w1 > $ST; note "w0 measured, wide window in the cache -> reboot"; systemctl reboot; } || note "flash failed, stop" ;;
w1) measure w1-wide; flashcache $X/mrc-trained.bin && { echo w2 > $ST; note "w1 measured, trained window back -> reboot"; systemctl reboot; } || note "flash failed, stop" ;;
w2) measure w2-trained; flashcache $X/mrc-wide.bin && { echo w3 > $ST; note "w2 measured -> wide -> reboot"; systemctl reboot; } || note "flash failed, stop" ;;
w3) measure w3-wide; flashcache $X/mrc-trained.bin && { echo w4 > $ST; note "w3 measured -> trained -> reboot"; systemctl reboot; } || note "flash failed, stop" ;;
w4) measure w4-trained; echo "done" > "$ST"; note "DONE"
    systemctl disable ouro-odtpower-chain.service; rm -f /etc/systemd/system/ouro-odtpower-chain.service; systemctl daemon-reload ;;
esac
