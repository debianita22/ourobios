# v1.7.0-rc1 on the W541

The ThinkPad W541 of the port (`nri`), 2026-11-10: v1.7.0-rc1, built from
`ci-test/v1.7.0-nri-xmp` (`19e053a`, patches 0275-0280), as a capsule from
v1.6.3-rc4 with *BIOS Lock* on: slot B, rc4 kept in slot A. The modules are
the four DDR3L SO-DIMMs of the port, which have no XMP profile (bytes
176 and 177 of each SPD, read from Linux through `at24`, are `ff ff`
where an XMP header has `0c 4a`), so MEM-13 cannot run here. The baseline is a `ddr-report.py` dump of rc4 taken
before the update (write Vref 0 on both channels).

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc4; v1.7.0-rc1 from slot B, *riuscito* |
| MEM-14 | PASS | below: the write Vref centred, C0 at 3 and C1 at -1, the same after a reboot, a cold boot and a resume; *Memory test passed* |
| MEM-10 | PASS | *Memory profile* at *SPD*: one training at the first boot (0.98 s, the version of the saved training changed), then the cache (0.11 s); no *Memory profile* line; byte 0x7d `0xa0`; timings (DDR3-1600 at 1.35 V, CL11, 2N), round trips and latencies those of rc4: of the 226 fields that differ from rc4, all are trained values or the write Vref ([compare](ddr-compare-rc4-vs-boot1.txt)) |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify` for 30 minutes after a resume: 4 passed, 0 failed, no machine check ([log](stress-30m.txt)) |
| MEM-11 | PASS, one line hidden | below: *XMP profile 1* on modules without one: the SPD timings, byte 0x7d `0xb0`, the resume works; back on *SPD* `0xa0` with no training |
| MEM-12 | PASS, one line hidden | below: `0xb2` gives the profile up (`0xa4`, then *XMP profile 1 failed before*); `0xb6` on *SPD* reads `0xa0` after a reboot |
| MEM-13 | not run | no DDR3L SO-DIMMs with an XMP profile at hand |
| reports | PASS but the known ones | [the first boot](hw-w541-nri-boot1.md): 18 PASS, ME-01 and EC-01 WARN, MEM-01 INFO (the training boot), BOOT-03 WARN for the two lines of the write Vref step below |

## MEM-14: the write Vref

| Boot | RAM init | C0 | C1 | Byte 0x7d |
|---|---|---|---|---|
| the first, which trains | 0.98 s | eye -16 to 23, width 39: Vref 3 | eye -17 to 15, width 32: Vref -1 | `0xa0` |
| a reboot | 0.11 s, the cache | 3 | -1 | `0xa0` |
| a cold boot from the RTC alarm | 0.11 s, the cache | 3 | -1 | `0xa0` |
| after a resume from S3 | 0.11 s | 3 | -1 | `0xa0` |
| after 30 minutes of stress-ng | | 3 | -1 | `0xa0` |

The ranges are closed on both sides (well inside -54 and 54) and wider than
8; `ddr-report.py` reads `vref_dq_ch0_ctrl=3` and `vref_dq_ch1_ctrl=-1` in
`VREF_ADJUST`. Against the training boot, the later states differ only in
the compensation codes (`*_COMP`, which follow the temperature), nothing
trained. The training of MEM-11 centred again at 4 and 1 (eyes -15 to 23
and -17 to 19): the spread of two trainings.

The first boot logs *Vref circuit 0 failed to converge* and *Vref circuit 1
failed to converge* once each, not at every value: the first value of the
scan jumps from 0 to -54, longer than the 50 µs that
`update_vref_and_wait()` waits for the done bit; the step waits 1 ms
(`WRV_SETTLE_MS`) right after that jump. Harmless, but `hw-report.py`
counts them in BOOT-03; passing `skip_wait` for that first jump would
leave the log clean.

## MEM-11 and MEM-12: the profile and the giving up

The owner set *Hardware* → *Memory* → *Memory profile* to *XMP profile 1*,
then back to *SPD*; the agent did the rest ([log](mem11-mem12.log)).

| Step | Result |
|---|---|
| XMP profile 1, the first boot | one training (the option is in the version), the SPD timings (the timing table equal to MEM-10's), byte `0xb0` |
| XMP profile 1, a boot with the cache | *Memory profile: XMP profile 1 requested*, *CH0S0 has no XMP profile 1, using the SPD timings*, byte `0xb0`; a resume from S3, byte `0xb0` |
| `0xb2` written (two boots not confirmed), a reboot | byte `0xa4`, one training |
| a second reboot | *Memory profile: XMP profile 1 failed before, using the SPD timings. Select the SPD timings once to try it again*, the cache |
| *SPD* again | byte `0xa0`, no *Memory profile* line, the cache (no training: the version follows the profile in use, which was the SPD timings already after the giving up) |
| `0xb6` written on *SPD*, a reboot | byte `0xa0` |

After each write of the byte the system clock, the RTC and the network time
agreed.

**The lines of the training boots are lost.** On every boot that trains,
the console of romstage before CBMEM overflows (*Pre-CBMEM romstage console
overflowed, log truncated*) and the first lines of romstage go: here
*Memory profile: XMP profile 1 requested* and *has no XMP profile 1* of the
first boot with the profile, and *2 boots in a row with XMP profile 1 did
not reach the payload* of the boot that gives up, which trains again. The
state shows that they ran (the bytes, the next boots' lines), but MEM-11
and MEM-12 expect to read them: a larger pre-CBMEM console for the `nri`
variant, or the decision logged again after CBMEM, would keep them.

## v1.7.0-rc2: the command Vref (MEM-15)

rc2 (`01a3449`: the patches of rc1 with 0278 and 0280 revised, 0290, and
the option lock patches 0281-0283) as a capsule from rc1, 2026-11-11:
slot A, over v1.6.3-rc4; rc1 stays in slot B ([files](rc2/)).

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc1; rc2 from slot A, *riuscito* |
| MEM-15 | PASS | *CMDV: eye -40 to 30, width 70, centre -5, Vref 0*, *CMDV: command Vref -5 (was 0)*: closed on both sides, wider than 20 (`mrc.bin` leaves -3); `vref_ca_ctrl=-5` in `ddr-report.py`, the same after a reboot, a cold boot, a resume and the stress; *Memory test passed*; RAM init of the training boot 1.10 s (0.98 s with rc1), 0.11 s from the cache |
| MEM-14 again | PASS | the *WRV:* lines after the *CMDV:* ones: C0 eye -20 to 23, Vref 1; C1 eye -17 to 17, Vref 0 (rc1: 3 and -1, 4 and 1, 2 and -1); no *failed to converge*, no *did not settle* (patch 0280 revised) |
| MEM-10 | PASS | one training at the first boot, then the cache; no *Memory profile* line; bytes 0x7d and 0x7e `0xa0`; the timings of rc1 |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify` for 30 minutes after a resume: 0 failed, no machine check ([log](rc2/stress-30m.txt)) |
| FLASH-06, VAR-01 | PASS | `OptionLockStatus` `06 00 00 00` and eight zeros; twenty writes of `Timeout`, all done: median 0.139 s, worst 0.139 s (0.27 s up to v1.6.3-rc3, before patch 0273); back at 3 s ([numbers](rc2/optlock.txt)) |
| report | PASS but the known ones | [the first boot](rc2/hw-w541-nri-boot1.md): 19 PASS, BOOT-03 PASS, ME-01 and EC-01 WARN, MEM-01 INFO (the training boot) |
| MEM-11, MEM-12 again | PASS | with the owner's two setup visits ([log](rc2/mem11-mem12.log)): on the boot that trains, *Memory profile: XMP profile 1 requested* and *CH0S0 has no XMP profile 1, using the SPD timings* are in the log, said again after CBMEM ([log of that boot](rc2/cbmem-mem11-training.txt)), byte `0xb0`; the same on the cache boot and after a resume; `0xb2` written: *2 boots in a row with XMP profile 1 did not reach the payload, using the SPD timings from now on* on the boot that gives up and trains, byte `0xa4`; then *XMP profile 1 failed before*; *SPD* again: `0xa0`, no line, the cache; `0xb6` written on *SPD*: `0xa0` after a reboot; the clock right after each write |

