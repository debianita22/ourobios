# The native RAM init (`nri`)

The `nri` variant trains the memory with coreboot's native RAM init (NRI)
instead of Intel's `mrc.bin`. Upstream still labels it *[NOT COMPLETE]*: it
trains enough to boot and to resume from S3, while some of the steps that
the MRC uses to widen the margins, save power and shorten latencies are not
public yet. This page lists what runs, what is missing, what this project
adds, what it does on the W541, and how to compare it with `mrc.bin` on the
same machine.

- [What runs](#what-runs)
- [On the W541](#on-the-w541)
- [Comparing with mrc.bin](#comparing-with-mrcbin)
- [Limits](#limits)

## What runs

At the coreboot pin of the releases (26.09-280), the NRI runs:

- SPD, memory clock, timings, controller and memory map, JEDEC init;
- sense amplifier offsets, receive enable, read MPR, write leveling;
- read and write timing centering and read voltage centering, one
  dimension at a time (1D);
- comp optimisation, late command training (CMD/CTL/CLK);
- alias check, ECC scrub (ECC DIMMs only);
- fast boot and S3 resume from the saved training.

This project adds:

- **patch 0086**, the DRAM voltage from the SPDs: 1.35 V when every DIMM
  runs at it (DDR3L), as `mrc.bin` sets it on the W541
  (`PCU_DDR_VOLTAGE` = 1); the code assumed 1.5 V on non-ULT Haswell, and
  the voltage selects the settings of the memory I/O;
- **patch 0087**, a memory test after training: every bank of every rank
  written and read back with the controller's test engine (REUT), and the
  training redone once when a step or the test fails. Upstream saves
  whatever the training produced and boots on it.

Missing, among the MRC's steps that the upstream author lists as
implemented in his tree and not published yet
([coreboot ticket 461](https://ticket.coreboot.org/issues/461)):

- timing and voltage centering together (2D);
- power training (DIMM ODT, drive strength, slew rate, equalisation);
- turnaround optimisation (rank to rank, read to write).

They widen the margins, lower the power of the memory interface and shorten
some latencies; none of them is needed to boot. And with two DIMMs per
channel the NRI always runs the commands at 2N, by a TODO in
`lookup_timings.c` written before the late command training existed;
`ddr-report.py` shows what `mrc.bin` chooses.

## On the W541

v1.3.9-rc2, i7-4810MQ with four 8 GiB DDR3L-1600 dual-rank SO-DIMMs (two per
channel, four ranks each), `nri` slot tried with `update.py other-slot`:

- the first boot trains (black screen meanwhile), tests every bank of the
  four ranks of both channels (*Memory test passed*) and saves the training;
  the next boots take the fast path (2.8 s to the payload);
- 1.35 V from the SPDs, as `mrc.bin` programs it (`PCU_DDR_VOLTAGE` = 1);
- 2N command rate (`LCT: Current tCMD = 2T`);
- the eye widths of the 1D training, in PI ticks (64 ticks per unit
  interval, 625 ps at DDR3-1600): read timing 28-44 per byte, write timing
  29-45, read voltage 43-100 half steps; command, control and clock 90-127
  of 128 at 2N. The NRI fails the training below 8.

## Comparing with mrc.bin

`tools/ddr-report.py` reads the registers of the memory controller (read
only) and shows timings, turnarounds, command rate, round-trip and I/O
latencies per rank, the CLK/CMD/CTL delays, the trained delays and Vrefs of
every byte of every rank, and the comp, ODT, equalisation and slew settings.
The difference between two dumps of the same machine is what the steps
missing from the NRI change:

```sh
curl -sSLO https://raw.githubusercontent.com/debianita22/ourobios/main/tools/ddr-report.py
sudo python3 ddr-report.py --save nri.txt     # booted on the nri slot
# back on the mrc slot (setup, Firmware Update, or update.py other-slot)
sudo python3 ddr-report.py --save mrc.txt
python3 ddr-report.py --compare mrc.txt nri.txt
```

The trained delays change a little from one cold boot to the next with the
same firmware; timings, turnarounds, latencies and electrical settings do
not.

## Limits

- The early console keeps 16 KiB. The log of a cold boot training is longer:
  `cbmem -c` reports *Pre-CBMEM romstage console overflowed* and keeps the
  last 16 KiB: on the W541 from the receive enable training on (the eyes,
  the command training, the memory test), not the SPD and timing part.
- S3 resume: tried on the W541 with v1.3.9-rc2 (suspend, wake, session
  intact). A report from 2025, with the NRI of that time, had a W541 reboot
  instead of resuming ([coreboot ticket 461](https://ticket.coreboot.org/issues/461));
  patch 0010 resets the machine when the S3 fast path fails.
- A training or a memory test that fails twice stops the boot; on a slot
  under trial, as after `update.py other-slot`, vboot goes back to the other
  slot after two tries ([docs/vboot.md](vboot.md)).
