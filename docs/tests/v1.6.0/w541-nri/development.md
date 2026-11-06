# What the W541 gives the next five items of the roadmap

Measured on the W541 of the port on 2026-11-05 and 11-06 under
v1.6.0-rc6-nri, Linux 7.3.0-4-cachyos: an i7-4810MQ (4 cores, 8
threads), four SO-DIMMs of DDR3L-1600, 8 GB each, two per channel (32 GB,
dual-channel over all of it), the ME stopped in the BUP (`me_disable`).
For [docs/roadmap.md](../../../roadmap.md): the memory training across
updates, the memory clear on every core, the device switches,
Hyper-Threading, the firmware watchdog. Nothing was written to the
flash; the only writes were the two `SOFT_RESET` registers of the PCH
in the Hyper-Threading test, from Linux, and the TCG MOR variable that
asks for a clear.

## Memory training across updates on the W541

What one update costs today, from `cbmem -t` of the first boot after
the rc6 capsule (which empties `RW_MRC_CACHE`) and of a later boot from
the cache:

| | Training (boot 1) | From the cache |
|---|---|---|
| RAM init (`before` to `after RAM initialization`) | 827 ms | 112 ms |
| elog init in romstage, at the training boot only | 23 ms | — |
| reset to the payload | 2.18 s | 1.44-1.52 s |

So keeping the cache saves about 0.7 s at the first boot after an
update, once: the "few seconds" of the roadmap are 0.7 s with `nri` on
this memory. Files: [cbmem-t-w541-nri-training.txt](cbmem-t-w541-nri-training.txt),
[cbmem-t-w541-nri-cache.txt](cbmem-t-w541-nri-cache.txt).

The cache as it is on the flash (`RW_MRC_CACHE`, 64 KiB at 0x500000):
one entry, metadata `MRCd`, 4108 bytes of data, version 3 (the
`reg_frame_rev()` of patch 0186), the data's xxh32 `0x570886c5`;
`RECOVERY_MRC_CACHE` empty. The region was the same byte for byte
after the training boot, two reboots, a cold boot and three resumes:
`mrc_cache` does not rewrite identical data, so a fast boot costs no
flash write. The first 64 bytes are in
[devices-w541-nri.txt](devices-w541-nri.txt).

What the fast boot checks before it trusts the cache, in the code of
the pin (`save_restore.c`, `restore_non_training()`): the decoded DIMM
parameters of each slot (`ctrl->dimms`, compared with `memcmp`) and the
CPU; nothing about the code that trained. That is the roadmap's point,
and this machine adds one: **its four SO-DIMMs have the same SPD byte
for byte, serial number included** (`de8215a0`, CRC `0x69e7`), and the
part number they carry, Samsung `M471B5273DH0-CK0`, is a 4 GB module
while the SPD describes 8 GB, 2 ranks of x8: relabelled modules with a
copied SPD. Neither `mrc.bin`'s check (a CRC of each DIMM's SPD) nor
NRI's (the decoded parameters) can tell such modules apart, so the
docs' way out without an OS, "a SO-DIMM swapped makes both RAM inits
train again", holds for a module of another kind or for one taken
out (the population changes), not for a swap among identical copies.
The text for the docs, when the item is done: *taken out*, or *replaced
by a module of another type*.

For the design of the key (`N` and a hash of the NRI code at build
time): one more input worth having is the population of the slots,
which `ctrl->dimms` already covers; the SPD serial numbers are not a
key on machines like this one.

## Clearing the memory on every core

What ramstage does on a boot where Linux asked for the clear (TCG MOR
set to 1 from the OS, then a reboot), from `cbmem -1`:

| | |
|---|---|
| Ranges cleared | `0-0x5000`, `0xa000-0xa0000`, `0xc0000-0x7f5ea000` (2.04 GB), `0x7f800000-0x80000000`, `0x100000000-0x85fe00000` (31.67 GB), then `0x5000-0xa000`: 33.82 GB |
| Time | 1647 ms of "exec" at the exit of `BS_DEV_INIT`: 20.5 GB/s on the boot processor |
| The boot | 3.11 s to the payload against 1.45 s without the clear |
| The other processors | up before it: *Attempting to start 7 APs*, *bsp_do_flight_plan done after 88 msecs* |

What one core and more can do on this memory, in Linux with
[memclr.c](memclr.c) (2 GiB per thread, touched first, then zeroed,
the best of three; one thread per core first, then the second threads
of the same cores; the governor at `performance`):