Against rc1, the command timings of the training boot moved by one or
two steps (CLK, CTL and CMD PI of the two channels), as between two
trainings of rc1 ([compare](rc2/ddr-compare-boot1.txt)). Against the
training boot, the reboot, the cold boot, the resume and the state after
the stress differ only in compensation codes and in the output code of
the Vref circuit, which follow the temperature: nothing trained.

## v1.7.0-rc3: the margins measured, the turnaround test (MEM-17, MEM-16)

rc3 (`f9dedc6`: rc2 with the option lock patch 0284, `edk2/0062` and
the NRI patches 0291-0298) as a capsule from rc2, 2026-11-11: slot B, over
rc1; rc2 stays in slot A ([files](rc3/)).

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc2; rc3 from slot B, *riuscito* |
| MEM-17 | PASS, three margins below the limits | the table below, complete: every search of the margin library ended (no *giving up*; patch 0296); *Margin limit check failed* and *Margins below the retrain limits, training kept*: the check only reports |
| MEM-16 | FAIL of the step, nothing changed | *TAT: Cn write to read, other rank, N: pass* for 4, 3, 2 and 1 on both channels, then *no value fails, test not usable, left at 4*: the turnaround test as patch 0298 sets it up does not see the turnaround (one clock cannot pass). `tWRRD` stays `20/4/4`, as the step is written to do |
| MEM-15, MEM-14 again | PASS | command Vref -6 (rc2: -5, -4), write Vref 2 and 1; no *failed to converge*; the same after a reboot, a cold boot, a resume and the stress |
| MEM-10 | PASS | one training (1.93 s: 1.10 s with rc2, the margin check and the turnaround test take 0.83 s), then the cache (0.11 s); bytes 0x7d and 0x7e `0xa0` |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after a resume: 0 failed, no machine check |
| FLASH-06, VAR-01 | PASS | `OptionLockStatus` `06 00 00 00` and eight zeros; twenty writes of `Timeout`: median 0.139 s; back at 3 s |
| report | BOOT-03 FAIL for the new lines | [the first boot](rc3/hw-w541-nri-boot1.md): 18 PASS; BOOT-03 counts the error and the warnings of the two new steps, which `hw-report.py` does not know yet; ME-01 and EC-01 WARN, MEM-01 INFO (the training boot) |

