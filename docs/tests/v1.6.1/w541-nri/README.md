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
| DEV-W01 Ethernet | PASS, with two fixes | *Ethernet* off works once the lockdown is cleared (patch 0262); on again brought the controller back only with the PHY woken through LANPHYPC (patch 0263), which the self-heal of ci-302 did on 2026-11-09: boot 505, one reset marked `GbP`, `00:19.0 [8086/153a] enabled` at the next boot, GPIO12 driven high by the MAC. See below |
| OPT-05 | PASS | the setup options reset only when the CMOS was lost too (patch 0256): `RTC_PWR_STS` set from Linux alone (`setpci 1f.0 a4.w=0004:0004`) and a reboot -> *Setup options: not reset, RTC power lost but the CMOS kept the last boot (POST 0xf8/0x00000000)*; the bit set and the `CMOS_POST` bytes 0x70-0x7a cleared -> *Setup options: 66 reset to defaults (RTC power lost)*, the setup back at its defaults, `RTC: failed = 0x1` |
| FLASH-01 | PASS | after the OPT-05 reset the defaults turn *BIOS Lock* and *Firmware protection* back on: PR0 over `WP_RO`, PR1 over `SI_ALL`, FLOCKDN, flashrom refused. Clean protected end state |

## v1.6.1-rc4 on the W541

rc4 (`959d89f`, the first release candidate with the W541 patches)
installed as a capsule from the CI build ci-303 with *BIOS Lock* on,
2026-11-09: slot B, confirmed, ESRT *v1.6.1-rc4 riuscito* (UPD-01,
UPD-02 PASS); the training cache kept by the capsule and valid for the
new slot, RAM init 0.11 s (MEM-03 PASS); FLASH-01 PASS (PR0 over `WP_RO`,
PR1 over `SI_ALL`, BIOS Lock on); 8 CPUs, the GbE present. Then the
Ethernet switch of DEV-W01 on the release: off, two restarts by the
firmware (boots 511 and 512 in the event log: the lockdown cleared, the
bit applied), `BUC` `0x20`, 00:19.0 gone; on again, two restarts (513,
514: the lockdown cleared, the bit cleared with the PHY woken in the same
boot), `BUC` 0, GPIO12 high, `00:19.0 [8086/153a] enabled`, `eno0` back.
No *Last POST code* event for any of the four resets. DEV-W01 Ethernet
PASS.
Then one `rtcwake -m mem -s 30`: resumed, every CPU back, the GbE and
`eno0` there, RAM init 0.11 s on the resume path, S3-01 PASS.

## FAN-10, the EC's CPU-limit events (after v1.6.1, on v1.6.1)

On AC, 2026-11-09: `stress-ng --cpu 0` for 10 minutes, then 3 more with
the ACPI EC driver's debug on (`file drivers/acpi/ec.c +p`): the EC
raised **no query at all** (no `Query(0x..) scheduled`, `SCI_EVT` 0 in
every transaction), so no 0x48, 0x49 or 0x5B; EC 0x88-0x8b (the thermal
alarms) stayed 0, EC 0x0d and 0xff (the acknowledgement bits the Lenovo
ASL writes) stayed 0; the package held its power limits (CPU-02). The
GPE 0x11 counter grew by about 5 a second under load and at idle alike:
not EC queries. Then the same 3 minutes on battery (the adapter
unplugged, 100%): again no query, no alarm, the acknowledgement bits 0.
The EC asks the OS for no CPU limit on this unit, on AC (170 W adapter)
or on battery; the Lenovo `_PPC` would lower the limit on battery by
itself, from the battery state, not on an EC event. Nothing to handle
for 0x48, 0x49 and 0x5B, as far as this unit shows.

## v1.6.2-rc1 on the W541: MEM-06, the new coreboot pin

