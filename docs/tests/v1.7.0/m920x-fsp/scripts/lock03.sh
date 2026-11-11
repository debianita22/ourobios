#!/bin/sh
# LOCK-03: a boot entry created and deleted; a variable of the test's own GUID
# created, changed and deleted through efivarfs
set -e
G=5b6f0a3e-7c1d-4e2a-9f10-0d0a6f726f42
V=/sys/firmware/efi/efivars/OuroBiosLockTest-$G
before=$(efibootmgr | grep -E "^Boot[0-9A-F]{4}|BootOrder" | sort | sha256sum)
efibootmgr -q -c -d /dev/nvme0n1 -p 2 -L "LOCK-03 test" -l '\EFI\lock03.efi'
n=$(efibootmgr | grep "LOCK-03 test" | sed 's/^Boot\([0-9A-F]*\).*/\1/')
echo "entry created: Boot$n"
efibootmgr -q -b "$n" -B
after=$(efibootmgr | grep -E "^Boot[0-9A-F]{4}|BootOrder" | sort | sha256sum)
[ "$before" = "$after" ] && echo "entries as before" || { echo "ENTRIES CHANGED"; exit 1; }
printf '\007\000\000\000one' > $V && echo "variable created: $(od -An -c $V | tr -s ' ')"
chattr -i $V; printf '\007\000\000\000two!' > $V && echo "variable changed: $(od -An -c $V | tr -s ' ')"
chattr -i $V; rm $V && echo "variable deleted"
