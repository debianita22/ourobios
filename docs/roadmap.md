# Roadmap

What was looked at for v1.4.0 and left for later, with the reason and the
next step. Most items come from Dasharo's features and test plans: each
was written up as a design against the code of rc4, then checked by a
second review against the same code, and the parts that held went into
rc4 ([CHANGELOG.md](../CHANGELOG.md)). The rest is here. None of it is a
promise of a date.

| Item | Boards | Why not now | Next step |
|---|---|---|---|
| [Firmware watchdog](#firmware-watchdog) | M920x | never used on Cannon Point upstream; testing it means resetting the machine on purpose | a read-only check of the timer on hardware, then a build with the option off |
| [Firmware update mode](#firmware-update-mode) | both | capsules need none of it; touches the lockdown code of both boards | the attribute check in coreboot, a test of the Secure Boot one-shot |
| [DMA protection](#dma-protection) | M920x | no pre-boot DMA protection to report; the FSP-M has no PMR data | reword the help of *Intel VT-d*; find the slot of the Thunderbolt card |
| [Capsule regions in the payload](#capsule-regions-in-the-payload) | both | only the project key signs capsules, and the build checks each manifest | an allowlist in `FmpDeviceSmmLib`, one release before anything needs another region |
| [Variable store robustness](#variable-store-robustness) | both | the store has not been seen damaged; the fallbacks are safe | coreboot's reader stopping where EDK2's does |
| [Measured boot](#measured-boot) | both | it starts in the read-only part, which capsules never write | a test read-only part with `TPM_MEASURED_BOOT` |
| [Top Swap and the Protected Range test](#top-swap-and-the-protected-range-test) | M920x | the read-only part is never written by an update | FLASH-04 with the protection on; a map with room for a second bootblock |
| [Settings reset on the W541](#settings-reset-on-the-w541) | W541 | rc4 is the M920x candidate; the Haswell code path differs | the same deletion in Haswell romstage, tested on the W541 |
| [Memory training across updates on the W541](#memory-training-across-updates-on-the-w541) | W541 | the cache version does not follow changes to the native RAM init | a version for the NRI code, then the M920x behaviour |
| [Cache version for coreboot's memory settings](#cache-version-for-coreboots-memory-settings) | M920x | no release changes them yet | `fsp_memory_soc_version()` from a Kconfig, checked by `ci-check.sh` |
| [Setup switches not added](#setup-switches-not-added) | M920x | they could lock the owner out, or change nothing | none planned |
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
causes no reset loop. The settings reset of rc4 refuses such a store and
writes nothing.

- **Why later**: no damaged store has been seen, and every fallback is
  safe.
- **Next step**: coreboot's `walk_variables()` stopping at the first
  record without the `0x55AA` start, as EDK2's loop does, and returning the
  matches before it, so that both read the same options after a cut write.
  And a corner case of the rc4 reset: a fault tolerant write block erased
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

From rc4 an RTC power loss resets the setup options of the M920x
([docs/m920x.md](m920x.md#resetting-the-settings)): the deletion is
shared code (`drivers/efi`), the hook is in Cannon Lake romstage only.
The W541 keeps its options through a CMOS clear.

- **Why later**: rc4 is the M920x candidate, and the Haswell path is
  different: its RTC failure bit is cleared by `sb_rtc_init()` in
  ramstage, which reads the live bit for the event log and the CMOS
  defaults, so the bit must not be cleared in romstage there.
- **Next step**: call `efi_option_reset_all()` in Haswell romstage before
  the RAM init when `rtc_failure()` says so (the RTC code is built for
  romstage too), set `DRIVERS_EFI_RESET_OPTIONS_ON_RTC_FAILURE` in the
  W541 defconfigs, and test both variants with the coin cell out.

## Memory training across updates on the W541

The M920x keeps the training across updates from rc4, because its cache
carries a version that changes with the FSP-M of the slot, the processor
and Hyper-Threading. The W541 capsules still empty `RW_MRC_CACHE`: the
version of `mrc.bin` is fixed, and the one of the native RAM init does not
change when its algorithm does, so a slot could resume a training made by
other code.

- **Next step**: a version for the native RAM init that changes with its
  code (a hash of the training code, or a number bumped by the patches
  that change it), then the two-slot manifest and
  `SMMSTORE_VBOOT_SWITCH_KEEPS_MRC_CACHE` for the W541 too.

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