| Threads | `memset` | `rep stosb` | AVX2 non-temporal stores |
|---|---|---|---|
| 1 | 21.8 GB/s | 24.3 GB/s | 21.8 GB/s |
| 2 | 12.3 GB/s each, 24.6 together | 11.9 each, 23.8 | 12.3 each, 24.6 |
| 4 | 6.1 GB/s each, 24.4 together | 6.0-6.1 each, 24.2 | 6.2 each, 24.8 |
| 8 | 3.0 GB/s each, 24.2 together | 2.9-3.0 each, 23.6 | 3.0-3.1 each, 24.3 |

DDR3L-1600 in two channels peaks at 25.6 GB/s, and one core gets 24.3
of it: on the W541 more processors give nothing. The firmware's 20.5
GB/s is within 16% of what one core can do; the most a better loop could
save is 33.8 GB at 24.3 GB/s instead of 20.5, about 0.26 s of the
1.65 s. What the next step can expect:

- the item is for the M920x, or for a machine with more bandwidth per
  core than one core can fill; on the W541, `mp_run_on_all_cpus()`
  would add the code and the risk (the PAE tables of each processor)
  for no gain;
- the single-processor loop is where the W541's 0.26 s are, as on the
  M920x: `rep stosb` with ERMS (this processor has it, no FSRM) in
  place of the `memset` of the 32-bit ramstage and the one-2-MiB-window
  loop of `memset_pae()`.

## Device switches on the W541

The devices, read under rc6 (whole lists in
[devices-w541-nri.txt](devices-w541-nri.txt)):

| Device | Where | What a switch would be |
|---|---|---|
| Ethernet | `00:19.0` I217-LM, the PCH's GbE | `BUC` (RCBA + 0x3414) reads `0x00000000`: LAN on, bit 5 (`LAN_DIS`) clear, not locked by anything read here. The roadmap's Sandy Bridge way (the bit in RW romstage, a full reset to bring it back) stands; the rollback test it asks for is still to do |
| Card reader | `01:00.0` O2 Micro OZ777 `[1217:8520]` behind root port 1, `00:1c.0` | a soft switch: the link of `00:1c.0` disabled after enumeration; the port stays powered |
| Wi-Fi | `02:00.0` Intel 9260 behind `00:1c.1`; its Bluetooth on xHCI USB2 port 11 (`8087:0025`) | already switched (`wlan`, `bluetooth`) |
| Camera | `5986:0366` *Integrated Camera* on xHCI USB2 port 12 (Linux numbering, port 11 counting from 0) | the USB2 port disable of the xHCI, `USB2PDO` (00:14.0 + 0xE4), today `0x00000000`; all USB2 ports are routed to the xHCI (`XUSB2PR` `0x3fff`), so the EHCI side needs nothing |
| Fingerprint reader | not fitted on this unit: no USB device for it in `lsusb` | the same bit as the camera, on whichever port it is wired to on units that have one; the help should say that it may be absent |
| Microphone | Realtek ALC3232 on `00:1b.0`: internal microphone node `0x12` (`0x90a60130`, fixed), microphone jack node `0x1a` (`0x03a11020`), headphone `0x15`, speaker `0x14` | the pin configuration of the verb table: `0x411111f0` for node `0x12` removes the internal microphone for every OS; the jack stays |
| Root ports 3 and 5 | `00:1c.2` and `00:1c.4`, nothing behind them today; root port 4 is off in `FD` (`0x03080001`, bit 19) | the ExpressCard and Thunderbolt switches exist already |

`FD2` reads `0x0000000f` and `FD` `0x03080001`: nothing else is
function-disabled. The W541's xHCI has six SuperSpeed ports, of which
the ACPI `_UPC` names SS1 (right) and SS2 (left) as hotplug, SS5
hardwired (paired with USB2 port 9), and the rest unused.

## Hyper-Threading on the W541

Measured with [the registers written from Linux](ht-w541-nri.txt), the
firmware of rc6 unchanged: `SOFT_RESET_DATA` (RCBA + 0x38F8) bit 0 set,
`SOFT_RESET_CTRL` (RCBA + 0x38F4) bit 0 set, then each kind of reset.
At the start both read `0x00000000`, and `SOFT_RESET_LOCK` (0x38F0,
which coreboot sets on Sandy Bridge) reads 0 and stays 0: the registers
are writable from the OS while rc6 runs.

