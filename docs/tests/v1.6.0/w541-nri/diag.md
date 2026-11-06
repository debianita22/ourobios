# TSC ADJUST at a resume and a USB 3.0 drive after a warm reset: the W541 troubleshooting

The two open items of [docs/roadmap.md](../../../roadmap.md) found in
the tests of rc6, run on the W541 with `nri` on 2026-11-06: part 1 under
rc6 from Linux, without writing the flash; part 2 with the measurement
build `ci-265-bd07465` (patch 0230 on `next` at `c74c7eb`: `DIAG` lines
at NOTICE, the only change besides them a wait of 10 ms at the exit of
`early_usb_init()`) in slot B, written with `update.py other-slot`, and
back to rc6 the same way. The read-only part stayed `ci-205`; slot B
holds the measurement build since, v1.5.0 is gone from it.

## TSC ADJUST: not coreboot

**What Linux sees** ([diag-tsc-linux.txt](diag-tsc-linux.txt)). The TSC
runs at 2793.5 MHz. Before a suspend `IA32_TSC_ADJUST` (0x3B) reads 0 on
all eight processors; right after the resume Linux prints
`TSC ADJUST differs: CPU0 0 --> N` and writes 0 back, and the register
is 0 again everywhere:

| Suspend | TSC of CPU 0 just before | N | N minus the TSC before |
|---|---|---|---|
| `rtcwake -m mem -s 30` | 15145494448943 | 15144001033268 | −1.49e9 (−0.53 s) |
| `rtcwake -m mem -s 60` | 18693831208 | 17268100758 | −1.43e9 (−0.51 s) |
| the measurement build, `-s 30` | 256986058912 | 255469128074 | −1.52e9 (−0.54 s) |

N follows the TSC of before the suspend, whatever the time asleep: not
the TSC plus 30 or 60 s. After the resume the TSC itself reads 1.7 s
worth of counts (Linux has zeroed the register by then): it restarted
from zero at the reset. No `TSC ADJUST differs within socket(s)`, and
the processors other than CPU 0 read 0 at their bring-up: CPU 0 only.

So something writes the TSC of CPU 0 with a value it saved before the
suspend, after the reset of the wake: the processor then moves
`IA32_TSC_ADJUST` by the same difference (N = saved value − TSC at the
write).

**What coreboot sees** ([diag-build-w541-nri.txt](diag-build-w541-nri.txt),
section *resume*). On the resume path of the measurement build
`TSC_ADJUST` is 0 at every point, from `romstage end` (TSC 1.93e9) to
the eight processors at `cpu_core_init`, `post_mp_init` after the SMM
relocation, `BS_OS_RESUME` and `before the wake vector`, the last code
before the jump to Linux, at TSC 2.824e9, 1.01 s after the reset. The
TSC there is the count since the reset. The write is after the jump:
from N = −1.52e9 against the TSC before, and the write at 2.82e9 or
later, the value written is the TSC of at least 0.47 s after the last
read from the shell, a value taken late in the suspend path.

What is left: Linux between its wake vector and `tsc_resume()`, or an
SMI that Linux causes on the way (the ACPI `_WAK` of these tables does
not write MSRs, nor does coreboot's SMM, as the code says). The kernel's
MSR tracepoints across a suspend are not the way to see it: tried once,
the kernel reset right after coreboot's jump to the wake vector (the
firmware's resume complete in its log; a test artefact, not a failure of
rc6). The message stays a known one of the report (BOOT-04).

## The USB 3.0 drive: not reproduced; a warm reset keeps its state