The margins of each rank after the training, each side: time in PI ticks
(64 per bit), voltage in steps of the reference. The retrain limits of
the MRC are 9 ticks and 16 steps.

| Rank | RdT left / right | WrT left / right | RdV low / high | WrV low / high |
|---|---|---|---|---|
| C0R0 | 18 / 18 | 17 / 17 | 26 / 26 | 21 / 22 |
| C0R1 | 18 / 19 | 15 / 17 | 24 / 27 | 21 / 18 |
| C0R2 | 18 / 19 | 19 / 20 | 36 / 37 | 36 / 22 |
| C0R3 | 18 / 19 | 17 / 19 | 36 / 37 | 35 / 24 |
| C1R0 | 16 / 11 | 14 / 14 | **14** / 20 | **15** / 17 |
| C1R1 | 14 / 13 | 14 / 14 | 17 / 18 | **15** / 20 |
| C1R2 | 16 / 14 | 15 / 15 | 26 / 28 | 20 / 29 |
| C1R3 | 16 / 14 | 15 / 16 | 27 / 29 | 22 / 29 |

Channel 1 is the narrower one, and its first DIMM (ranks 0 and 1) the
narrowest: three voltage margins there are one or two steps below the
limit of 16, the read timing of C1R0 is off centre (16 left, 11 right),
and the write Vref of a channel is one for its four ranks (ranks 2 and 3
of channel 0 would take a reference some 6 steps lower than ranks 0 and
1). This is what the 2D centring and the per-rank steps of the MRC work
on; with these numbers as the measure of before, the 2D centring can be
tried in a candidate of its own.

Against the training boot, the later states differ only in compensation
codes. `mrc.bin` on the same machine was not measured with this check: it
has its own.

## v1.7.0-rc4: the 2D centring, the turnaround test in several forms (MEM-18, MEM-16)

