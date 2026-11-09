# v1.6.3-rc1 on the W541

The ThinkPad W541 of the port (`nri`; the read-only part, `ci-205`, boots
only `nri` slots), 2026-11-09, run by an agent on the machine with
nobody there, as [docs/test-v1.6.3-w541.md](../../../test-v1.6.3-w541.md)
asks. Part 1 on v1.6.2 (slot A; v1.6.2-rc1 in slot B), then the capsule
of v1.6.3-rc1 (run 42696841540, patches 0266-0269) from v1.6.2 with
*BIOS Lock* and *Firmware protection* on: written to slot B, v1.6.2 stays
in slot A. A copy of the flash from before the run is on the M920x of the
port.

## Part 1: v1.6.2 as it runs

| ID | Result | Notes |
|---|---|---|
| baseline | PASS but IDLE-01 | [hw report](hw-w541-nri-v1.6.2-1.md) with the copy of the flash: 23 PASS, ME-01 and EC-01 WARN (known), VB-02 WARN (a bug of `hw-report.py`, below), IDLE-01 FAIL (below); `cbmem -l`: `COREBOOT` 0x8000 bytes, *coreboot table: 29528 bytes* (0x7340, 90% of the entry), *CFR: Written* in the [log](cbmem-v1.6.2.txt) |
| CMOS-01 | INFO | byte 0x7e `0x00`, byte 0x7f `0x00`, three reads each |
| FLASH-01 | PASS | PR0 over `WP_RO`, PR1 over `SI_ALL`, FLOCKDN; again after the five resumes |
| FLASH-06 | PASS | `OptionLockStatus` `06 00 00 00` and eight zeros |
| VAR-01 | PASS | twenty writes of `Timeout` (4 and 3 in turn), all done: median 0.272 s, worst 0.273 s, best 0.271 s; back at 3 s ([numbers](var01-v1.6.2.txt)) |
| S3-02 | PASS | five `rtcwake -m mem -s 30`, 20 s apart: `fail` 0, `success` 1 to 6, CPUs 0-7, the Ethernet and the camera there; [hw report after](hw-w541-nri-v1.6.2-after-s3.md): FLASH-01 and TPM-03 PASS |
| PCI-05 | not run, needs the owner | the NVIDIA GPU is off in the setup: `00:01.0` is not on the bus (as in every record of this machine); `peg-report.py` then takes `01:00.0`, the SD reader, for the GPU |
| CONF-02 | PASS | 0 errors, no 3115; DSDT 15 remarks (10 × 2173, 3 × 2184, 2 × 2146: `Arg0` of `MLCG` and `WAKE` never used, not in the list of docs/testing.md), 48 × 4089; SSDT 8 × 3168 (`Processor()`, *ACPI processor objects* on), 1 × 2184, 12 × 4089 ([dsdt](iasl-dsdt-v1.6.2.log), [ssdt](iasl-ssdt-v1.6.2.log)) |
| CONF-03 | PASS | no CRITICAL or HIGH; 703 passed, the 4 MEDIUM of the rc7 record of v1.6.0 (`MethodCIDInvalidString` for `PNLF` and `ALS0`, `HPETVendorId`, `HPETClockPeriod`); `efi_test` built for the running kernel, loaded and removed ([log](fwts-v1.6.2.log)) |
| CONF-04 | PASS | `bios_wp`, `spi_lock`, `smm`, `smrr`, `bios_ts`, `uefi.access_uefispec` PASSED (the last with the kernel driver), `spi_desc` FAILED by design ([logs](chipsec-v1.6.2/)) |
| IDLE-01 | FAIL | the screen off: PC2 89%, PC6 0%, 9.1 W, where v1.6.1-rc4 had PC6 78.8% after a resume. The SD reader, after any resume from S3: below |
| NET-02 | not run, needs the owner | no cable on the Ethernet port (`eno0` without carrier); the M920x, which has `wakeonlan`, was reachable as the sender |

