# The native RAM init (`nri`)

The `nri` variant trains the memory with coreboot's native RAM init (NRI)
instead of Intel's `mrc.bin`. Upstream still labels it *[NOT COMPLETE]*: it
trains enough to boot and to resume from S3, while some of the steps that
the MRC uses to widen the margins, save power and shorten latencies are not
public yet. This page lists what runs, what this project adds, what is still
missing, how the two compare on the W541, and how to measure them on the
same machine.

- [What runs](#what-runs)
- [On the W541](#on-the-w541)
- [Measuring](#measuring)
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
  whatever the training produced and boots on it;
- **patch 0088**, a shorter read round trip: the receive enable training
  keeps the read data in the I/O two qclks or more longer than it needs to,
  for the board layout; after the command training, the IO latencies and
  round trip latencies go down one qclk at a time while a write and read
  test passes on every rank, and one qclk goes back as a guard band
  ([On the W541](#on-the-w541) for what `mrc.bin` does there). A training
  redone after a failed memory test leaves them as trained.

Missing: the steps the upstream author lists as implemented in his tree and
not published yet ([coreboot ticket 461](https://ticket.coreboot.org/issues/461)),
which widen the margins and lower the power of the memory interface; none
of them is needed to boot. On the W541, `mrc.bin` leaves the results of
each of them in the registers:

- timing and voltage centering together (2D), and the centering of the
  write and command Vrefs of the DIMMs;
- power training: read ODT, drive strength, transmit and receive
  equalisation, receive bias, ODT and sense amplifier windows per byte;
- the deskew of each bit within a byte (the NRI keeps the read offsets at
  zero on purpose, so as not to use up the range of the read strobe delay,
  and the write ones neutral);
- turnaround optimisation. On the W541 only one turnaround differs: write
  to read between ranks, 3 clocks with `mrc.bin` and 4 here. It stays at 4:
  the memory test of patch 0087 works on one rank at a time and would not
  see a turnaround too short, and the NRI does not run the turnaround
  patterns of the REUT yet.

With two DIMMs per channel the NRI runs the commands at 2N, by a TODO in
`lookup_timings.c` written before the late command training existed;
`mrc.bin` does the same on the W541.

## On the W541

i7-4810MQ with four 8 GiB DDR3L-1600 dual-rank SO-DIMMs (two per channel,
four ranks each), `nri` slot of v1.3.9-rc2 tried with `update.py
other-slot`:

- the first boot trains (black screen meanwhile), tests every bank of the
  four ranks of both channels (*Memory test passed*) and saves the training;
  the next boots take the fast path (2.8 s to the payload);
- the eye widths of the 1D training, in PI ticks (64 ticks per unit
  interval, 625 ps at DDR3-1600): read timing 28-44 per byte, write timing
  29-45, read voltage 43-100 half steps; command, control and clock 90-127
  of 128 at 2N. The NRI fails the training below 8;
- suspend to RAM and resume.

The registers after `mrc.bin` (v1.3.9-rc1) and after the NRI (rc2, before
patch 0088), from `ddr-report.py`:

| | `mrc.bin` | NRI |
|---|---|---|
| Voltage, CL-tRCD-tRP-tRAS, tFAW, tRFC | 1.35 V, 11-11-11-28, 24, 208 | the same |
| Refresh interval (2x refresh, `ENABLE_DDR_2X_REFRESH`) | 3.9 µs | the same |
| Command rate | 2N | the same |
| Turnarounds rank to rank (read/read, write/write, read/write) | 6, 7, 11 | the same |
| Turnaround write to read, other rank | 3 | 4 |
| tXP (power down exit) | 6 | 5, the JEDEC minimum |
| Round trip, channel 0 / 1 (qclk) | 44 / 45 | 49 / 49 |
| IO latency + rt_iocomp | 4 + 21 | 7 / 6 + 23 |
| Write Vref channel 0 / 1, command Vref | +3 / +2, -3 | 0, 0 |
| Transmit equalisation | 51-56 per byte | 59 |
| Read ODT offsets, drive offsets per byte | -6..+1, -3..+3 | 0, 0 |
| Per bit deskew, read and write | trained | none |

The round trip is the only difference that changes how fast the memory
answers: 5 and 4 qclks, 3.1 and 2.5 ns per read. The receive enable delays
are the same with both, within 4 PI ticks, and so is round trip minus IO
latency minus rt_iocomp (19 qclks on channel 0, 20 on channel 1): `mrc.bin`
keeps the read data in the I/O for a shorter time, which is what patch 0088
does.

## Measuring

`tools/ddr-report.py` reads the registers of the memory controller (read
only) and shows timings, turnarounds, command rate, round-trip and I/O
latencies per rank, the CLK/CMD/CTL delays, the trained delays and Vrefs of
every byte of every rank, and the comp, ODT, equalisation and slew settings.
The difference between two dumps of the same machine is what the steps
missing from the NRI change:

```sh
curl -sSLO https://raw.githubusercontent.com/debianita22/ourobios/main/tools/ddr-report.py
sudo python3 ddr-report.py --save nri.txt     # booted on the nri slot
# back on the mrc slot (update.py other-slot with the mrc image)
sudo python3 ddr-report.py --save mrc.txt
python3 ddr-report.py --compare mrc.txt nri.txt
```

The trained delays change a little from one cold boot to the next with the
same firmware; timings, turnarounds, latencies and electrical settings do
not.

`tools/mem-latency.c` measures how long a read from the memory takes, with
a chain of pointers in random order through a buffer much larger than the
caches; `tools/idle-report.py` the power at idle. The same commands on each
variant, with the machine on the same power source and at rest:

```sh
curl -sSLO https://raw.githubusercontent.com/debianita22/ourobios/main/tools/mem-latency.c
gcc -O2 -o mem-latency mem-latency.c
./mem-latency                 # median of 9 runs over 512 MiB
```

## Limits

- The early console keeps 16 KiB. The log of a cold boot training is longer:
  `cbmem -c` reports *Pre-CBMEM romstage console overflowed* and keeps the
  last 16 KiB: on the W541 from the receive enable training on (the eyes,
  the command training, the round trip, the memory test), not the SPD and
  timing part.
- S3 resume: tried on the W541 with v1.3.9-rc2 (suspend, wake, session
  intact). A report from 2025, with the NRI of that time, had a W541 reboot
  instead of resuming ([coreboot ticket 461](https://ticket.coreboot.org/issues/461));
  patch 0010 resets the machine when the S3 fast path fails.
- A training or a memory test that fails twice stops the boot; on a slot
  under trial, as after `update.py other-slot`, vboot goes back to the other
  slot after two tries ([docs/vboot.md](vboot.md)).
