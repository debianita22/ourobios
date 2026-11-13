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

## v1.7.0-rc6: the steps of the MRC (MEM-19, MEM-20, MEM-21)

rc6 (`2f1246a`: rc5 with the NRI patches 0302-0306, read in the MRC of
the stock firmware of the W541, and the M920x work to `638e640`) as a
capsule from rc5, 2026-11-12: slot A, over rc4; rc5 stays in slot B
([files](rc6/)). One training so far.

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc5; rc6 from slot A |
| MEM-19 | PASS | *TAT C0/C1: tWRRD_dr/dd 3 (was 4)*: `tWRRD 20/3/3`, as with `mrc.bin`; the turnaround test passed with the read and write timing and voltage at ±7 |
| MEM-20 | write and command Vref PASS, read FAIL of the margins | command Vref -5 (scan centre -4, margins 37.0 / 36.0); write Vref 4 and 0 (scan centres 5 and 2, then the three-timing margins: channel 1 low 23.6-25.7, high 18.0-23.0); per-bit receiver offsets centred on the data (4 to d, none at 0 or f), the byte references not moved (+0); but every read timing margin 2 to 4 ticks narrower than with rc5 (below) |
| MEM-21 | FAIL, a bug found | the per-byte choices go the way of `mrc.bin` on channel 1 (read termination +2 and +4 on bytes 6 and 7, transmit equalisation 3 to 5, `mrc.bin` 51-56), but `optimise_comp()` then moved the read termination into the global code: static legs off, global code 8 to 24, the offsets of most bytes clamped to -16, that is a much weaker termination than trained. Patch 0307 for rc7 |
| MEM-10 | PASS | one training, 3.74 s (rc5: 2.3-2.5 s), then the cache (0.11 s) |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after a resume: 0 failed, no machine check; the same after a reboot, a cold boot and a resume |
| FLASH-06, VAR-01 | PASS | `OptionLockStatus` armed; twenty writes of `Timeout`: median 0.153 s |

The margins after the training (time in PI ticks, voltage in Vref steps;
retrain limits 9 and 16), rc5's three trainings for comparison:

| Rank | RdT left / right | WrT left / right | RdV low / high | WrV low / high |
|---|---|---|---|---|
| C0R0 | 17/16 (rc5 19-20) | 18/19 | 27/29 | 20/27 |
| C0R1 | 17/16 (rc5 19-20) | 19/20 | 30/33 | 27/26 |
| C0R2 | 17/16 (rc5 20-21) | 20/21 | 26/27 | 40/28 |
| C0R3 | 16/17 (rc5 20-21) | 19/19 | 27/28 | 30/32 |
| C1R0 | 10/10 (rc5 13-15) | 15/16 | **16**/19 | 21/23 |
| C1R1 | 11/12 (rc5 13-16) | 15/17 | 19/17 | 22/21 |
| C1R2 | 14/14 | 17/17 | 22/25 | 25/35 |
| C1R3 | 12/16 | 18/18 | 20/28 | 23/33 |

The write margins are as good as rc5's best training and even on both
sides; every read margin is narrower, on both channels. `ddr-report.py`
says why: `DATA_COMP_1 rcomp_odt_up=24` (rc5: 8), `disable_odt_static=1`,
and the read termination offsets of 14 of the 16 bytes at -16. The
per-byte training had measured its choices (-4 to +4) with the static
legs on; `optimise_comp()`, run after it, moved the mean of the offsets
(-1) into the global code, which turned the static legs off, and
recomputed the offsets as differences of codes, clamped to their field.
Patch 0307 moves the mean only when an offset is near the end of its
field, which is what the move is for.

## v1.7.0-rc7: the termination kept as trained (MEM-20, MEM-21)