Afterwards, while the connectors were mapped, a hotplug into the same
connector reproduced it, and replugs pinned it on that connector:
[below](#the-right-ss-connector-trains-its-superspeed-link-badly).

The drive is a SanDisk Ultra Flair (`0781:5591`) in the **SS port on
the right side** (farthest from the screen), xHCI SuperSpeed port SS2 (`port17`), USB2 port 2: not
in "the left port" as the README of the record first said from the
`_PLD` of the firmware (below).

**Part 1, under rc6** ([diag-usb-linux.txt](diag-usb-linux.txt)):

| Step | `port17` | The drive |
|---|---|---|
| 1. after a cold boot and three suspends | `0x1203`: U0, 5 Gb/s | on bus 4 at 5000M |
| 2. `reboot` (the FADT reset, `0xCF9` = 6) | `0x1203` | at 5000M, no `Cannot enable` |
| 3a. xHCI held in D0 | `0x1203` | the same |
| 3b. the controller removed and rescanned (HCRST by Linux) | `0x1203` | the same |
| 3c. the drive pulled and put back | Rx.Detect, then `0x1203` after 11 s | at 5000M |
| 4. another USB 3.0 device | not run | none at hand |
| 6. v1.5.0 | not run | nothing to compare with |

The failure did not come back. What the boots of 11-05 and 11-06 show
together: the failure was there in the boot of 21:36 on 11-05 (a reboot
after the training boot of rc6), and in the boots after it that came
from a warm reset, including the two of the Hyper-Threading test; it
went away at the first cold boot, and never came back across warm
resets, resumes, a replug and the removal of the controller. A warm
reset keeps the port powered, so the drive keeps whatever state it was
in: stuck, it stays stuck; linked, it links again. What put it in that
state on 11-05, between 21:20 and the first line the journal kept
(06:35), is lost with the log.

**Part 2, the measurement build** ([diag-build-w541-nri.txt](diag-build-w541-nri.txt)).
`port17` is SuperSpeed port 1 in the `DIAG` lines:

| Boot | `MEM_SR` | The warm reset of romstage | Port 1 at `BS_PAYLOAD_BOOT` (or the wake vector) | In Linux |
|---|---|---|---|---|
| cold | 0 | skipped | `0x2a0`, Rx.Detect | `0x1203` |
| warm, with the drive | 1 | `WPR` to the six ports, `PR` never seen, done in 5 µs | `0x2802a0`: Rx.Detect, `WRC` and `PRC` | `0x1203` |
| warm, without it | 1 | the same, 5 µs | `0x2802a0` | empty |
| resume | 1 | from U3 (`0x1263`), `PR` set; at 100 ms Polling with `PR` (`0x12f1`), `timed out` | `0x1203`, U0 | `0x1203` |

- At a boot, cold or warm, coreboot hands every SuperSpeed port to the
  payload without a link: the drive is not even connected
  (`CCS` 0) when romstage's reset runs at a warm boot, so that reset does
  nothing to it. The link comes from the payload's or Linux's controller
  reset. Romstage cannot have left the port stuck at a warm boot.
- At a resume the reset engages and takes a little more than 100 ms: at
  the exit of `early_usb_init()`, 10 ms after the time-out, the port is
  in U0 (`0x281203`). The `warm_reset_usb3_ports: timed out` of every
  resume is the 100 ms limit, shorter than a warm reset with a device on
  the port (80-120 ms of LFPS, then the training), not a failure; in
  ramstage `usb_xhci_reset_usb3()` leaves that port alone (U0) and the
  wake vector gets it linked.
- `0x12f1`, the state of the port at the time-out of a resume, is
  the `0x2f0` of the stuck boots of 11-05 (`PR` set, Polling): the
  stuck drive is a warm reset that never ended.

What it says for the code: nothing in romstage to fix for the warm
boot; a limit of 150 ms (or polling `WRC` like ramstage) would make the
resume's message go and cost nothing when the ports are empty.

## The USB ports are described on the wrong side

Checked connector by connector with the owner naming each one
([diag-portmap.txt](diag-portmap.txt), 12:14-12:27): the drive put in
each connector, the attach watched in the kernel log and in every
`PORTSC`:

| Connector | xHCI port | Speed | `_UPC`/`_PLD` of patch 0071 (the OEM tables) |
|---|---|---|---|
| left side, nearest the screen, the *Always On* one | 3: HS3, no SuperSpeed | USB 2.0, 480 Mb/s | back: **wrong panel** |
| left side, farthest from the screen, marked SS | 1: HS1 and SS1 (`port16`) | USB 3.0, 5 Gb/s | right, and the comment calls it the *Always On* one: **wrong side** |
| right side, nearest the screen | 6: HS6, no SuperSpeed | USB 2.0, 480 Mb/s | right: right |
| right side, farthest from the screen, marked SS | 2: HS2 and SS2 (`port17`) | USB 3.0, 5 Gb/s | left: **wrong side** |

Three of the four connectors are on another panel than the tables say,
and the *Always On* connector is the USB 2.0 port 3, not port 1. Patch
0071 took the OEM buffers of GNET as they are; the OS shows the position
to users only (port names, the `physical_location` of Linux), so nothing
works differently, but the comment of `usb.asl` and the buffers want the
sides of this table, and the help of *USB always on* the connector it
powers (port 3). Earlier in this file and in the README the two right
ports were called "lower" and "upper"; "farthest from the screen" and
"nearest" are the owner's names.

## The right SS connector trains its SuperSpeed link badly

During the same check the drive, plugged into the right SS connector,
went to *Compliance mode* (`port17` `0x0a000340`) and showed up nowhere,
neither at 5 Gb/s nor at 480 Mb/s: the failure of 11-05, this time from a
hotplug under rc6, with no warm reset involved. With the xHCI held in D0
Linux does not notice (Compliance sets no change bit); let into runtime
suspend, the controller stayed asleep. Removing and rescanning the
controller (a reset by Linux, HCRST) brought the drive up at 5 Gb/s at
once: the stuck state is in the port and the controller, which a
controller reset clears, and which a warm reset of the machine carries
over (the drive keeps power, so it does not restart its own training).

Then replugs of the same drive, the same way, into each connector:

| Connector | Plugs | At 5 Gb/s at the first try | No link |
|---|---|---|---|
| left SS (SS1) | 6 | 6 | 0 |
| right SS (SS2) | about 8 | 3 | 5: Polling for about 0.5 s, then Rx.Detect, or Compliance |
| right SS with the SuperSpeed of port 2 off (`USB3_PSSEN` bit 1 cleared from Linux, put back after) | 3 | 3, at 480 Mb/s on HS2 | 0 |

When the SuperSpeed link fails, this drive does not fall back to the
USB 2.0 pair of the connector, which works (the last row): it stays
on the SuperSpeed side, so the user sees nothing at all. The drive is
not the cause (6 of 6 on the left), nor is the firmware (the same
controller, the same code for both ports, and the failures come at a
hotplug with Linux running): the SuperSpeed contacts or the signal path
of the right SS connector are marginal on this W541. The way to confirm
it is another USB 3.0 device in that connector, and the connector
cleaned; nothing to change in the firmware for it, but the CHANGELOG's
note of v1.3.10 (a drive in Compliance mode with `nri`) may well be the
same connector.

### Against the Lenovo firmware

The question was whether the right SS port gets different PHY settings
from the stock firmware, which `nri` would miss: each SuperSpeed lane
has its own transmitter and receiver settings in the PCH (IOBP/HSIO
registers), and a connector farther from the chip could want others.
Compared with GNET94WW (Lenovo's `gnuj39us.iso`, BIOS 2.42, the PEI
module `fd236ae7-0791-48c4-b29e-29bdeee1a838`, PchInit):

- the module carries two sets of HSIO tables for SATA and the xHCI. A
  function reads the LPC device ID (`8c4f`, Lynx Point-H, is in its
  list) and the revision, and returns the revision as is; the tables
  are picked from it: 2 gets set B, 3 to 5 get set A;
- this PCH is revision `05`, so the stock firmware writes set A: the
  xHCI table (20 rows for the lanes shared with PCIe, 36 for the four
  dedicated USB 3.0 lanes) and the SATA one, row for row the values of
  `hsio/lpt_h_cx.c` that `nri` writes;
- set B (other values for the same USB 3.0 lanes, such as `0x1401` in
  `0xe90031cc` instead of `0x1407`) is for revision 2 only.

So the stock firmware programs the SuperSpeed lanes of this machine as
`nri` does, with no setting per connector. What the comparison does not
cover: the board's own lines (a redriver or its enable, through GPIOs or
the EC, which the W541's GPIO table of coreboot takes from the stock
firmware) and the xHCI's MMIO settings beyond the HSIO. With the same
code and the same values the left SS connector links 6 times in 6, the
right one 3 in about 8: the connector, or the path to it, stays the
likely cause.

## Files

- [diag-tsc-linux.txt](diag-tsc-linux.txt): part 1a.
- [diag-usb-linux.txt](diag-usb-linux.txt): part 1b, the port at each
  step, the replug and the port map.
- [diag-portmap.txt](diag-portmap.txt): the connectors one by one, the
  Compliance mode from a hotplug and the replugs of each SS connector.
- [diag-build-w541-nri.txt](diag-build-w541-nri.txt): part 2, the
  `DIAG` lines of each boot of the measurement build (the first one,
  with the training, lost its romstage points to the pre-CBMEM console),
  the port in Linux and the TSC lines of the kernel. The whole
  `cbmem -c` of each boot is on the machine, in
  `~/ourobios-test-v1.6.0/w541-nri/diag/part2/`.
