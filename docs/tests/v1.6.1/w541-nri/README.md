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
| DEV-W01 Ethernet | partial | *Ethernet* off works (after the lockdown is cleared, see below); on again did not bring the controller back after the plain reset; a global reset (patch 0262) to be tried |
| OPT-05 | PASS | the setup options reset only when the CMOS was lost too (patch 0256): `RTC_PWR_STS` set from Linux alone (`setpci 1f.0 a4.w=0004:0004`) and a reboot -> *Setup options: not reset, RTC power lost but the CMOS kept the last boot (POST 0xf8/0x00000000)*; the bit set and the `CMOS_POST` bytes 0x70-0x7a cleared -> *Setup options: 66 reset to defaults (RTC power lost)*, the setup back at its defaults, `RTC: failed = 0x1` |
| FLASH-01 | PASS | after the OPT-05 reset the defaults turn *BIOS Lock* and *Firmware protection* back on: PR0 over `WP_RO`, PR1 over `SI_ALL`, FLOCKDN, flashrom refused. Clean protected end state |

Not run (no hardware on this unit): NET-02 (Wake on LAN, patch 0259) and
the fingerprint switch; FAN-10's CPU-limit count.

## The Ethernet switch

`onboard_ethernet` sets the LAN disable bit of `BUC` (RCBA 0x3414 bit 5,
in the RTC well) in romstage. coreboot's finalize sets the Function
Disable SUS Well lockdown (`FDSW`, 0x3420 bit 7) at every boot
(`southbridge/intel/common/finalize.c`).

| Step | `BUC` at the OS | GbE | coreboot |
|---|---|---|---|
| b1, defaults | `0x00` | present | |
| b2, after the setup save (off) | `0x00` | present | *GbE: BUC 0x00000000 does not take the change* |
| b3, after an S5 | `0x20` | gone | (the first boot wrote and reset; its log is lost with the reset) |
| b4, reboot | `0x20` | gone | |
| b5, after the setup save (on) | `0x20` | gone | *GbE: BUC 0x00000020 does not take the change* |
| b6, after an S5 | `0x00` | gone | *PCI: Static device PCI: 00:00:19.0 not found* |
| b7, b8, reboots | `0x00` | gone | the same |

- **The lockdown blocks the write.** At b2 and b5 the value read at the
  OS, a minute after romstage, was still the old one: the write did not
  take, and the code (patch 0241) gave up without a reset. The lockdown
  survives a warm reset and is cleared across an S5: at the first boot of
  b3 and b6 the write took, and the code reset (`full_reset()`, CF9 0x0E).
  Patch 0262 resets first when the lockdown is set, so the write takes at
  the next boot without an S5, as the Lenovo firmware does.
- **Off works** after that reset. **On did not**: at b6 the bit was
  cleared with the lockdown clear and CF9 0x0E followed, the sequence the
  datasheet asks for, and the controller stayed absent through the next
  boots.
- **The Lenovo firmware** (GNET94WW, PchInitPeim 0x243e, PchResetPeim;
  [stock-gnet94ww.md](stock-gnet94ww.md#2-io-port-access)): `BUC` already
  as wanted, nothing; `FDSW` locked, a global reset (CF9GR, then CF9 0x0E)
  before any write; otherwise the write, a read-back, and for an enable
  a reset whose type depends on `FD2` bit 1 (the HECI hidden): with it, a
  plain CF9 0x0E (`PowerCycleReset`), without it, as on a Lenovo setup
  with its ME on, a global reset. ouroBIOS hides the HECI, so the plain
  reset is what the stock would do here, and that is the one that failed.
- **Being tried**: patch 0262 resets with a global reset instead
  (CF9GR is unlocked in romstage), the stock's reset with its ME on.
  Open: whether a global reset re-enables the controller with the ME
  disabled, and whether a full power-down (G3) does, which is assumed,
  not yet seen. If neither the global reset nor anything short of a
  power-down brings it back, the switch keeps its disable and the help
  keeps saying that turning it back on needs a full power-down (patch
  0263).

Files: `ht/` on the test machine (`b1`-`b8`, `gbe-reenable-finding.txt`).