rc7 (`9d02341`: rc6 with patch 0307) as a capsule from rc6, 2026-11-12:
slot B, over rc5; rc6 stays in slot A ([files](rc7/)). One training so
far: the second and the third (the *XMP profile 1* and *SPD* visits)
when the owner is at the machine.

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc6; rc7 from slot B |
| MEM-21 | PASS of the fix | `DATA_COMP_1 rcomp_odt_up=8`, `disable_odt_static=0`, the read termination offsets as trained (channel 0: 0, -4 x6, -2; channel 1: all 0), drive -2 to +4, transmit equalisation 3 to 5 (`mrc.bin` 51-56: the same range), receiver bias 3 or 5. Against rc6 the choices of channel 1 differ (rc6: termination +2 and +4 on bytes 6 and 7): one more training to see whether they are measured or noise |
| MEM-19 | PASS | `tWRRD 20/3/3` again |
| MEM-20 | PASS, two read margins of channel 1 one step below | command Vref -5 (margins 37.0 / 35.0), write Vref 4 and 2 (margins at the three write timings within 2 steps of even); read margins back to rc5's best on channel 0 (RdT 18-21), the write voltage margins of both channels the widest yet (channel 1 21-34, rc5 15-33); C1R0 RdV high 16 and C1R1 RdV low 15, at and one below the retrain limit, the margin check only reports |
| MEM-10 | PASS | one training, 3.62 s, then the cache (0.11 s) |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after a resume: 0 failed, no machine check; the same after a reboot, a cold boot and a resume |
| FLASH-06, VAR-01 | PASS | `OptionLockStatus` armed; twenty writes of `Timeout`: median 0.153 s |
| report | PASS but the known ones | [the first boot](rc7/hw-w541-nri-boot1.md): 19 PASS, BOOT-03 INFO (the margin report), no unknown line |

| Rank | RdT left / right | WrT left / right | RdV low / high | WrV low / high |
|---|---|---|---|---|
| C0R0 | 19/18 | 19/20 | 28/32 | 29/29 |
| C0R1 | 19/19 | 19/20 | 29/31 | 28/28 |
| C0R2 | 20/20 | 21/22 | 38/36 | 41/35 |
| C0R3 | 21/20 | 21/21 | 37/35 | 37/39 |
| C1R0 | 12/12 | 17/16 | 18/**16** | 23/22 |
| C1R1 | 13/13 | 15/16 | **15**/20 | 22/21 |
| C1R2 | 16/17 | 17/18 | 29/28 | 25/34 |
| C1R3 | 16/16 | 17/18 | 25/31 | 24/32 |

Against rc5's three trainings: channel 0 as wide in the reads and wider
in the writes; channel 1 wider in the writes on every rank, and its
first DIMM (C1R0, C1R1) still the narrow one in the reads, as in rc5's
first training. Whether that is still a spread between trainings is
what the second and third trainings of rc7 are for.

## v1.7.0-rc11: the lock of every option and the reclaim in SMM (LOCK)

rc8 to rc10 changed nothing of the W541's coreboot configuration (the
HSTI of `edk2/0063` and the reclaim of the M920x): rc8 was checked and
not installed. rc11 (`e190a98`) gives the W541 what the M920x runs,
`SMMSTORE_OPTION_LOCK_ALL`, `SMMSTORE_RECLAIM` and
`DRIVERS_OPTION_CFR_LOCK_AT_BOOT` (the SMM stack at 8 KiB); the RAM init
is rc7's. As a capsule from rc7, 2026-11-12: slot A, over rc6; rc7 stays
in slot B ([files](rc11/)). The scripts of the M920x
(`docs/tests/v1.7.0/m920x-fsp/scripts`), `lock03.sh` with the W541's
disk; the copies of the flash need `spi_intel_platform` unloaded, or
flashrom reads 8 of the 12 MiB.

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc7; rc11 from slot A, *riuscito*; the training kept (`Using cached memory parameters`, 0.11 s) |
| LOCK-01, 0284 | PASS | `OptionLockStatus` `06 00 00 00` and eight zeros; ramstage: *SMMSTORE: option lock for every setup option, armed by the payload*; all 68 options with `CFR_OPTFLAG_LOCK_AT_BOOT` (and 10 read-only ones) |
| LOCK-02 | PASS | 8 SMIs a write; 0.036 s at boot, 0.027 s after the reclaim at boot (v1.7.0-rc7: 0.153 s) |
| LOCK-03 | PASS | a boot entry created and deleted, the entries as before; the test variable created, changed, deleted |
| **LOCK-11** | **FAIL: the EFI runtime services lost** | from a store with 131 KiB free, 115 writes of 1000 bytes went through, the store at 5.8 KiB free, with no slow write; the 116th, the one that needed the reclaim, failed with `EIO`, and the kernel logged `[Firmware Bug]: Page fault caused by firmware at PA: 0xff910048`, *Froze efi_rts_wq and disabled EFI Runtime Services* ([log](rc11/lock11-kernel-fault.txt)). Until the reboot every variable read failed too (`efibootmgr`: *Skipping unreadable variable "Boot0000": Input/output error*). No commit record and no note of the handler in the flash (the SMI never came) |
| LOCK-06, after the reboot | PASS | the payload reclaimed at its start: 145 KiB free, 199 records, the same 68 options as before the run; no record to finish |
| LOCK-04 | PASS | three resumes from S3: the lock armed, PR0 and PR1 back, LOCK-02 and LOCK-03 work |
| CONF-08 | WARN, one failure not known | 8 of 13; the known limits (descriptor and ME region writable by the host, Secure Boot off, no pre-boot DMA protection) and *SMM: the TSEG base is not locked*: `TSEGMB` (00:00.0 0xb8) reads `0x7f800000`, lock bit clear, where every other lock of `northbridge_final()` is set (BDSM, BGSM, TOLUD, TOUUD, REMAP, DPR, `SMRAMC` D_LCK) and that function writes it with them. Not new in rc11: the HSTI is the first to look (patch 0308, below) |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after the resumes: 0 failed, no machine check |
| LOCK-05, LOCK-09, LOCK-10 | not run | LOCK-05 with the next capsule; LOCK-10 needs the setup; LOCK-09 is the behaviour before the reclaim |

