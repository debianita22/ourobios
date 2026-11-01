# Changelog

What changes from one release to the next. The notes of each release on
GitHub include its section; release candidates take the section of the
version they lead to. For the releases before v1.3.0, see their notes on
the [releases page](https://github.com/debianita22/ourobios/releases).

## v1.4.1

- *Security* → *Memory protection* → *Clear memory at power-on*, on both
  boards, has a third setting, *When the OS asks*: the memory is cleared
  only after a reset while the OS held secrets in it, as the TCG Platform
  Reset Attack Mitigation specification (MOR) has it, and a clean reboot
  is that much shorter (2 s on an M920x with 40 GB, 1.7 s on a W541 with
  32 GB). coreboot reads the request of the OS, bit 0 of the UEFI
  variable `MemoryOverwriteRequestControl`, from the variable store
  before the payload (patches 0192-0194); the payload offers the
  variable only with this setting and clears the bit before the next OS
  starts (`edk2/0039`, `edk2/0040`); a boot that finds no variable, as
  the first one with the setting, clears too. *Always*, the default, and
  *Never* do what on and off did, and the OS sees no MOR with them, as
  before. Windows with BitLocker clears its request after a clean
  shutdown; Linux kernels with `CONFIG_RESET_ATTACK_MITIGATION` (Debian,
  Ubuntu, Proxmox) set it at every boot and never clear it, so their
  memory is still cleared at every boot, which is right for an OS that
  does not remove its secrets at shutdown
  ([docs/flashing.md](docs/flashing.md#clearing-the-memory-at-power-on)).
- EDK2 moves to `6c14abf865e0` of MrChromebox's `uefipayload_2608`: the
  branch was rewritten after v1.4.0, and the commit v1.4.0 pins
  (`ddf612165c8b`) is no longer on it. The fall-through to the next boot
  entry when an automatic boot fails, which v1.4.0 always did, becomes a
  setting next to *Auto Boot Time-out*, on by default. The 38 patches of
  `patches/edk2` apply unchanged.
- A fix of mainline EDK2 after the base of MrChromebox's branch
  (`edk2/0041`, tianocore 027e7a437): a boot entry with a short-form hard
  drive path, as efibootmgr, shim and Windows make them, could be skipped
  when the boot manager's cache of that path missed before the disks were
  connected, instead of being tried again after connecting them.
- The builds no longer depend on MrChromebox keeping a pinned commit on a
  branch: `tools/build.sh` takes a pinned EDK2 or LvglPkg commit that his
  repositories no longer give from the project's forks, under a tag
  `pin-<12 digits>`; [`configs/edk2-pins.txt`](configs/edk2-pins.txt)
  lists the EDK2 commit of every release since v1.0.0, and
  `tools/upstream.sh mirror`, every week, opens an issue while one of
  them has no tag.
- `tools/hw-report.py`: BOOT-02 says which *Clear memory at power-on*
  setting the boot read, whether the OS had asked, and whether the memory
  was cleared.
- On the M920x (and the M720q/M920q), the voltage regulator design of
  the Lenovo firmware for FSP-S (`VrPowerDeliveryDesign` 11, patch 0195),
  found in the setup variable of its image: Intel's current limits and
  load lines for this board instead of generic values. With an i3-8100
  power and voltage are the same; it is the setting Lenovo validated for
  every processor these boards take.
- On the M920x (and the M720q/M920q), C1E and the C1/C3 auto-demotion of
  the processor, as Intel's defaults and the Lenovo firmware have them
  (patch 0196): coreboot's CPU init left them off. Idle 0.54 W instead of
  0.57 W with an i3-8100, the same package C-states.
- On the W541 with its ME halted by `me_cleaner -S`, the event log no
  longer records a *Management Engine error* at every boot, nor the
  console a critical `mbp is not ready!`: an ME that stops in its
  bring-up on purpose takes the disable path (patch 0197), so a real
  error of the ME stands out again.
- docs/m920x.md: the fan readout under Linux at every boot
  (`/etc/modules-load.d`, the EC has nothing that loads `nct6683` by
  itself).

## v1.4.0

- After rc3, on the M920x with the Intel ME disabled in the setup, boots
  are at most 5 s slower than the others instead of 15 s: FSP-M no
  longer retries its HECI messages to the disabled ME nor reads its MBP
  (0191). FspMemoryInit takes 0.23 s or, on most boots, 5.23 s: the ME
  answers the DRAM Init Done message late, as it applies its disable
  there, and the message cannot be left out (the boot hangs).
- **ThinkCentre M920x Tiny** (Intel Coffee Lake, Q370): a release of its
  own in every version, `vX.Y.Z-m920x-fsp`, built from coreboot's
  `lenovo/m720q_m920q` board with Intel's FSP-M RAM init and the rest of
  the W541 releases: the EDK II payload and its setup menu, vboot with two
  signed RW slots and a minimal read-only part, signed capsules and fwupd,
  with an ESRT GUID of its own ([docs/m920x.md](docs/m920x.md)). A
  pre-release until it is confirmed on the machine. Patches 0136-0141:
  vboot's data in flash on Cannon Lake, the M920x with its 24 MiB flash,
  vboot with two RW slots, SpeedStep and Turbo Boost as setup options, the
  setup menu; patch 0065 and `edk2/0020` take the `fsp` slots too.
- More than one board in the repository: `boards/<board>/board.sh`
  describes each (variants, flash and chips, blobs, the checks of
  `tools/verify-rom.sh`), and `tools/build.sh --board w541|m920x|all`
  builds them. The W541 files, release names and GUIDs stay as they were;
  the fwupd metadata of the `mrc` release carries the `.cab` of every board,
  and fwupd offers each machine its own.
- `tools/vpd.py`: the machine types and SKU of the M920x, `--sku`.
- From rc2, on the M920x: Latency Tolerance Reporting on the PCIe root
  ports in use, as with the OEM firmware. Without it the NVMe SSD and the
  Wi-Fi card could not use LTR nor ASPM L1.2, and at idle the package
  stayed at PC3 while the cores sat in C10 (0142). The audio codec, a
  Realtek ALC233, gets the whole verb table of the OEM firmware, with its
  Realtek coefficients and the speaker path; coreboot's page for the board
  lists the front audio jacks as not working (0143). DDI-E gets two of
  the four lanes of DDI-A, which has no panel on this desktop: the VBT has
  a DisplayPort on DDI-E, most likely for the VGA option, and i915 warned
  at every boot that it had no lanes (0144).
- From rc3, on the M920x, what macOS needs of the firmware on a Coffee
  Lake desktop, as for the W541, not yet tried with macOS
  ([docs/macos.md](docs/macos.md#thinkcentre-m920x)): the setup options
  *ACPI processor objects* (`Processor`, with `plugin-type` on the
  first) and *C-state configuration lock*, in *Compatibility* → *macOS*
  (0145-0147, 0149); under macOS only, an embedded controller by name,
  `\_SB.USBX` and the PMC of the PCH, as the SSDT-EC, SSDT-USBX and
  SSDT-PMC samples of OpenCore (0148).
- From rc3, the fan of the M920x follows the temperature
  ([docs/m920x.md](docs/m920x.md#fan)). Up to rc2 it stayed at about 850
  rpm whatever the load, and the CPU went to 95-100 °C: coreboot's
  NCT6687D driver cleared the temperature sources of the EC, with none
  in the devicetree, so its firmware read 0 °C everywhere. The board now
  sets the sources the EC firmware has itself, and at every boot tells
  the EC the platform as Lenovo's firmware does (PEG card, TDP class,
  power-loss policy), so that it loads its profile for it (0150-0153).
  The ICE mode of the OEM setup is in *Hardware* → *Cooling*: *Better
  acoustics* (the default), *Better cooling*, *Full speed*.
- From rc3, the M920x wakes on LAN after a shutdown, as with the OEM
  firmware: the override of the PCH for the wake of the LAN from S4 and
  S5 is on, *Energy Saver* → *Wake on LAN from off* (0154-0155). Without
  it Linux arms the port up to S4 only, as the ACPI tables say.
- From rc3, the M920x boots about 4 s faster: the serial console of
  coreboot (COM1 of the Super I/O, a real UART behind an optional
  connector) prints from INFO instead of DEBUG, which at 115200 baud took
  5 s per boot; `cbmem -1` still has every line. The level is a saved
  option: on an installed machine, *Console* → *Console Log Level*
  ([docs/m920x.md](docs/m920x.md#boot-time)). The help of *Clear memory
  at power-on* gives its time there, 2 s with 40 GB (0156).
- `tools/vpd.py set --from-lenovo DUMP`: the serial number, MTM and UUID
  of an M920x from the dump of its Lenovo firmware (the `DmiVar`
  variables of the AMI NVRAM), the UUID of the factory included, which
  is not on the label ([docs/m920x.md](docs/m920x.md#serial-number-and-machine-type-vpd)).
- From rc3, the DMI and SATA Power Optimizers of the PCH on the M920x, off by
  default in the Coffee Lake FSP-S and never set on Cannon Lake: with LTR on
  every link (0142), the package still stopped at PC3 at idle (0157-0158).
- From rc3, the Windows product key of a machine that came with it, in an
  ACPI MSDM table as with the OEM firmware, from the `msdm_product_key`
  key of the VPD (0159); `tools/vpd.py set --from-lenovo` takes it from
  the dump of the Lenovo firmware, `--windows-key` by hand.
- From rc3, *Hardware* → *Devices* on the M920x, as the Devices menu of the
  OEM setup: Ethernet, audio, Wi-Fi with its Bluetooth, front and rear USB
  ports (0160-0162). The
  TCO watchdog of the PCH works (`iTCO_wdt`), which Proxmox blacklists:
  [docs/m920x.md](docs/m920x.md#status) says how to use it for its HA.
- After rc3, on the M920x: *Console* → *Serial Console* in the setup, to turn
  the serial console off (about 1 s less per boot at INFO); the speed of
  the CPU fan in the boot log, or an error when it does not turn (0163);
  no more "LPC IO decode base 0!" error at every boot (0164), nor the
  warnings for the minimum D-state of the PCH thermal device, the GPE
  routing and the missing RW_VPD (0165-0167); under Linux, no more "failed
  to evaluate _DSM 2c176672-..." from iwlwifi: the Wi-Fi card has an ACPI
  node (0168).
- After rc3, the PEG port of the M920x riser slot off when no card is on
  it (0169): FSP-M's Auto left the empty port on at almost every boot,
  and with it the package stopped at PC3 at idle (about 1.1 W) even with
  0157-0158; the PC9 measured with ci-143 came from a boot on which it
  was off. *Hardware* → *Devices* → *PCIe riser slot*: Auto, Enabled
  (for a card that Auto does not see), Disabled.
- After rc3, about 0.5 s less at every boot of the M920x and of the W541:
  SMM no longer reads the *BIOS Lock* option from the flash without
  cache at the end of the boot, ramstage gives it the value (0170).
- After rc3, the M920x with other processors and cards than the port
  machine's: PL2 1.25 times the TDP as the OEM firmware, instead of 65 W
  for every processor (a T model drew 65 W in bursts, a 65 W one with
  Turbo Boost stopped under its 81 W); the fan class follows PL1 when it
  is set; Turbo Boost and Hyper-Threading are in the menu only where the
  processor has them (0171). The *Wireless* switch also turns off a CNVi
  card; without processor graphics (an F processor, or *Intel graphics*
  off in the setup) the riser port stays on; EDK2 loads the option ROMs
  of the cards, so a graphics card on the riser shows the firmware screen
  and the setup (0172 and the M920x defconfig).
  A machine that already saved its settings keeps the PL2 it had:
  *Energy Saver* → *Processor* → *CPU PL2 power limit* → 0.
- After rc3, on the M920x, two bugs reported upstream for the M720q and the
  M920q: the DisplayPort output was described as HDMI in the VBT, so a DP
  monitor was not detected under Linux (coreboot bug #670, 0174); a
  memory training cache made with another processor or with
  Hyper-Threading the other way is no longer given back to FSP-M, which
  trains again (0173). The first boot after the update trains the memory
  once, about 40 s with a black screen. The global reset of bug #655
  was already fixed in the coreboot of rc3.
- `tools/update.py other-slot` also takes the test builds of the CI
  (`ouroBIOS-ci-N-...`), to try one in the slot that is not running.
- After rc3, on the M920x, an RTC power loss (the coin cell out or flat, the
  clear-CMOS jumper) resets the setup options to their defaults, as with
  the Lenovo firmware: coreboot deletes them before the memory training
  reads the first one, and the setup writes each default back (0175,
  [docs/m920x.md](docs/m920x.md#resetting-the-settings)). The ME comes
  back on, *Firmware protection* too (turn it off again before writing the
  flash with flashrom), and so do the boot entries a setup switch had
  removed (iPXE, CSMWrap, USB drives); the other boot entries, the Secure
  Boot keys, the setup password, the VPD and the event log stay. With a
  flat coin cell every loss of AC power does it. Only the slots of v1.4.0 and
  later do it.
- After rc3, the state of the Intel ME of the M920x, which the OS cannot ask
  once the ME is disabled (no HECI device): *General* → *About this
  ThinkCentre* → *Management Engine* in the setup, with its status
  registers in the help, and two SMBIOS OEM strings (type 11, `ME: ...`
  and `ME HFSTS: ...`) for `dmidecode -t 11` and `tools/update.py status`
  (0176, [docs/m920x.md](docs/m920x.md#intel-me)).
- After rc3, *Hardware* → *Cooling* → *TCC activation offset* on the M920x,
  as in the OEM setup: the processor throttles that many °C below its
  TjMax (0-15, default 0), cooler and quieter under a long load; listed
  on the processors that can take it (0177,
  [docs/m920x.md](docs/m920x.md#fan)).
- After rc3, three switches of the OEM setup in *General* → *Boot* of the
  M920x, which the payload reads (0178, `edk2/0036-0037`,
  [docs/m920x.md](docs/m920x.md#boot-options)): *Option ROMs of the cards*,
  *All* or *Graphics cards only* (NVMe, SATA and USB cards still boot with
  the firmware's own drivers); *Boot from USB drives*, off to keep them out
  of the boot order and the boot menu (not a security setting: the Shell,
  CSMWrap, an OS entry and the fallback path still start them); *Boot menu
  prompt*, off to hide "Press ESC" on the logo, while Esc still works.
- After rc3, updates of the M920x keep the memory training: the capsules
  rewrite the two RW slots only, `tools/update.py other-slot` leaves
  `RW_MRC_CACHE` as it is (`--retrain` empties it), and *Go back to* in
  the setup no longer erases it (0179, `edk2/0038`). The new slot trains
  again only when the cache was made with another FSP-M, processor or
  Hyper-Threading setting (0173), so an update no longer takes the 20-40 s
  of a training; the first update from rc3 or earlier usually still does,
  once. Staging these capsules takes the `tools/update.py` of v1.4.0 or later,
  which still takes those of rc1-rc3: the release notes now download it
  from the commit of the release instead of `main`. The W541 still empties
  the cache at every update
  ([docs/update.md](docs/update.md#what-changes-and-what-stays)).
- After rc3, on the W541, the state of its Intel ME, which `me_cleaner -S`
  stops in its bring-up loader and whose HECI interface the firmware hides
  by default, so that only the boot log told what it did: *General* →
  *About this ThinkPad* → *Management Engine* in the setup, with the six
  status registers (HFS1-6), the working state, the mode, the error code
  and the progress phase in its help, and the two SMBIOS OEM strings of
  the M920x (type 11, `ME: ...` and `ME HFSTS: ...`) for `dmidecode -t 11`
  and `tools/update.py status` (0181). Lynx Point hides HECI before the
  tables are written, so coreboot reads the registers earlier, when the
  devices are initialized, without a message to the ME and not on S3
  resume. The progress phase comes first: an ME stopped in the bring-up
  loader by the AltMeDisable strap, as the one of the release images, is
  *Disabled (AltMeDisable, BUP)*, any other stop there *Stopped in BUP
  (state 0xNN)*, and only then the operation mode gives the texts of the
  M920x. The help of *Intel ME interface (HECI)* no longer says that the ME
  keeps running. None of the W541 changes of v1.4.0 has run on the laptop
  yet: [docs/testing.md](docs/testing.md) lists their tests, marked *not
  yet tried*.
- After rc3, *General* → *Boot* of the W541 has two of the switches of the
  M920x, which its payload reads (0182, `edk2/0037`), both on by default:
  *Boot from USB drives*, off to keep the USB drives of the laptop and the
  dock out of the boot order and the boot menu (not a security setting: an
  entry made by an OS, the Shell, CSMWrap, *Boot From File* and the
  fallback path still start them), and *Boot menu prompt*, off to hide
  "Press ESC" on the logo while Esc still opens the boot menu. The *Boot*
  card is now always shown. No *Option ROMs* switch: the W541 payload runs
  no option ROMs (`EDK2_LOAD_OPTION_ROMS` stays off), as the VBIOS of the
  NVIDIA GPU is a legacy image for the OS only, and the one other card with
  a ROM would be an ExpressCard, whose unsigned code would then run in the
  firmware.
- After rc3, three EC settings of the Lenovo setup of the W541, decoded from
  its firmware, GNET94WW (0183): *Energy Saver* → *Power* → *Power on with
  AC attached*, off by default, which starts the laptop, or resumes it from
  hibernation, when the AC adapter is plugged in; *General* → *Sound* →
  *Keyboard beep*, on by default, the beep of the EC for a key combination
  that it does not handle; and *USB always on* → *AC and battery*, which
  now does what it says. Before v1.4.0 the devicetree set the EC bit that
  keeps the yellow USB port unpowered on battery, so *AC and battery* most
  likely acted as *AC only* in hibernation and power-off. **A W541 already
  set to *AC and battery* powers that port on battery in hibernation and
  power-off from v1.4.0 on, which runs the battery down**; *AC only* keeps the
  old behaviour, and the help of *USB always on* says what each value does.
  The EC keeps these bits only while it has power, and a slot before v1.4.0
  (after a vboot fallback, or with `update.py other-slot`) writes the old
  ones again. The other H8 ThinkPads, the T440p included, are unchanged.
  Whether *Keyboard beep* changes anything is for the test on the laptop:
  the Lenovo firmware also writes a beep mask that differs from ours by one
  bit.
- After rc3, *Security* → *Virtualization* → *Untrusted ExpressCard and
  Thunderbolt* on the W541 (0184), off by default and shown with *Intel
  VT-d* on: the root ports of the ExpressCard slot and of the Thunderbolt
  port get the ACPI `ExternalFacingPort` property, and Linux with its
  IOMMU on (`intel_iommu=on`) treats the devices behind them as untrusted,
  with a DMA domain of their own and bounce buffers. The DMAR opt-in flag
  stays off: nothing protects the memory before the OS (the payload has no
  IOMMU driver), and Windows Kernel DMA Protection needs TPM 2.0, which the
  W541 does not have. The comments of the DSDT, which called the two ports
  the WWAN and the ExpressCard slot, are fixed.
- After rc3, the EC events that the Lenovo firmware of the W541 reports to
  the OS, which our DSDT dropped (0190), with the same HKEY codes: dock and
  undock (0x4010, 0x4011), the thermal alarm of the EC (the thermal zone
  notified, and 0x6022 at its critical level), the battery alarms (0x6011,
  0x6012), NumLock (0x6000) and the 0x1009 hotkey when the OS enables it;
  `thinkpad_acpi` makes kernel messages and netlink events of the alarms.
  And the software mute handshake (`HAUM`, `SAUM`): `thinkpad_acpi` no
  longer adds its *ThinkPad Console Audio Control* mixer on top of the EC,
  and mute goes through the codec, as with the Lenovo firmware
  (`thinkpad_acpi.software_mute=0` keeps the old way). The T440p, whose
  Lenovo DSDT handles these events the same way, gets them too, NumLock
  aside. Left out, with the reason in `ec.asl`: the events that the Lenovo
  firmware drops too or handles in its SMM code, the CPU limits that the EC
  asks for (they need a `_PPC` policy and a test with a smaller adapter),
  the radio switch, the Ultrabay and sticky Fn
  ([docs/roadmap.md](docs/roadmap.md#ec-events-left-out)). Checked in
  `acpiexec` on the DSDTs of the W541 and the T440p.
- After rc3, `nri`: the 1D training of the read timing, the write timing and
  the read voltage of ranks 1-3 of each channel ran with the register file
  of rank 0, and the W541 of [docs/raminit.md](docs/raminit.md) has four
  ranks per channel. The fix of Angel Pons, not merged upstream yet
  ([Gerrit 96694](https://review.coreboot.org/c/coreboot/+/96694), 0185),
  with the revision of the saved training bumped to 3 (0186): a slot with
  the fix never boots on a training made without it, and an older slot
  never boots on one made with it, also after a vboot fallback. The first
  boot of a v1.4.0 slot trains, as after every W541 capsule. A DIMM with
  more than the 10 column address bits that Haswell drives, as a 16 GiB
  SO-DIMM of 8 Gb chips ([coreboot ticket
  626](https://ticket.coreboot.org/issues/626): margins that look fine,
  then corrupted memory), is left out with an error that names its slot,
  and the laptop boots on the others (0188; `mrc.bin` and the Lenovo
  firmware do not support them either). The native RAM init records its
  timestamps as `mrc.bin` does, so `cbmem -t` and `tools/hw-report.py`
  (MEM-01, BOOT-02) see it (0189). On both variants SMBIOS gives each slot
  the size and ranks of its own module, also with two DIMMs of different
  sizes in a channel (0187).
- After rc3, the settings reset on an RTC power loss of the M920x (0175) has
  its trigger for Haswell (0180): romstage deletes the setup options before
  the first one is read, with a POST code before and one after, so that a
  boot that follows one that hung there skips it; on Haswell the option
  needs `CMOS_POST`. It stays off in the W541 builds
  (`CONFIG_DRIVERS_EFI_RESET_OPTIONS_ON_RTC_FAILURE` is not set in
  `configs/w541-*.defconfig`) until the M920x passes its test (OPT-05 of
  [docs/testing.md](docs/testing.md#setup-options-opt)) and the W541 is
  checked for whether software can set its RTC power loss bit, which would
  then turn *BIOS Lock* off at the next boot. A CMOS clear still keeps the
  settings of a W541
  ([docs/roadmap.md](docs/roadmap.md#settings-reset-on-the-w541)).
- `tools/update.py status` also shows the state of the ME (from v1.4.0,
  on both boards) and of the flash
  protection, on both boards: whether `WP_RO` is in a locked Protected
  Range, *BIOS Lock*, whether flashrom can write the slots.
  `tools/update.py protection` reads it in detail from the registers of
  the SPI controller, each Protected Range mapped onto the regions of the
  flash map, without writing anything; `--expect-ro on|off` gives an exit
  status for scripts, 2 whenever it cannot tell
  ([docs/update.md](docs/update.md#flash-protection)). On the W541 it reads
  the SPI controller of Lynx Point, behind the LPC bridge, after a check of
  its RCBA, through one read-only page of `/dev/mem`; *BIOS Lock* counts as
  on with SMM_BWP set, or with BLE set and BIOSWE clear; `other-slot` warns
  about *BIOS Lock* and the Protected Ranges there too. A kernel that
  refuses the page (lockdown, or `IO_STRICT_DEVMEM` while `intel-spi` and
  `iTCO_wdt` hold it) gets the reason and a hint, and *BIOS Lock* and the
  saved options are still shown. On both boards the texts now say that the
  protection holds until the next reset or S3 resume, and that a change of
  the options applies from the next boot or resume. The names of the
  release candidates and CI builds of `nri` (`-rc3-nri`, `ci-N-...-nri`),
  which read as `mrc`, are recognised.
- `tools/hw-report.py`: a read-only report of a running machine, PASS, WARN
  or FAIL per area with thresholds: boot time, the RAM init against the
  training cache (FspMemoryInit over 2 s with a valid cache is a warning,
  over 5 s a failure), firmware and kernel log, package C-states, PCIe ASPM
  and LTR, the riser port, fan, ME, TPM, vboot slot, flash protection,
  SMBIOS and ACPI tables; with a copy of the flash also the event log,
  `RW_NVRAM` and the saved options. [docs/testing.md](docs/testing.md): the
  release test matrix of the M920x and the W541.
- `tools/hw-report.py` on the W541, written from the code of v1.4.0 (it has not
  run there yet): BOOT-03 no longer fails at every boot on the `[CRIT]` line
  of the reduced ME (`intel_me_path: mbp is not ready!`); BOOT-04 no longer
  takes the GPLV and `_DSM` messages, gone since v1.3.5, for known ones,
  which would hide them coming back; MEM-01 and BOOT-02 take the RAM init of
  `nri` from its timestamps (0189; the whole romstage on older slots), and
  *Using cached memory parameters* counts as a valid cache; FLASH-01 reads
  the registers through the probe of `update.py` on both boards and, when
  the kernel refuses them, compares the Protected Range that coreboot logged
  with `WP_RO` (`INFO`, never `PASS`); a Protected Range over `WP_RO` with
  FLOCKDN off is a `WARN` on both boards; ME-01 takes the state from the
  SMBIOS strings of 0181, or the `ME: HFSTS1-6` line of the log, against
  *Intel ME interface (HECI)*. A new EC-01 warns when the EC firmware is
  older than 1.15 (GMHT30WW), which fixes CVE-2019-6171 and which only the
  Lenovo firmware can install
  ([docs/flashing.md](docs/flashing.md#before-you-start)). CPU-01 also gives
  whether the TCC offset can be set and its value (both boards), FAN-01 a
  hint for `thinkpad_acpi`, TPM-01 the state of a TPM 1.2, and a check that
  misses its log lines names the console log level of the boot.
- `tools/sbom.py`: the software bill of materials of a ROM, read from the
  image itself: coreboot, vboot, libgfxinit, EDK II, LvglPkg, iPXE, CSMWrap
  and SeaBIOS with versions and licenses; Intel's FSP-M and FSP-S,
  microcode, ME, flash descriptor, GbE and VBT (on the W541 also `mrc.bin`
  and the NVIDIA VBIOS) with versions and SHA-256; how much of the image is
  open-source code, closed binaries, data and empty flash. Each release
  carries it as `…-sbom.md` and as CycloneDX 1.5 (`….cdx.json`), both in
  its `SHA256SUMS`, and its notes a short table from it and the checksums.
- The notes of the M920x releases say what a first install with `flashrom
  --ifd -i bios` empties (settings, boot entries and Secure Boot keys, the
  event log, the memory training, vboot's state, the VPD) and copy the VPD
  of the backup into the image before writing it (`tools/vpd.py copy
  --in-place`).
- Issue forms for the repository: *Bug report* (component, device and
  variant, firmware version, how it was written, how often, the
  `tools/hw-report.py` report and the coreboot log), *Feature request*
  and *Hardware report* (processor, memory, cards, what works and what
  does not); no blank issues, links to the docs instead. What was looked
  at for this version and left for later: [docs/roadmap.md](docs/roadmap.md).

## v1.3.10

- macOS with OpenCore ([docs/macos.md](docs/macos.md)): two setup options,
  *C-state configuration lock* (CFG Lock; off, macOS boots without
  OpenCore's `AppleXcpmCfgLock` quirk) and *ACPI processor objects*
  (*Processor*: the CPUs declared the way macOS looks for them, without an
  SSDT that wraps them); under macOS only, the HPET with IRQ 0 and 8 and
  the 8254 timer without IRQ 0, as on a Mac, and the last backlight level
  put back at wake, which the resume path starts at 50% (patches
  0089-0091, 0095, 0096). With the `_OSI` to `XOSI` rename of some
  OpenCore configurations the parts under macOS stay off: remove it
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- `nri`: v1.3.10-rc1 hid the two EHCI controllers, as the native RAM init
  puts every USB port on the xHCI one. With it a USB drive plugged in was
  mostly not found, under Linux and macOS: under Linux, whenever the xHCI
  controller was in runtime suspend (kept in D0, it found the drive), and
  in a USB 3.0 port the SuperSpeed link went to compliance mode, so the
  drive ran at USB 2.0 speed. It was the only change to USB, and rc2 drops
  it: the EHCI controllers stay as in v1.3.9. Verified on the W541 with
  rc2 (nri, installed with the capsule): the drive is found in all four
  ports, and in a USB 3.0 one it links at SuperSpeed (U0, 5 Gb/s).
- ACPI: the model, serial number, type and OEM name of the battery as
  strings (they were buffers); the CPUs notified by `_PSR` only when the
  power source changes, not at every read; the EC wake cause read as one
  byte (patches 0092-0094).
- From rc3, more for macOS ([docs/macos.md](docs/macos.md)): the wake
  source left in PM1_STS and GPE0_STS at S3 resume, for every OS, as with
  the OEM firmware (macOS tells a wake by the user from a dark wake by
  it), with SCI_EN set before the SMIs come on so that a power button wake
  cannot turn into a power off (0099); under macOS, the sleep LEDs and the
  wake on lid opening set in `_PTS`, as `_SST` and `_PSW` do under Linux
  (0100); the backlight registers and the MMIO of the xHCI controller
  addressed at the BAR they have when the methods run, all 64 bits of it,
  not the one of boot (0101, 0102); the battery read one byte at a time,
  so that macOS reads it without ECEnabler (0103); two options in
  *Hardware* → *Graphics*: the display left to the OS at wake, without the
  mode set of libgfxinit, and the firmware screen at the panel's
  2880×1620 (0104-0107, off by default).
- From rc4: with *Firmware screen resolution* on *Panel, up to 2880 x
  1620*, the setup of rc3 opened on a black screen, at any UI scale: a page
  fault in LVGL v9.5.0, whose circle mask writes past its buffer for some
  radii from 922 px on, and the orbs of the wallpaper reach 939 and 1004 px
  at 1620 px of height. rc4 takes the fix of LVGL v9.6.0 and draws the orbs
  without a circle mask, which only clipped pixels that their gradient
  leaves transparent (lvglpkg/0016-0017); the smoke test of the payload
  (`tools/build.sh smoke`) now also opens the setup at 2880×1620, and stops
  on an exception of the payload. Verified in QEMU (q35) with the payload
  of rc4: at 2880×1620 the setup opens and answers the keys at each of the
  four UI scales (rc3: page fault at each); at 1920×1080 the whole smoke
  test passes, and the wallpaper differs from rc3's by at most 2 levels per
  color. A capsule update at 2880×1620 too, from a ROM of
  `tools/build.sh update-test` with the screen at that size: the update
  screen drawn through the whole write, the capsule applied, the other slot
  equal to it, then booted by vboot; so rc4 installs with `update.py stage`
  on rc3 with the option on. Verified on the W541 with rc4 (nri), installed
  that way on rc3 with the option on: the update succeeded, the firmware
  screen is at 2880×1620 and the setup opens. Out of the black screen on
  rc3 without updating, from Linux: `sudo efibootmgr -n` with the number of
  the *UEFI Shell* entry, a restart, then in the Shell
  `setvar gfx_fb_limit -guid ceae4c1d-335b-4685-a4a0-fc4a94eea085 -bs -nv
  =00000000` and `reset`: the firmware screen is at 1920×1080 again. A
  Linux started by OpenCore with `RequestBootVarRouting` sees OpenCore's
  boot entries, not the firmware's, and no *UEFI Shell*: there, update.
- From rc5: rc3 and rc4 powered the laptop off at every wake from S3, by
  the power button, the lid or a key, under Linux and macOS. The EC wakes
  the system through the power button line, so PWRBTN_STS is set at every
  wake, and rc3 leaves it to the OS (0099); but the SMI handler ran its PM1
  handler at any SMI# with that status set, also with `SCI_EN` set, and
  ramstage sends APMC commands before the OS resumes (finalize, the lock of
  the other vboot slot): the first one turned the wake into a power off.
  The SMI handler now leaves PM1 and GPE0 events to the OS when `SCI_EN` is
  set, as `soc/intel/common` does (0108). The event log of the W541 with
  rc4 (`tools/elog.py`) shows it at each wake: *ACPI wake* S3 from the
  power button, then *Power button*, written by the PM1 handler, and *ACPI
  enter* S5; the next boot reads POST code 0x76 (`BS_POST_DEVICE`, where
  `lpc_final()` sends the finalize command). Verified on the W541 with rc5
  (nri) under CachyOS: the laptop resumes from S3 again.
- From rc6: no "No handler for Region [ERAM]" for `BAT0._STA` and
  `BAT1._STA` in the log of macOS at boot. macOS evaluates them before its
  EC driver is up; they now read no EC RAM before `_REG` (3, 1) and return
  "no battery" until then, and `_REG` notifies both batteries (0x81) when
  the handler arrives, so that the OS checks them again (0109). Linux runs
  `_REG` before it looks at the batteries: nothing changes there. Checked
  in `acpiexec` on the DSDT of the W541.
- From rc6, for *Light the display up at wake* off, with which macOS left
  the display off at wake on rc5: it reads the live HPD state of the panel
  port (`SDEISR`) before it powers the panel up, and an eDP panel raises
  HPD only once it has power, which that path did not give it (with the
  option on, libgfxinit powers the panel up to probe it). Measured on the
  W541 under Linux: the HPD of the panel port is high with the panel
  powered and low with it off, with its detection enabled. At wake with
  the option off the firmware now forces the panel VDD on, without the
  power sequence and the backlight, and waits its power-up delay, 200 ms
  (0111); enables the hotplug detection of the ports whatever the
  register holds (0110); and logs what the OS finds, `GMA: SDEISR ...
  PP_STATUS ... PP_CONTROL ...` in `cbmem -c`. Linux takes the forced
  VDD over. Verified on the W541 with rc6 under CachyOS, with the option
  off: at wake the log reads `PCH_PORT_HOTPLUG 00000000 -> 00101010` (S3
  clears the register, and the code before 0110 enabled the detection
  again too) and `SDEISR 00800000 PP_STATUS 00000000 PP_CONTROL
  00000008`: HPD high, the panel with VDD and no power sequence; i915
  shows no warning. Under macOS the display still stays black at wake
  with the option off (the laptop wakes): leave it on there, unless the
  OS side does what is missing (next point).
- rc7 and rc8, for macOS with *Light the display up at wake* off: macOS
  drives the panel of the W541, on DDI D, as a DisplayPort sink. At wake
  it trains the link and runs the pipe, but it never powers the panel up
  through the panel power sequencer nor enables the backlight, which
  libgfxinit does with the option on. rc7 did both from the `_WAK` of
  the firmware under macOS (0112); but then the backlight came on at
  every wake from S3, the dark wakes of macOS too, before macOS had
  decided to light the display up. From rc8 0112 is gone: that is for
  the OS to do when it lights the display up, as a Lilu plugin for
  AppleIntelFramebufferAzul does (after `LightUpDP`, the power sequence
  and then the backlight; before `DisableDisplay`, the backlight only,
  so that the panel keeps power and HPD), and dark wakes stay dark. 0110
  and 0111 stay: Azul checks HPD before anything else at wake.
  SSDT-PNLWAK, with the `_WAK` of the DSDT renamed, does what 0112 did.
- From rc9, under macOS on AC, closing the lid sleeps (0113). macOS takes
  the panel of the W541 for an external display: with no built-in
  display online, IOGraphics puts it in desktop mode, and in desktop mode
  on AC macOS does not sleep on lid close; the panel stayed lit inside
  the closed lid. On a lid close event under macOS on AC, the EC methods
  now press the sleep button, as Fn+4 does; on battery macOS sleeps by
  itself. No clamshell mode under macOS on AC: a closed lid sleeps there
  also with an external display. Linux and Windows as before. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc10, the lid reads no EC RAM before the EC driver of the OS is up
  (0114), as the batteries since rc6 (0109): macOS read it at boot before
  its EC driver, logged "No handler for Region [ERAM]", took the lid for
  closed and found it open only some 20 s later, which would turn off a
  panel that it drives as built in. Until `_REG` the lid now reads open,
  and `_REG` notifies it so that the OS reads it again. Linux runs `_REG`
  before it looks at the lid: nothing changes there. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc10, under macOS with *NVIDIA discrete GPU* on in the setup, the
  GPU is powered off at boot (0115): macOS has no driver for it (Apple
  removed the Kepler drivers in Monterey), and it stayed powered in D0
  for nothing. `-wegnoegpu` only hides it, and the SSDTs that call the
  `_OFF` of the OEM firmware find no such path in this DSDT. The `_INI` of
  the PEG port calls the `_OFF` of its power resource, the sequence of
  the runtime power management of Linux, and `_WAK` calls it again if
  the wake powered the GPU: the firmware powers it at boot, so at a
  resume from S4. *Hardware* → *Graphics* → *NVIDIA GPU off under
  macOS*, on by default and shown with the GPU on: off leaves the GPU
  powered, e.g. for the Kepler drivers that OpenCore Legacy Patcher
  installs, without the `_OSI` rename, which would turn off all the
  other fixes under macOS. Linux and Windows as before. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc11, after a review of all the patches (0116-0119): no full
  flash access for the OS at S3 resume, when the boot that the OS
  resumes from had the firmware update mode on and the payload found
  no capsule (0116; until now the lock of the vboot slot switch ran
  first and covered it, by link order); the SMI handler in SCI mode no
  longer clears PM1_STS and GPE0_STS when their bits are the only ones
  in SMI_STS, which threw away an event the OS had yet to see (0117,
  as the common SMM code of soc/intel); at wake with *Light the display
  up at wake* off, the firmware waits for the HPD of the panel instead
  of the whole 200 ms power-up delay, and logs `GMA: HPD up after N ms
  with VDD` (0118); the framebuffer limit and the aperture size options
  are read once per boot instead of twice, each read a walk of the
  option store in flash (0118, 0119). The DSDT does not change.
- From rc11 too, the AC adapter reads no EC RAM before the EC driver of the
  OS is up (0120), as the batteries (0109) and the lid (0114): the last
  two "No handler for Region [ERAM]" of macOS at boot. Until `_REG` the
  adapter reads as at the last check, on AC at boot, and `_REG`
  notifies it. And *Hardware* → *Expansion ports* has a switch for each
  SATA port of the W541 besides the drive bay (0121): the M.2 slot on
  the I/O subcard (port 1), the M.2 WWAN/SSD slot (port 4) and the
  Ultrabay (port 5), on by default. A port turned off is not implemented
  in the controller, and the OS does not wait for a link on it at boot
  and at every wake, about a second per empty port. Keep the port of a
  slot with a drive on: macOS on the M.2 SATA drive needs port 4.
- From rc12, coreboot `26.09-438-g206078d6d990`, 158 commits after the pin
  of the earlier release candidates (26.09-280): the 117 patches apply
  with the same bodies, only their context moves (the PLATFORM_INFO and VR
  MSR refactoring of cpu/intel/haswell); upstream does not touch the
  cache-as-RAM layout, vboot, the console, the timestamps nor the FMAP and
  CBFS caches, and bootblock and romstage have the same regions
  (`configs/ro-interface.txt`, `rw-ok`), so the slots still run behind the
  read-only part of v1.3.9. EDK2 from MrChromebox `uefipayload_2608` at
  `ddf612165c8b`, three commits after the pin (the setup hotkey, failed
  automatic boot options, the SubForm parsing fix that our patch 0002
  already covered).
- From rc12, *Compatibility* → *macOS* → *Intel display audio* (0122):
  the HD Audio controller of the display ports of the Intel GPU (0:3.0),
  on by default: the audio over the mini DisplayPort and a port of the
  dock (DP-B and DP-C in the VBT; the panel and VGA have none). Under
  macOS AppleHDAHDMI_DPDriver waited 10 s for its codec at every wake and
  at every sleep with the display off: 10-20 s of wake time instead of
  about 1.3 s, with the battery polling held meanwhile. Off, the
  controller is hidden for every OS, and with it the audio over those
  ports.
- From rc12, more of an OpenCore configuration in the firmware, under
  macOS only ([docs/macos.md](docs/macos.md)):
  - with *ACPI processor objects* on *Processor*, `plugin-type` on the
    first thread, which turns XCPM on, as `SSDT-PLUG` does (0123);
  - *Compatibility* → *macOS* → *Panel under macOS* (0124, 0129), how the
    Intel framebuffer of the configuration has macOS drive the panel.
    *External display*, the default on the W541, whose panel is on DDI D
    where the laptop framebuffers have no built-in connector: macOS has
    no backlight control for it, so the brightness keys set the PWM
    themselves, as the `_Q14`/`_Q15` renames and their SSDT did, and
    closing the lid on AC sleeps the laptop (0113). *Built-in display*,
    for a laptop framebuffer with its built-in connector on DDI D (not
    tried when rc12 came out; tried since, see rc14): the backlight
    device of macOS, `\_SB.PCI0.GFX0.PNLF`
    (`_UID` 15, the PWM at the 0xad9 of the Haswell Macs from boot and
    after every wake, as `SSDT-PNLF`), an ambient light sensor (`ALS0`, as
    `SSDT-ALS0`), the keys as ACPI events for BrightnessKeys.kext, and the
    lid left to macOS;
  - *Compatibility* → *macOS* → *USB, audio and LAN wake* (0130), off by
    default: macOS does not arm the wake of the USB, HD Audio and
    Ethernet controllers (`_PRW` with S0), as the `_PRW` renames of
    OpenCore configurations did against wakes right after sleep;
  - `\_SB.USBX`, the USB power properties of the SMBIOS of the Macs from
    Skylake on, as `SSDT-USBX` (0131).

  Remove from the configuration what each of them replaces: macOS takes a
  second definition of an object for an error and drops the SSDT. The
  NVRAM of macOS needs no emulation either
  ([docs/macos.md](docs/macos.md#native-nvram)).
- **From rc12, OpenCore needs the `Booter` quirks for the memory
  attributes table of the firmware**: `RebuildAppleMemoryMap` on and
  `EnableWriteUnprotector` off (`SyncRuntimePermissions` on too, up to
  rc15: see rc16 and rc17 below). With the
  quirks of the configuration of the W541 up to rc11
  (`EnableWriteUnprotector` on, the other two off) macOS restarts the
  laptop at the resume from S3, with no panic report, and `pmset -g log`
  reads `Failure during wake: IGPU(),HDEF(),SATA(AppleIntelPchSeriesAHCI)
  : Some drivers failed to handle setPowerState`. Seen on the W541 with
  rc12 (`nri`); with the three quirks set it resumes
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- From rc12, *Compatibility* → *macOS* → *Device properties for macOS*
  (0128), off by default: on, the firmware gives macOS, through the `_DSM`
  of each device, the `DeviceProperties` of the OpenCore configuration of
  this W541 (`configs/macos/DeviceProperties.plist`): AAPL,ig-platform-id
  0x0D220003, device-id 0x0412 and the framebuffer patches on the Intel
  GPU, `layout-id` 28 on the audio, the card reader and the LPC bridge as
  Apple's, `class-code` 0xFFFFFFFF on the Intel display audio. Then that
  section of the configuration can go.
- From rc12, the setup menu in six categories, each option in one card
  only (0125-0127, edk2/0028, lvglpkg/0018); the option names and values
  stay, and so do the settings. *General*: *About this ThinkPad*, *Boot*,
  *Sound*, and links to *Time and Date Settings*, *Firmware Update*,
  *Boot Splash Settings* and *Graphical UI Configuration*, which *System
  Configuration* still lists too; *Energy Saver*: *Battery*, *Processor*,
  *Processor voltage* (the undervolting options, a category of their own
  until now), *Thermal*, *Power*; *Hardware*: *Intel graphics*, *NVIDIA
  graphics*, *Storage* (the SATA ports), *Expansion ports* (ExpressCard
  and Thunderbolt), *Wireless*; *Keyboard*: *Keys*, *Pointing devices*;
  *Security*: *Flash protection*, *Memory protection*, *Virtualization*,
  *Management Engine*, and links to *Secure Boot Configuration* and to
  the password; *Compatibility*, new: *macOS* (*ACPI processor objects*,
  *C-state configuration lock*, *NVIDIA GPU off under macOS*, *Light the
  display up at wake*, *Panel under macOS*, *Intel display audio*, *USB,
  audio and LAN wake*, *Device properties for macOS*) and *Advanced*
  (*Non-maskable interrupts*). The options that the entries above place
  in *Hardware* → *Graphics*, *General* → *Advanced* or *Energy Saver* →
  *Processor* are in these cards now. The help of every option says what
  it does, its default and when to change it, and some names say more:
  *After a power loss* (was *Restore AC Power Loss*), *Intel ME interface
  (HECI)* (was *Intel Management Engine*), *Keyboard light*
  (*Illumination Control*), *Battery charged first* (*Battery Charge
  Priority*). The build checks the menu of each variant, built on the host
  from the same sources (`tools/build.sh menu`): an option in two cards,
  or in none, stops it; `tools/qemu-setup-shots.py` takes screenshots of
  the setup with the menu of the W541 in QEMU
  ([patches/README.md](patches/README.md#the-setup-menu-and-its-screenshots)).
- From rc13, the `_PSW` of the lid and of the sleep button write no EC RAM
  before `_REG` (3, 1) (0132), as the batteries (0109), the lid (0114)
  and the AC adapter (0120) read none: macOS called the one of the lid at
  boot, before its EC driver, and logged "No handler for Region [ERAM]"
  for `WKLD = Zero`, the last of them at boot. Until `_REG` each keeps the
  setting it is asked for, and `_REG` writes the last one to the EC.
  Linux calls `_PSW` after `_REG`: nothing changes there. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc14, *Device properties for macOS* follows *Panel under macOS*
  (0133): with *Built-in display* the firmware gives the Intel GPU a
  laptop framebuffer, 0x0A260006 with its built-in connector (con0) on
  DDI D, where the panel of the W541 is
  (`configs/macos/DeviceProperties-builtin.plist`); with *External
  display* the desktop framebuffer 0x0D220003, as before. *Built-in
  display* has been tried on the W541 (rc12 `nri`, macOS 14.8.9,
  OpenCore 1.0.8, the same properties in OpenCore): macOS drives the
  panel as its built-in display, with the backlight through `PNLF`,
  sleep on lid close and the panel back at wake. It takes AzulFix 1.1.7
  or later and *Light the display up at wake* off
  ([docs/macos.md](docs/macos.md#the-panel-as-built-in-display)).
  `tools/devprops2asl.py --builtin` writes the properties of both;
  checked in `acpiexec` on the DSDT of the W541.
- From rc15, what trimming the OpenCore configuration of the W541 (rc14,
  OpenCore 1.0.8) found for the firmware. Checked in QEMU with the payload
  of the W541, then on the W541 with rc16 (below):
  - the com buffer of SMMSTORE, which the runtime variable services
    write, is runtime services data in the memory map (`edk2/0029`). It
    was reserved memory with `EFI_MEMORY_RUNTIME` (0x7F635000-0x7F644FFF
    on the W541), which XNU does not map: without OpenCore's
    `ProtectMemoryRegions` macOS restarted right after boot.efi, with no
    panic report. Linux maps both kinds; in QEMU it writes variables as
    before;
  - the payload runs from 1 GiB, and its HOB memory, where the DXE core
    starts, follows it (`edk2/0030`): the memory from 1 MiB to 1 GiB is
    free for the OS loaders. With the payload at 8 MiB and the HOB memory
    after it, up to 83 MiB, the slides of the kernel of macOS below 41
    were taken ("Only 215/256 slide values are usable!"), and OpenCore
    needed `ProvideCustomSlide`, and `EnableSafeModeSlide` with it;
  - the firmware revision of the UEFI system table is the release:
    X << 24 | Y << 16 | Z << 8 | N for vX.Y.Z-rcN, N = 0 for vX.Y.Z,
    0 for a build that is not a release (`tools/build.sh`, as
    `PcdFirmwareRevision` of EDK2; it was 0x00010000 for every release).
    Under macOS, where OpenCore replaces the SMBIOS, it is the place
    that tells the release: `firmware-revision` <0f0a0301> for rc15
    ([docs/update.md](docs/update.md#versions-variants-downgrades)).

  Without `ProtectMemoryRegions`, `ProvideCustomSlide` and
  `EnableSafeModeSlide` OpenCore boots macOS (seen on the W541 with rc16;
  [docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
  `AvoidRuntimeDefrag` stays, as before: without it boot.efi moves the
  runtime services data, and the com buffer of SMMSTORE, which SMM
  writes at its physical address, is runtime services data from rc15.
- From rc16, OpenCore's `AvoidRuntimeDefrag` should not be needed either
  (patch 0134, `edk2/0029`). boot.efi of macOS moves the runtime services
  code and data after `ExitBootServices()`, and leaves MMIO in place: SMM
  read the arguments of SMMSTORE, and from rc15 its com buffer, where
  they had been (the quirk hides the runtime services from boot.efi). The
  com buffer is now MMIO with `EFI_MEMORY_RUNTIME`, as
  `ProtectMemoryRegions` made it up to rc14, which every OS maps for the
  runtime services, with one page more in CBMEM after the block, where
  the runtime driver puts the arguments once the OS has called
  `SetVirtualAddressMap()`. Nothing that SMM reads or writes is runtime
  services code or data. Checked in QEMU with the payload of the W541:
  the com buffer of 68 KiB as runtime MMIO in the memory map, for Linux
  too, the variables that Linux writes at runtime with the arguments in
  that page (`DEBUG_SMI`) and read at the next boot; the smoke test. On
  the W541 macOS boots without it, and its NVRAM works
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)). Not
  with `DevirtualiseMmio` on, which takes `EFI_MEMORY_RUNTIME` away from
  MMIO, unless the com buffer is in `MmioWhitelist`.
- From rc16, the tests check what rc15 brought: the update test, in the
  memory map an OS gets at `ExitBootServices()`, no reserved range with
  `EFI_MEMORY_RUNTIME`, all of the memory from 1 MiB to 1 GiB free and
  the com buffer of SMMSTORE runtime MMIO with its page of arguments;
  `tools/verify-rom.sh`, the firmware revision of a release ROM
  ([docs/vboot.md](docs/vboot.md#how-it-is-tested)).
- From rc17, the smoke test of each variant does to the runtime services
  of the payload what boot.efi of macOS does without OpenCore's
  `AvoidRuntimeDefrag` (`tools/efi/rt-reloc-test.c`): after
  `ExitBootServices()` and `SetVirtualAddressMap()` their code and data go
  elsewhere, the old copies are filled with 0xCC, and the services are
  called only at their virtual addresses. Every service must answer, the
  two variables written must be in the flash with their data, nothing may
  write to the old copies, and `ResetSystem()` must reset: a physical
  address that the payload or SMM still uses at runtime fails it
  ([README](README.md#building)). The payload of rc16 passes it; the one
  of rc15 does not (`SetVariable()` returns `EFI_DEVICE_ERROR`: the
  arguments of SMMSTORE were runtime services data).
- From rc17, a DEBUG build of the payload, which no release is, no longer
  faults in `ResetSystem()` under macOS or Windows: the first `DEBUG()`
  of a runtime driver, which for ResetSystemRuntimeDxe came at runtime,
  looked for the print level in the HOB list, boot services memory.
  Runtime drivers read it from `PcdDebugPrintErrorLevel` (`edk2/0031`),
  as every module does with coreboot, which passes no such HOB. The
  release payload, without `DEBUG()`, builds byte for byte the same.
- From rc17, OpenCore's `SyncRuntimePermissions` should not be needed
  (`edk2/0032`). The memory attributes table (MAT), from which macOS
  sets what the runtime services may run and write, did not describe a
  runtime driver loaded after ReadyToBoot, as OpenCore loads
  OpenRuntime: the table was installed again at each runtime allocation
  of the load, before the DXE core had the record of the sections of
  the driver, which stayed runtime code without an image, read-only and
  not executable, until runtime memory was allocated again. Now the
  table is installed again once the record is in: the code read-only,
  the header and the data not executable. Checked in QEMU with
  OpenShell, MmapDump and a runtime driver loaded from the shell. With
  OpenRuntime 1.0.8 a later allocation corrected the table anyway, and
  on the W541 the quirk is off with rc16 already; the patch takes away
  the dependence on that allocation
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- The OpenCore configuration of the W541 with rc16 (OpenCore 1.0.8): of
  `Booter` → `Quirks` only `RebuildAppleMemoryMap` is on, and macOS
  works. `AvoidRuntimeDefrag` (not needed from rc16),
  `ProtectMemoryRegions`, `ProvideCustomSlide` and `EnableSafeModeSlide`
  (from rc15), `SyncRuntimePermissions` and `EnableWriteUnprotector` are
  off ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- From rc18, one payload for the two variants. FmpDxe, the driver that
  publishes the firmware in the ESRT and applies the capsules, had the
  GUID of its variant as its FILE_GUID, so the two payloads differed in
  those bytes only and EDK2 was built twice. Its FILE_GUID is now one
  fixed GUID in both defconfigs (`EDK2_CAPSULE_MAIN_FW_GUID`, patch 0135);
  the GUID of each variant in the ESRT, the one its capsules carry, comes
  from the coreboot table at every boot, as the one FmpDxe publishes
  already did (`edk2/0033`). `tools/build.sh` builds EDK2 once and gives
  the second variant the payload of the first, after checking that the
  two `.config` differ only in the RAM init, the name and the GUID
  ([README](README.md#building)). The update test of the CI runs with
  the fixed FILE_GUID too. FmpDxe keeps the result of its last update
  (`FmpState`, the `last_attempt_*` fields of the ESRT) under its
  FILE_GUID, so the first boot with rc18 shows no last attempt, until the
  next capsule; the variables under the old GUID stay in the store,
  unused ([docs/update.md](docs/update.md#how-it-works)).
- From rc18, the CI builds each release a second time from scratch on
  another runner, in parallel with the first build, and compares the two
  bit by bit (jobs `repro` and `compare`, `tools/ci.sh compare`: on a
  difference, the regions of the flash map and the compilers of the two)
  instead of building again on the same runner after the first build:
  the run is shorter, and two machines agree on the ROM, not one with
  itself. `tools/build.sh repro` still does it on one machine.
- From rc19, the smoke test runs once per payload (the two variants share
  one since rc18), and `tools/build.sh prepare` fetches of EDK2 only the
  submodules the payload uses (OpenSSL without its own, the brotli of
  BaseTools, LvglPkg with LVGL: 0.9 GB instead of 2.8, a third of the
  time), keeping coreboot's EDK2 Makefile from fetching the others. KVM
  for the QEMU tests was tried on GitHub's runners and is not used: under
  nested virtualization every SMI of SMMSTORE costs an exit to the
  hypervisor, and the update test, which writes the flash through SMM,
  took longer than with TCG (`OUROBIOS_QEMU_ACCEL=kvm` turns it on by
  hand).
- From rc19, every patch of the three series says how it was tested
  (`TEST=`: the tests of the CI, QEMU, the W541, or that there is no
  recorded test), its subject fits in 72 columns and the lines it adds
  in 96 (the Kconfig default of 0053, a string, excepted); the ones
  renamed keep their numbers. What the patches do does not change: 23
  lines of the coreboot series are wrapped, nothing else.
- From rc19, one OpenSSL in the payload: the Secure Boot, capsule,
  password and TPM drivers used a copy each (five, 800-1000 KiB apiece);
  they now share the one of CryptoDxe through its protocol
  (`CRYPTO_PROTOCOL_SUPPORT` of EDK2, which patch `edk2/0034` makes
  reach them). The modules of the payload go from 9.8 to 7.5 MiB in
  memory and the compressed payload in flash loses 115 KiB in each slot;
  the variable driver keeps its own OpenSSL, as runtime code must.
  Verified in QEMU: the smoke test and the capsule update, whose
  signature check goes through the protocol.
- rc20 fixes what the shared OpenSSL of rc19 changed in the order the
  DXE drivers come up: the drivers that use it now wait for CryptoDxe,
  so the TPM driver started after the Secure Boot keys of a fresh
  variable store had been written, and their measurements in PCR 7 (PK,
  KEK, db, dbx, SecureBoot: seven events of the TPM log) were dropped
  on that first boot of a TPM 1.2 machine. Patch `edk2/0035` starts
  CryptoDxe from the a priori list, before every other driver, and the
  order is the one of rc18 again. Verified with a TPM 1.2 in QEMU: the
  TPM log of rc18, 21 events, digest for digest. Nothing changes for
  the boots after the first, where no key is written. In
  `tools/build.sh prepare`, the submodules of EDK2 a tree prepared
  before rc19 had marked active one by one are unmarked, so the list
  of the ones the payload uses applies to that tree too, and a
  placeholder folder left in the path of a submodule is removed before
  the submodule is fetched.
- From rc21, the smoke test of the CI also checks Secure Boot and the
  ESRT (`tools/efi/secure-boot-test.c`): the payload must verify the
  signature of a test application against a CA put in db, accept a shim
  signed by Microsoft, refuse an image signed by a certificate in no
  database, an unsigned one and one whose hash is in dbx despite a good
  signature, compute SHA-256 and the PBKDF2 of the setup password right
  through CryptoDxe, and the ESRT must carry the entry of the
  variant with the GUID from the coreboot table. The second variant,
  whose payload is the first one's, runs this step on its own q35 image:
  since rc19 nothing booted the nri payload in the CI. With the TPM 1.2
  of swtpm, the measurement log must have the Secure Boot keys measured
  in PCR 7 at the first boot, with the right digests: the check that
  would have caught the rc19 regression.

## v1.3.9

**Installs with flashrom, not with the capsule**: it writes the read-only
part again ([docs/flashing.md](docs/flashing.md#from-v13x-to-v139)).

- The read-only part of v1.3.9 (patch 0085, `LENOVO_HASWELL_COMMON_CAR`;
  [docs/vboot.md](docs/vboot.md#the-read-only-part-of-v139)): one
  cache-as-RAM layout for `mrc.bin` and the native RAM init, with the stack
  after the regions that the bootblock and verstage leave to romstage, so
  that the `mrc` read-only part, the one with `mrc.bin`, starts the slots
  of either variant; an early console of 16 KiB in place of 3, where the
  messages of the bootblock and of vboot fit; the CBFS caches 8 KiB each in
  place of 16. The read-only part is now built from the coreboot pin of the
  slots, 26.09-280 (v1.3.0's was 26.09-53). Verified on a W541 with
  v1.3.9-rc1 (`mrc`, written with flashrom): it starts its slot, the log
  keeps the messages of the bootblock and of verstage, and the same
  read-only part starts the `nri` slots of rc2 and rc3.
- New ESRT GUIDs for both variants: the slots of v1.3.9 do not boot behind
  the read-only part of v1.3.0-v1.3.8, nor those behind the new one, so the
  capsule of v1.3.9 does not install on them (`update.py stage`, fwupd and
  the setup refuse it) and the releases after v1.3.9 install with their
  capsule on v1.3.9 only. Verified on a W541: the capsule of v1.3.9-nri,
  staged with `update.py stage --latest` on the `nri` slot of rc3, wrote
  the other slot, which trained and passed the memory test; the ESRT
  reports v1.3.9 and the last update as successful.
- Native RAM init (`nri`), from its comparison with the MRC's steps and
  with `mrc.bin` on the W541: the DRAM voltage from the SPDs (patch 0086:
  1.35 V on the W541's DDR3L, as `mrc.bin` sets it; the code assumed
  1.5 V, which selects the DDRIO settings), and a memory test after
  training with the training redone once if it fails (patch 0087, as the
  MRC's MEMTST; nothing on fast boots). On the W541 with four DIMMs the
  `nri` slot of rc2 trained, passed the test and took the fast path after
  ([docs/raminit.md](docs/raminit.md)).
- Native RAM init: a shorter read round trip (patch 0088). Compared on
  the W541 with `ddr-report.py`, `mrc.bin` reads 2.5-3.1 ns sooner: same
  receive enable delays, but the read data kept fewer qclks in the I/O.
  The NRI now takes those qclks off after the command training while a
  read test passes on every rank, and keeps one as a guard band. On the
  W541 the `nri` slot of rc3 ends with the latencies of `mrc.bin` (round
  trips of 44 and 45 qclks) and reads from Linux as fast; it passed 30
  minutes of `stress-ng --vm` with verification under load, and after an
  S3 resume the registers are the trained ones, shorter round trips
  included. The other differences, the power training and the voltage
  centering of `mrc.bin`, are listed in
  [docs/raminit.md](docs/raminit.md#on-the-w541).
- The `nri` variant is published as a release together with the `mrc`
  one, never as the latest (the fwupd remote reads the `mrc` release);
  release candidates stay pre-releases for both. Up to v1.3.8 `nri` was
  always a pre-release.
- `tools/ddr-report.py`: the memory controller as the RAM init left it
  (timings, turnarounds, command rate, latencies, trained delays and Vrefs
  per byte, comp, ODT, equalisation), read only, and two dumps compared:
  `mrc.bin` against the native RAM init on the same machine;
  `tools/mem-latency.c`, how long a read from the memory takes.
- `tools/update.py other-slot`: the slot of a release, from its image,
  written into the slot that is not running, with flashrom in three
  regions only, and vboot asked to try it with two tries, so that a slot
  that does not boot falls back to the one that ran, as after a capsule.
  From v1.3.9 behind the `mrc` read-only part also the other variant; the
  tool checks what the read-only part on the laptop can start
  ([docs/update.md](docs/update.md#a-release-from-its-image-in-the-other-slot)).
  Verified on a W541: from `mrc` (rc1) to the `nri` slot of rc2, back to
  `mrc`, then to the `nri` slot of rc3.

## v1.3.8

- EDK2 moved to MrChromebox `f7cbaab0d5a2` (`uefipayload_2608`, two
  commits after the pin of v1.3.7): the complete Microsoft DBX (the
  revocation list of Secure Boot, 24 KiB) enrolled with the default keys,
  with the newer update appended, instead of the last update alone; the
  same union in `dbxDefault`, so that fwupd can tell the DBX version. All
  the patches apply as they are. About 24 KiB more in each slot.
- A lighter payload (patch `edk2/0027`): the drivers the W541 has no use
  for are left out, UFS and UHCI host controllers (the PCH has EHCI and
  xHCI), EFI byte code option ROMs, and the NTFS, exFAT and ext2
  filesystems (FAT and ext4 stay, for the ESP and a Linux boot volume).
  About 110 KiB less in each slot, DBX included: about 304 KiB free with
  `mrc` and 237 KiB with `nri` (194 and 128 in v1.3.7). Verified on a W541
  with v1.3.8-rc2: fwupd reports the DBX version (20260707), the boot
  manager still boots a USB stick, and OpenBSD installed from it.

## v1.3.7

- The PCIe link to the NVIDIA GPU, as the Lenovo firmware of the W541 sets
  it up (patches 0078-0084). With `mrc.bin` the graphics port of the
  processor (PEG, `00:01.0`) is hidden from it, so that the integrated GPU
  stays the primary one, and `mrc.bin` then leaves the port as it comes
  out of reset; the native RAM init did not program it either. Measured on
  a W541 with v1.3.6: 75 of the 107 fields of Intel's analog front-end
  (AFE) settings for the port at their hardware defaults, the 8 GT/s
  presets at 0 on all 16 lanes, phase 3 of the 8 GT/s equalization not
  done. The Lenovo firmware (GNET94WW), read in its System Agent reference
  code and its setup data, programs the AFE settings and the 8 GT/s
  presets before the link trains: preset 3 for the root port, 7 with hint
  2 for the GPU. Once the link is up it reads the full swing of the GPU
  and writes the coefficients of its preset to each lane, then equalizes
  again for 8 GT/s; its search of the best preset per lane is off on the
  W541. The firmware now does the same, *As the Lenovo firmware* in
  *Hardware* → *NVIDIA GPU link tuning*, shown while *NVIDIA discrete GPU*
  is on. The same setting also offers *AFE and 8 GT/s presets* (the
  presets without the equalization; the default of v1.3.7-rc1, with
  Intel's presets 8, 7 and 2), *AFE* alone and *Off* (as up to v1.3.6), to
  compare them with the same image. The coreboot log reports the link and
  the equalization (`cbmem -1 | grep PEG`), and `tools/peg-report.py`
  shows the link from Linux with the errors of both ends
  ([docs/flashing.md](docs/flashing.md#the-link-to-the-nvidia-gpu)).
  When Linux powers the GPU off and on again (runtime PM), the ACPI
  power resource equalizes the link again the same way (patch 0084).
  Verified on a W541 with v1.3.7-rc2 (`mrc`): the GPU reports a full
  swing of 60, the link comes up at 8 GT/s x16 with all three
  equalization phases done, and no error is recorded on either end at
  8 GT/s, after 20 reclock cycles of nouveau, after a power-off and on of
  the GPU by Linux, or after a suspend and resume. The optional patch
  `test-peg-afe`, the AFE part alone, is gone.
- The firmware powers the GPU up with 100 ms from its power to the end of
  its reset and 100 ms after it, as the PCIe specifications want and as
  the ACPI power resource already did (10 and 50 ms before): 140 ms more
  at a boot that powers it up.

## v1.3.6

- coreboot and EDK2 moved to their upstream of October 2026 (coreboot
  `26.09-280-gacdbfd47295d`, 227 commits after the pin of v1.3.0; EDK2
  `9c0cb3a58343`). All the patches apply as they are. The read-only part
  on the laptops stays the one of v1.3.0: the slots of the new pin still
  read what it leaves in cache-as-RAM (vboot's shared data and nvdata, the
  early console, the timestamps, the FMAP and CBFS caches: same structs,
  same addresses), checked by hand and recorded as a `rw-ok` line in
  `configs/ro-interface.txt`, which `tools/ci-check.sh` and
  `tools/verify-rom.sh` accept. The update test in QEMU and the two
  variants pass on the new pin.
- The version in the ESRT and in the capsules is four bytes, X.Y.Z.R
  (fwupd's *quad* format): a release is X.Y.Z.0, its candidate N the
  release before with R = N (v1.3.7-rc2 is 1.3.6.2). Before, the
  candidates had the number of their release, so fwupd saw one version and
  offered neither a later rc nor the release after an rc. The setup page and
  `tools/update.py` show the tag (v1.3.7-rc2), `fwupdmgr` the four numbers;
  a W541 on v1.3.6-rc1 or older (X.Y.Z in the old layout, read as 1.3.0.6)
  updates to any of the new numbers as usual
  ([docs/update.md](docs/update.md#versions-variants-downgrades)), and the
  setup page and `tools/update.py` still show the old numbers by their tag
  (v1.3.5, not v1.3.1-rc5); `tools/update.py` still reads the `.cab` of
  those releases (format *triplet*). `tools/ci-check.sh` refuses a lowest
  supported version between v1.3.0 and v1.3.6, where the two layouts
  overlap. The *Go back to* of the setup and coreboot's check behind it
  (patches `edk2/0020` and 0065) read the version from the release name in
  the other slot in the same layout, `-rcN` included: in the old one, once
  the lowest supported version is raised, they would have refused a newer
  release (v1.3.7 read as `0x01030007`, below v1.3.6). The update test in
  QEMU numbers its ROMs so that a parser left on the old layout fails it.
- A testing remote for fwupd, `configs/fwupd/ourobios-testing.conf`, off
  until turned on (`fwupdmgr enable-remote ourobios-testing`): the metadata
  of the latest release, candidates included, from the assets of the fixed
  `testing` entry of the releases page, which every release replaces when
  it is the highest so far ([docs/update.md](docs/update.md#the-fwupd-remote)).
- Network boot: *iPXE Network Boot* in the boot menu (iPXE 2025.12 with its
  Intel driver, for the I217 of the W541, and nothing of EDK2's network
  stack: patches 0075 and `edk2/0022`), at the end of the boot order. PXE,
  HTTP and iPXE scripts; Ctrl-B at the banner for its shell.
- Legacy BIOS boot: *CSMWrap Legacy Boot* in the boot menu
  ([CSMWrap](https://github.com/CSMWrap/CSMWrap), the CSM and VGA BIOS of
  SeaBIOS as a UEFI application, built by `tools/build.sh prepare`:
  patches 0076 and `edk2/0023`), for what does not boot from UEFI, from
  SATA, NVMe and USB drives through SeaBIOS's own drivers; one logical
  processor stays with CSMWrap. While Secure Boot is on the entry goes,
  and the firmware refuses to start CSMWrap even from a `Boot####`,
  `BootNext` or `SysPrep####` written from the OS (a file of the firmware
  volume is not checked against the Secure Boot keys: patch `edk2/0025`,
  after v1.3.6-rc2).
- *General* → *Boot* in the setup turns each of the two off (patch 0077).
  The smoke test in QEMU starts both from the boot manager: iPXE gets its
  address from QEMU's DHCP, downloads a script over TFTP and runs it;
  CSMWrap boots the master boot record of a SATA disk. The payload's
  image in memory grows to 11 MiB (patch `edk2/0024`); each flash slot
  keeps about 215 KiB free with `mrc` and 148 KiB with `nri` (about 510
  and 443 before).
- A screen of its own for the firmware update (patch `edk2/0026`, after
  v1.3.6-rc3), instead of a white bar under the logo: the ouroboros of the
  logo lights up from its head around to its tail as the progress, and the
  bar under it is a map of the flash region being written, one column per
  4 KiB block (rewritten, already as in the capsule, still to do, the one
  being written). Around them the versions and the vboot slots, what is
  being done, the percentage, how much was rewritten and how much was
  already there, the time left, and what not to do; at the end the snake
  winks and the screen counts down to the reset; after a failure it shows
  the block that failed and that the slot in use was not touched.
  FmpDeviceSmmLib publishes what it writes for the screen; the text is
  Montserrat, as in the setup, which `tools/ui-font.py` turns into a compact
  font from the files of LvglPkg when the tree is prepared. The firmware
  that is running draws it: it shows from the update after the one that
  installs it. It takes about 18 KiB of each flash slot, measured between
  v1.3.6-rc3 and rc4: about 195 KiB stay free with `mrc` and 129 KiB with
  `nri`.
- Reproducible builds: the release build of each variant is built a second
  time from scratch in CI, CSMWrap and iPXE included, and compared bit by
  bit with the first (`tools/build.sh repro`). The build date was already
  the date of the commit; the payload now has no debug directory in its PE
  images (patch `edk2/0021`, `GenFw --zero`), whose CodeView entries named
  the `.dll` of each module with the absolute path of the build, 116 of
  them. With the same compilers (coreboot's cross toolchain; GCC and
  binutils of Ubuntu 24.04 for the payload, iPXE and CSMWrap, named in the
  `-layout.txt` of the releases after v1.3.6-rc2) the stages and the
  payload of a release can be rebuilt from its tag and compared; the whole
  ROM also needs the project's vboot key, which signs the slots.

## v1.3.5

- No more `thinkpad_acpi: acpi_evalf(\BLTH, vd, ...) failed: AE_NOT_FOUND`
  (and `\WGSV`) on the console at every shutdown and reboot: the two
  methods the driver calls to save the Bluetooth and WWAN state for S4/S5
  are in the DSDT now (patch 0067).
- A clean kernel log: no more *ACPI Warning: SystemIO range ... conflicts
  with OpRegion ... (\_SB.PCI0.GPLV)*, three times at every boot (the
  GPIO methods of Lynx Point's ASL, which no board uses, are gone: patch
  0068), and no more *ACPI: \: failed to evaluate _DSM ... (0x1001)* from
  iwlwifi (the cards behind the root ports have a device node, as on the
  OEM firmware: patch 0069).
- The USB ports described as the OEM firmware does (`_UPC`, `_PLD`): the
  OS knows which port is a connector and on which side, which carries the
  camera or the fingerprint reader, and which has nothing; the port devices
  of the Lynx Point-H xHCI were those of the -LP chipset (patches 0070,
  0071).
- Wake-on-LAN is possible: the Ethernet controller has its ACPI device
  with `_PRW`, and the Wi-Fi and WWAN root ports theirs, as on the OEM
  firmware (patch 0072). Nothing wakes the laptop unless the OS enables
  it (`ethtool -s enp0s25 wol g`).
- The battery trip point (`_BTP`, the `alarm` attribute of the battery in
  Linux), as on the OEM firmware (patch 0073).
- `_S3D` on the devices and `_RMV` on the WWAN and ExpressCard slots, as
  on the OEM firmware (patch 0074).

## v1.3.4

- Going back without an OS: the *Firmware Update* page of the setup shows
  the slot that runs and the release in the other one, and *Go back to*
  restarts into that release, which vboot tries at the next two boots and
  leaves if it does not boot, as `update.py rollback` does. The setup
  checks what a capsule would (not the release that runs, the same
  variant, not older than the oldest accepted update), and only the setup
  can do it: the payload locks the switch before it starts a boot option
  (an OS loader, the UEFI Shell) and at `ExitBootServices()`, coreboot on
  resume from suspend (patches 0065, `edk2/0020` and `lvglpkg/0015`,
  [docs/update.md](docs/update.md#from-the-setup)). What runs before the
  lock (a `Driver####` or `SysPrep####` option, an option ROM) gets the
  same checks from coreboot itself: the variant, and not older than the
  lowest supported version of the running release.
- An fwupd remote: the mrc release carries the metadata of both variants,
  signed by the capsule key (`ourobios.xml.gz`, `.jcat`), and
  `configs/fwupd/ourobios.conf` downloads it from the latest release, so
  that `fwupdmgr update`, GNOME Software and KDE Discover offer the
  releases (not the release candidates). It needs the project certificate
  in `/etc/pki/fwupd`, as the packages already did
  ([docs/update.md](docs/update.md#the-fwupd-remote)).
- The battery charge behaviour from Linux on the W541 too
  (`/sys/class/power_supply/BAT0/charge_behaviour`: `inhibit-charge`,
  `force-discharge`), as on the T440p (patch 0066, until v1.3.3 the
  optional `test-charge-behaviour`): the Lenovo ACPI tables of the two
  laptops declare the same embedded controller registers.
- The update test in QEMU goes back from the setup too, with the keys sent
  by QEMU, and checks that a boot option cannot switch slot, before or after
  `ExitBootServices()` (`tools/efi/slot-lock-test.c`). It also fills
  `RW_NVRAM` before a capsule, cuts the power halfway through a slot (vboot
  stays on the old one, the capsule staged again finishes it) and applies a
  capsule from a USB drive.

## v1.3.3

- EDK2 at MrChromebox's `0d39245e6`: writing a Secure Boot key from
  Linux (`sbctl enroll-keys`, `efi-updatevar`) no longer faults in the
  variable driver, which verifies authenticated variables outside SMM,
  and no longer takes the EFI runtime services down (CryptoPkg,
  `RuntimeFreeMem()`). The three commits before it load an Intel GOP
  driver and VBT from CBFS, which this firmware does not use: libgfxinit
  draws the screen.
- v1.3.3-rc1 is the same firmware with another version, tested on the
  W541: the capsule update from v1.3.2, suspend and resume. From it:
  `sudo python3 update.py stage --latest`.
- The smoke test of the build also checks the UEFI variables: in two
  boots of the emulated laptop the UEFI Shell writes a test variable, and
  it must be in SMMSTORE, then rewritten with the first copy deleted.
- The build tests the capsule update in QEMU before a release
  (`tools/build.sh update-test`, `tools/qemu-update.py`, a job beside the
  ROMs): three q35 images with vboot's two RW slots and its nvdata in flash,
  the EDK2 payload of these patches and capsules made as those of the
  releases. Each capsule must write only the slot that is not running;
  vboot tries it and the payload confirms it; the capsule of the release
  already in the other slot (`update.py rollback`) writes nothing to the
  slots; vboot goes back to the old slot when the new one does not verify
  or does not reach the payload; the ESRT is checked at every boot
  ([docs/vboot.md](docs/vboot.md#how-it-is-tested)).
- `tools/update.py status` adds a note when the version that runs is not
  the one of the last capsule, written with success: vboot went back to the
  other slot, or the flash was rewritten afterwards.

## v1.3.2

- The firmware is built from the same coreboot, EDK2, patches and blobs
  as v1.3.1; only its version changes. It takes a laptop on v1.3.2-rc1,
  which also had patch 0064, back to that code:
  `sudo python3 update.py stage --latest`.
- `tools/idle-report.py`: package and core C-states, RAPL and battery
  power and memory traffic at idle, and the power state of the devices
  that can keep the processor awake: ASPM, LTR and runtime PM of each PCI
  device, SATA link power management, USB autosuspend, graphics
  ([docs/flashing.md](docs/flashing.md#power-at-idle)).
- `tools/pm-regs.py`: the power management registers of processor,
  System Agent and PCH, as the firmware left them.
- `tools/update.py stage` goes from a release candidate to its release,
  or to a later candidate, without `--allow-older`.
- `tools/update.py rollback FLASH.bin`: back to the release in the slot
  that is not running, the one before the last update, with its signed
  capsule; the firmware rewrites nothing and only switches slot
  ([docs/update.md](docs/update.md#going-back)).
- The build boots the EDK2 payload of each variant in QEMU before a
  release (`tools/build.sh smoke`, `tools/qemu-smoke.py`): it must open
  the setup and answer the keys.
- Docs: the boot menu timeout is set in the setup menu, *Boot Manager* →
  *Auto Boot Time-out*; NVIDIA's own driver never powers this GPU down;
  where the boot time goes; a SATA link that never sleeps keeps the
  processor out of the package C-states below PC2, about 7 W at idle
  ([docs/flashing.md](docs/flashing.md#power-at-idle)). v1.3.2-rc1 also
  asked for the maximum ratio of the processor before `mrc.bin` (patch
  0064): the processor stayed at 800 MHz, and the patch is gone.

## v1.3.1

- VT-d: the remapping engine of the devices other than the graphics now
  handles the 2 MiB and 1 GiB pages it reports (patch 0063). Up to
  v1.3.0, with `intel_iommu=on`, Linux 7.2 used them for SATA transfers,
  which faulted and read back zeros (`csum failed` on btrfs); with those
  releases use `intel_iommu=on,sp_off` or `iommu=pt`.
- TPM 1.2: one TCPA table, coreboot's, with the events EDK2 measures
  (patch edk2/0019), so Linux reads the whole event log.
- The build checks that the RW slots still fit the read-only part that
  is already on the laptops.

## v1.3.0

- Verified boot with two RW slots: a capsule writes the slot that is not
  running and tries it, and vboot goes back to the other one if the new
  one does not verify or does not boot ([docs/vboot.md](docs/vboot.md)).
  *Firmware protection* (*Security*) write-protects the read-only part at
  every boot. From v1.2.x the move is one write with flashrom.
- The firmware is named ouroBIOS, with its logo in the setup menu and on
  the boot splash.
- The ESRT reports the result of the last update (patch edk2/0018).
- verstage reads the real sleep state (patch 0058): before, it could take
  a cold boot for a resume from S3 and keep the slot of the last boot
  instead of trying a new one.
- With *Intel Management Engine* disabled, the ME's PCI interface is
  hidden also when the ME is reduced by me_cleaner (patch 0059); the HD
  audio of the NVIDIA GPU gets its interrupt (patch 0060); the flash size
  is read right from the descriptor (patches 0061-0062).
- `tools/update.py`: `vboot`, `vboot-work` and `vars`.
