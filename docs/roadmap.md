# Roadmap

What was looked at for v1.4.0 and left for later, with the reason and the
next step. Most items come from Dasharo's features and test plans, the
W541 ones also from a comparison with its Lenovo firmware (GNET94WW) and
with upstream coreboot: each was written up as a design against the code
of v1.4.0, then checked by a second review against the same code, and the
parts that held went into v1.4.0 ([CHANGELOG.md](../CHANGELOG.md)). The rest
is here. None of it is a promise of a date.

| Item | Boards | Why not now | Next step |
|---|---|---|---|
| [Firmware watchdog](#firmware-watchdog) | both | never used on Cannon Point upstream; testing it means resetting the machine on purpose; the W541 is a laptop someone sits at | a read-only check of the timer on hardware, then a build with the option off |
| [Firmware update mode](#firmware-update-mode) | both | capsules need none of it; touches the lockdown code of both boards | the attribute check in coreboot, a test of the Secure Boot one-shot |
| [DMA protection](#dma-protection) | M920x | no pre-boot DMA protection to report; the FSP-M has no PMR data | reword the help of *Intel VT-d*; find the slot of the Thunderbolt card |
| [Capsule regions in the payload](#capsule-regions-in-the-payload) | both | only the project key signs capsules, and the build checks each manifest | an allowlist in `FmpDeviceSmmLib`, one release before anything needs another region |
| [Variable store robustness](#variable-store-robustness) | both | the store has not been seen damaged; the fallbacks are safe | coreboot's reader stopping where EDK2's does |
| [Measured boot](#measured-boot) | both | it starts in the read-only part, which capsules never write; measuring from ramstage on the W541 gives no root of trust and little on a TPM 1.2 | a test read-only part with `TPM_MEASURED_BOOT` |
| [Top Swap and the Protected Range test](#top-swap-and-the-protected-range-test) | M920x | the read-only part is never written by an update | FLASH-04 with the protection on; a map with room for a second bootblock |
| [Settings reset on the W541](#settings-reset-on-the-w541) | W541 | built in v1.4.0 (patch 0180), off: the shared deletion is untested, and the OS may be able to set the RTC power loss bit | OPT-05 on the M920x, the bit checked on the W541, then OPT-05 there |
| [Memory training across updates on the W541](#memory-training-across-updates-on-the-w541) | W541 | safe for `mrc`, not for `nri`, whose cache version is a number bumped by hand | a variant tag and a key from the code, `mrc` first |
| [Cache version for coreboot's memory settings](#cache-version-for-coreboots-memory-settings) | M920x | no release changes them yet | `fsp_memory_soc_version()` from a Kconfig, checked by `ci-check.sh` |
| [Setup switches not added](#setup-switches-not-added) | M920x | they could lock the owner out, or change nothing | none planned |
| [Hyper-Threading on the W541](#hyper-threading-on-the-w541) | W541 | the bit is documented for Sandy Bridge only; S3 and a reset loop unknown | a test build that reads the bit and the threads after S3 |
| [Device switches on the W541](#device-switches-on-the-w541) | W541 | the Ethernet bit is sticky and needs a full reset; the others are soft switches | Ethernet the Sandy Bridge way, then card reader and microphone |
| [Wake on LAN after a shutdown on the W541](#wake-on-lan-after-a-shutdown-on-the-w541) | W541 | nothing for it in coreboot's Lynx Point code; the EC side unknown | what the Lenovo firmware programs |
| [Power-on and hard disk passwords](#power-on-and-hard-disk-passwords) | W541 | a drive locked by EDK2 cannot be unlocked after S3 on coreboot | none planned |
| [NVIDIA power steering and the EC's CPU limits](#nvidia-power-steering-and-the-ecs-cpu-limits) | W541 | little use under Linux; a `_PPC` policy and adapter tests | count the EC's CPU limit events |
| [EC events left out](#ec-events-left-out) | W541 | the radio switch is unchecked; one HKEY slot | `rfkill` and EC 0x48 on a W541; an HKEY queue |
| [Card reader of the W541](#card-reader-of-the-w541) | W541 | the premise was wrong: the reader is most likely not a Realtek | `lspci -nn` on the laptop |
| [TCC offset on the W541](#tcc-offset-on-the-w541) | W541 | the field is reserved on Haswell client processors | the TCC line of `hw-report.py` on a W541 |
| [Upstream changes not taken](#upstream-changes-not-taken) | W541 | 96893 unreviewed and no gain here; 95880 and 95912 at Code-Review -2 | the next coreboot pin; `rfkill` on a W541 |
| [Openness score](#openness-score) | both | already in `tools/sbom.py` | a comparison with Dasharo's own tool |

## Firmware watchdog

Dasharo's *Firmware watchdog*: a hardware timer that resets the machine
when the firmware hangs between the memory training and the boot logo, so
that two hangs of a newly updated slot make vboot fall back on their own,
without anyone at the power button. On the M920x it would be the
overclocking watchdog of the PCH (`OC_WDT_CTL`, ACPI base + 0x54), which
coreboot drives in `soc/intel/common/block/oc_wdt` for Alder Lake only:
romstage of the RW slot would arm it before FSP-M with the timeout of a
setup option (off by default, never below 180 s), and SMM would stop it
when the payload confirms the slot. The TCO watchdog does not fit: here
it is on and locked, and coreboot's TCO SMI clears the timeout, so a
second timeout never resets once SMIs run.

- **Why later**: no firmware hang has been seen on the M920x. Nobody knows
  yet whether this watchdog on Cannon Point-H resets the host or the whole
  platform, whether its enable bit survives that reset, or whether the
  Coffee Lake FSP-M and FSP-S leave it alone (on another platform FSP-M
  programs it). If it survived a reset into a slot without the feature,
  the OS of that slot would be reset every N minutes. Each check is a
  deliberate reset of the machine.
- **Next step**: a build with the option, off, in the slot that boots, so
  that romstage clears the enable bit at every boot; then one armed test
  with a long timeout (300 s or more) and the stop ready. In the code: a
  second read-back at `BS_PAYLOAD_BOOT`, the status bits kept as they are
  in every write, and the option hidden on the M720q/M920q, which share
  `cfr.c`.

On the W541 the same watchdog is in Lynx Point (PMBASE + 0x54, which
coreboot only names `C3_RES`), and the Lenovo firmware drives it
(`WdtPeim`) with the bit layout of coreboot's `oc_wdt`; the TCO timer
could serve too while *BIOS Lock* is off. Later there as well: the W541
is a laptop that someone sits at, and the questions of the M920x (what it
resets, whether its enable bit survives the reset) are the same.

## Firmware update mode

Dasharo's *Enter Firmware Update Mode*: one boot with *BIOS Lock*,
*Firmware protection* and Secure Boot off, armed again after it. The
supported updates need none of it: capsules (from Linux, fwupd, the
setup) are written from SMM on the boot that applies them, which *BIOS
Lock* lets through, the Protected Range covers only `WP_RO`, which they
never write, and FmpDxe checks its own certificate, not db. It would help
the flashrom paths only: `update.py other-slot` (*BIOS Lock*, and Secure
Boot through the kernel's lockdown), and writes of the read-only part or
of the whole BIOS region (all three), which today take one trip to the
setup to turn things off and another to turn them on, often forgotten.

- **Why later**: it changes the lockdown code of both boards, security
  code where a slip turns the protections off for good, plus two EDK2
  patches. The review found fail-open cases to close first: a copy of the
  flag with the runtime attribute, written by root under an older
  firmware, would keep the protections off at every boot (coreboot does
  not look at the attributes); `CFR_OPTFLAG_LOCK_AT_BOOT` does nothing in
  this tree; Secure Boot left off after vboot falls back to an older slot;
  PCR 7 changes break disk keys sealed to the TPM.
- **Next step**: coreboot honours the flag only with exactly the NV and BS
  attributes, EDK2 deletes and creates it again before EndOfDxe, a
  suppressed number option instead of a bool; then the hardware test of
  the Secure Boot one-shot (SecureBoot must read 0 in that boot and 1
  after) on both boards.

## DMA protection

Dasharo's *Early boot DMA Protection* and *Keep IOMMU enabled when
transferring control to OS*. The first needs the PMR data that coreboot's
`ENABLE_EARLY_DMA_PROTECTION` takes from an FSP HOB, which the Coffee Lake
FSP-M does not produce (its GUID is not in `fspm.bin`); Cannon Lake does
not select coreboot's VT-d block, and the payload has no IOMMU driver, so
a full design would also break its storage, USB and network DMA and the
option ROMs until it had one. What is cheap: the DMAR opt-in flag
(`DMA_CTRL_PLATFORM_OPT_IN_FLAG`, as Tiger Lake and Alder Lake set it) and
an `ExternalFacingPort` property on the root port of the optional
Thunderbolt card.

- **Why later**: the flag tells the OS that the firmware protected the
  memory during the boot, which ouroBIOS does not do (bolt may then
  authorize Thunderbolt devices without asking, Windows turns on Kernel
  DMA Protection), so it can only be an expert option, off by default. The
  property alone already makes Linux treat the devices behind the port as
  untrusted, and nothing in the trees says which connector the Lenovo
  Thunderbolt card uses. Neither changes anything on a machine without it.
- **Next step**: the help of *Hardware* → *Intel VT-d* still says it gives
  *Kernel DMA Protection*, which needs the flag: to be reworded first.
  Then, with a Thunderbolt card or Windows to test, the property as its own
  option behind VT-d (or coreboot's `DRIVERS_INTEL_DTBT`, which finds the
  bridge by its PCI ID, with its security level fixed), and the flag as a
  separate one.

The W541, whose ExpressCard slot and Thunderbolt port are known, has the
property from v1.4.0 as its own option, *Security* → *Virtualization* →
*Untrusted ExpressCard and Thunderbolt* (patch 0184), and leaves the flag
out for the same reason; Windows Kernel DMA Protection also needs a TPM
2.0, which the W541 does not have.

## Capsule regions in the payload

The payload writes every region that the manifest of a signed capsule
names (`FmpDeviceSmmLib`), through the SMMSTORE handler, which serves the
whole flash on an update boot, descriptor, GbE and ME included (the
release descriptor leaves them writable). `tools/update.py` and the build
check the list of each capsule (`update.py info`); fwupd and the setup's
USB update do not. A signed capsule built wrong, naming `SI_GBE`,
`SMMSTORE` or `RO_VPD`, would be written.

- **Why later**: only the project key signs capsules, and every release
  capsule goes through `update.py info` in `tools/build.sh`. An allowlist
  is enforced by the payload that runs, so it must ship one release before
  any capsule that needs another region.
- **Next step**: refuse before any write
  (`LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE`) a manifest with a name
  outside `RW_SECTION_A`, `RW_SECTION_B` and `RW_MRC_CACHE`, and one that
  is not an A/B update while the flash has both slots (a manifest naming
  `SI_GBE` alone would skip a check made only for A/B updates); unit tests
  for both, and a QEMU capsule naming `SMMSTORE` that must be refused with
  nothing written.

## Variable store robustness

What a damaged `SMMSTORE` does today: EDK2's fault tolerant write is in
the payload, and garbage after the last valid record triggers a reclaim
that drops it. A bad volume or store header makes the payload erase and
format the whole store, boot entries and Secure Boot keys included.
coreboot's reader never stops the boot, but it is all or nothing: one
malformed record before the erased tail and every option falls back to
its default for that boot, until the payload's reclaim repairs the store.
The ME option is read with a fallback that sends no command, so this
causes no reset loop. The settings reset of v1.4.0 refuses such a store and
writes nothing.

- **Why later**: no damaged store has been seen, and every fallback is
  safe.
- **Next step**: coreboot's `walk_variables()` stopping at the first
  record without the `0x55AA` start, as EDK2's loop does, and returning the
  matches before it, so that both read the same options after a cut write.
  And a corner case of the v1.4.0 reset: a fault tolerant write block erased
  in the middle of its own reclaim counts as no write pending.

## Measured boot

`CONFIG_TPM_MEASURED_BOOT` is off on both boards, so coreboot measures
nothing: PCR 0 holds only the separator of the payload, and only the
payload measures (PCRs 1, 4, 5 and 7 on the M920x). `tools/hw-report.py`
reports it, and [docs/testing.md](testing.md) lists it as a known gap
(TPM-03).

- **Why later**: measurements start in the read-only part, with the
  bootblock and verstage, which is where the root of trust is, and the TPM
  is started in ramstage (`TPM_INIT_RAMSTAGE`, vboot's secure data mocked
  without the TPM). Turning it on means a new read-only part, written once
  with flashrom, never by a capsule. The read-only parts on the machines
  are old (on the M920x of the port it is still ci-130), and measurements
  from the slots alone would not cover the code that verifies them.
- **Next step**: a test read-only part with measured boot and the TPM
  started early, its cost in boot time, PCR 0 and 2 against the event log
  on both boards (TPM 2.0 on the M920x, TPM 1.2 on the W541); then a
  release that changes the read-only part for it, with its own GUIDs as
  v1.3.9 did ([docs/vboot.md](vboot.md#the-read-only-part-of-v139)).

For the W541 a design that keeps the read-only part was looked at for
v1.4.0: ramstage, once CBMEM is up, logs what ran before it (FMAP, the
read-only bootblock with verstage, GBB, `mrc.bin`, the microcode) and the
VBLOCK of the slot that vboot verified, whose signed hash stands for the
slot, then everything it loads (payload, DSDT, VBT, the NVIDIA ROM), and
replays the log into the TPM. `TPM_MEASURED_BOOT` as it is would break
three things: its log in cache-as-RAM moves the regions that the
read-only part of v1.3.9 leaves to romstage (`configs/ro-interface.txt`);
with vboot the TPM code expects verstage to have started the TPM, which
`VBOOT_MOCK_SECDATA_NO_TPM` leaves to ramstage; and coreboot's TPM 1.2 log
would have about 4 KiB where the TCPA area of today has 64 KiB, too small
for the events that the payload adds to it (`edk2/0019`). Heads measures the W541 from ramstage too
(`TPM_INIT_RAMSTAGE`), without vboot.

- **Why later**: it has no root of trust of its own. The bootblock and
  verstage run unmeasured, and the trust rests on `WP_RO` and the
  signature of vboot, which root can get around while *BIOS Lock* is at
  its default, off: `bootmedia_lock` written to 0 in `SMMSTORE` with
  flashrom, a reboot, then the read-only part rewritten.
  It measures no setup option either: PCR 2 is the same with VT-d or the
  flash protection off. And on Linux a TPM 1.2 has few users: the sealing
  and attestation tools target TPM 2.0.
- **Next step**, if it is done: *BIOS Lock* required (or the help and the
  docs saying that it is needed), the security options measured, the
  read-only microcode and FIT too, `mrc.bin` only for an `mrc` slot (an
  `nri` slot behind the `mrc` read-only part never runs it), and explicit
  ramstage guards in the TPM code instead of dead code removal.

## Top Swap and the Protected Range test

Dasharo issues
[#1474](https://github.com/Dasharo/dasharo-issues/issues/1474) and
[#1489](https://github.com/Dasharo/dasharo-issues/issues/1489): a second
copy of the bootblock that the PCH boots with its Top Swap bit, so that a
write of the read-only part cut short still boots, and a test that the
Protected Ranges really stop writes.

- **Why later**: here the read-only part is written only by flashrom, by
  hand, and never by an update: a capsule writes the slots, and vboot
  falls back between them. A cut write of `WP_RO` is the case the
  external programmer covers ([docs/m920x.md](m920x.md#recovery)). Top
  Swap needs a flash map with room for the second copy, a new read-only
  part written with flashrom, and the swap bit set before `BILD` locks it
  (set on the M920x). The registers are read today
  (`tools/update.py protection`), but the protection has not been seen on
  yet on the M920x of the port (*Firmware protection* is off there).
- **Next step**: FLASH-04 of [docs/testing.md](testing.md) with
  *Firmware protection* on (PR0 over `WP_RO`, `--expect-ro on` exits 0),
  and a write of one block of `WP_RO` with flashrom that must fail, the
  backup and the programmer at hand. Top Swap with the next change of the
  read-only part, if one comes.

## Settings reset on the W541

From v1.4.0 an RTC power loss resets the setup options of the M920x
([docs/m920x.md](m920x.md#resetting-the-settings)). The W541 has the
trigger from v1.4.0 too (patch 0180): Haswell romstage calls the shared
deletion (`drivers/efi`) right after the early PCH init, before the first
option is read, when the RTC failure bit is set and the boot is not an S3
resume, with POST codes 0x37 and 0x38 around it, so that a boot that
follows one that hung there skips it (on Haswell the option needs
`CMOS_POST`); `sb_rtc_init()` in ramstage clears the bit and logs the
event as before. It is off: `CONFIG_DRIVERS_EFI_RESET_OPTIONS_ON_RTC_FAILURE`
is not set in `configs/w541-*.defconfig`, so the W541 keeps its options
through a CMOS clear.

- **Why later**: the shared deletion has not run on a machine yet (OPT-05
  on the M920x). On the W541 software clears the RTC power loss bit (bit
  2 of `GEN_PMCON_3`, `00:1f.0` 0xa4) by writing it: if the OS can also
  set it, a reboot would put *BIOS Lock* back to its default, off. A laptop also
  loses the RTC power more easily: with a dead coin cell, a battery taken
  out or run down without AC is enough. The mark of a deletion that hung
  is in the CMOS as well, so the test notes must give the way out: the
  power button held 4 s with the AC adapter or a battery still attached;
  removing every supply would repeat the deletion.
- **Next step**: OPT-05 on the M920x; on the W541 the bit test (write it,
  read it back, reboot), then OPT-05 on a test build with the option on,
  with the AC adapter, the batteries and the coin cell out. Before the
  line goes on in the defconfigs: `tools/elog.py` names for POST codes
  0x37 and 0x38, `tools/hw-report.py` taking *RTC power lost: setup
  options reset to defaults* (the outcome printed again once CBMEM is up)
  as an event, and release notes that say it.

## Memory training across updates on the W541

The M920x keeps the training across updates from v1.4.0, because its cache
carries a version that changes with the FSP-M of the slot, the processor
and Hyper-Threading. On the W541 the capsules, `update.py other-slot` and
*Go back to* still empty `RW_MRC_CACHE`, so every update trains once. A
vboot fallback does not: the other slot boots on the cache that the new
one saved, which is why v1.4.0 bumps the revision of the NRI data with its
rank fix (patch 0186).

- **Why later**: the two variants need different answers. For `mrc`,
  keeping the cache is safe: `mrc.bin` is in the read-only part, so every
  slot runs the same one, and it checks the saved data itself (a CRC32
  over it, its own version, the processor and a stepping class, a CRC of
  the SPD of each DIMM) and trains on a mismatch. For `nri` it is not: the
  key is `reg_frame_rev()`, a number bumped by hand (only by patches 0008
  and 0186), and the fast boot restores the saved settings without a
  test, so a slot could resume a training made by other code (a cache from
  before patch 0086 would have kept the DDR3L at 1.5 V). The gain was never
  measured on the W541 ("a few seconds"); from v1.4.0 `cbmem -t` shows the
  training of `nri` (patch 0189).
- **Next step**: a tag in the cache version, `M` or `N` in bits 31:24 and
  24 bits of key: for `mrc` the inputs of `mrc.bin` (fields of `pei_data`,
  hashed with the streaming xxh32 rather than copied on the 8 KiB stack,
  and the size of the blob), for `nri` a hash made at build time of the
  NRI code and its Kconfig, plus the memory fields of the devicetree. Then
  capsule regions per variant without `RW_MRC_CACHE`,
  `SMMSTORE_VBOOT_SWITCH_KEEPS_MRC_CACHE` for the W541 and the tables of
  `update.py`; the first capsule without the region must carry slots with
  the tag, and `mrc` can go first. The docs must then say that the cache
  is not authenticated (today every update also clears a tampered one),
  and give the way out without an OS: a SO-DIMM taken out or swapped makes
  both RAM inits train again. The T440p shares the code and would train
  once.

## Cache version for coreboot's memory settings

On the M920x the cache version is the revision of FSP-M with its build
byte replaced by the processor and Hyper-Threading bits. The FSP-M
settings that coreboot itself chooses (`fsp_params.c`, the romstage of the
board) are not in it: a release that changed them would keep resuming the
old training. Today the rule is written next to `BOARD_CAPSULE_REGIONS`
in `boards/m920x/board.sh`: such a release bumps
`fsp_memory_soc_version()` (bits 3:0 are free) or puts `RW_MRC_CACHE` back
in the list.

- **Next step**: `fsp_memory_soc_version()` from a 4-bit Kconfig,
  default 0 (today's version, no training), and a check in
  `tools/ci-check.sh` that flags a change to those files without a bump.

## Setup switches not added

From the same list of Dasharo options:

- **USB stack off**: the Tiny has no PS/2 port, so the firmware would have
  no keyboard left, and no way back into the setup but an external
  programmer. *Hardware* → *Devices* already turns the front and rear
  ports off in hardware.
- **No boot menu key**: it would leave only `Boot0000` (*Enter Setup*,
  through `BootNext`) and the OS's request to boot to the firmware UI as
  ways into the setup; *Boot menu prompt* hides the line instead, and Esc
  still works.
- **Render standby (RC6)**: already on, from the FSP-S default, and i915
  uses it; a switch could only turn it off.
- **PS/2 drivers in the M920x payload**: the board has no PS/2 port and
  coreboot keeps the keyboard device of the Super I/O off, so the payload's
  PS/2 drivers find nothing (a probe of a few ms). Dropping them
  (`# CONFIG_EDK2_PS2_SUPPORT is not set`, `-D PS2_MOUSE_ENABLE=FALSE`)
  broke the CI smoke test, build ci-153: `tools/qemu-smoke.py` types on
  QEMU's PS/2 keyboard, so Esc never reached the setup. Next step: give
  the smoke test a USB keyboard for payloads without PS/2 (and check that
  QMP `send-key` reaches it rather than the i8042), then drop them.

## Hyper-Threading on the W541

The Lenovo setup has *Intel Hyper-Threading Technology*, on by default;
the M920x has the option from v1.4.0 (patch 0171), the W541 not. On Haswell
it would be the bit of the PCH that keeps the second thread of each core
off from the next CPU-only reset (`SOFT_RESET_DATA`, RCBA + 0x38F8),
which coreboot sets for Sandy Bridge and Ivy Bridge (`model_206ax`).

- **Why later**: nothing in the tree says that the bit does it on
  Haswell. Written without a read-back, a bit that does not stick resets
  the laptop at every boot. Nothing says either whether it survives S3: if
  not, Hyper-Threading comes back after the first suspend while the OS
  counts four threads, and a reset once the resume is detected would end
  the resume, as the sleep type is already cleared. With it off, every
  cold boot also has one more reset after verstage, which takes one of
  the two tries that vboot gives a new slot.
- **Next step**: a test build that logs `SOFT_RESET_DATA` and the thread
  count at a cold boot and after an S3 resume with the bit set; then the
  option, with a read-back, at most one reset per boot, and shown as on
  the M920x (when it is off, or when CPUID reports more than one thread),
  checked with `lscpu`, the ACPI processor objects (`Processor` for macOS
  too) and the MADT.

## Device switches on the W541

*I/O Port Access* of the Lenovo setup turns the Ethernet controller, the
card reader, the microphone, the camera and the fingerprint reader off;
the M920x has *Hardware* → *Devices* from rc3. On the W541 only the
ExpressCard, Thunderbolt and SATA ports, the radios and the display audio
have a switch.

- **Why later**: the Ethernet controller is turned off by a bit of the
  PCH (the LAN disable of `BUC`) that lives in the RTC well: coreboot
  sets it and never clears it, and turning the controller back on takes a
  full reset, as coreboot does on Sandy Bridge (`pch_enable_gbe()`). That
  belongs in RW romstage, not in the bootblock of the read-only part,
  with a read-back, as the lockdown of the finalize step may lock the
  bit. A slot without the option, after a fallback or *Go back to*, would
  leave the Ethernet off until an RTC reset. The card reader can only be
  cut from its link after coreboot has enumerated it, so its port stays
  powered (a soft switch), and the microphone only through the pin
  configuration of the codec.
- **Next step**: the Ethernet switch the Sandy Bridge way, named
  `onboard_ethernet` as on the M920x, tested with a rollback to an older
  slot while it is off; the card reader (link disable) and the
  microphone (pin configuration), with help texts that call them soft
  switches; the camera and the fingerprint reader through their USB
  ports.

## Wake on LAN after a shutdown on the W541

The Lenovo setup has *Wake On LAN*, *AC Only* by default or *AC and
Battery*. ouroBIOS has the wake that the OS arms, from S3 and S4 (`_PRW`
on the Ethernet controller, patch 0072); the M920x wakes from S5 too from
rc3 (patches 0154-0155).

- **Why later**: coreboot's Lynx Point code has nothing for the wake of
  the LAN from S5 nor for `SLP_LAN#`, and what the EC does for *AC and
  Battery* is not known.
- **Next step**: find in the Lenovo firmware what it programs for the
  option (PCH, GbE, EC), then a magic packet from power-off on AC and on
  battery (NET-02 of [docs/testing.md](testing.md)).

## Power-on and hard disk passwords

The Lenovo setup has a power-on password and hard disk passwords;
ouroBIOS has the supervisor password, asked for before the setup and the
boot menu (`edk2/0003`).

- **Why later**: EDK2's hard disk password driver cannot unlock a drive
  after S3 here: it needs a PEI phase on the resume path, which coreboot's
  S3 resume does not have, so a locked drive would stay locked after a
  suspend. A power-on password would be asked at every boot, unattended
  ones included, and is a payload change of its own.
- **Next step**: none planned.

## NVIDIA power steering and the EC's CPU limits

Two things that the Lenovo firmware of the W541 does for power:
*Discrete GFX Perf Mode*, NVIDIA's power steering (GPS: its `NVPS` method
sets the performance limits of the CPU for the GPU driver), and a `_PPC`
that follows the wattage of the adapter, the batteries and the power
limit registers of the EC, with the EC events 0x48, 0x49 and 0x5B that
ask for a CPU limit.

- **Why later**: little use under Linux, and much work: a `_PPC` policy
  of our own, which needs tests with a 65 W or 90 W adapter and with the
  batteries.
- **Next step**: count the EC's queries under load, on battery and with a
  smaller adapter (FAN-10 of [docs/testing.md](testing.md)): the Lenovo
  firmware writes acknowledgement bits back for 0x48 and 0x5B, and if the
  EC repeats those events without them, they need handling first.

## EC events left out

Patch 0190 handles the EC events that the Lenovo firmware reports to the
OS. Left out, with the reason in `ec.asl`:

- 0x48, 0x49, 0x5B, the CPU limits
  ([above](#nvidia-power-steering-and-the-ecs-cpu-limits));
- 0x41, the radio switch (HKEY 0x7000): the Lenovo `WLSW` returns a
  constant, ours EC 0x48 bit 1 (`GSTS`), and on 0x7000 `thinkpad_acpi`
  reads it and would hard-block the radios if it read 0, which nobody has
  checked on a W541 (upstream change 95880 is about the same bit);
- 0x2C, 0x2D, 0x38, 0x44, the Ultrabay, which has no device in our DSDT;
- 0x70 and 0x72-0x74, sticky Fn and Fn+Esc: `thinkpad_acpi` ignores
  their codes, 0x74 needs a `GMKS` method, and they would follow hotkeys
  closely;
- 0x1E, 0x6B-0x6F, 0x77, which the Lenovo firmware does not handle
  either, and 0x43, which it sends to its SMM code only.

HKEY keeps one pending event, where the Lenovo firmware keeps one per
class: two events before the OS reads them lose the first. Also open from
the same comparison: the beep mask of the EC (0x86 here, 0x87 with the
Lenovo firmware; FAN-08) and the Lenovo writes of EC 0x02 bit 7 and 0x03
bits 5-6.

- **Next step**: `rfkill list` and EC 0x48 on a W541, which decide 0x41
  (and 95880); a queue in the shared `thinkpad.asl`, gated for the other
  ThinkPads, before the sticky Fn events.

## Card reader of the W541

The Lenovo firmware image of the W541 has the init code of a Realtek
RTS5227 reader and of an O2 Micro one, and coreboot runs its RTS5227 init
on the T440p only, so a port with the values of the W541 looked like a
gap.

- **Why not**: the premise is wrong. The same image serves the W540 and
  the W541, so the two modules can be one per model; and on this W541 the
  device properties for macOS (patch 0128) give the reader an SDHCI
  driver, which a Realtek RTS52xx is not, while Libreboot's fix for SD
  boot on the W541 is for a Bayhub (O2 Micro) reader. That fix (MrChromebox
  EDK2 `c205cebb`) is already in the payload, and coreboot's Realtek driver
  binds only Realtek IDs.
- **Next step**: `lspci -nn` on the laptop. With an O2 Micro reader, at
  most the subsystem IDs that the Lenovo `DxeO2MicroInit` writes, which
  are cosmetic.

## TCC offset on the W541

The M920x has *TCC activation offset* from v1.4.0 (patch 0177).

- **Why later**: on the Haswell client processors of the W541, Intel
  marks the field (MSR 0x1A2 bits 27:24, settable when bit 30 of
  `PLATFORM_INFO` says so) reserved, Linux gives Haswell a TCC offset mask
  of 0, and no Haswell board of coreboot sets it: the option would most
  likely be hidden on every W541. The EC's fan curve, the cooling policy
  and the PL1/PL2 limits cover the same ground.
- **Next step**: the TCC line of CPU-01 (`tools/hw-report.py`) on a W541
  (CPU-05 of [docs/testing.md](testing.md)). With bit 30 set and a write
  from Linux that sticks, the option, which must also be able to write 0
  back (`configure_thermal_target()` never writes 0).

## Upstream changes not taken

- [96893](https://review.coreboot.org/c/coreboot/+/96893), the initial
  round trip delta of the NRI at 0 on Haswell, after a decompiled
  MemoryInit.efi: posted on 2026-10-30 with no review yet, it also changes
  the ULT value, and on the W541 patch 0088 already ends at the 4 + 21 of
  `mrc.bin` ([docs/raminit.md](raminit.md#limits)). Next step: once
  merged, with the next coreboot pin, where the rt_iocomp step of 0088
  becomes a no-op.
- [95880](https://review.coreboot.org/c/coreboot/+/95880), no master
  wireless switch bit on newer H8 ECs (`no_wireless_switch`), and
  [95912](https://review.coreboot.org/c/coreboot/+/95912), the tablet
  switch method only for tablets: both at Code-Review -2 for an invalid
  sign-off, so they would stay here for good, and nothing shows that the
  EC of the W541 reads `GSTS` as 0 (the Lenovo DSDT declares it at the
  same place, though its `WLSW` returns a constant). Next step: `rfkill
  list` and EC 0x48 on a W541; with Bluetooth or WWAN hard-blocked, 95880
  set for the W541.
- 96645-96647, NRI cleanups merged after the pin (no-ops on DDR3), and
  96630 (acpigen): with the next coreboot pin, patches 0087, 0088 and 0185
  rebased onto them. 0185 itself goes once 96694 is merged; `upstream.yml`
  reports it by its subject.

## Openness score

Dasharo publishes how much of each image is open source.
`tools/sbom.py` already measures it from the image itself, and each
release carries it in its bill of materials: on the ci-150 builds 36.6%
of the code of the M920x image is open source (63.4% Intel's FSP, ME and
other binaries), 85.9% of the W541 `mrc` image and 89.3% of the `nri`
one.

- **Next step**: only a comparison with Dasharo's own tool on one image,
  to see whether it counts the descriptor and the GbE region as closed
  binaries, as `sbom.py` does.