**Why LOCK-11 fails on the W541.** 0xff910048 is the variable store as
the flash is mapped (the 12 MiB flash ends at 4 GiB, so it starts at
0xff400000; `SMMSTORE` is at 0x510000 of it, and the store follows the
0x48 bytes of the firmware volume header): `Reclaim()` of the variable
driver walks the store there, at `NonVolatileVariableBase`. The fault is
at the physical address in virtual mode: the pointer was not converted
at `SetVirtualAddressMap()`, because the memory map that the OS got has
no runtime region for the flash. The only `EfiMemoryMappedIO` with
`EFI_MEMORY_RUNTIME` is 17 pages at 0x7f5e9000, the com buffer
([runtime map](rc11/efi-runtime-map.txt)); the M920x with rc10 has a
second one, 128 pages at 0xff410000, its store.

The cause, read in the sources: the memory table of coreboot on Haswell
has no entry for the flash (the last one below 4 GiB is
0xfed90000-0xfed91fff; Cannon Lake reserves the BIOS region, and the
payload makes every reserved range above the memory an MMIO range of
its GCD), so on the W541 the store is in a hole of the GCD.
`SmmStoreLibInitialize()` asks for the descriptor of the store and adds
the range only if that fails; `GetMemorySpaceDescriptor()` succeeds on a
hole, as `EfiGcdMemoryTypeNonExistent`, and
`SetMemorySpaceCapabilities()` and `SetMemorySpaceAttributes()` succeed
on it too, with no effect on the memory map, which lists only MMIO
ranges. Until rc10 nothing read the store at runtime; the reclaim of
`edk2/0064` does. On the W541 a store filled from the OS so turns the
runtime services off instead of refusing the write, which is worse than
rc7, where the write failed with `ENOMEM`: rc11 is not to release for
the W541.

**Fixed for the next candidate** (`e2337c6` on
`ci-test/v1.7.0-m920x-option-lock`; the CI build ci-375 is green, and
not on a machine yet: the CI builds have no capsule):

- `edk2/0065`: `SmmStoreLib` adds the store as runtime MMIO when the GCD
  has it as non-existent, and the variable driver does not reclaim at
  runtime when the store in the flash could not be converted at
  `SetVirtualAddressMap()`: on any board a full store then fails the
  write, as before `edk2/0064`, where rc11 faults;
- patch 0308, for CONF-08: a write of the lock bit of `TSEGMB` from the
  OS does not take (`setpci -s 00:00.0 b8.l=7f800001` reads back
  `7f800000`): with `D_LCK` set the host bridge no longer takes writes
  to the register, and `northbridge_final()` runs after `smm_lock()`.
  The patch sets the bit in `smm_lock()`, before `D_LCK`; whether it
  takes there is what the next candidate shows.

To run on it: LOCK-11 (the first reclaim in SMM on a Lynx Point), the
runtime map with the store, CONF-08 with 9 of 13, `TSEGMB` after a
resume.

## v1.7.0-rc12: the store mapped at runtime, the TSEG lock bit

rc12 (`e2337c6`: rc11 with `edk2/0065` and patch 0308) as a capsule from
rc11, 2026-11-12: slot B, over rc7; rc11 stays in slot A
([files](rc12/)). The same chain as rc11.

