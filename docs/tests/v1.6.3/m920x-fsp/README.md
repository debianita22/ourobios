# v1.6.3-rc1 on the M920x

The run of [docs/test-v1.6.3-m920x.md](../../../test-v1.6.3-m920x.md) on
the ThinkCentre M920x of the port, 2026-11-09 and 10, by an agent on the
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
| OPT-06 | INFO: **the OS can set the bit** | run last, on v1.6.2. The address confirmed: `cbmem -1` *GEN_PMCON: d8a01608 00002200*, `./mm r 0xfe001024` `0x00062210`, the difference only the lock bits 4, 17 and 18. R0 `0x00062210` (bit 2 clear); `./mm w 0xfe001024 0x00062214` read back R1 `0x00062214`: bit 2 set by the OS, as on the W541; `./mm w 0xfe001024 0x00062210` read back R2 `0x00062210`, equal to R0: the bit clears by writing 0 (a plain read-write bit, not write-1-to-clear). No boot happened with the bit set; after the next boot the 36 options are those of the baseline ([part1/opt-06.txt](part1/opt-06.txt)). The next step is patch 0256's check (a lost CMOS as well) on this board |
| WDT-02 | PASS (on v1.6.2, the defect of 0267 seen) | see [WDT-02](#wdt-02-a-reset-by-the-watchdog) below |
| NET-02 | not asked | no request from the W541 or the owner so far |

## Part 2: the candidate

v1.6.3-rc1 (run 42696841540, the pre-release `v1.6.3-rc1-m920x-fsp`)
as a capsule from v1.6.2 with both protections on (UPD-02): the
signature valid, rc1 from slot A at the next boot, *ultimo: v1.6.3-rc1,
riuscito*.

| ID | Result | Notes |
|---|---|---|
| UPD-02, UPD-01 | PASS | the capsule written by the payload of v1.6.2 into slot A |
| UPD-05 | PASS | back to v1.6.2 after WDT-02 on rc1: `update.py rollback` on a copy of the flash, a reboot, v1.6.2 from slot B, *ultimo: v1.6.2, riuscito*; rc1 kept in slot A |
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
| WDT-02 | PASS | the line with the register and *1 in a row*, the status clear at the OS, `0xa0`, no line after a reboot: [WDT-02](#wdt-02-a-reset-by-the-watchdog) below |
| WDT-01 | not run, needs the owner | the setup menu |

Every boot of rc1 logs *Firmware watchdog: off (OC_WDT_CTL 0x00002000)*
in romstage and *at the payload, OC_WDT_CTL 0x00002000*, and the
register reads `0x00002000` at the OS.

The event log of the copy after rc1 has 262 events against 338 at the
start: coreboot shrank it on 2026-11-09 at 20:58 UTC, on v1.6.2, at the
boot of the baseline (*Log area cleared, 1027 bytes*), as it does when
the log nears its 4 KiB. Nothing of rc1.

## WDT-02, a reset by the watchdog

The overclocking watchdog armed from Linux, `./pio w 0x1854 0x8000e077`
(reload, enable, all modes, ICC survivability, 120 s; it read back
`0x0000e077`), with no guest up and `sync` first. Once on rc1 (slot A)
and, after the return to v1.6.2 (UPD-05, below), once on v1.6.2 (slot
B). Files in [wdt-02](wdt-02).

| What | rc1 | v1.6.2 |
|---|---|---|
| the reset | about 140 s after the arm (armed 22:52:41, the boot event of the next boot at 22:55:05, the kernel at 22:55:26) | about 148 s (armed 23:04:39, the kernel at 23:07:18 after 10.5 s of firmware) |
| the line | *Firmware watchdog: the last reset came from the watchdog (OC_WDT_CTL 0x02002000), 1 in a row*, then *off (OC_WDT_CTL 0x00002000)* | *the last reset came from the watchdog* (no register, as expected), then *off (OC_WDT_CTL 0x02002000)* |
| the enable bit | clear in `0x02002000`: it did **not** survive the reset | no *OC Watchdog: disabling watchdog timer* line: the same |
| at the OS | `0x00002000`: the status cleared by the firmware; `./pio cr 0x7e` `0xa0` | `0x02002000`: bit 25 still set, v1.6.2 never clears it |
| which status bit | bit 25 (the ICC survivability status: the arm set bit 13), bit 24 clear | the same |
| a reboot | no watchdog line | the line again for a reset one boot old: the defect that 0267 corrects. Cleared by hand afterwards (`0x02002000` written back), `0x00002000` |
| the slot | slot A, tries 0, no fallback | slot B, confirmed |

**The kind of reset: a global reset of the platform**, not a reset of
the host. Against a warm reboot of the same boards (`GEN_PMCON_A`
`d8a01608`, `prev_sleep_state 0`), the boot after the watchdog has
`GEN_PMCON_A` `d9801408`: `GBL_RST_STS` (bit 24) set, `MEM_SR` (bit 21)
and `HOST_RST_STS` (bit 9) clear; `prev_sleep_state 5 (S5)`; the event
log has *System boot* and *ACPI wake S5* and no *System reset*, as after
a power-on. The memory training was not redone (*RW_MRC_CACHE does not
need update*); FspMemoryInit took 5.25 s on rc1 (the ME's wait of patch
0191, which comes at random) and 0.25 s on v1.6.2. The ME stayed off
(ME-01 PASS). The time from the arm to the reset, 140-150 s against the
120 s programmed, includes the power-down and power-up of a global
reset.

On rc1 `update.py vboot` shows the slot's result as `-` (unknown), not
*confermato*: vboot clears the result at every boot that is not a try
(`vb2_select_fw_slot()`), and only a trying boot gets *success* from the
payload; the same `-` is in the records of v1.6.2 before this run
(#158). The reset was not counted against the slot: no try used, no
fallback.

## The end

Back on v1.6.2 from slot B (UPD-05 above), rc1 kept in slot A, the
read-only part of `ci-203`. The last boot, a reboot after OPT-06 with
the bit clear and the watchdog status cleared by hand: report 25 PASS
with a copy of the flash ([hw-end.md](hw-end.md)), FLASH-01 PASS
(*BIOS Lock* and *Firmware protection* on), *Firmware watchdog: off
(OC_WDT_CTL 0x00002000)* with no watchdog line, `./pio r 0x1854`
`0x00002000`, `./mm r 0xfe001024` `0x00062210` (bit 2 clear), the
`Timeout` of the boot manager 3 s as it was, the option lock armed, the
36 options those of the baseline. Byte 0x7e holds `0xa0`, written by rc1
(v1.6.2 does not use it). VM 101 stays stopped as it was; nothing was
set up to survive the reboots.

The answers for the roadmap:

- **OPT-06**: on Cannon Point too the OS can set `RTC_PWR_STS`, so a
  reset of the options needs more than that bit, as patch 0256 does on
  the W541.
- **WDT-02**: a reset by the watchdog is a global reset of the platform
  (`GBL_RST_STS`, S5, the event log as after a power-on); its status is
  bit 25 (ICC survivability, armed with bit 13) and stays set until
  written; the enable bit does not survive it. rc1 reads and clears the
  status and counts the reset (patches 0267, 0268); v1.6.2 reports the
  same reset again at every boot until the status is cleared by hand.

## rc2: patch 0270

v1.6.3-rc2 (run 42799869464, `next` with patch 0270) as a capsule from
v1.6.2 with both protections on, slot A (over rc1), 2026-11-10; v1.6.2
stays in slot B. The owner asked for the test of 0270 with the stray
bit, which OPT-06 showed the OS can set.

| ID | Result | Notes |
|---|---|---|
| UPD-02 | PASS | signature valid, rc2 from slot A, *ultimo: v1.6.3-rc2, riuscito*; report 21 PASS ([rc2/hw-rc2-1.md](rc2/hw-rc2-1.md)) |
| OPT-07 (0270) | PASS | before: the 36 options from a copy of the flash, CMOS 0x70-0x7e `80 f8 f8 00…00 a0` (the bank mark and POST code 0xf8 in both banks, [rc2/cmos-pre.txt](rc2/cmos-pre.txt)); bit 2 set from Linux, `0x00062210` → `0x00062214`; a reboot. Romstage: *GEN_PMCON: d8a01608 00002204*, *Setup options: not reset, RTC power lost but the CMOS kept the last boot (POST 0xf8/0x00000000)* ([rc2/cbmem-rc2-bitset.txt](rc2/cbmem-rc2-bitset.txt)); at the OS bit 2 clear (`0x00062210`), the 36 options identical to those before, no RTC event in the event log, the CMOS not zeroed (the bank mark moved on to `0x81` as at every boot, 0x7e still `0xa0`), the clock right (`timedatectl`, chrony synchronized), slot A confirmed, FLASH-01 PASS ([rc2/hw-rc2-post.md](rc2/hw-rc2-post.md); its one WARN is that line). The next boot: no *Setup options* line, `GEN_PMCON: … 00002200` |
| S3-01 | PASS | one resume after the test, PR0 and PR1 back |
| OPT-05 | not run, needs the owner | the real case, a CMOS clear: the options must be reset once |

## Part 3: the owner's

Not run, needs the owner: VAR-01 with *BIOS Lock* off, WDT-01 (and the
last step of WDT-03), BOOT-09 (`serial_console=1` is still saved),
ME-05, OPT-05, DMA.
