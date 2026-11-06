# v1.6.0 on the M920x: the test record

The tests of [docs/test-v1.6.0.md](../../../test-v1.6.0.md) on the
ThinkCentre M920x of the port (i3-8100, 32 + 8 GB, NVMe, a monitor on HDMI, TPM
2.0 SLB9670, the ME in soft temporary disable from the setup), from
2026-11-03 to 11-05, from the CI build ci-244 to v1.6.0-rc6. What each
candidate carried, what every test gave, the numbers the next
development can start from, and what is still to do. The files next to
this one are the reports and logs of rc6.

## The machine and its state at the end

| | |
|---|---|
| Read-only part | `ouroBIOS-ci-203-045bf06` (26.09-438, measured boot generation 2): written with flashrom on 2026-11-01, never since; a capsule does not touch it |
| Slot A | v1.6.0-rc5 |
| Slot B | v1.6.0-rc6, running, confirmed |
| Protections | *BIOS Lock* and *Firmware protection* on through every update from rc1 on: all of them came in as capsules, written by the payload through SMM |
| Settings | the 35 options saved in SMMSTORE, among them `me_state=1` (soft disable), `clear_dram_on_boot=2` (when the OS asks), `serial_console=1`, `debug_level=7`, `igd_enabled=1`, `bios_lock=1` |
| Event log | 258 events, 99 boots, 2903 of 16384 bytes on 2026-11-05 |

## What went in, candidate by candidate

| Candidate | `next` | What it carried | How it got on the machine |
|---|---|---|---|
| ci-244 | `98e7f1c` | the v1.6.0 candidate of the checklist | `update.py other-slot` with flashrom, *BIOS Lock* off, 2026-11-03 |
| rc1 | `e38daa7` | patch 0223 (first version) | capsule from ci-244, slot A |
| rc2 | `2da0903` | 0223 revised (the PM registers in the bootblock and verstage; Lynx Point keeps the state for `mrc.bin`) | capsule from rc1, slot B |
| rc3 | `0b05bb3` | documents and tools only (MEM-01 known with the ME off, `update.py vboot`) | capsule from rc2, slot A |
| rc4 | `2d05c5c` | patch 0224 (the processor graphics always on, no *Intel graphics* switch) | capsule from rc3, slot B |
| rc5 | `cafc6b2` | `hw-report.py` BOOT-02 net of the ME's wait; the firmware of rc4 | capsule from rc4, slot A |
| rc6 | `65e0068` | patches 0225 (the measurement log at DEBUG), 0226 (*Disabled (HAP bit)* for the ME), 0227 and `edk2/0053` (no UEFI Shell), `edk2/0054-0055` (two SDHCI drivers out), the serial console off by default | capsule from rc5, slot B: the first capsule written by the payload of v1.6.0 itself |

## Results

Run from the machine, without anyone at the monitor. `hw-report.py` of
`next` at `cafc6b2` or later.