rc4 (`ab61309`: rc3 with the 2D centring on, patches 0299 and 0300, and
the option lock work of the M920x branch to `c0dd6aa`) as a capsule from
rc3, 2026-11-11: slot A, over rc2; rc3 stays in slot B ([files](rc4/)).

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc3; rc4 from slot A, *riuscito* |
| MEM-18 | mixed | the 2D centring ran to the end and the memory test passed; channel 0 wider on every rank, channel 1 ranks 2 and 3 wider, its first DIMM narrower in the read timing (below); per-bit codes trained, from 4 to c, none at 0 or f (`RxPerBit`, `TxPerBit`); *Vref circuit 1 failed to converge* three times during the 2D centring of the writes (the only unknown line of BOOT-03) |
| MEM-16 | the test sees errors, the turnaround is not measurable this way | the `TATD:` lines below: every form between ranks passes at every value down to 0, the control on one rank passes, the same-rank control fails below 16; *no value fails, test not usable, left at 4* |
| MEM-17 | PASS, the table of rc4 | *Margin limit check failed*, the training kept: C1R0 WrV low 16, C1R1 RdV low 12 and WrV low 15 at or below the limit |
| MEM-15, MEM-14 again | PASS | command Vref -4, write Vref 2 and -1; the same after a reboot, a cold boot, a resume and the stress |
| MEM-10 | PASS | one training (2.50 s: 1.93 s with rc3, the 2D centring takes 0.57 s), then the cache (0.11 s) |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after a resume: 0 failed, no machine check |
| FLASH-06, VAR-01 | PASS | `OptionLockStatus` armed; twenty writes of `Timeout`: median 0.153 s; back at 3 s |
| report | BOOT-03 WARN | [the first boot](rc4/hw-w541-nri-boot1.md): 18 PASS; the margin report and the turnaround left as it was as events (INFO), the *failed to converge* lines as the one unknown |

The margins after the training, rc3 then rc4 (time in PI ticks, voltage
in Vref steps; retrain limits 9 and 16):

| Rank | RdT left / right | WrT left / right | RdV low / high | WrV low / high |
|---|---|---|---|---|
| C0R0 | 18/18 → 19/20 | 17/17 → 18/17 | 26/26 → 29/28 | 21/22 → 20/25 |
| C0R1 | 18/19 → 20/20 | 15/17 → 18/18 | 24/27 → 29/30 | 21/18 → 22/25 |
| C0R2 | 18/19 → 20/21 | 19/20 → 19/20 | 36/37 → 38/38 | 36/22 → 35/32 |
| C0R3 | 18/19 → 21/21 | 17/19 → 18/19 | 36/37 → 36/38 | 35/24 → 33/33 |
| C1R0 | 16/11 → **11/12** | 14/14 → 15/14 | 14/20 → 18/18 | 15/17 → 16/21 |
| C1R1 | 14/13 → **12/14** | 14/14 → 15/14 | 17/18 → **12/19** | 15/20 → 15/22 |
| C1R2 | 16/14 → 17/16 | 15/15 → 16/17 | 26/28 → 24/31 | 20/29 → 20/33 |
| C1R3 | 16/14 → 17/18 | 15/16 → 16/16 | 27/29 → 25/28 | 22/29 → 18/33 |

On channel 0 every eye is wider, and the write voltage margins, which
were lopsided on ranks 2 and 3 (36/22, 35/24), are now even. On channel
1 the read timing of the first DIMM lost width (C1R0 27 to 23 ticks in
all, C1R1 27 to 26) and C1R1 its low read voltage margin (17 to 12),
while its write margins grew. One training each: part of the difference
can be the spread between two trainings, and the three *failed to
converge* lines say that some of the write Vref moves of channel 1 did
not settle in the 50 µs that `update_vref_and_wait()` waits, so some
points of that DIMM may have been measured at a reference still moving.

The turnaround test, rc4 (`TATD:`, each value from the one set, P pass, F fail):

```
C0 20/4/4 C1 20/4/4 as set (sr/dr/dd)
4 ranks, 1 line   dr+dd  4P 3P 2P 1P 0P   (both channels)
4 ranks, 8 lines  dr+dd  4P 3P 2P 1P 0P
4 ranks, ODT      dr+dd  4P 3P 2P 1P 0P
ranks 0+1         dr     4P 3P 2P 1P 0P
ranks 0+2         dd     4P 3P 2P 1P 0P
rank 0 alone      dr+dd  4P 3P 2P 1P 0P   (control: no turnaround between ranks)
rank 0 alone      sr     20P 16P 12F 8F 4F (control: tWTR violated)
```

The test sees errors (the same-rank control fails as soon as tWTR is
violated), and no form between ranks fails even at 0, where the bursts
would overlap: the memory controller keeps a spacing of its own between
a write and a read of another rank, and the register below that does not
change it. The turnaround between ranks cannot be found by a scan; what
`mrc.bin` sets (3) has to come from the trained delays of the ranks, and
the step of patch 0298 changes nothing, as written.

## v1.7.0-rc5: three trainings of the 2D centring (MEM-18)

