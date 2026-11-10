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
| WDT-02 | PASS | below: a global reset about 120 s after the arm, ICCSURV_STS set, the enable cleared by the reset, *1 in a row*, `0x7e` back at `0xa0` at the OS |

## WDT-02: a reset by the watchdog

Armed from Linux with `0x8000e077` (reload, enable, all modes, ICC
survivability, 120 s), *Firmware watchdog* Off, both slots v1.6.2 or
later, the register `0x00002000` before. Once on rc1, once on v1.6.2
after the return to it ([files](wdt02/)).

| What | rc1 | v1.6.2 |
|---|---|---|
| the reset | between 120 and 125 s after the arm: the last line of the journal 23:00:01, the boot in the event log 23:00:10, the kernel 141 s after the arm | the same, 141 s to the kernel |
| romstage | *the last reset came from the watchdog (OC_WDT_CTL 0x02002000), 1 in a row*, then *off* | *... (OC_WDT_CTL 0x02002000)*, then *off* (no count: patch 0268 is not in v1.6.2) |
| the status | bit 25 (ICCSURV_STS) set, bit 24 clear: the timer was armed with ICC survivability (bit 13) | the same |
| the enable | bit 14 clear after the reset: the reset leaves the watchdog off | the same |
| the kind of reset | the ME's *Power Management Event: Clean global reset* (a plain reboot logs *Pseudo-global reset*); the RAM init from the cache, no training; the event log only *System boot* and *System reset*, no event of its own | the same |
| at the OS | `0x00002000`, the status clear (romstage cleared it); byte 0x7e `0xa0`: SMM cleared the count when the payload confirmed the boot | `0x00002000` |
| a reboot | no *last reset came from the watchdog* line: reported once (three reboots) | not run |
| the slot | still slot B, next slot B, no try counted; vboot's result reads `-` (unknown) for the current and the previous boot, where it read *confermato* before: `vbnv_mark_tried_slot_good()` writes the result only when it is *trying*, and the reset left an *unknown* one that the next boots keep | slot A, *confermato* (it was on trial after the return) |

The answers the roadmap waited for: the status bits are set after a
reset by the watchdog (ICCSURV_STS, with the mode the firmware arms), the
enable bit does not survive it, and the reset is a global one that keeps
the training cache. So the count of patch 0268 works on this board: the
romstage of rc1 counted the reset and SMM cleared it.

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

Followed up on 2026-11-10 on v1.6.2 ([sd-fix/](sd-fix/)): the state is
not tied to S3, a cold boot showed it too (PC2 93.6% with the screen
off before any resume), so the good reading of v1.6.1-rc4 does not make
it a regression of v1.6.2. Clearing the reader's *LTR Mechanism Enable*
(DevCtl2 bit 10) took the package to PC7 84% (1.5 W) at once, and it
stayed there across a resume; clock PM and ASPM off changed nothing,
nor did writing its Max Snoop Latency, which reads 0 in every state
while coreboot programs 3146 µs (the no-snoop one reads 3146 µs). The
reader reports latencies that depend on a state inside it. Fixed by
patches 0271-0272, after rc2: LTR left off on the reader, and `_OSC`
keeps the control of LTR from the OS.

## v1.6.3-rc3: the card reader without LTR

rc3 (`72cb533`, patches 0271-0272) as a capsule from v1.6.2, slot B,
2026-11-10 ([files](rc3/)). Linux logs *_OSC: platform does not support
[LTR]* and no longer lists LTR among what it controls; coreboot logs
*Card reader: LTR off on PCI: 00:01:00.0*. LTR enable (DevCtl2 bit 10):
root ports 1 and 2 and the Wi-Fi on, the card reader off, as coreboot
left them.

| State, the screen off | Package | Power |
|---|---|---|
| after the boot | PC7 88.1% | 1.14 W |
| after resume 1 | PC7 74.8% | 2.49 W |
| after resume 2 | PC7 84.6% | 1.56 W |
| after resume 3 | PC7 86.1% | 1.40 W |