| ID | Result | Notes |
|---|---|---|
| BOOT-01 | PASS | the stages `26.09-517`, the version of each candidate; from rc6 the serial line: about 6.1 s of the boot at level 7 (Debug) on COM1 at 115200 baud, 1.4 s at Info, 0.1 s at Notice |
| BOOT-02 | PASS | 10.7 s to the payload with the saved level Debug and the serial on, the memory cleared at the request of the Linux kernel (2.0 s); 15.7 s on the boots where the ME answers late (below), which the report takes out |
| BOOT-03 | PASS | no message unknown to the report after the two known ones of this port were added (HECI hidden at a resume, the DPLL of i915) |
| BOOT-04 | PASS | the i915 DPLL error at about one boot in three: known, not of the firmware ([dpll.md](dpll.md)) |
| BOOT-07 | PASS | reboots from Linux, cold boots from S5 by RTC alarm, resets after a capsule: MEM-01 and BOOT-02 as expected after each |
| BOOT-09 | not observable here | `serial_console=1` is saved from before rc6, so the serial console stays on and the SPCR table is there; the new default shows only without a saved value |
| BOOT-10 | PASS | the first boot of rc6 deleted the *UEFI Shell* entry; `efibootmgr` lists Setup, NVMe, iPXE, CSMWrap, the OS |
| CONF-01 | PASS | WSMT revision 1, flags 7 |
| CONF-02 | PASS | DSDT 0 errors, 17 warnings (all 4089 of the disassembler), 27 remarks (23 of 2173, 4 of 2184); SSDT 0 errors, 5 warnings 4089, remarks 2 of 2184 and 2 of 2063 (*Initializer list shorter than declared package length*: the PIC branch of `_PRT`, and the PEPD constraint of the PCH thermal controller `00:12.0`, which has no ACPI name; patches 0228 and 0229, after rc6) |
| CONF-03 | PASS | `fwts --acpitests --uefitests wsmt mcfg`: 468-469 pass, 0 failed, 5 warnings, no *MCFGMMIONotReserved* ([fwts-m920x-fsp.log](fwts-m920x-fsp.log)); on ci-244 one MEDIUM, the firmware version 0 of a CI build |
| CONF-04 | PASS, `spi_desc` FAILED by design | chipsec 1.13 with the native Linux helper (no kernel driver) on rc6, the logs in [chipsec/](chipsec/): `bios_wp` PASSED (BC `0xAA`, writes restricted to SMM, PR0 over `WP_RO`), `spi_lock` PASSED (HSFS `0x230AF801`, FLOCKDN), `smm` PASSED (SMRAMC `0x1A`, D_LCK), `smrr` PASSED (base `0x76000000`, mask `0xFF800000`, WB, the same on every thread), `bios_ts` PASSED (BILD 1, Top Swap off); `spi_desc` FAILED: the descriptor is writable by the CPU, as the README's known limits say (`UNLOCK_FLASH_REGIONS`, which the HAP bit option needs); `uefi.access_uefispec` PASSED with the chipsec kernel driver (built from the 1.13.16 sources against the headers of the running kernel, loaded by chipsec for the test and unloaded after): every variable checked, PK, KEK, db, dbx and `certdb` time-based authenticated, the rest NV+BS+RT, protected according to the spec |
| CONF-07 | PASS | the ECAM window reserved; the WARN of ci-244 was the report reading `pnp` resources named `PNP0C02:00` by Linux 7.0, fixed in the report |
| MEM-01 | PASS or INFO | 0.22-0.25 s with the cache valid or on a resume; 5.22-5.24 s on the boots and resumes where the ME answers the DRAM Init Done message late (below) |
| MEM-09 | PASS | on ci-244, the steps run by the owner: the lock taken, ordinary writes with it held, the request of the OS not clearable, the clear at the next boot |
| ELOG-01 | PASS | the log continues across every capsule; v1.5.0 lost the last two events of each boot (the lockdown before them), v1.6.0 does not |
| FLASH-01 | PASS | `WP_RO` behind PR0, the registers locked, with both protections on |
| VB-02 | PASS | each candidate confirmed in its slot, the previous one confirmed too |
| OPT-01, OPT-02 | PASS | the 35 options; VT-d off and on from the setup with its effect at every boot (ci-244) |
| TPM-01, TPM-03 | PASS | 11 measurements of coreboot and 3 of vboot, PCR 0-7 replay in both banks |
| TPM-03 after S3 | PASS from rc1 | on ci-244 and v1.5.0 PCR 2 went past the log after a suspend (patch 0223) |
| S3-01, S3-02, S3-03 | PASS | five `rtcwake -m mem -s 25` on each of ci-244, rc1, rc2, rc5, rc6; the network up after each |
| PCI-02 | PASS | the PEG port off without a card on the riser |
| PCI-09 | INFO | BAR 0 of the SPI controller `00:1f.5` outside the payload's aperture, no driver of the payload uses it: by choice |
| UPD-01 | PASS | the ESRT of each candidate, *riuscito*; on a CI build a WARN by design (version 0) |
| UPD-02 | PASS | from ci-244 the capsule of v1.5.0, from v1.5.0 that of rc5 (both written by the payload that ran); from rc5 that of rc6: the payload of v1.6.0 writing a capsule for the first time on a machine |
| UPD-05 | PASS | `update.py rollback` from rc6: the payload took the capsule of rc5, found slot A equal and switched; `stage` of rc6 brought it back |
| UPD-06 | PASS | the capsule of the W541 refused before the reboot |
| ME-01 | PASS | soft temporary disable as asked, HECI hidden; with rc6 `HAP: clear in the flash descriptor, as me_state asks` (the descriptor not written) |
| ME-05 | not run | the HAP bit: the owner's decision, with the copy of the flash off the machine |
| IDLE-01, ID-01 to ID-03, USB-01 to USB-05, NET-01 to NET-04, DISP-01 to DISP-04 | PASS | as the reports say |
| USB-06, DISP-05, NET-05, BOOT-05, BOOT-06, Secure Boot from a USB drive, CSMWrap, WIN-*, CONF-06 | not run | someone at the monitor |

## Numbers

