# v1.6.0 on the W541 (nri): the test record

The tests of [docs/test-v1.6.0.md](../../../test-v1.6.0.md) on the
ThinkPad W541 of the port (20EGS24J00, i7-4810MQ, 32 GB of DDR3L-1600 in
four SO-DIMMs, the 3K panel, EC GMHT29WW, TPM 1.2, the ME stopped in the
BUP with `me_disable`), variant `nri`, on 2026-11-05 and 11-06, with
v1.6.0-rc6. Run from the machine by Claude Code, without anyone at the
screen but for the power button; the rows that need someone at the
setup or the boot menu are still to do. The files next to this one are
the reports and logs of rc6.

## The machine and its state

| | |
|---|---|
| Read-only part | `ouroBIOS-ci-205-d123865-nri`, a CI build from before v1.5.0, with patch 0199 (the TPM failure does not stop the boot): only `nri` slots can go behind it, and `update.py other-slot` refuses `mrc` |
| Slot A | v1.6.0-rc6-nri, running, confirmed |
| Slot B | v1.5.0-nri until 11-06; since then the measurement build `ci-265-bd07465` ([diag.md](diag.md)) |
| Protections | *BIOS Lock* on; *Firmware protection* off (FLASH-01 WARN), to be turned on again at the end |
| Settings | the 59 options saved in SMMSTORE, among them `me_disable=1`, `clear_dram_on_boot=2` (when the OS asks), `serial_console=0`, `debug_level=6` |
| Event log | 321 events, 45 boots at the install; continued across the capsule |

## The install

From v1.5.0-nri, *BIOS Lock* on, on 2026-11-05 around 21:20: the rc6
capsule (`.cab` checked against `SHA256SUMS`, its signature and jcat)
staged with `update.py stage`, a reboot, the update screen, then rc6 from
slot A, which trained the memory (a second of black screen). The payload
of v1.5.0 wrote the capsule: the "from v1.5.0" case of UPD-02. The copy of
the flash of rule 1 was read after the install, not before it, and is
kept off the machine.

## Results

