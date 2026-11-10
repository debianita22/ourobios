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

## The machine after the run

v1.7.0-rc1 in slot B, rc4 in slot A; *Memory profile* back on *SPD*,
byte 0x7d `0xa0`; *BIOS Lock* and *Firmware protection* on; no helper
left.