| Step | `SOFT_RESET` after it | Threads (`MSR_CORE_THREAD_COUNT`, 0x35) | What else |
|---|---|---|---|
| Before | data 0, ctrl 0 | `0x40008`: 4 cores, 8 threads | — |
| Bit set, a suspend to S3 and the resume | data 1, ctrl 1: kept | `0x40004`: 4 threads | coreboot's resume: *CPU has 4 cores, 4 threads enabled*, 3 APs; Linux: *CPU4 failed to report alive state* to CPU7, `online` 0-3 |
| Bit set, a reboot from Linux (the FADT reset, `0xCF9` = 6) | data 1, ctrl 1: kept | `0x40004` | the MADT and the processor objects with 4 entries, Linux counts 4 present CPUs, *Using cached memory parameters*, the TPM set up and measured (TPM-03 PASS), BOOT-02 1.45 s |
| Data 0, ctrl 1, MOR set, a reboot | data 0, ctrl 1 | `0x40008`, 8 threads back | the memory cleared (above), TPM-03 PASS |
| Bit set again, a shutdown (S5) and a power-on with the button | data 0, ctrl 0: lost | `0x40008` | a cold boot as usual |

What it answers of the roadmap's questions:

- **The bit does it on Haswell.** With `SOFT_RESET_DATA` bit 0 and the
  control bit set, the processor comes out of the next reset with one
  thread per core; coreboot, the ACPI tables and Linux follow the
  CPUID on their own.
- **It survives S3, and it applies at the resume.** A firmware that set
  it at a cold boot would get one thread per core after every resume as
  well: the risk of the roadmap (Hyper-Threading back after the first
  suspend while the OS counts four threads) does not happen. The other
  way round is the one to fear: a change of the option between the
  boot and a suspend would change the thread count under the OS.
  Written once at the cold boot, before the OS, that cannot happen.
- **It survives a warm reset, not S5.** The register keeps its value
  across the reboots from Linux and is 0 after a power cycle: a slot
  without the option, after a fallback or *Go back to*, gets its
  threads back at the next cold boot, and keeps one per core until then.
  The fallback is not stuck.
- **The reset with the control bit is a warm reset of the whole
  platform, not of the processor only.** The TPM was reset (the
  measurements of the next boot replay), as were the devices: coreboot's
  comment "CPU only" on Sandy Bridge is not what Lynx Point does here,
  and there is no TPM lockout to wait for.

What it means for the option, beyond the roadmap's list:

- the reset has to be in the bootblock or verstage, before the RAM
  init, as on Sandy Bridge. **There NRI sees a warm reset with `SSKPD`
  still 0** and, by `do_actual_raminit()`, discards the cache (*Warm
  reset occurred early in cold boot*): every cold boot with the option
  off would train, 0.7 s each and a flash write whenever the training
  comes out different. The option needs that path to know its own
  reset: for instance `SOFT_RESET_DATA` already equal to what the option
  asks, read before the RAM init, means "the reset was ours", not a
  hang during a training. On `mrc` the same question goes to
  `mrc.bin`'s boot mode, which this machine cannot run;
- one reset per cold boot, never on a resume (the register is already
  right after S3), and none on a warm reboot when the value is already
  right, as in `set_soft_reset()` of `model_206ax`; the lock bit after
  it, as there;
- the vboot try counter: the reset happens after verstage, so it costs
  a try only if verstage runs again before the slot is confirmed. To
  check with the test build.

## The firmware watchdog

The two timers of Lynx Point, read while rc6 ran, nothing written:

| Register | Value | Meaning |
|---|---|---|
| PMBASE + 0x54 (0x554), the overclocking watchdog (`C3_RES` in coreboot) | `0x00002000` | the same value as on the M920x: there and off, enable (bit 14) 0, timeout 0, bit 13 set |
| `TCO1_CNT` (PMBASE + 0x68) | `0x1800` | the TCO timer halted and locked |
| `TCO2_CNT`, `TCO2_STS`, `TCO1_STS` | `0x0008`, 0, 0 | no timeout seen |
| `TCO_RLD`, `TCO_TMR` | 3, 4 | the reload counting, the default timeout |
| `GCS` (RCBA + 0x3410) | `0x00000c21` | `NO_REBOOT` (bit 5) set: coreboot's bootblock (*Disabling Watchdog reboot... done.*) keeps a TCO timeout from resetting; *BIOS Interface Lock Down* (bit 0) set |
| ACPI | no `WDAT` | the OS has no firmware watchdog to drive (and this machine boots Linux with `nowatchdog`) |

So on the W541 the TCO timer is out for a second reason besides the
lock: `NO_REBOOT` is set at every boot, and only the TCO SMI would see a
timeout. The overclocking watchdog reads as on the M920x, which makes
the roadmap's plan (arm it in romstage of the RW slot, stop it from SMM
when the payload confirms the slot) the same on both boards, with the
same open questions. On this laptop the armed test stays the owner's.