**Boot time** (`cbmem -T`, the report's BOOT-02), rc5 and rc6, the
saved level Debug, the serial console on, the memory cleared:

| Step | rc5 | rc6 |
|---|---|---|
| to romstage (bootblock, verstage) | 0.92 s | 0.89 s |
| romstage, FSP-M inside | 0.63 s, 0.25 s | 0.63 s, 0.25 s |
| postcar and the load of ramstage | 0.13 s | 0.07 s |
| ramstage (2.0 s of memory clear, FSP-S 0.06 s) | 7.99 s | 7.99 s |
| the payload read, measured and decompressed | 0.58 s | 0.52 s |
| the payload loaded to the jump | 0.62 s | 0.62 s |
| total | 10.70 s | 10.71 s |

With the serial console off and the level at Info, the report's estimate
says the boot loses most of the 6.1 s the serial takes at Debug: not
measured here, the saved option keeps the console on.

**The ME's wait.** With `me_state=1` FSP-M waits for the ME's answer to
the DRAM Init Done message, up to 5 s, on some boots and resumes and
not others (patch 0191 explains it): measured as 5.22-5.24 s or
0.22-0.25 s, nothing in between. Over the candidates: warm boots 7 slow
of 11, resumes from S3 12 slow of 20 (rc1 5 of 5, rc2 3 of 5, rc5 2 of
5, rc6 1 of 5, ci-244 0 of the 2 read), cold boots from S5 0 of 1. It
does not follow the slot, the candidate, a capsule just written, the
MOR clear (which coreboot does in ramstage, 2.0 s for 42.7 GB), the
training (no *Memory cache update* in the event log since 10-31), the
options, the PM registers or `HFSTS1` before FSP-M. ME-05 (the HAP bit)
is the setting that removes it.

**S3 and the TPM.** On each resume the TPM keeps its PCRs and the OS log
is the one of the boot. Up to v1.5.0 and on ci-244, romstage measured
`fspm.bin` and the microcode again into PCR 2: TPM-03 FAIL after the
first suspend (PCR 2 SHA-256 `379DF983...` against `FB31F3CE...`
replayed from the 12 events of the log). From rc1 nothing is extended on
the resume path; the bootblock of the read-only part (ci-203, before
patch 0223) still logs the FMAP, itself and romstage into cbmem's log at
each resume, three entries, none extended: `cbmem -L` goes from 14 to 29
entries after five suspends, the OS log stays at its 121 events. FSP-M
on a resume: 0.22 s, or 5.22 s with the ME's wait.

**Capsules.** A capsule writes the slot that does not run in about a
minute, the equal blocks skipped; the ESRT, the settings, the boot
entries, the VPD and the event log stay. From rc1 to rc6 six capsules
and two rollbacks, no retraining (the cache version of patch 0222 at 0).

**The flash.** `WP_RO`, `SI_ALL`, `RW_MRC_CACHE` and the slot not
written are byte for byte the same across the copies taken on 11-03,
11-04 and 11-05; `RW_ELOG`, `RW_NVRAM`, `SMMSTORE` and the slot written
change as expected.

**The DPLL of i915**: [dpll.md](dpll.md).

## Findings and where they went

- TPM-03 after S3: patch 0223, CHANGELOG, docs/vboot.md, the checklists.
- The *Intel graphics* switch: patch 0224, CHANGELOG, docs/m920x.md.
- The 5 s of FSP-M: not a defect of v1.6.0 nor of the capsule (docs/m920x.md
  corrected); MEM-01 and BOOT-02 of the report know it.
- The bootblock in the read-only part: CHANGELOG, docs/vboot.md.
- The elog of v1.5.0 with *BIOS Lock* on and off: CHANGELOG; the report
  knows the messages up to v1.5.0.
- The i915 DPLL: docs/roadmap.md, a known message of the report.
- `hw-report.py`: CONF-07 on Linux 7.0, the known messages by release,
  MEM-01 and BOOT-02 with the ME's wait; `update.py vboot` names a CI
  build and the read-only part; the checklists: the fwts options, PCI-09,
  MEM-01, TPM-03 after S3.

## Still to do on this machine

- *Console* → *Serial Console* off from the setup, a boot, BOOT-01 and
  BOOT-02 again (BOOT-09, and the boot time without the serial).
- The read-only part of v1.6.0 (the bootblock with 0223): with both
  protections off, `flashrom ... -i WP_RO`, the VPD copied first.
- ME-05, the HAP bit, if wanted.
- USB-06, DISP-05, NET-05, BOOT-05, BOOT-06, Secure Boot from a USB
  drive, CSMWrap, the Windows tests, CONF-06.

## Files

- [hw-m920x-fsp-1.md](hw-m920x-fsp-1.md): the report of rc6 at a boot
  from Linux (the third of rc6, after the rollback and back).
- [hw-m920x-fsp-after-s3.txt](hw-m920x-fsp-after-s3.txt): the report of
  rc6 after five suspends, with the copy of the flash (`--dump`).
- [cbmem-m920x-fsp.txt](cbmem-m920x-fsp.txt) and
  [cbmem-t-m920x-fsp.txt](cbmem-t-m920x-fsp.txt): `cbmem -1` and
  `cbmem -T` of that boot, whole.
- [fwts-m920x-fsp.log](fwts-m920x-fsp.log): fwts on rc6.
- [dpll.md](dpll.md): the i915 DPLL measurements.
- [chipsec/](chipsec/): the logs of the seven chipsec modules of CONF-04 on rc6.
- [development.md](development.md): what the machine gives the next
  items of the roadmap (the memory clear on every core, the device
  switches, Hyper-Threading, the firmware watchdog), with
  [devices-m920x-fsp.txt](devices-m920x-fsp.txt), its devices and
  codec pins.
