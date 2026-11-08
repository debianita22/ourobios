# The W541 features of v1.6.1 on the machine

Branch `w541-v1.6.1` built as the CI build `ci-294-5381836` (patches
0246-0258) and `ci-295-39d3b0c` (0246-0261), `nri`, on the ThinkPad W541,
2026-11-08. Written to slot B then slot A with `update.py other-slot` and
flashrom, from slot A (ci-273) and slot B (ci-294); the training cache
kept (the NRI code did not change). A systemd one-shot ran a chain of
boots (`ht/`), with two setup visits by the owner: all the switches off
and the watchdog at 5 minutes, then all back on and the watchdog off.

| ID | Result | Notes |
|---|---|---|
| CPU-06 | PASS | *Hyper-Threading* off: `MSR 0x35` `0x40004` (4 cores, 4 threads), `lscpu` 4 CPUs, `SOFT_RESET_DATA`/`CTRL`/`LOCK` `1`/`1`/`1` (set and locked, patches 0247, 0258); the native RAM init `Using cached memory parameters` across the warm reset (patch 0248), no *Last POST code* in the event log (the reset is POST `0xfc`, patch 0246); it survives S3 (after `rtcwake -m mem` still 4 CPUs, every AP back); every cold boot re-applies it with one reset, the cache kept. On again: 8 CPUs, `0x40008`, the cache kept. `ACPI0007`/`LNXCPU` 0/8, consistent |
| MEM-03 | PASS | slot B (ci-294) to slot A (ci-295), the same NRI code: `Using cached memory parameters`, no training (patch 0250, the key from the code); RAM init 0.11 s on a fast boot and an S3 resume |
| WDT-01 | PASS | *Firmware watchdog* 5 minutes: `Firmware watchdog: armed, 300 s (OC_WDT_CTL 0x0000e12b)` in romstage, `at the payload` in ramstage, `OC_WDT_CTL 0x0000212b` at the OS (EN clear): SMM stopped it when the payload confirmed the slot (patches 0254-0255); the machine stayed up past 420 s. On an S3 resume romstage stops it (`Firmware watchdog: off`). `hw-report.py` WDT-01 reads it on the W541 (port 0x554) |
| DEV-W01 camera | PASS | *Integrated camera* off: `USB2PDO` (xHCI 0xE4) bit 11 set (`0x00000800`), gone from `lsusb` and `/dev/video*`; on again: back (patches 0244-0245) |
| DEV-W01 card reader | PASS | *Card reader* off: `Card reader: disabling the link of PCI: 00:00:1c.0`, the O2 Micro OZ777 gone from `lspci`, root port 1 Link Control bit 4 set (`0x0c13`); on again: back (patch 0257) |
| DEV-W01 microphone | PASS | *Internal microphone* off: the ALC3232 card stays in `arecord -l` (the codec is there), the internal array not offered (patch 0243, the pin as not connected) |
| DEV-W01 Ethernet | partial | *Ethernet* off works, but only after a full power cycle, and re-enabling needs a full power-down. See below |
| OPT-05 | PASS | the setup options reset only when the CMOS was lost too (patch 0256): `RTC_PWR_STS` set from Linux alone (`setpci 1f.0 a4.w=0004:0004`) and a reboot -> *Setup options: not reset, RTC power lost but the CMOS kept the last boot (POST 0xf8/0x00000000)*; the bit set and the `CMOS_POST` bytes 0x70-0x7a cleared -> *Setup options: 66 reset to defaults (RTC power lost)*, the setup back at its defaults, `RTC: failed = 0x1` |
| FLASH-01 | PASS | after the OPT-05 reset the defaults turn *BIOS Lock* and *Firmware protection* back on: PR0 over `WP_RO`, PR1 over `SI_ALL`, FLOCKDN, flashrom refused. Clean protected end state |

Not run (no hardware on this unit): NET-02 (Wake on LAN, patch 0259) and
the fingerprint switch; FAN-10's CPU-limit count.

## The Ethernet switch

`onboard_ethernet` sets the LAN disable bit of `BUC` (RCBA 0x3414 bit 5),
in the SUS well, which `FDSW` (0x3420 bit 7) freezes with a lockdown.

- **Off** works. At the first boot after the setup save `BUC` stayed
  `0x00000000` and the controller was still there (`GbE: BUC 0x00000000
  does not take the change`): the lockdown was set from the boot before,
  which a warm reset keeps. After a full power cycle (the owner's
  power-on), `BUC` read `0x00000020` and the controller was gone. Patch
  0262 fixes the auto path: a full reset to clear the lockdown when the
  write does not take, so the next boot's romstage writes it before the
  lockdown is set again. ci-295 does not have 0262; the manual power
  cycle stood in for it.
- **On again does not work within a reset or S5.** With the option back
  on, a cold boot from `rtcwake -m off` cleared `BUC` bit 5 (`0x00000000`)
  and `full_reset()`ed, but the controller stayed absent: `PCI: Static
  device PCI: 00:00:19.0 not found, disabling it`. The LAN disable lives
  in the SUS well, which survives both the CF9 0x0E full reset (by design,
  which is why `BUC` is sticky) and S5 (the SUS well stays powered for the
  RTC and Wake on LAN). Clearing the bit does not re-power or re-clock the
  GbE; only a G3 (the AC adapter and the battery removed, or RTCRST) resets
  the SUS well and brings it back.
- **Open**: re-enable the GbE within one boot (clear `BUC` very early and
  re-enable its clock), or say in the help text that turning Ethernet back
  on needs a full power-down. The disable is useful as it is; the re-enable
  caveat is the one to fix or document.

Files: `ht/` on the test machine (`b1`-`b8`, `gbe-reenable-finding.txt`).