## Part 2: v1.6.3-rc1

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) staged on v1.6.2 and written by its payload; rc1 from slot B, *v1.6.3-rc1, riuscito* |
| reports | PASS but the known ones | the [first boot](hw-w541-nri-rc1-1.md) with the copy of the flash and [after a reboot](hw-w541-nri-rc1-reboot.md) with a new one: 22 PASS each, BOOT-01 `v1.6.3-rc1-nri`, ELOG-01 269 events, ME-01 and EC-01 WARN, VB-02 WARN (the bug below); IDLE-01 INFO (the greeter's panel on); PCI-01 WARN at the first boot only, left by a PCI rescan of the SD test |
| MEM-03 | PASS | *Using cached memory parameters*, *'RW_MRC_CACHE' does not need update*, RAM init 0.11 s |
| TBL-01 | PASS | `COREBOOT` 0x10000 bytes; *coreboot table: 29536 bytes* (8 more than v1.6.2: the version string), *CFR: Written 28152 bytes*, no *didn't fit*; `cbmem` reads it, the kernel's coreboot bus lists the CBMEM entries; OPT-01 the same 67 options with the same values ([log](cbmem-rc1-1.txt)) |
| CONF-02 | PASS | APIC, DMAR, DSDT, FACS, HPET, MCFG, TCPA, WSMT the same byte for byte; BGRT (image address), FACP (FACS and DSDT addresses) and the SSDT differ in addresses only, and the SSDT's range of the coreboot table is 0x10000 long instead of 0x8000 (patch 0269); the warnings and remarks as in part 1 |
| FLASH-01, FLASH-06 | PASS | as in part 1, at each boot and after the resumes |
| VAR-01 | PASS | median 0.269 s, worst 0.270 s ([numbers](var01-rc1.txt)): the numbers of part 1 |
| S3-02 | PASS | three `rtcwake -m mem -s 30`: `fail` 0, `success` 0 to 3, CPUs 0-7 |
| WDT-03 | PASS, the last step not run | byte 0x7e `0xa0` at the first boot (it held `0x00`: SMM wrote the mark at the first confirmed boot), after the resumes and at each of the next five boots; `0x55` written, a reboot: `0xa0`; `0xa3` written with *Firmware watchdog* Off, a reboot: no *resets in a row* line, `0xa0`; the clock right after each write (system, RTC and network time the same second). The step with the watchdog at 5 minutes needs the owner's setup visit (WDT-01) ([log](wdt03.log)) |
| WDT-01 | not run, needs the owner | the setup visit; the watchdog Off throughout: *Firmware watchdog: off*, OC_WDT_CTL `0x00002000` at every boot |
| VB-01, VB-02 | PASS | rc1 in slot B, confirmed; v1.6.2 in slot A, confirmed |
| WDT-02 | to come | after this first push |

## The SD reader after a resume

With the screen off the package stays in PC2 at about 9 W after any resume
from S3, on v1.6.2 and on rc1; after a fresh boot it reaches PC7 89% at
1.0 W. One resume is enough. The O2 Micro OZ777 (`01:00.0`, behind root
port 1) is what holds it:

| State, the screen off | Package | Power |
|---|---|---|
| rc1, a fresh boot | PC7 89.0% | 1.04 W |
| rc1, after one resume | PC2 91.8%, PC6+ 0 | 9.20 W |
| the same, the reader removed from PCI | PC7 85.0% | 1.41 W |
| the same, the driver unbound | PC7 86.6% | 1.26 W |
| the reader back (rescan, or the driver bound again) | PC7 55-89% | 1-5 W, settling |

The config space of the reader (4 KiB) is the same byte for byte at boot,
after a resume and after a rescan; its SDHCI registers too, but the
buffer data port. v1.6.1-rc4 on the same kernel reached PC6 78.8% after
a resume (`ht/rc4-s3`, 2026-11-09 15:37), so this came with v1.6.2: the
new coreboot pin, or the payload. Not bisected; files in
[sd-idle/](sd-idle/). The panel on keeps the package in PC2 or PC3 in
any case (known), so a user sees it only with the screen off or the lid
closed.

## A bug of hw-report.py

VB-02 says *CBET4000 ouroBIOS-v1.6.3-rc1-nri non e' in nessuno slot
della copia* at every boot: it looks for the running version with
`b.endswith(fw.bios)`, where the SMBIOS version (`CBET4000 ouroBIOS-...`)
is the longer string and the slot's build name the shorter; the test
wants the other way round. The vboot state itself is right.

## Not run here

The `mrc` variant (the read-only part starts only `nri` slots) and
Windows (none installed). The owner's rows of part 3: macOS, S3 with the
lid and Fn, DISP-03, NET-02 in its settings, WDT-01, VAR-01 with *BIOS
Lock* off, Secure Boot with shim, CSMWrap, NET-05, BOOT-05/06, OPT-02,
MEM-09, USB-06, DISP-05, DEV-W01 on a unit with the reader, OPT-05 with
the coin cell out.
