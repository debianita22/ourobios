# v1.6.1-rc1 on the M920x

The pre-release v1.6.1-rc1 (branch `ci-test/v1.6.1-optlock`, `f9eb022`)
on the ThinkCentre M920x of the port, 2026-11-07: installed as a capsule
from v1.6.0 with *BIOS Lock* and *Firmware protection* on, slot A; v1.6.0
stays in slot B.

| ID | Result | Notes |
|---|---|---|
| UPD-02 | PASS | the capsule written by the payload of v1.6.0, rc1 from slot A, ESRT *v1.6.1-rc1 riuscito* |
| FLASH-01, FLASH-05 | PASS | patch 0235: coreboot logs `FPR 1 is enabled for range 0x00000000-0x00bfffff` and *Enabled bootmedia protection for SI_ALL*; `update.py protection` shows PR0 over `WP_RO` and PR1 `0x8bff0000` over `SI_ALL` (the descriptor, the GbE and the ME), both locked by FLOCKDN, and again after three resumes from S3 ([protection-rc1.txt](protection-rc1.txt)); the descriptor's FRACC still grants the CPU writes, the PR refuses them. No write was tried |
| FLASH-06 | regressions PASS, the arm not observable | `SMMSTORE_OPTION_LOCK=y` in the build. The expected `Option lock: armed` line never reaches `cbmem -1`: the M920x builds have `DEBUG_SMI` off, which compiles every `printk` of SMM out (`src/console/Makefile.mk`, `console.h`), so the check of the row and of `hw-report.py` cannot see it; the payload's own `DEBUG` lines (*security options write-locked: %r*) are not in a release build either. The regressions: variable writes from the OS after the arm go through (`efibootmgr -t 4`, then `-t 3`), three resumes from S3 with the protected ranges back, TPM-03 PASS. The coreboot options (`bios_lock`, `bootmedia_lock`) are not visible in efivarfs (only `me_state_counter` is), so the positive proof stays the raw SMMSTORE write of the row |
| S3-01 | PASS | three `rtcwake -m mem` |
| TPM-03 | PASS | |
| MEM-01, BOOT-02 | INFO, PASS | the boot after the capsule paid the ME's 5 s wait: 15.68 s, 10.44 s without it |

The report of the first boot: [hw-m920x-fsp-rc1.txt](hw-m920x-fsp-rc1.txt).

Done for rc2: the payload writes what coreboot answered to the arm into
the volatile variable `OptionLockStatus` (edk2 0057, read-only to the OS
by a lock-on-create Variable Policy registered before EndOfDxe), which
`hw-report.py` reads. The options considered were: a status command of the option lock
in SMMSTORE that `hw-report.py` can query from the OS, the arm's result
left in CBMEM by ramstage-visible memory (a word in the SMMSTORE com
buffer or a CBMEM entry the SMI handler writes), or `DEBUG_SMI` on in a
test build.

## v1.6.1-rc2

rc2 (`c7eda40`, with edk2 0057) as a capsule from rc1, slot B,
2026-11-07, both protections on. FLASH-06 is now observable:
`OptionLockStatus` is in efivarfs, 12 bytes `06 00 00 00` (BS+RT, volatile)
then eight zeros, EFI_SUCCESS: the option lock armed; efivarfs marks it
immutable as for any variable, and `hw-report.py` FLASH-01 says
*option lock: armato*. The variable keeps its value across two resumes
from S3, variable writes from the OS still go through (`efibootmgr -t`),
and PR0 and PR1 are set again after the resumes. Report: 21 PASS, 2 INFO,
1 SKIP.

### rc2, the checklist round (2026-11-07 and 08)

| ID | Result | Notes |
|---|---|---|
| reports | PASS | a reboot ([rc2/hw-m920x-fsp-1.md](rc2/hw-m920x-fsp-1.md)) and a cold boot from S5 ([rc2/hw-m920x-fsp-2.md](rc2/hw-m920x-fsp-2.md): 10.67 s, FSP-M 0.25 s): 21 PASS, 2 INFO, 1 SKIP; with the copy of the flash 23 PASS, the event log 297 events, VB-02 slot B confirmed and A confirmed, OPT-01 35 options |
| CONF-02 | PASS | DSDT and SSDT 0 errors, no remark 2063 |
| CONF-03 | PASS | fwts: 465 pass, 0 failed, 5 warnings ([rc2/fwts-m920x-fsp.log](rc2/fwts-m920x-fsp.log)) |
| CONF-04 | PASS, `spi_desc` FAILED by design | the six modules PASSED with the kernel driver for `access_uefispec`; `spi_desc` reads FRAP, the write is refused by PR1 ([rc2/chipsec/](rc2/chipsec/)) |
| UPD-05 | PASS | `update.py rollback` from rc2: slot A already rc1, the payload of rc2 only switched slots; rc1 booted, without `OptionLockStatus` (it comes with 0057); the capsule of rc2 staged again brought rc2 back from B, the lock armed ([rc2/upd-05.txt](rc2/upd-05.txt)) |
| FLASH-06 | PASS | `OptionLockStatus` armed at every boot of rc2, cold or warm, and kept across resumes |

`hw-report.py` changed from this round: ME-01 falls back on the OEM
strings of SMBIOS after a resume from S3, when the CBMEM console has
started again without the `ME:` lines (INFO instead of SKIP), and
FLASH-01 turns WARN when the payload reports the option lock not armed
while the protections are on.
