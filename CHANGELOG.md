# Changelog

What changes from one release to the next. The notes of each release on
GitHub include its section; release candidates take the section of the
version they lead to. For the releases before v1.3.0, see their notes on
the [releases page](https://github.com/debianita22/ourobios/releases).

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
  attributes table of the firmware**: `RebuildAppleMemoryMap` and
  `SyncRuntimePermissions` on, `EnableWriteUnprotector` off. With the
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
