# v1.6.2 on the W541

The ThinkPad W541 of the port (`nri`; the read-only part of this machine
boots only `nri` slots), 2026-11-09: v1.6.2-rc1 as a capsule from v1.6.1,
then the release as a capsule from rc1. What ran for v1.6.1, the
Ethernet switch included, is in
[docs/tests/v1.6.1/w541-nri](../../v1.6.1/w541-nri/README.md).

## v1.6.2-rc1 on the W541: MEM-06, the new coreboot pin

rc1 (`9aee912`, coreboot 26.09-607) as a capsule from v1.6.1, slot B,
2026-11-09. The first boot trains, as the version of the cache follows
the NRI code (0.83 s, *Memory test passed*, `RW_MRC_CACHE` updated).
The round trip ends where v1.6.1 and `mrc.bin` end: C0 44, C1 45, IO
latency 4, `rt_iocomp` 21; the step of patch 0088 still shortens 3 and
2 qclk after the receive enable training (IOLAT 7 and 6), so CB:96893
(the initial delta at 0) did not make it a no-op. `ddr-report --compare`
against the v1.6.1 dump: 408 fields differ, as a new training does
(comp and PI values, receive enable within 2, Vref within 2) plus two
systematic changes from the upstream code: `rx_eq` 0 to 1 on every byte
(the Broadwell support commit sets the Haswell initial RX equalization
to 1) and `read_rf_rank` 3 to 0 (the unified sense amp test); the
per-bit `RX_OFFSET_VDQ` values are repacked by the refactoring, with
patch 0008's fix kept. Dumps: `ht/rc1/`.
Then `stress-ng --vm 4 --vm-bytes 75% --verify` for 30 minutes without an
error or a machine check, and one `rtcwake -m mem -s 30`: resumed, every
CPU back, RAM init 0.11 s on the resume path. The cache across the
slots was shown before: a slot with the same NRI code keeps it (MEM-03
of v1.6.1, in its record), a slot with other code trains once on it (this first
boot of rc1 on the cache of v1.6.1: *needs update*, then *updated*; the
pre-CBMEM romstage log overflowed, so the *version mismatch* line itself
is not in `cbmem`). MEM-06 PASS on rc1.

## The fingerprint switch on rc1 (DEV-W01, patch 0265)

This W541 has no reader, so the switch could only be checked for what it
touches: *Fingerprint reader* off, `USB2PDO` reads `0x00000100` (bit 8
alone), the Bluetooth module (xHCI USB2 port 11) and the camera (12) and
the two EHCI hubs stay, nothing else disappears from `lsusb`; on again,
`0x00000000`, the Bluetooth module and the camera there. The port itself is empty on this unit, as the Lenovo table
says for a unit without the reader; whether the reader of another W541
sits on it is still to see there.

## The release as a capsule from rc1

v1.6.2 (`e952f0f`) as the capsule of the release, staged with
`update.py stage --latest` from rc1 (slot B), 2026-11-09: written to slot
A at the reboot, the ESRT *riuscito* (`fw_version` 0x01060200, status 0,
UPD-01, UPD-02). The payload of the release is not that of rc1 (`BdsDxe`
rebuilt by the package work, `SdMmcPciHcDxe` without HS400 Enhanced
Strobe, `edk2/0059`): the update screen and the boot went as before. The
training cache kept (*does not need update*, RAM init 0.11 s: the NRI
code is that of rc1), hw-report 20 PASS with the known ME and EC
warnings, camera, Bluetooth, Ethernet and the O2 Micro reader all there,
`USB2PDO` 0. One `rtcwake -m mem -s 30`: resumed, every CPU back (S3-01).
Not tried: an SD card seen by the payload (none at hand at the time).
Files: `ht/v162/` on the test machine.