| ID | Result | Notes |
|---|---|---|
| BOOT-01 | PASS | `coreboot-26.09-517-geab226a1c3f7-ouroBIOS-v1.6.0-rc6-nri`, postcar and ramstage the same |
| BOOT-02 | PASS | 2.18 s to the payload at the training boot, 1.44-1.53 s from the cache, 3.11 s with the memory cleared at the request of the OS |
| BOOT-03 | PASS | at a boot, the known `fallback/slic`; the `warm_reset_usb3_ports: timed out` of the resumes (below) is in the log of the resume, which the report did not read |
| BOOT-04 | PASS | no firmware warning in the kernel log; `[Firmware Bug]: TSC ADJUST differs` on CPU0 at every resume, as before |
| BOOT-07 | PASS | reboots from Linux, a cold boot after S5, the boot after the capsule |
| BOOT-10 | PASS | at the first boot no *UEFI Shell* entry: Setup, the two SATA entries, CSMWrap, iPXE, USB |
| CONF-01 | PASS | WSMT revision 1, flags 7 |
| CONF-03 | not run | `fwts` is in the AUR only on this system |
| CONF-07 | PASS | the ECAM window reserved |
| MEM-01 | PASS, INFO at the training | 0.83 s at the first boot of rc6, 0.11 s from the cache on every boot and resume after it |
| MEM-02 | PASS | 4 modules, 32 GB, Linux sees 30.8 GB; their SPDs are copies of one another ([development.md](development.md#memory-training-across-updates-on-the-w541)) |
| PCI-09 | PASS | every BAR of bus 0 inside the aperture of the payload |
| TPM-01, TPM-03 | PASS | TPM 1.2 and TCPA; 9 measurements of coreboot and 3 of vboot, PCR 0-7 replay (SHA-1) |
| S3-01 | PASS | three `rtcwake -m mem` on 11-06, back each time (the five of S3-02 with the lid and Fn are still to do) |
| UPD-01, UPD-02 | PASS | v1.6.0-rc6, *riuscito*; settings, VPD and event log kept |
| UPD-06 | PASS | the v1.5.0 capsules of `mrc` and of the M920x refused by `update.py stage` before the reboot |
| VB-01, VB-02 | PASS | slot A, confirmed; at the first boot VB-02 WARN with one try, as for any new slot |
| CPU-05 | PASS | on 2026-11-03 |
| `efibootmgr -t 3` | PASS | `Timeout: 3 seconds` after the reboots |
| ME-01, EC-01 | WARN, known | as in the reports of v1.5.0 |
| FLASH-01 | WARN, known | *Firmware protection* off |
| IDLE-01 | PASS or INFO | PC6 70% with the panel off, PC2 with the 3K panel on (known) |
| OPT-02, MEM-09, UPD-05, USB-06, DISP-05, BOOT-05, BOOT-06, NET-05, S3-02 and S3-03 with the lid and Fn, the dGPU on and off, macOS, Secure Boot with shim, CSMWrap | not run | someone at the setup, the boot menu or the lid; MEM-09 and UPD-05 too |

## Numbers

**Boot time** (`cbmem -t`, from the reset): to romstage 0.45 s (the TPM
60 ms, the slot's hash 0.21 s, the PCR extend 44 ms); romstage 0.17 s
from the cache, 0.90 s with the training; ramstage 0.56 s (the device
init 0.52 s); the payload loaded and decompressed 0.27 s.
Files: [cbmem-t-w541-nri-training.txt](cbmem-t-w541-nri-training.txt),
[cbmem-t-w541-nri-cache.txt](cbmem-t-w541-nri-cache.txt).

**The memory clear** at the request of the OS: 33.8 GB in 1.65 s, 20.5
GB/s, in ramstage; one core in Linux does 24.3 GB/s on this memory and
more cores add nothing ([development.md](development.md#clearing-the-memory-on-every-core)).

**The flash.** `WP_RO`, both slots, `RW_MRC_CACHE` and
`RECOVERY_MRC_CACHE` the same byte for byte between the copy of 11-05
and one of 11-06 after three reboots; `SMMSTORE`, `RW_ELOG` and
`RW_NVRAM` changed, as expected.

## Findings

- **A USB 3.0 drive after a warm reset.** A SanDisk Ultra Flair
  (`0781:5591`) in the lower port on the right (xHCI SS2, port 17; the
  `_PLD` of the tables puts that port on the left, see below) stayed in
  *Polling* with the port reset bit set (`PORTSC 0x2f0`) or in
  *Compliance mode* (`0x340`) in the boots of 11-05 and 11-06 that came
  from a warm reset, and Linux logged `usb4-port2: Cannot enable` about
  every 4 s; a cold boot cleared it. Followed up the same day in
  [diag.md](diag.md): not reproduced across warm resets, resumes, a
  replug or the removal of the controller; a warm reset keeps the drive
  in whatever state it was, and coreboot hands the port to the payload
  without a link at every boot, so romstage is not what left it stuck.
  The `warm_reset_usb3_ports: timed out` of every resume is a 100 ms
  limit shorter than a warm reset with a device on the port: the port
  is in U0 10 ms later.
- **`TSC ADJUST differs` at every resume is not coreboot**: the register
  is 0 at every point of the resume path up to the jump to the wake
  vector, and Linux finds the TSC of before the suspend written back
  after it ([diag.md](diag.md#tsc-adjust-not-coreboot)).
- **The USB ports are described on the wrong side**: of the four
  connectors, three are on another panel than the `_UPC`/`_PLD` of
  patch 0071, taken from the OEM tables, say
  ([diag.md](diag.md#the-usb-ports-are-described-on-the-wrong-side)).
- **The SPDs of the four SO-DIMMs are identical, serial number
  included**, and the part number is that of a 4 GB module: the docs
  of the memory training across updates must not promise a retraining
  when a module is swapped ([development.md](development.md#memory-training-across-updates-on-the-w541)).
- **Hyper-Threading through `SOFT_RESET_DATA` works on Haswell**, and
  survives S3 and warm resets, not S5; NRI would retrain at every cold
  boot with the reset unless it knows its own reset
  ([development.md](development.md#hyper-threading-on-the-w541)).

## Still to do on this machine

- The rows of the table marked *not run*, with someone at the screen.
- CONF-03 with `fwts`.
- The USB 3.0 drive: another USB 3.0 device in the lower right port
  across a reboot (none was at hand).
- At the end *Firmware protection* on, and `hw-report.py` with
  FLASH-01 PASS.

## Files

- [hw-w541-nri-boot1-training.md](hw-w541-nri-boot1-training.md): the
  report of the first boot of rc6, with the training.
- [hw-w541-nri-cold.md](hw-w541-nri-cold.md): the report after a cold
  boot from S5.
- [cbmem-w541-nri.txt](cbmem-w541-nri.txt): `cbmem -1` of that cold
  boot, whole.
- [cbmem-t-w541-nri-training.txt](cbmem-t-w541-nri-training.txt),
  [cbmem-t-w541-nri-cache.txt](cbmem-t-w541-nri-cache.txt): `cbmem -t`
  with the training and from the cache.
- [development.md](development.md): what the machine gives the next
  items of the roadmap, with [devices-w541-nri.txt](devices-w541-nri.txt)
  (the devices, the PCH registers, the codec pins, the SPDs, the FMAP),
  [ht-w541-nri.txt](ht-w541-nri.txt) (each step of the Hyper-Threading
  test and the scripts that ran it) and [memclr.c](memclr.c).
- [diag.md](diag.md): the troubleshooting of `TSC ADJUST` and of the USB
  3.0 drive, with the measurement build, and the map of the USB ports,
  with [diag-tsc-linux.txt](diag-tsc-linux.txt),
  [diag-usb-linux.txt](diag-usb-linux.txt) and
  [diag-build-w541-nri.txt](diag-build-w541-nri.txt).