The reader's LTR stays off across the resumes; `suspend_stats/fail` 0.
[The report](rc3/hw-w541-nri-rc3.md): 19 PASS, BOOT-03 without an error
or a warning, ME-01 and EC-01 WARN (known), PCI-01 WARN for the reader's
LTR off (now known to `hw-report.py`), and BOOT-04 FAIL below.

**A new finding, which the card reader hid**: with the package free to go
deep and the greeter's screen off, i915 enters PC8 at runtime suspend
and warns *PCH PWM1 enabled* in `hsw_enable_pc8` (11 times on rc3, 194
on v1.6.2 this morning after the reader's LTR was cleared by hand). The
only backlight device is `acpi_video0`, no `intel_backlight`: i915 does
not drive the PCH PWM, so it does not turn it off with the panel. It
does not stop the package from reaching PC7.

Followed up the same day: the warnings came every 20-30 s for as long
as the screen stayed off after a resume (5 in 90 s), and stopped after
one screen on and off. Before the sleep, with the screen off,
`BLC_PWM_PCH_CTL1` read `0x40000000` (the PWM off); right after the
resume `0xc0000000` with the duty at 50% (`0x12ba095d`), the panel still
unpowered (`PCH_PP_CONTROL` `0x00000008`): `gma_setup_panel()` of
coreboot runs on resume also when the display is left to the OS, and
enables the PWM. i915 resumes with the backlight off and leaves it. The
enable bit cleared by hand after a resume: no warning in 90 s, and with
the screen on again i915 enabled the PWM at its level. Patch 0274 does
that in `_WAK`, but under macOS.

## A bug of hw-report.py

Fixed on `next` (2026-11-10). VB-02 said *CBET4000 ouroBIOS-v1.6.3-rc1-nri non e' in nessuno slot
della copia* at every boot: it looks for the running version with
`b.endswith(fw.bios)`, where the SMBIOS version (`CBET4000 ouroBIOS-...`)
is the longer string and the slot's build name the shorter; the test
wanted the other way round. The vboot state itself was right.

## The end

`update.py rollback` from rc1: v1.6.2 from slot A, *riuscito*, rc1 kept
in slot B. [The last report](hw-w541-nri-v1.6.2-end.md): FLASH-01 PASS
(*BIOS Lock* and *Firmware protection* on), *Firmware watchdog* off,
OC_WDT_CTL `0x00002000`, the boot manager's `Timeout` 3 s as before;
BOOT-03 and WDT-01 WARN name the reset by the watchdog of the boot before
(they go at the next boot). Three plain reboots more than the plan's one
happened after WDT-02 on rc1: the agent was cut off and started the step
again. The boot-time helpers of the run were removed.

## The power-offs

The cold boot: `rtcwake -m off -s 180` at 07:16:54 on 2026-11-10; the
machine was off at 07:17:01 and the RTC alarm, set for 07:19:56, started
it from off (the kernel at 07:20:15). The first time this was tried on
the board, and the net that NET-02 needs. [Its report](hw-w541-nri-v1.6.2-cold.md):
20 PASS, ME-01 and EC-01 WARN (known), IDLE-01 INFO (the greeter's panel
on), S3-01 INFO and ELOG-01 SKIP (no resume, no copy of the flash);
BOOT-02 1.50 s from the reset to the payload, the RAM init from the cache
(0.11 s), FLASH-01 PASS. NET-02 was not tried after it: no cable on the
Ethernet port.

## Not run here

The `mrc` variant (the read-only part starts only `nri` slots) and
Windows (none installed). The owner's rows of part 3: macOS, S3 with the
lid and Fn, DISP-03, NET-02 in its settings, WDT-01, VAR-01 with *BIOS
Lock* off, Secure Boot with shim, CSMWrap, NET-05, BOOT-05/06, OPT-02,
MEM-09, USB-06, DISP-05, DEV-W01 on a unit with the reader, OPT-05 with
the coin cell out.
