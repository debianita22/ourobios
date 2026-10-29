# Blobs of the ThinkCentre M920x Tiny

The first 12 MiB of the Lenovo firmware of the M920x the port was made on
(machine type 10S2), read from its two chips with an external programmer,
with the descriptor unlocked: the release images carry them unchanged
([docs/m920x.md](../../../docs/m920x.md)). `SHA256SUMS` pins them:
`tools/build.sh` and `tools/ci-check.sh` stop if a file changes. They are
proprietary (Intel, Lenovo), not covered by the GPL of the rest of the
repository.

| File | Size | What | In the release images |
|---|---|---|---|
| `ifd.bin` | 4 KiB | Intel flash descriptor (CNP-H) of the Lenovo firmware, unlocked with `ifdtool -p cnl -u`: every master reads and writes every region; Lenovo's bounds, GbE `0x1000-0x2FFF`, ME `0x3000-0xBFFFFF`, BIOS `0xC00000-0x17FFFFF` | yes, unchanged |
| `gbe.bin` | 8 KiB | GbE configuration of the I219-LM, MAC address `e8:6a:64:cd:fd:06` | yes, unchanged, at `0x1000` |
| `me.bin` | 7664 KiB | Intel CSME 12.0.6.1120 (PMC 300.2.11.1015), complete, with the CSME's data as the Lenovo firmware left them; the rest of the 12276 KiB ME region is empty (`0xFF`) | yes, at `0x3000` |

The build pads the ME region with `0xFF`, and the first 12 MiB of every
image are then byte-identical to those of the Lenovo dump with its
descriptor unlocked: `boards/m920x/intel.sha256` has their SHA-256, which
`tools/verify-rom.sh` checks on every build. On that machine the flash
still has the same descriptor, GbE and CSME firmware; the CSME's data have
changed since, as the CSME writes them at runtime.

They come from the two chips like this (`ifdtool` of coreboot):

```sh
cat bios1.rom bios2.rom > lenovo.rom                       # 16 + 8 MiB
util/ifdtool/ifdtool -p cnl -u lenovo.rom                  # -> lenovo.rom.new
head -c 4096 lenovo.rom.new > ifd.bin
dd if=lenovo.rom bs=4096 skip=1 count=2 of=gbe.bin
# me.bin: 0x3000-0xBFFFFF without the trailing 0xFF, to a 4 KiB boundary
python3 -c 'd = open("lenovo.rom", "rb").read()[0x3000:0xC00000].rstrip(b"\xff"); open("me.bin", "wb").write(d + b"\xff" * (-len(d) % 4096))'
```

Another M920x has its own descriptor, GbE (MAC address) and ME state: an
update with `flashrom --ifd -i bios` leaves them alone, and
[docs/m920x.md](../../../docs/m920x.md#recovery) shows how to build the chip images from
your own backup for an external programmer.
