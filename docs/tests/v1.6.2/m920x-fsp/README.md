# v1.6.2 on the M920x

v1.6.2 (`e952f0f`) on the ThinkCentre M920x of the port, 2026-11-09:
installed as a capsule from v1.6.1 with *BIOS Lock* and *Firmware
protection* on, slot B; v1.6.1 stays in slot A as the fallback. No
release candidate of v1.6.2 ran on this machine before it.

| ID | Result | Notes |
|---|---|---|
| UPD-02 | PASS | the capsule (`update.py stage`, signature valid) written by the payload of v1.6.1; v1.6.2 from slot B, ESRT *v1.6.2 riuscito* |
| VB-02 | PASS | in the copy of the flash: next slot B, current B confirmed, previous A confirmed |
| FLASH-01 | PASS | PR0 over `WP_RO` and PR1 over `SI_ALL`, locked; again after a resume from S3 |
| FLASH-06 | PASS | the option lock armed: `OptionLockStatus` `06 00 00 00` and eight zeros (EFI_SUCCESS) |
| WDT-01 | PASS | off (`firmware_watchdog` Off), also after S3 |
| S3-01 | PASS | `rtcwake -m mem`, the report again after the resume: 22 PASS |
| CONF-02 | PASS | DSDT and SSDT byte for byte those of v1.6.1: 0 errors, no remark 2063 |
| CONF-03 | PASS | fwts `acpitables mcfg wsmt uefirtvariable`: 43 passed, 0 failed |
| BOOT-02, MEM-01 | PASS | 10.62 s from reset to the payload, FspMemoryInit 0.25 s with the training cache kept |

The report of the first boot, 22 PASS:
[v1.6.2/hw-m920x-fsp-1.md](v1.6.2/hw-m920x-fsp-1.md). With the copy of
the flash 25 PASS: ELOG-01 338 events, OPT-01 36 options, TPM-03 11
measurements of coreboot and 3 of vboot. The only kernel error line of
the boot is the known *SGX disabled or unsupported by BIOS*. The
read-only part stays the one of `ci-203`.

What v1.6.2 changes on this board since v1.6.1 is in the payload: of
the EDK II work after rc1, `edk2/0059` (HS400 Enhanced Strobe out of
`SdMmcPciHcDxe`, and the M920x has no SD or eMMC controller) and
`BdsDxe`, relinked by the package work and `edk2/0060` (the same size, the
code differs: measured on the W541 `nri` ROM of the release against
rc1); the other modules of the volume are byte for byte the same. The
boot manager ran here as it did: the capsule, the boot and the resume
above.
