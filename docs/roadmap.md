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
| [Firmware update mode](#firmware-update-mode) | both | decided on 2026-11-05: not made; capsules need none of it, and a one-shot of the protections and Secure Boot is security code that can fail open | none planned; `update.py other-slot` reminds to turn *BIOS Lock* on again |
| [DMA protection](#dma-protection) | M920x | no pre-boot DMA protection to report; the FSP-M has no PMR data | reword the help of *Intel VT-d*; find the slot of the Thunderbolt card |
| [Capsule regions in the payload](#capsule-regions-in-the-payload) | both | done in v1.6.0 (`edk2/0045`): the payload writes only the two slots and `RW_MRC_CACHE`, and on a flash with both slots only an update of one slot at a time | a new region in `PcdFmpDeviceSmmAllowedRegions` one release before any capsule that writes it |
| [Variable store robustness](#variable-store-robustness) | both | looked at for v1.6.0: coreboot's all-or-nothing reader is upstream's choice, and the corner case of the reset is not one | none planned |
| [Top Swap and the Protected Range test](#top-swap-and-the-protected-range-test) | M920x | the read-only part is never written by an update | FLASH-04 with the protection on; a map with room for a second bootblock |
| [Settings reset on the W541](#settings-reset-on-the-w541) | W541 | built in v1.4.0 (patch 0180), off: the shared deletion is untested, and the OS may be able to set the RTC power loss bit | OPT-05 on the M920x, the bit checked on the W541, then OPT-05 there |
| [Memory training across updates on the W541](#memory-training-across-updates-on-the-w541) | W541 | safe for `mrc`, not for `nri`, whose cache version is a number bumped by hand | a variant tag and a key from the code, `mrc` first |
| [Cache version for coreboot's memory settings](#cache-version-for-coreboots-memory-settings) | M920x | done in v1.6.0 (patch 0222): a Kconfig for the version, and `tools/fspm-settings.sh` stops CI when the files of those settings change | the first bump, with the release that changes them |
| [Setup switches not added](#setup-switches-not-added) | M920x | they could lock the owner out, or change nothing | none planned |
| [Hyper-Threading on the W541](#hyper-threading-on-the-w541) | W541 | the reset before the RAM init makes NRI discard its cache at every cold boot; `mrc` not measured | the bit works on Haswell, survives S3 and warm resets, not S5 (measured on a W541); the option, with NRI knowing its own reset |
| [Device switches on the W541](#device-switches-on-the-w541) | W541 | the Ethernet bit is sticky and needs a full reset; the others are soft switches | Ethernet the Sandy Bridge way, then card reader and microphone |
| [Wake on LAN after a shutdown on the W541](#wake-on-lan-after-a-shutdown-on-the-w541) | W541 | nothing for it in coreboot's Lynx Point code; the EC side unknown | what the Lenovo firmware programs |
| [Power-on and hard disk passwords](#power-on-and-hard-disk-passwords) | W541 | a drive locked by EDK2 cannot be unlocked after S3 on coreboot | none planned |
| [NVIDIA power steering and the EC's CPU limits](#nvidia-power-steering-and-the-ecs-cpu-limits) | W541 | little use under Linux; a `_PPC` policy and adapter tests | count the EC's CPU limit events |
| [EC events left out](#ec-events-left-out) | W541 | no radio switch to report (checked on a W541 on 2026-11-03); one HKEY slot | an HKEY queue |
| [Card reader of the W541](#card-reader-of-the-w541) | W541 | the premise was wrong: the reader is an O2 Micro OZ777, which the payload drives already | none planned |
| [TCC offset on the W541](#tcc-offset-on-the-w541) | W541 | done in v1.6.0 (patches 0220-0221): CPU-05 passed on a W541 on 2026-11-03 | none planned |
| [Upstream changes not taken](#upstream-changes-not-taken) | W541 | 96893 unreviewed and no gain here; 95880 not for the W541; 95912 at Code-Review -2 | the next coreboot pin |
| [EDK II from TianoCore](#edk-ii-from-tianocore) | both | moved in v1.6.0: the payload of the ROMs is TianoCore's tag with the package [`edk2/OuroBiosPkg`](../edk2/README.md) and `patches/tianocore`, the same payload as MrChromebox's tree with `patches/edk2`; what is left is the carried series, 100 patches | the series shorter: the *drop* commits in the payload, each with its test, then the *package* ones into `OuroBiosPkg`, the *upstream* ones proposed; the *drop* ones already out of the payload when `patches/edk2` retires ([docs/edk2-migration.md](edk2-migration.md)) |
| [LVGL v10](#lvgl-v10) | both | not out yet (v9.6, in the setup from v1.6.0, is the last of v9); LvglPkg calls the setters of v9.6 in place of the flag functions that v10 removes (`lvglpkg/0021`) | the pin |
| [The _OSI queries of the DSDT](#the-_osi-queries-of-the-dsdt) | both | no Windows requirement asks for them, and a query of "Windows 2012" or later changes the backlight Linux picks | none planned |
| [HSTI](#hsti) | both | the only honest answer to its tests is partly "no", and Windows reads it for a report only | none planned |
| [Openness score](#openness-score) | both | already in `tools/sbom.py`; compared with Dasharo's tool after rc5: the descriptor, GbE and VBT are data there too now, the ME region is counted whole by Dasharo and by its bytes here | none planned |
| [Clearing the memory on every core](#clearing-the-memory-on-every-core) | both | measured on both: on the W541 one core already fills the memory, on the M920x the clear is bound by its unequal DIMMs; the loop is `rep stosl` already | decided on 2026-11-06: not made; a test build only for a machine with two equal DIMMs |
| [The UEFI Shell in the payload](#the-uefi-shell-in-the-payload) | both | done in v1.6.0 (`edk2/0053`, patch 0227): the boards' payload leaves the Shell out, and the smoke test writes its variables with `tools/efi/setvar.c` from a disk image | none planned |
| [The DPLL of i915 at boot on the M920x](#the-dpll-of-i915-at-boot-on-the-m920x) | M920x | i915's own wait for the PLL, not the firmware's | a report to i915 with the numbers |
| [A USB 3.0 drive after a warm reset on the W541](#a-usb-30-drive-after-a-warm-reset-on-the-w541) | W541 | settled (2026-11-06): the SuperSpeed side of the right SS connector of that W541 trains badly (3 links in about 8 plugs, the left one 6 in 6, the same drive); a warm reset carries a stuck port over; not the firmware | the sides of the connectors in patch 0071; a longer limit (or `WRC`) in `warm_reset_usb3_ports()` |
| [TSC ADJUST after a resume on the W541](#tsc-adjust-after-a-resume-on-the-w541) | W541 | not coreboot (measured 2026-11-06): the register is 0 up to the jump to the wake vector, and the TSC of before the suspend is written back after it | the Linux side, with a debug kernel rather than MSR tracepoints across a suspend |

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
  `cfr.c`. Read on the M920x under rc6 (2026-11-05): `OC_WDT_CTL`
  `0x00002000`, the watchdog there and off, FSP leaves it alone; the
  TCO timer halted and locked, no `WDAT` table
  ([docs/tests/v1.6.0/m920x-fsp/development.md](tests/v1.6.0/m920x-fsp/development.md#the-firmware-watchdog)).

On the W541 the same watchdog is in Lynx Point (PMBASE + 0x54, which
coreboot only names `C3_RES`), and the Lenovo firmware drives it
(`WdtPeim`) with the bit layout of coreboot's `oc_wdt`; the TCO timer
could serve too while *BIOS Lock* is off. Later there as well: the W541
is a laptop that someone sits at, and the questions of the M920x (what it
resets, whether its enable bit survives the reset) are the same. Read on
the W541 under rc6 (2026-11-06): the overclocking watchdog `0x00002000`,
as on the M920x; the TCO timer halted and locked, and `NO_REBOOT` set by
the bootblock at every boot, so the TCO is out on two counts; no `WDAT`
([docs/tests/v1.6.0/w541-nri/development.md](tests/v1.6.0/w541-nri/development.md#the-firmware-watchdog)).

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
- **Decided (2026-11-05)**: not made. Every supported update goes in with
  the protections on, through a capsule; what is left for flashrom (the
  other W541 variant behind the `mrc` read-only part, a new read-only
  part about once a year, a recovery) is rare enough for two trips to the
  setup, and a mode that turns the protections and Secure Boot off by
  itself adds a way to leave them off, and on a Secure Boot boot a PCR 7
  that disk keys sealed to the TPM do not expect. What it would have
  saved, the forgotten second trip, `update.py other-slot` now says in its
  last lines, and `update.py protection` and FLASH-01 of `hw-report.py`
  report.

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
- **Next step**: (the help of *Hardware* → *Intel VT-d* no longer
  promises *Kernel DMA Protection*, from v1.5.0, patch 0206.) With a
  Thunderbolt card or Windows to test, an IOMMU driver in the payload
  (EDK2's `IntelVTdDxe`) and how it hands the IOMMU over to each OS
  (macOS, with `DisableIoMapper`, untested with it on); then the property
  as its own option behind VT-d (or coreboot's `DRIVERS_INTEL_DTBT`, which finds the
  bridge by its PCI ID, with its security level fixed), and the flag as a
  separate one.

The W541, whose ExpressCard slot and Thunderbolt port are known, has the
property from v1.4.0 as its own option, *Security* → *Virtualization* →
*Untrusted ExpressCard and Thunderbolt* (patch 0184), and leaves the flag
out for the same reason; Windows Kernel DMA Protection also needs a TPM
2.0, which the W541 does not have.

## Capsule regions in the payload

Up to v1.5.0 the payload wrote every region that the manifest of a signed
capsule named (`FmpDeviceSmmLib`), through the SMMSTORE handler, which
serves the whole flash on an update boot, descriptor, GbE and ME included
(the release descriptor leaves them writable). `tools/update.py` and the
build check the list of each capsule (`update.py info`); fwupd and the
setup's USB update do not. A signed capsule built wrong, naming `SI_GBE`,
`SMMSTORE` or `RO_VPD`, would have been written.

- **Done in v1.6.0** (`edk2/0045`): `PcdFmpDeviceSmmAllowedRegions` of the
  platform, `RW_SECTION_A RW_SECTION_B RW_MRC_CACHE`. The image check and
  the write refuse, before anything is written and with
  `LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE`, a manifest with another
  name, and one that is not an update of one slot at a time while the
  flash has both slots (a manifest with the running slot alone would write
  it). Host unit tests for both (`tools/build.sh edk2-unit-test`, in
  `check.yml` and `build.yml`), and two QEMU capsules, one naming
  `SMMSTORE` next to the slots, one with the running slot alone, refused
  with nothing written (`tools/qemu-update.py`). The capsules of every
  release so far name only those regions, so they still install, rollbacks
  included. Found with them: a boot with capsules restarted before it
  confirmed the slot that runs, so a refused capsule could use up the
  tries of a slot that vboot was trying; it confirms it first now
  (`edk2/0046`).
- **Next step**: a capsule that needs another region needs it in the
  allowlist one release before: the payload that runs enforces it.

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

- **Looked at for v1.6.0, nothing to change**:
  - coreboot's reader stopping at the first record without the `0x55AA`
    start, as EDK2's loop does, would undo a choice of upstream: since
    e25e29977f (review 95132) and fae8549751 (95583), in the pin of
    v1.6.0, `walk_variables()` validates the whole store before it returns
    a value and wants the unused bytes erased, and
    `tests/drivers/efivars.c` checks it (`efi_test_validate_tail_after_match`).
    After a cut write the two disagree for one boot, coreboot on the
    defaults, until the payload's reclaim at its start; the defaults are
    safe, so it stays as upstream has it.
  - The corner case of the v1.4.0 reset, a fault tolerant write working
    block erased in the middle of its own reclaim, which
    `ftw_write_pending()` counts as no write pending (patch 0175), is
    right: FaultTolerantWriteDxe then finds a valid work space in the
    spare block, writes it back to the working block and aborts the last
    write (`InitFtwProtocol()` in `FtwMisc.c`, which the payload does not
    patch there), so no copy of the variable store is written back over
    what the reset deleted.
- **Next step**: none planned, unless upstream's reader changes.

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
- **Measured on the W541** (2026-11-05, `nri`, rc6;
  [docs/tests/v1.6.0/w541-nri/development.md](tests/v1.6.0/w541-nri/development.md#memory-training-across-updates-on-the-w541)):
  the training 0.83 s, the cache 0.11 s, so 0.7 s once per update; the
  cache does not get rewritten on fast boots. Its four SO-DIMMs carry the
  same SPD, serial number included: neither RAM init can see a swap among
  such modules, so the way out without an OS is a module taken out, or
  replaced by one of another type, not any swap.

## Cache version for coreboot's memory settings

On the M920x the cache version is the revision of FSP-M with its build
byte replaced by the processor and Hyper-Threading bits. The FSP-M
settings that coreboot itself chooses (`fsp_params.c`, the romstage of the
board) are not in it: a release that changed them would keep resuming the
old training. The rule is written next to `BOARD_CAPSULE_REGIONS`
in `boards/m920x/board.sh`: such a release bumps the version (bits 3:0
are free) or puts `RW_MRC_CACHE` back in the list.

- **Done in v1.6.0** (patch 0222): `fsp_memory_soc_version()` returns
  `CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION`, 0-15, set to 0 in
  `boards/m920x/fsp.defconfig` (today's version: no training).
  `tools/fspm-settings.sh`, in `check.yml`, keeps the SHA-256 of the files
  that set those UPDs in the tree with the series (`fsp_params.c` and
  `cnl_memcfg_init.c` of Cannon Lake, the romstage and the devicetree of
  the board) in `boards/m920x/fspm-settings.txt`, with the version, and
  stops when one of them changes, with a patch or a new coreboot pin: if
  the memory settings change, the version goes up in the defconfig and in
  the file, and the first boot after the update trains once; if not,
  `tools/fspm-settings.sh --update` records the files as looked at.
- **Next step**: the first bump, with the release that changes them.

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
  too) and the MADT. The M920x of the port cannot help: its i3-8100 has
  one thread per core
  ([docs/tests/v1.6.0/m920x-fsp/development.md](tests/v1.6.0/m920x-fsp/development.md#hyper-threading)).
- **Measured on the W541** (2026-11-06, the registers written from
  Linux under rc6; [docs/tests/v1.6.0/w541-nri/development.md](tests/v1.6.0/w541-nri/development.md#hyper-threading-on-the-w541)):
  the bit does it on Haswell (4 cores, 4 threads after the next reset);
  the register is not locked, survives S3 and applies at the resume,
  survives a warm reset, not S5; the reset with the control bit resets
  the TPM too. For the option: at the cold boot NRI would see the reset
  with `SSKPD` at 0 and retrain at every boot, unless it knows its own
  reset.

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
- **From the M920x** (2026-11-05): how each switch looks on a Cannon
  Point PCH, the devices and the codec pins of the Tiny, in
  [docs/tests/v1.6.0/m920x-fsp/development.md](tests/v1.6.0/m920x-fsp/development.md#device-switches).
- **From the W541** (2026-11-06): `BUC` 0 (LAN on, not locked), the
  card reader behind `00:1c.0`, the camera on xHCI USB2 port 12, no
  fingerprint reader on that unit, the internal microphone on node
  `0x12` of the ALC3232, in
  [docs/tests/v1.6.0/w541-nri/development.md](tests/v1.6.0/w541-nri/development.md#device-switches-on-the-w541).

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
  reads it and would hard-block the radios if it read 0; on a W541 it
  reads 1 (below; upstream change 95880 is about the same bit);
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

- **Checked on a W541** (2026-11-03, v1.5.0): EC 0x48 reads 0x52, so
  `GSTS` (bit 1) is 1, and `rfkill list` shows no radio hard-blocked.
  `thinkpad_acpi` would read 1 on 0x7000 and block nothing, so 0x41 could
  be handled safely, but Lenovo's PSREF of the W541 lists no radio switch
  for it to report: it stays out. 95880 is not for the W541 (below).
- **Next step**: a queue in the shared `thinkpad.asl`, gated for the
  other ThinkPads, before the sticky Fn events.

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
- **Checked on a W541** (2026-11-03): `lspci -nn` gives `01:00.0 SD Host
  controller [0805]: O2 Micro, Inc. OZ777 SD/MMC Card Reader Controller
  [1217:8520]`, an SDHCI that the payload drives with SdMmcPciHcDxe: 8520
  is `BHT_PCI_DEV_ID_FJ2` of MrChromebox's Bayhub support (`a091558`), and
  `c205ceb` keeps its slot removable. Nothing of coreboot's Realtek code
  applies.
- **Next step**: none planned; the subsystem IDs that the Lenovo
  `DxeO2MicroInit` writes are cosmetic.

## TCC offset on the W541

The M920x has *TCC activation offset* from v1.4.0 (patch 0177).

- **Why later**: on the Haswell client processors of the W541, Intel
  marks the field (MSR 0x1A2 bits 27:24, settable when bit 30 of
  `PLATFORM_INFO` says so) reserved, Linux gives Haswell a TCC offset mask
  of 0, and no Haswell board of coreboot sets it: the option would most
  likely be hidden on every W541. The EC's fan curve, the cooling policy
  and the PL1/PL2 limits cover the same ground.
- **Checked on a W541** (2026-11-03, i7-4810MQ): CPU-01 reads bit 30 of
  `PLATFORM_INFO` set and an offset of 0 in bits 27:24 of MSR 0x1A2.
- **Checked on a W541** (2026-11-03): an offset of 5 written from Linux
  (`wrmsr -a 0x1a2`) reads back on every core, and 0 again after it.
- **Done in v1.6.0** (patches 0220-0221): *Energy Saver* → *Thermal* →
  *TCC activation offset*, 0-15, listed only on a processor with bit 30
  set; the CPU code writes it, 0 included.
- **Checked on a W541** (2026-11-03, build `ci-240-8287da3`): CPU-05 of
  [docs/testing.md](testing.md) passed: the option listed, 15 on every
  core, also after S3, the package throttling at TjMax less the offset
  under load, macOS starting and sleeping with it, and 0 again with the
  option at 0.

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
  same place, though its `WLSW` returns a constant). On a W541 (checked
  on 2026-11-03) `GSTS` reads 1 and `rfkill list` shows nothing
  hard-blocked: 95880 is not for the W541.
- 0185 goes once 96694 is merged; `upstream.yml` reports it by its
  subject. 96645-96647 (NRI cleanups, no-ops on the W541) and 96630
  (acpigen) are in the pin of v1.6.0, 26.09-517.

## Openness score

Dasharo publishes how much of each image is open source.
`tools/sbom.py` already measures it from the image itself, and each
release carries it in its bill of materials: on the ci-150 builds 36.6%
of the code of the M920x image is open source (63.4% Intel's FSP, ME and
other binaries), 85.9% of the W541 `mrc` image and 89.3% of the `nri`
one.

- **Done after v1.6.0-rc5** (2026-11-05), by reading Dasharo's
  [Openness-Score](https://github.com/Dasharo/Openness-Score)
  (`openness_score/coreboot.py`) against the rc5 images, not by running
  it. The classes match (stages, the payload and `dsdt.aml` open;
  microcode, FSP, `mrc.bin` and option ROMs closed; metadata, the splash,
  the runtime regions and vboot's data; erased flash and free CBFS
  space empty) but for two things. The descriptor, the GbE NVM and the
  Platform Data region are data for Dasharo (`IFD_DATA_REGIONS`), and so
  is the VBT, whose format Intel publishes; `sbom.py` counted them as
  closed binaries and now counts them as data too, which moves the
  shares by 0.1% at most (rc5: 37.2% of the code open on the M920x,
  86.2% on `mrc`, 89.6% on `nri`). And Dasharo counts the ME region of
  the descriptor whole, as closed code, unless every byte of it is
  erased (`_classify_ifdtool_region`), where `sbom.py` counts the bytes
  of every region that are not erased flash: on the W541, whose ME was
  cut down with `me_cleaner -S` to 86 KiB of its 5 MiB region, Dasharo's
  rule gives 44.6% (`mrc`) and 46.2% (`nri`), and on the M920x, with 5.2
  MiB of CSME in a 12 MiB region, 24.2%. `sbom.py` keeps its rule, the
  code that is in the flash, and says so in the report; the Dasharo
  figure for an image is the same report with the ME region taken whole.

## EDK II from TianoCore

The payload is MrChromebox's EDK II at a pinned commit, a fork of
TianoCore whose `UefiPayloadPkg` boots on coreboot. Upstream TianoCore
(checked at 2026-10-28) has what the fork once added for coreboot:
SMMSTORE variables (`SmmStoreFvb`, `VARIABLE_SUPPORT=SMMSTORE`),
`CAPSULE_SUPPORT` with `BOOTLOADER=COREBOOT`, `BlSupportSmm`,
`PchSmiDispatchSmm`. What the project uses that upstream has not:
`CfrSetupMenuDxe` and LvglPkg (the whole setup, the *System Preferences*
layout), `BootSplashConfigDxe` and the splash, `UserAuthPkg` (the
supervisor password), `EnrollDefaultKeys` (the Secure Boot keys at the
first boot; upstream has `SecureBootDefaultKeysDxe` with the keys as
PCDs, the standard way), `PlatformGopPolicy`, `NetworkDrivers`,
`EcAcpiBatteryStatusDxe`, the SD/MMC drivers, and the `-D` defines that
coreboot's `payloads/external/edk2/Makefile` passes for the fork
(`BOOTSPLASH_IMAGE`, `LVGL_ENABLE`, `CSMWRAP`, `NETWORK_IPXE`,
`CAPSULE_MAIN_FW_GUID`). Of the 52 patches in `patches/edk2`, fourteen touch
packages outside `UefiPayloadPkg`: `0001` (UiApp), `0004` (OvmfPkg
SioBusDxe), `0007` (Ps2MouseDxe), `0019` (TcgDxe), `0021` (BaseTools,
`tools_def`), `0032` (DxeCore), `0039` and `0043` (Variable, MOR), and
`0041` and `0047`-`0051` (UefiBootManagerLib and UsbBusDxe, already in
mainline: they go).
MrChromebox's branch itself is `edk2-stable202608` and 100 commits of his:
[docs/edk2-migration.md](edk2-migration.md) lists them, each with what it
becomes (40 to the package, 23 carried, 17 to propose upstream, 18 left
out, 2 already in TianoCore's `master`).

The order, each step tested in the QEMU smoke and update tests before any
ROM: (a) the upstream payload built against coreboot at `EDK2_REPO_OFFICIAL`
on a tag `edk2-stableYYYYMM`, with variables, capsules, the ESRT and
Secure Boot through `SecureBootDefaultKeysDxe` and the PCDs of the keys,
without a setup. The first part of it is `tools/build.sh edk2-upstream`
(the workflow `edk2-upstream.yml`, by hand or on a push to a `ci-edk2/`
branch): `edk2-stable202608` as it is, in a q35 image with this tree's
coreboot, SMMSTORE and the TPM 1.2 of the W541, then the steps of the
smoke test that need no setup of the project (`qemu-smoke.py
--upstream`): the Shell writing variables to SMMSTORE across a reboot,
the runtime services moved as macOS's boot.efi moves them, the TPM log
replayed and, in a second image with `SECURE_BOOT_ENABLE`, the store that
the payload formats on an erased SMMSTORE. Each step is reported on its
own, so that the run says what is missing, not only the first thing; the
ones that fail for a known gap do not fail the job, and are listed with
what closes them ([docs/edk2-migration.md](edk2-migration.md#step-a-edk2-stable202608-in-qemu)).
The Secure Boot keys and the capsules come after; (b) the setup, splash
and password as a package of their
own outside the tree (`OuroBiosPkg`: CfrSetupMenuDxe, LvglPkg and its
LVGL, the update screen), built with the upstream tree, so that the
*System Preferences* setup stays as it is; (c) the changes to core
packages carried as patches on the tag, each to be proposed upstream,
moved to the package or left out. Steps (b) and (c) are in CI as an
import of the payload of the ROMs: [`edk2/OuroBiosPkg`](../edk2/README.md)
and `patches/tianocore`, which `tools/edk2-import.py` makes from
MrChromebox's tree with `patches/edk2`, the same sources file for file,
built by coreboot with patches 0216 and 0217 into the third image of
`edk2-upstream` and, for each board, by `tools/build.sh edk2-parity`
([docs/edk2-migration.md](edk2-migration.md#steps-b-and-c-the-package-and-the-carried-patches));
(d) the defconfigs, `tools/build.sh`, `configs/edk2-pins.txt` and
`upstream.yml` on the upstream tags, which are stable, instead of the
mirror of a moving branch. All in the payload: no change to the
read-only part, and a slot that does not boot falls back.

Done in v1.6.0, steps (b) to (d): the defconfigs build the payload from
TianoCore's `edk2-stable202608` with the package and the carried series,
the same payload byte for byte as MrChromebox's `6c14abf865e0` with
`patches/edk2` (`tools/build.sh edk2-parity`), and `upstream.yml` watches
the stable tags of TianoCore and MrChromebox's branch, from which the
import takes new commits ([docs/edk2-migration.md](edk2-migration.md#step-d-the-boards-on-the-package)).
Left: the carried series, shorter one commit at a time, each with the
payload's tests, until what remains of MrChromebox's work is the package
and the patches proposed upstream.

## LVGL v10

From v1.6.0 the setup runs LVGL v9.6, the last release of v9, at the head
of its `release/v9.6` branch (`LVGL_COMMIT` of `tools/build.sh`,
`patches/lvglpkg/0019-0021`), in place of the v9.5.0 of LvglPkg's
submodule. v9.6 deprecates the generic flag functions
(`lv_obj_add_flag()`, `lv_obj_remove_flag()`, `lv_obj_has_flag()`...) for
a setter and a getter per flag, and v10 removes them with the other
deprecated symbols. LvglPkg called them 54 times, in the display engine
and in `lv_port_indev.c`; `lvglpkg/0021` calls the setters and the getters
instead, one for one, as the flag functions of v9.6 call the same
setters, and the build has the deprecation warning on again.

- LVGL's `scripts/migration/migrate_obj_flags.py`, at `c738d776e` in
  v9.6 and on master, was not usable: it turns `lv_obj_clear_flag()`, the
  name LvglPkg uses, into the getter of the flag (the flag stays as it
  was, and it builds), and `lv_obj_has_flag()` of a user flag into a
  clear of it; its own test suite fails on the second. `is_remove` misses
  `"clear"` in one function and is always true in the other.
- MrChromebox's LvglPkg cannot take 0021 while its submodule is LVGL
  v9.5.0, which has no setter per flag.
- `lvglpkg/0019`, the UEFI header bindings out of `lvgl.h`, is a fix for
  LVGL itself: its master has the same lines.

Next step: 0019 and the fix of the migration script to LVGL; then the
pin, when v10 is out (`tools/upstream.sh lvgl` opens an issue).

## HSTI

The Hardware Security Testability Interface is a UEFI protocol with the
result of the security tests of the platform's own firmware, which
Windows reads for its device security report. The tests ask for what
these machines do not have (a locked descriptor, boot guard, pre-boot
DMA protection) next to what they do (BIOS Lock, Secure Boot, the WSMT):
a protocol that reports part "no" tells Windows what the known limits
of the README already say. Not planned; the WSMT (patches 0211-0215)
covers what Windows acts on.

## The _OSI queries of the DSDT

The common platform ASL of coreboot (`southbridge/intel/common/acpi/platform.asl`)
asks `_OSI` for the Windows strings up to "Windows 2006" and sets `OSYS`,
which the DSDT of these boards reads only to hide the HPET from versions
of Windows before XP (`HPTS`). The OS answers `_OSI`; the firmware asks.
No Microsoft requirement (WHCP, the Windows ACPI requirements) asks the
firmware to query the recent strings: they exist for firmware that wants
to behave differently with each version of Windows, which these tables
do not. Asking for "Windows 2012" or later would not change what Windows
does, but it changes Linux, which answers yes to every Windows string and
remembers the newest one the firmware asked for: from "Windows 2012" on,
`acpi_osi_is_win8()` is true, and `drivers/acpi/video_detect.c` then
prefers the native backlight of i915 to the ACPI one (`acpi_video0`), and
reports no backlight instead of the vendor one when neither is there
(checked on Linux mainline at 6628e7d, 2026-11-01). That is a change of the
brightness path on the W541 for no gain elsewhere: not planned. macOS
answers "Darwin" only, unless an OpenCore configuration renames `_OSI`.


## Clearing the memory on every core

*Clear memory at power-on* runs `clear_memory()` of
`security/memory/memory_clear.c` on the boot processor at the exit of
`BS_DEV_INIT`: `memset` below 4 GiB, `memset_pae()` through one PAE
window above. On the M920x of v1.6.0-rc5 that is 2.0 s for 40 GB (about
21 GB/s, BS_DEV_INIT exit "exec"), at every boot where Linux asked
([docs/flashing.md](flashing.md#clearing-the-memory-at-power-on)); on the
W541 1.7 s for 32 GB. The processors are up by then (MP init at
`BS_DEV_INIT_CHIPS`), so the ranges could be split among them with
`mp_run_on_all_cpus()`, each with its own PAE tables and window, as
`memset_pae()` changes the paging of the processor it runs on. DDR4-2400
in two channels peaks at 38.4 GB/s, so the gain is between none and about
0.8 s: a test build that times the clear with one, two and four
processors decides, ramstage only, and the S3 resume never clears.
Measured on the M920x of the port on 2026-11-05
([docs/tests/v1.6.0/m920x-fsp/development.md](tests/v1.6.0/m920x-fsp/development.md#clearing-the-memory-on-every-core)):
42.7 GB in 2.0 s, 21.4 GB/s; in Linux one core zeroes at 29-35 GB/s and
four at about 45 together, but that machine has 32 + 8 GB, dual-channel
over 16 GB only, so the clear is bound by the memory there; the test
build wants two equal DIMMs, and the single-processor loop has headroom
of its own. On the W541 (2026-11-06,
[docs/tests/v1.6.0/w541-nri/development.md](tests/v1.6.0/w541-nri/development.md#clearing-the-memory-on-every-core)):
33.8 GB in 1.65 s, 20.5 GB/s; one core in Linux does 24.3 GB/s of the
25.6 of DDR3L-1600 in two channels, and two, four or eight do no more:
no gain from the other processors there, at most 0.26 s from a faster
loop on one.

What the loop is, in the code of the pin (2026-11-06): `memset` of the
32-bit ramstage is glibc's i386 one, `rep stosl` after the alignment
(`arch/x86/memset.c`), and `memset_pae()` maps one 2 MiB window at a
time (a PDE write and a TLB flush each, some 16,000 windows for 32 GB,
milliseconds in all) and calls that `memset` on it: the clear already
runs a string store on one processor, and the headroom the two records
measure is what `rep stosb` (ERMS, both processors have it) does
against `rep stosl`: in Linux +11% on the W541 (24.3 against 21.8 GB/s
for `memset`) and -17% on the M920x (29.3 against 35.3), where the
memory is the bound anyway.

- **Decided (2026-11-06)**: not made. On the W541 more processors give
  nothing and the loop at most 0.26 s; on the M920x the clear is bound by
  its 32 + 8 GB and `rep stosb` is slower there. The test build with
  one, two and four processors stays optional, for a machine with two
  equal DIMMs where four cores could take the clear from 21 to 35-38
  GB/s; `mp_run_on_all_cpus()` with a PAE window per processor would be
  the shape of it.

## The UEFI Shell in the payload

The payload carries the UEFI Shell (`EDK2_HAVE_EFI_SHELL`, coreboot's
default), with a boot entry after the disks. Measured on the M920x
payload of v1.6.0-rc5 with the volume's files: the Shell is 954,430 bytes,
about 249 KiB compressed alone with LZMA, some 12% of the 2.0 MB
payload, the third file after `CryptoDxe` (470 KiB) and
`VariableRuntimeDxe` (384 KiB, its own copy of the crypto, which it needs
at runtime), ahead of the LVGL display engine (245 KiB), CSMWrap with
SeaBIOS (181 KiB) and iPXE (128 KiB). Left out (`-D SHELL_TYPE=NONE`), it
would save about 0.05 s per boot of reading and decompressing on the
M920x, and 249 KiB of slot on the W541 (295-365 KiB free on rc5).
With Secure Boot on it starts like any file of the firmware volume,
without a check against db (`DxeImageVerificationLib` lets every image
from a volume run), so whoever sits at the boot menu has `mm`,
`setvar` and `bcfg` without a signed loader; the flash and the
authenticated variables stay protected by SMM.

What held it back: the smoke test of the payload (`tools/qemu-smoke.py`)
drove the payload through the built-in Shell: `setvar` into SMMSTORE,
`BootNext` for iPXE and CSMWrap.

- **Done in v1.6.0**: the owner chose the Shell off (2026-11-05).
  `EDK2_HAVE_EFI_SHELL` is off in the three configurations (`SHELL_TYPE`
  NONE); the boot manager deletes the `Boot####` option for the Shell that
  an earlier version made (`edk2/0053`), and the help of *Boot from USB
  drives* no longer lists it (patch 0227). The smoke test boots
  `tools/efi/setvar.c` from an EFI system partition on a fresh copy of
  the image: it takes the variable from QEMU's fw_cfg and writes it with
  `SetVariable()`, for the test variable and for `BootNext`. The upstream
  test (`tools/build.sh edk2-upstream`) keeps the Shell of its payloads.
  Measured on the build of the branch (run 258): the payload of the W541
  from 2,046,796 to 1,807,557 bytes, of the M920x from 2,048,878 to
  1,808,912, 234 KiB each; the slots of the W541 have 528 KiB (`nri`) and
  597 KiB (`mrc`) free. The time on the M920x is to be measured on the
  machine (BOOT-02, the loading of the payload).

## The DPLL of i915 at boot on the M920x

With a monitor on HDMI, i915 reports `*ERROR* DPLL 1 not locked` at
about one boot in three of the M920x (BOOT-04 of `hw-report.py`, a known
message). The display works all the same. Measured on the machine of the
port (Linux 7.0, 1360x768 on HDMI-A-2, 2026-11-03):

- The error is i915's own PLL enable, not the firmware's: `skl_ddi_pll_enable()`
  waits 5 ms for the lock bit of DPLL 1 (libgfxinit waits 10 ms and never
  sees it fail at 84.75 MHz). At boot i915 always re-enables the PLL,
  since the state it inherits cannot be kept (it wants 12 bits per
  colour, port clock 127.125 MHz and a GCP infoframe; libgfxinit runs 8
  bits, 84.75 MHz, no infoframes), and it re-enables it at every
  blank/unblank of the output too, long after the firmware is gone.
- The failure follows the activity of the system, not the firmware's
  state: with the output switched off and on from fbcon, 0 to 4 failures
  in 30 at idle, 7 to 20 in 30 with all four cores busy (the same at 800
  MHz and with turbo off), 30 in 30 with a process reading the display
  registers 20000 times a second. At 8 bits per colour none in 120. At
  boot the system is busy, hence the rate. Not SAGV, not the DC states of
  the DMC (the same with `enable_sagv=0` and `enable_dc=0`), not the
  state i915 inherits (the same before and after a modeset asked from
  userspace), not the change of PLL dividers. When it does lock in time
  it locks within 1 ms; when it does not, the lock bit came 100 to 700
  ms later in the two cases caught by a register poll.
- The same error was logged once under MrChromebox's firmware on this
  machine, and Intel's own CI saw it on Coffee Lake in 2018
  (freedesktop bug 107345: gen9 inherited Broadwell's 5 ms, the spec
  gives no value), where a longer timeout was proposed and not merged.

Nothing in the firmware changes it: the PLL i915 enables is its own
choice from the monitor's EDID, and a handoff i915 could keep (a
fastset) would take deep colour and infoframes from libgfxinit, for a
message that costs nothing. What would fix it is i915 (a longer wait, or
a retry of the enable), to be reported upstream with these numbers;
`tools/hw-report.py` keeps it as a known message meanwhile.

## A USB 3.0 drive after a warm reset on the W541

Found in the tests of v1.6.0-rc6 on the W541 with `nri`
([docs/tests/v1.6.0/w541-nri/README.md](tests/v1.6.0/w541-nri/README.md#findings),
2026-11-06). A SanDisk Ultra Flair (`0781:5591`) left in a USB
3.0 port (xHCI SuperSpeed port SS2, the SS connector on the right side) links at 5 Gb/s after a cold boot
and keeps the link through a suspend; after every reboot from Linux
its link stays in *Polling* with the port reset bit set (`PORTSC`
`0x2f0`) or in *Compliance mode* (`0x340`), Linux logs `usb4-port2:
Cannot enable` each time the xHCI leaves runtime suspend, about every
4 s, and the controller's wake-ups cost package C-states. The v1.3.10
entry of the CHANGELOG describes the same compliance mode on `nri`, in
a different setting (the EHCI controllers hidden, dropped in rc2).

What the firmware does with the SuperSpeed ports on `nri`, in the code
of the pin: in romstage `early_usb_native.c` (built for `nri` and for
Broadwell's MRC, not for `mrc`) warm-resets every USB 3.0 port, with
`WPR` written into each `PORTSC`, and polls the port reset bit `PR` for
up to 100 ms (`warm_reset_usb3_ports()`). With the ports routed to the
xHCI it does so whenever `is_mem_sr()` says the memory is in self
refresh (`GEN_PMCON_2` bit 5), which is true on an S3 resume and on a
warm reboot alike, so the reset runs at every reboot from the OS too,
right after the controller's own reset. In the log of rc6 it times out
(`BIOS_ERR`) on every resume with a device in a USB 3.0 port, and takes
6 µs at a warm boot: too short for a warm reset to have happened at
all, which suggests the ports were not yet in a state that takes a
`WPR` then. In ramstage `usb_xhci.c` resets the disconnected or polling
ports once more, on an S3 resume only (`usb_xhci_reset_usb3()`, which
waits for `WRC` instead). Which of the two leaves the link in Polling
after a reboot, and whether it is this drive, is not known; `mrc` has
no early USB init, so it tells the two apart.

- **Next step**: on the W541, a reboot with another USB 3.0 device in
  that port, then this drive under v1.5.0 (slot B, `update.py
  rollback`) and under `mrc`, which has no early USB init. If `nri`
  alone does it, the romstage reset is the place to look: a test build
  that prints `PORTSC` of each SuperSpeed port before and after the
  `WPR` write and at the end of romstage, on a warm boot and on a
  resume, says whether the reset engages and in which link state it
  leaves the port; if every variant does it, the drive.
- **Measured on 2026-11-06** ([docs/tests/v1.6.0/w541-nri/diag.md](tests/v1.6.0/w541-nri/diag.md#the-usb-30-drive-not-reproduced-a-warm-reset-keeps-its-state)):
  the drive is in the SS connector on the right (the `_PLD` says left).
  Not reproduced under rc6 across warm resets, three resumes, the xHCI
  held in D0, its removal and rescan, and a replug; a warm reset keeps
  the port powered, so the drive keeps its state, stuck or linked, and
  only a cold boot cleared it on 11-05. The measurement build (patch
  0230): at a boot, cold or warm, every SuperSpeed port reaches the
  payload in Rx.Detect, no device connected yet when romstage's `WPR`
  runs (5 µs, nothing to reset), so romstage cannot leave the link
  stuck; at a resume the reset engages, times out at 100 ms in Polling
  with `PR` set and is in U0 10 ms later. Another USB 3.0 device was not
  at hand, nor was v1.5.0 run. The ports themselves:
  [three of the four connectors](tests/v1.6.0/w541-nri/diag.md#the-usb-ports-are-described-on-the-wrong-side)
  are on another panel than the `_PLD` of patch 0071.
- **Settled the same day** ([docs/tests/v1.6.0/w541-nri/diag.md](tests/v1.6.0/w541-nri/diag.md#the-right-ss-connector-trains-its-superspeed-link-badly)):
  a hotplug into that connector under rc6 left it in Compliance mode,
  and a reset of the controller by Linux cleared it; with the same
  drive the right SS connector links at 5 Gb/s 3 times in about 8, the
  left one 6 in 6, and the right one always at 480 Mb/s with its
  SuperSpeed turned off. The SuperSpeed side of that connector is
  marginal on this W541: not the firmware. Left for the docs: the
  sides in patch 0071 (the *Always On* connector is the USB 2.0 port 3),
  and the 100 ms limit of `warm_reset_usb3_ports()`.

## TSC ADJUST after a resume on the W541

At every resume from S3 the W541 logs `[Firmware Bug]: TSC ADJUST
differs: CPU0 0 --> 238168774730. Restoring` (rc6 and v1.5.0 alike;
[docs/tests/v1.6.0/w541-nri/README.md](tests/v1.6.0/w541-nri/README.md#results)):
Linux expects `IA32_TSC_ADJUST` of the boot processor at 0, reads a
value in the 10^11 range and writes 0 back, so the TSC stays coherent
and nothing else follows. The register is zero after a reset and
changes only when software writes it or writes the TSC itself (the SDM:
a write to `IA32_TIME_STAMP_COUNTER` moves `IA32_TSC_ADJUST` by the
same amount), and coreboot writes neither, in no stage and not in SMM;
the payload does not run on a resume. So either the value survives the
suspend in that processor or something between the wake and Linux's
check writes the TSC. `tools/hw-report.py` knows the message (BOOT-04)
on the W541 only; on the M920x it has not been seen.

- **Next step**: on the W541, right after a resume, `sudo rdmsr -p0
  0x3b`, `sudo rdmsr -p0 0x10` and `cat /proc/uptime` (Linux has zeroed
  the register by then, the TSC tells whether it was written: it is
  small after a reset, large if it kept counting), and a test build that
  prints both from the boot processor at the start of ramstage on the
  resume path, before anything else runs.
- **Measured on 2026-11-06** ([docs/tests/v1.6.0/w541-nri/diag.md](tests/v1.6.0/w541-nri/diag.md#tsc-adjust-not-coreboot)):
  N follows the TSC of before the suspend, not the time asleep (−0.5 s
  from the last read before `rtcwake`, with 30 or 60 s asleep), on CPU 0
  only. The measurement build reads `TSC_ADJUST` 0 at every point of the
  resume path, the eight processors included, up to the last code
  before the jump to the wake vector, 1.01 s after the reset: the TSC is
  written after the jump, with a value saved late in the suspend.
  Not coreboot; what is left is Linux between its wake vector and
  `tsc_resume()`, or an SMI it causes. Kernel tracepoints on MSR
  accesses across the suspend reset the machine right after the jump
  (one try): a debug kernel is the way.