| ID | Result | Notes |
|---|---|---|
| UPD-01, UPD-02, LOCK-05 | PASS | the capsule (`SHA256SUMS` OK, signature valid) written by the payload of rc11 with the lock of every option armed; rc12 from slot B, *riuscito*; the training kept |
| `edk2/0065` | PASS | the runtime memory map has the store: `EfiMemoryMappedIO` 0xff910000, 128 pages, next to the com buffer |
| **LOCK-11** | **PASS** | 600 writes of 1000 bytes from a store with 137 KiB free: four reclaims through coreboot, at the 121st, 241st, 361st and 481st write, 8.9 to 9.2 s each (2.2 to 2.4 s on the M920x: the SPI controller of the Lynx Point is the slower one), the other writes as usual; the 601st failed with `ENOSPC`, the limit of four a boot, and the handler left its note (*reclaims of the boot used*). No firmware fault, no warning in the kernel log, the runtime services on |
| After the limit | PASS | until the reboot a write that does not fit fails with `ENOSPC` (`efibootmgr`: *Could not prepare Boot variable: No space left on device*), the reads work; the reboot reclaims at the start of the payload (145 KiB free, 200 records), no record to finish |
| LOCK-06 | PASS | the 68 options of the copy after the reboot are those of before the run |
| LOCK-01, 0284, LOCK-02, LOCK-03 | PASS | as rc11: the lock armed, 68 options with `CFR_OPTFLAG_LOCK_AT_BOOT`, 8 SMIs and 0.031 s a write |
| Patch 0308, CONF-08 | PASS | `TSEGMB` reads `0x7f800001` at boot, after the reboot, the cold boot and three resumes: the lock bit takes before `D_LCK`. HSTI 9 of 13, the four known limits, none unknown |
| LOCK-04 | PASS | three resumes: the lock armed, PR0 and PR1 back, LOCK-02 and LOCK-03 work |
| MEM-04 | PASS | `stress-ng --vm 4 --vm-bytes 75% --verify`, 30 minutes after the resumes: 0 failed, no machine check |
| LOCK-10 | PASS | by the owner, 2026-11-13: a change saved before any boot is kept (*Memory profile*); after a boot option that returned (iPXE without a network), the setup refused to save a change with the message that the settings are locked until the next restart |
| report | PASS but the known ones | [the first boot](rc12/hw-w541-nri-boot1.md): 22 PASS; ME-01 and EC-01 WARN |

One thing to know: a reclaim at runtime is one SMI of 9 s on the W541,
with every processor in SMM. Linux logged nothing (no soft lockup, no
clocksource warning), and it happens only when the OS fills the store,
at most four times a boot.


### The second and third training of the RAM init of rc7 (MEM-20, MEM-21)

