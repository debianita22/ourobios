# v1.6.3-rc1 on the M920x

The run of [docs/test-v1.6.3-m920x.md](../../../test-v1.6.3-m920x.md) on
the ThinkCentre M920x of the port, 2026-11-09, by an agent on the
machine (Proxmox, root, lockdown `[none]`). At the start: v1.6.2 in
slot B, v1.6.1 in slot A, the read-only part of `ci-203`, *BIOS Lock*
and *Firmware protection* on. The guests: VM 101 stopped, no
containers, so none to shut down or start again. The copy of the flash
of the start is kept on the machine only: no other place was
reachable, and the image holds the VPD and the MSDM key.

## Part 1: v1.6.2 as it runs

The baseline is from a normal boot (the boot before was a resume from
S3, whose log has no coreboot table line).

| ID | Result | Notes |
|---|---|---|
| — | PASS | report 25 PASS with the copy of the flash ([part1/hw-1.md](part1/hw-1.md)); the `COREBOOT` entry of `cbmem -l` 0x8000 bytes, *coreboot table: 18352 bytes*, *CFR: Written 16708 bytes*; 10.45 s to the payload, FspMemoryInit 0.23 s; `update.py vboot`: next B, current B confirmed, previous A confirmed. OPT-01, 36 options: `acpi_cpu_objects=0, bios_lock=1, boot_menu_prompt=1, bootmedia_lock=1, cfg_lock=1, clear_dram_on_boot=2, csmwrap_boot=1, debug_level=7, eist=1, firmware_watchdog=0, front_usb=1, hyper_threading=1, ice_mode=0, igd_aperture_size=2, igd_dvmt_prealloc=4, igd_enabled=1, ipxe_boot=1, legacy_8254_timer=0, me_state=1, me_state_counter=0, onboard_audio=1, onboard_ethernet=1, onboard_wlan=1, option_roms=2, peg_slot=0, pkg_power_limit_lock=0, power_on_after_fail=1, rear_usb=1, serial_console=1, tcc_offset=0, tdp_pl1_override=0, tdp_pl2_override=65, turbo_mode=1, usb_boot=1, vtd=1, wake_on_lan=1` |
| CMOS-01 | INFO | byte 0x7e reads `0x00` (three reads, chrony stopped around them) |
| FLASH-06 | PASS | `06 00 00 00` and eight zeros |
| VAR-01 | INFO | twenty writes of `Timeout` (`efibootmgr -q -t 4`/`-t 3`): median 0.533 s, worst 0.541 s, best 0.531 s; `efibootmgr -q` without a write takes 0.002 s, so the time is the write. Above the 0.5 s of the row ([part1/var-01-1.txt](part1/var-01-1.txt)); `Timeout` back at 3 s |
| OPT-06 | to run | last of all (the order of the run). The address is confirmed: `cbmem -1` *GEN_PMCON: d8a01608 00002200*, `./mm r 0xfe001024` `0x00062210`, the difference only the lock bits 4, 17 and 18; bit 2 clear |
| WDT-02 | to run | after this first push |
| NET-02 | not asked | no request from the W541 or the owner so far |

## Part 2: the candidate

v1.6.3-rc1 (run 42696841540, the pre-release `v1.6.3-rc1-m920x-fsp`)
as a capsule from v1.6.2 with both protections on (UPD-02): the
signature valid, rc1 from slot A at the next boot, *ultimo: v1.6.3-rc1,
riuscito*.

| ID | Result | Notes |
|---|---|---|
| UPD-02, UPD-01 | PASS | the capsule written by the payload of v1.6.2 into slot A |
| — | PASS | report at the first boot 22 PASS ([rc1/hw-rc1-1.md](rc1/hw-rc1-1.md)), BOOT-01 `ouroBIOS-v1.6.3-rc1-m920x-fsp`; after a reboot, with a new copy of the flash, 25 PASS ([rc1/hw-rc1-2.md](rc1/hw-rc1-2.md)) |
| MEM-03, BOOT-02 | PASS | *MRC: 'RW_MRC_CACHE' does not need update*, FspMemoryInit 0.25 s; 10.59 s to the payload |
| TBL-01 | PASS | the `COREBOOT` entry 0x10000 bytes; *coreboot table: 18360 bytes* (8 more than v1.6.2: the version strings), *CFR: Written 16712 bytes*, no *didn't fit*; `cbmem` and the kernel read the table; OPT-01 the same 36 options with the same values |
| CONF-02 | PASS | against part 1: the DSDT and nine other tables the same byte for byte; the FADT differs in the FACS and DSDT addresses only, the SSDT in the CBMEM range (base 0x75ADE000 → 0x75AD6000, length 0x8000 → 0x10000, the larger coreboot table) and the address of `PPOP`. DSDT and SSDT 0 errors, no remark 2063 |
| CONF-03 | PASS | fwts `acpitables mcfg wsmt uefirtvariable`: 43 passed, 0 failed, no CRITICAL or HIGH ([rc1/fwts-rc1.log](rc1/fwts-rc1.log)) |
| CONF-04 | PASS | chipsec 1.13.16 with its driver: `bios_wp`, `spi_lock`, `smm`, `smrr`, `bios_ts`, `uefi.access_uefispec` PASSED, `spi_desc` FAILED by design ([rc1/chipsec](rc1/chipsec)) |
| FLASH-01, FLASH-06 | PASS | PR0 over `WP_RO`, PR1 over `SI_ALL`, locked, also after the resumes; the option lock armed |
| VAR-01 | INFO | median 0.517 s, worst 0.522 s ([rc1/var-01-rc1.txt](rc1/var-01-rc1.txt)): the numbers of part 1, a little lower |
| S3-01 | PASS | three `rtcwake -m mem -s 30`: three resumes, `suspend_stats/fail` 0; FLASH-01, TPM-03 and WDT-01 PASS after ([rc1/hw-rc1-s3.md](rc1/hw-rc1-s3.md)) |
| WDT-03 | PASS (the agent's steps) | `0xa0` at the first boot of rc1 (the byte held `0x00`, CMOS-01), after each of the next five boots and after each of the three resumes; `0x55` written, after a reboot `0xa0`; `0xa3` written, after a reboot with *Firmware watchdog* Off no *resets in a row* line and `0xa0`. The RTC right after each write (`timedatectl`, chrony 0.000001 s from NTP). The step with the watchdog at 5 minutes needs the owner's visit of WDT-01 ([rc1/wdt-03.txt](rc1/wdt-03.txt)) |
| VB-01, VB-02 | PASS | rc1 in slot A, current A confirmed; v1.6.2 in slot B ([rc1/vboot-rc1.txt](rc1/vboot-rc1.txt)) |
| WDT-02 | to run | after this push |
| WDT-01 | not run, needs the owner | the setup menu |

Every boot of rc1 logs *Firmware watchdog: off (OC_WDT_CTL 0x00002000)*
in romstage and *at the payload, OC_WDT_CTL 0x00002000*, and the
register reads `0x00002000` at the OS.

The event log of the copy after rc1 has 262 events against 338 at the
start: coreboot shrank it on 2026-11-09 at 20:58 UTC, on v1.6.2, at the
boot of the baseline (*Log area cleared, 1027 bytes*), as it does when
the log nears its 4 KiB. Nothing of rc1.

## Part 3: the owner's

Not run, needs the owner: VAR-01 with *BIOS Lock* off, WDT-01 (and the
last step of WDT-03), BOOT-09 (`serial_console=1` is still saved),
ME-05, OPT-05, DMA.
