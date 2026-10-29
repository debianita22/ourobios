# Blobs of the ThinkCentre M920x Tiny

The first 12 MiB of the coreboot image that ran on this M920x (machine type
10S2) before this project, read from its flash: the release images carry
them unchanged ([docs/m920x.md](../../../docs/m920x.md)). `SHA256SUMS` pins
them: `tools/build.sh` and `tools/ci-check.sh` stop if a file changes.
They are proprietary (Intel, Lenovo), not covered by the GPL of the rest of
the repository.

| File | Size | What | In the release images |
|---|---|---|---|
| `ifd.bin` | 4 KiB | Intel flash descriptor (CNP-H): GbE `0x1000-0x2FFF`, ME `0x3000-0xBFFFFF`, BIOS `0xC00000-0x17FFFFF`, the same bounds as the Lenovo descriptor of the machine; every master reads and writes every region | yes, unchanged |
| `gbe.bin` | 8 KiB | GbE configuration of the I219-LM, MAC address `00:2b:67:0b:91:73` | yes, unchanged, at `0x1000` |
| `me.bin` | 7664 KiB | Intel CSME 12.0.35.1427 (PMC 300.2.11.1024), complete; the rest of the 12276 KiB ME region is empty (`0xFF`) | yes, at `0x3000` |

The build pads the ME region with `0xFF`, and the first 12 MiB of every
image are then byte-identical to those of the image the blobs come from:
`boards/m920x/intel.sha256` has their SHA-256, which `tools/verify-rom.sh`
checks on every build. The Lenovo firmware dump of the same machine has
CSME 12.0.6.1120 and a locked descriptor with the same region bounds.

Another M920x has its own descriptor, GbE (MAC address) and ME state: an
update with `flashrom --ifd -i bios` leaves them alone, and
[docs/m920x.md](../../../docs/m920x.md#recovery) shows how to build the chip images from
your own backup for an external programmer.