The RAM init of rc12 is that of rc7 (patches 0302-0307). Its first
training is [rc7's](#v170-rc7-the-termination-kept-as-trained-mem-20-mem-21);
the second by *XMP profile 1* on modules without one (byte 0x7d `0xb0`,
*using the SPD timings*), the third back on *SPD* (`0xa0`), 2026-11-13,
each with *Memory test passed* and no training done again
([logs](rc12/)).

| | Training 1 (rc7) | Training 2 | Training 3 |
|---|---|---|---|
| Command Vref | -5 | -5 | -6 |
| Write Vref, channel 0 / 1 | 4 / 2 | 5 / 1 | 5 / 1 |
| `tWRRD_dr/dd` | 3 | 3 | 3 |
| RAM init | 3.62 s | 3.44 s | 3.42 s |
| C0 RdT, all ranks | 18-21 | 19-20 | 19-21 |
| C0 RdV | 28-38 | 28-38 | 26-37 |
| C0 WrV | 28-41 | 26-40 | 26-42 |
| C1R0 RdT / RdV / WrV | 12/12, 18/**16**, 23/22 | 15/15, 23/25, 23/25 | 16/15, 23/24, 25/26 |
| C1R1 | 13/13, **15**/20, 22/21 | 15/16, 25/24, 27/23 | 15/15, 24/23, 25/24 |
| C1R2 | 16/17, 29/28, 25/34 | 18/17, 34/36, 28/34 | 17/17, 33/36, 27/35 |
| C1R3 | 16/16, 25/31, 24/32 | 18/18, 35/38, 25/34 | 17/19, 35/34, 26/34 |

- MEM-19 PASS: the turnaround 3 in every training.
- MEM-20, the Vrefs: PASS. The write Vref of each channel within one
  step in the three trainings (rc5: 3, 0, 0 on channel 1), the command
  Vref within one (rc5: -6, -4, -4), and the write voltage margins of
  channel 1 within 3 steps and even on both sides (rc5: 15 to 24).
- MEM-20, the reads of channel 1: not there yet. Two trainings of three
  have every margin above the limits, as wide as rc5's best; the first
  had the reads of channel 1 narrower on every rank (RdV 5 to 9 steps,
  RdT 2 to 3 ticks), with two margins of its first DIMM at and one below
  the retrain limit. The same share as rc5 (one narrow training in
  three), so the steps of 0304 to 0306 did not remove the spread of the
  reads; the writes they did.
- MEM-21: the per-byte choices are not the same from one training to
  the next (the read termination of channel 0 nearly so: -4 on bytes 1
  and 3 to 6 each time; that of channel 1 and the drive strength change),
  so on channel 1 the measure is within its noise, and the choices are
  not what makes the narrow training: training 2 and 3 differ in them
  and have the same margins.

What the narrow training has that the others have not is still to
find: the three logs and register dumps are here for it. What is left
to compare are the steps before the new ones (receive enable, the 1D
read centring, the sense amplifier offsets that the per-bit step now
overwrites), and a retrain when the margin check fails
(`HASWELL_NRI_MARGIN_CHECK_RETRAIN`, off) would turn a narrow training
into another draw.

## The reads of channel 1 after a power-up: the dGPU (MEM-22)

With rc5 to rc12 one training in three came out with the reads of
channel 1 narrower (RdT 2 to 4 ticks, RdV 5 to 9 steps, every rank, two
margins of C1R0 and C1R1 at or below the retrain limit). Looked into on
2026-11-13 with rc12's RAM init, the trainings made by *XMP profile 1*
on modules without one and byte 0x7d written from Linux ([files](heat/)):

| What came before the training | Trainings | C1R0 RdT / RdV, the range |
|---|---|---|
| a power-up: a capsule's reset (rc3 to rc7), a power cycle reset (`CF9` `0x0e`), a boot from off | 7, and 3 more with the diagnostic builds | 10-14 / 14-21, two of them below the retrain limit |
| a warm reset (the setup, `systemctl reboot`), the processor cool (41 C) or hot (79 C) | 12 | 15-16 / 22-26 |
| a warm reset with the dGPU powered on from Linux (`pmh7.py dgpu on`) | 2 | 11-12 / 14-19 |
| the same, the dGPU left off | 2 | 16 / 24-26 |

Not the temperature, and nothing within the boot: two diagnostic builds
(not released, branch `ci-test/w541-nri-powerup-diag`) measured the
margins again after 3 s, after a ZQ calibration, with the periodic
compensation on and after a second training in the same boot, all as
narrow; the registers of the memory controller at the training were the
same after a power-up and after a warm reset. The dGPU is: the EC powers
it on at power-up and keeps its state across a warm reset (PMH7 0x50,
bit 3), and the firmware turned it off, *Dual graphics* being off, in
`mb_late_romstage_setup()`, after the RAM init. So every training after
a power-up ran with the dGPU powered and every one after a warm reset
without, and the board runs without. Patch 0309 sets it before the RAM
init (`b5a44b4` on `ci-test/v1.7.0-m920x-option-lock`); MEM-22 runs it.

MEM-22 with the CI build of `b5a44b4` (ci-381, written to slot B with
flashrom, BIOS Lock off by the owner), 2026-11-13 ([files](fix/)): PASS.

| Training | Before it | C1R0 RdT / RdV | C1R1 RdT / RdV | Margin check |
|---|---|---|---|---|
| f0 | warm reset (the new version of the saved training) | 15/15, 25/22 | 14/16, 26/21 | passed |
| f1 | power cycle reset | 14/15, 22/22 | 14/15, 23/23 | passed |
| f2 | power cycle reset | 16/15, 23/24 | 15/16, 25/23 | passed |
| f3 | boot from off (90 s) | 16/15, 23/24 | 14/14, 24/21 | passed |
| f4 | warm reset | 15/15, 22/25 | 15/16, 24/24 | passed |

After a power-up as after a warm reset, within a tick and 3 steps;
PMH7 0x50 reads `0x70` (dGPU off) in Linux each time. Channel 0 as
before (RdT 18-21, RdV 27-40), and the writes of both channels too.


## The machine after the run

v1.7.0-rc12 in slot B, rc11 in slot A, with its third training;
*Memory profile* on *SPD*, byte 0x7d
`0xa0`; *BIOS Lock* and *Firmware protection* on; no helper left.