rc1 (`9aee912`, coreboot 26.09-607) as a capsule from v1.6.1, slot B,
2026-11-09. The first boot trains, as the version of the cache follows
the NRI code (0.83 s, *Memory test passed*, `RW_MRC_CACHE` updated).
The round trip ends where v1.6.1 and `mrc.bin` end: C0 44, C1 45, IO
latency 4, `rt_iocomp` 21; the step of patch 0088 still shortens 3 and
2 qclk after the receive enable training (IOLAT 7 and 6), so CB:96893
(the initial delta at 0) did not make it a no-op. `ddr-report --compare`
against the v1.6.1 dump: 408 fields differ, as a new training does
(comp and PI values, receive enable within 2, Vref within 2) plus two
systematic changes from the upstream code: `rx_eq` 0 to 1 on every byte
(the Broadwell support commit sets the Haswell initial RX equalization
to 1) and `read_rf_rank` 3 to 0 (the unified sense amp test); the
per-bit `RX_OFFSET_VDQ` values are repacked by the refactoring, with
patch 0008's fix kept. Dumps: `ht/rc1/`.
Then `stress-ng --vm 4 --vm-bytes 75% --verify` for 30 minutes without an
error or a machine check, and one `rtcwake -m mem -s 30`: resumed, every
CPU back, RAM init 0.11 s on the resume path. The cache across the
slots was shown before: a slot with the same NRI code keeps it (MEM-03
of v1.6.1, above), a slot with other code trains once on it (this first
boot of rc1 on the cache of v1.6.1: *needs update*, then *updated*; the
pre-CBMEM romstage log overflowed, so the *version mismatch* line itself
is not in `cbmem`). MEM-06 PASS on rc1.

## The fingerprint switch on rc1 (DEV-W01, patch 0265)

This W541 has no reader, so the switch could only be checked for what it
touches: *Fingerprint reader* off, `USB2PDO` reads `0x00000100` (bit 8
alone), the Bluetooth module (xHCI USB2 port 11) and the camera (12) and
the two EHCI hubs stay, nothing else disappears from `lsusb`; on again,
`0x00000000`, the Bluetooth module and the camera there. The port itself is empty on this unit, as the Lenovo table
says for a unit without the reader; whether the reader of another W541
sits on it is still to see there.

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
- **After the test** (2026-11-09): a power-down with the AC adapter
  and the battery out (the coin cell kept), then a warm reboot with PMH7
  register 0x26 bit 2 set (a "woken by LAN" flag, not the PHY power, as
  the Lenovo firmware shows), then a 1-to-0 transition of `BUC` bit 5
  with the lockdown clear and a CF9 0x0E (ci-299): the controller stayed
  absent, `BUC` 0, every PCH register that `pchregs.py` reads as at b1,
  the descriptor, GbE and ME regions byte-identical, the GbE lane of the
  IOBP as coreboot programs it at every boot, the ME status lines the
  same. The Lenovo firmware does nothing else for the LAN
  ([stock-gnet94ww.md](stock-gnet94ww.md#2-io-port-access)).
- **The cause** (2026-11-09): GPIO12, LANPHYPC, read native and low.
  The MAC hides itself when it finds no PHY at reset, and the I217 PHY
  leaves its low-power mode only on LANPHYPC, a level that only the MAC
  drives: a hidden MAC never raises it, so the PHY stays asleep and the
  MAC stays hidden, whatever `BUC` says, through resets and power
  cycles (the PHY's low-power state does not need the RTC well: it is
  simply never woken). Patch 0263 drives GPIO12 high as a GPIO for 50 ms
  and resets. With ci-302 in slot B: `GbE: MAC absent with the LAN
  enabled, waking the PHY`, one reset (event log: boot 505, *System
  reset*, no hang event), and at the next boot `PCI: 00:00:19.0
  [8086/153a] enabled`, `eno0` back, GPIO12 high, CMOS 0x7f cleared.
  The Lenovo firmware never meets the case: its ME, which owns the PHY,
  wakes it.

Files: `ht/` on the test machine (`b1`-`b8`, `gbe-reenable-finding.txt`).