rc5 (`3a5d77c`: rc4 with patch 0301, which waits for a late Vref move,
without the turnaround patches 0298 and 0300, and with the option lock
work of the M920x branch to `f783399`) as a capsule from rc4,
2026-11-11: slot B, over rc3; rc4 stays in slot A ([files](rc5/)). The
build had to be run three times: the runners of GitHub could not resolve
the package mirror of Ubuntu for two hours; nothing in the code.

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc4; rc5 from slot B, *riuscito* |
| MEM-18 | PASS | three trainings, below: no *failed to converge* in any (patch 0301), the memory test passed in each; channel 0 the same in the three and wider than with rc3; channel 1 narrow in the first, wider than with rc3 in the other two; the read timing of its first DIMM centred in all three |
| MEM-17 | PASS | the margin check below the limits only in the first training (C1R1 RdV low 15, WrV high 15); none in the second and the third |
| MEM-15, MEM-14 again | PASS | command Vref -6 and write Vref 3/3 in the first training, -4 and 3/0 in the second, -4 and 2/0 in the third; the first the same after a reboot, a cold boot, a resume and the stress |
| MEM-11 | PASS | the second training by *XMP profile 1* on modules without one: *XMP profile 1 requested*, *has no XMP profile 1, using the SPD timings*, byte `0xb0`; back on *SPD* it trained again (the profile had not been given up, unlike in MEM-12), byte `0xa0` |
| MEM-10 | PASS | the trainings take 2.51, 2.30 and 2.32 s, the cache 0.11 s |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after a resume: 0 failed, no machine check |
| FLASH-06, VAR-01 | PASS | `OptionLockStatus` armed; twenty writes of `Timeout`: median 0.153 s |
| report | PASS but the known ones | [the first boot](rc5/hw-w541-nri-boot1.md): 18 PASS; BOOT-03 INFO (the margin report), no unknown line |

The margins of channel 1 in the three trainings of rc5, against rc3 (no
2D centring) and rc4 (time in PI ticks, voltage in Vref steps; retrain
limits 9 and 16):

| Rank | | RdT left / right | WrT left / right | RdV low / high | WrV low / high |
|---|---|---|---|---|---|
| C1R0 | rc3 | 16/11 | 14/14 | 14/20 | 15/17 |
| | rc4 | 11/12 | 15/14 | 18/18 | 16/21 |
| | rc5, 1 / 2 / 3 | 13/13, 15/15, 15/15 | 15/16, 15/14, 15/15 | 19/18, 24/25, 25/24 | 18/18, 17/24, 18/23 |
| C1R1 | rc3 | 14/13 | 14/14 | 17/18 | 15/20 |
| | rc4 | 12/14 | 15/14 | 12/19 | 15/22 |
| | rc5, 1 / 2 / 3 | 13/13, 15/15, 16/15 | 13/15, 14/16, 14/15 | 15/17, 27/24, 24/26 | 22/15, 18/21, 18/23 |
| C1R2 | rc3 | 16/14 | 15/15 | 26/28 | 20/29 |
| | rc5, 1 / 2 / 3 | 15/16, 18/17, 18/16 | 17/18, 17/18, 18/18 | 26/25, 35/34, 35/35 | 26/29, 23/33, 24/32 |
| C1R3 | rc3 | 16/14 | 15/16 | 27/29 | 22/29 |
| | rc5, 1 / 2 / 3 | 16/16, 18/17, 19/17 | 17/18, 17/18, 18/18 | 26/26, 33/34, 34/36 | 22/28, 20/32, 21/33 |

Channel 0 is within a step or two in the three trainings (read timing
19-21 each side, write timing 18-20, read voltage 27-38, write voltage
22-37), one to three steps wider than with rc3 on every rank: that is
the effect of the 2D centring. Channel 1 spreads from one training to the
next more than the 2D centring moves it: the first training of rc5 came
out as narrow as rc3 and rc4 did, the second and the third had every
margin above the limits and the voltage margins of all its ranks 6 to 12
steps wider. The narrow margins seen with rc3 and rc4 were mostly that
spread, not the 2D centring. What the 2D centring does on channel 1 in
every training is the read timing of the first DIMM: centred (13/13,
15/15) where rc3 left it 16/11. The narrow first training also took a
higher write Vref for channel 1 (3, against 0 in the other two) and a
lower command Vref (-6 against -4): which of the trainings of the NRI
decide the spread is still to see.

## The machine after the run

v1.7.0-rc5 in slot B, rc4 in slot A, with the training of the third boot;
*Memory profile* on *SPD*, byte 0x7d
`0xa0`; *BIOS Lock* and *Firmware protection* on; no helper left.
