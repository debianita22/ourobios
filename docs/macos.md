# macOS with OpenCore

ouroBIOS boots macOS through OpenCore as any UEFI firmware does: OpenCore
and its configuration live on the disk, and the firmware knows nothing
about them. Part of what an OpenCore configuration for the W541 adds,
though, makes up for choices of the firmware. From v1.3.10 the firmware
does some of it itself, always, under macOS only or behind a setup option,
so that the configuration can drop it. This page lists what, and what
stays in OpenCore.

- [What the firmware does](#what-the-firmware-does)
- [In the OpenCore configuration](#in-the-opencore-configuration)
- [The panel as built-in display](#the-panel-as-built-in-display)
- [Native NVRAM](#native-nvram)
- [Not done](#not-done)
- [Linux and Windows](#linux-and-windows)

From v1.3.10-rc12 the setup options for macOS are together in
*Compatibility* → *macOS*, and the help of each says what it replaces in
OpenCore.

## What the firmware does

"Under macOS" means when the OS answers `_OSI ("Darwin")`, which macOS
does and Linux and Windows do not on this laptop. A configuration that
renames `_OSI` to `XOSI` hides that answer from the firmware: see
[below](#in-the-opencore-configuration).

| | When | What OpenCore did for it |
|---|---|---|
| The CPU threads as `Processor` objects, `\_SB.CP00`-`\_SB.CP07` (patches 0090, 0091), and from rc12 `plugin-type` 1 on the first one, which turns XCPM on (0123) | setup: *Compatibility* → *macOS* → *ACPI processor objects*: *Processor* (default: *Device (ACPI0007)*, the form ACPI asks for since 6.3) | an SSDT that declares `Processor` objects for the ACPI0007 devices (without one, macOS finds no CPU and stops early in the boot), and `SSDT-PLUG` for `plugin-type` |
| CFG Lock off (0089, 0091) | setup: *Compatibility* → *macOS* → *C-state configuration lock*: off (default: on) | the kernel quirk `AppleXcpmCfgLock` |
| The HPET shown, with IRQ 0 and 8, and the 8254 timer without IRQ 0, as on a Mac (0095) | under macOS | renames and an SSDT for the HPET and the 8254: the IRQ fix (*FixHPET* of SSDTTime) |
| How macOS drives the panel, as the Intel framebuffer of the configuration sets it up (0124, 0129). *External display*, for a desktop framebuffer (the panel of the W541 is on DDI D, where the laptop framebuffers have no built-in connector): macOS has no backlight control for it, and the brightness keys set the PWM themselves. *Built-in display*, for a laptop framebuffer ([tried](#the-panel-as-built-in-display)): the backlight device of macOS, `\_SB.PCI0.GFX0.PNLF` (`APP0002`, `_UID` 15), with the PWM of the panel set to the maximum of the Haswell Macs, 0xad9, the duty cycle scaled, at boot and after every wake; an ambient light sensor, `\_SB.ALS0` (a stub: the W541 has none); the keys as ACPI events (Notify of `LCD0`) for BrightnessKeys.kext | under macOS, setup: *Compatibility* → *macOS* → *Panel under macOS* (default: *External display* on the W541) | external: the `_Q14`/`_Q15` renames and an SSDT that keeps the keys from notifying the OS; built-in: `SSDT-PNLF` (at boot only) and `SSDT-ALS0` |
| The last backlight level put back at wake (0096) | under macOS | nothing: the resume path starts the backlight at 50% and macOS kept it there until a brightness key |
| The sleep LEDs (power button and logo pulsing, moon on) and the wake on lid opening, before S3 (0100) | under macOS | an SSDT that calls `\_SI._SST`, if the configuration had one: macOS does not call it |
| Sleep on lid close on AC: the sleep button pressed for macOS, as Fn+4, since it takes the panel of the W541 for an external display and runs in desktop mode, in which it does not sleep on lid close on AC (0113); no clamshell mode on AC | under macOS, on AC, with *Panel under macOS* on *External display* | nothing: the lid did not sleep on AC, and the panel stayed lit inside the closed lid |
| The Intel display audio controller (0:3.0) hidden, whose codec macOS waited 10 s for at every wake and sleep (0122); with it goes the audio over the mini DisplayPort and a port of the dock, for every OS | setup: *Compatibility* → *macOS* → *Intel display audio*: off (default: on) | nothing: a wake took 10-20 s |
| The USB, HD Audio and Ethernet controllers kept from waking macOS: their `_PRW` gives S0 as the deepest sleep state they wake from, so macOS does not arm their PME (GPE 0x0d) for S3 (0130) | under macOS, setup: *Compatibility* → *macOS* → *USB, audio and LAN wake*: off (default: off) | the `_PRW` renames (`0D 03` and `0D 04` to `0D 00`) against wakes right after sleep |
| The USB power properties of the Macs from Skylake on, in `\_SB.USBX` (0131): `kUSBSleepPowerSupply` and `kUSBWakePowerSupply` 5100 mA, `kUSBSleepPortCurrentLimit` and `kUSBWakePortCurrentLimit` 2100 mA, as OpenCore's sample | under macOS | `SSDT-USBX` |
| The device properties of the OpenCore configuration of this W541 (`DeviceProperties`: the framebuffer of the Intel GPU, `layout-id` 28, the card reader and the LPC bridge as Apple's, Intel display audio without a driver), through the `_DSM` of each device for Apple's UUID (0128; `configs/macos/DeviceProperties.plist`, written into the DSDT by `tools/devprops2asl.py`). From rc14 the framebuffer follows *Panel under macOS*: the desktop 0x0D220003 for *External display*, the laptop 0x0A260006 with its built-in connector on DDI D for *Built-in display* (0133, `configs/macos/DeviceProperties-builtin.plist`, `tools/devprops2asl.py --builtin`) | under macOS, setup: *Compatibility* → *macOS* → *Device properties for macOS*: on (default: off) | `DeviceProperties` → `Add` |
| The empty slots turned off: the SATA ports besides the drive bay (0121), the ExpressCard slot and Thunderbolt (0033), for every OS: no port to wait for at every wake, no hot-plug path left open | setup: *Hardware* → *Storage* and *Hardware* → *Expansion ports* (default: on) | nothing: macOS waited for a link on each empty SATA port, about a second per port at every wake |
| The NVIDIA GPU powered off, as macOS has no driver for it (Apple removed the Kepler drivers in Monterey): at boot, and again after a wake that powered it, as a resume from S4 does (0115) | under macOS, with *NVIDIA discrete GPU* on (*Hardware* → *NVIDIA graphics*); setup: *Compatibility* → *macOS* → *NVIDIA GPU off under macOS* (default: on) | an SSDT that calls `_OFF` (the path of the OEM firmware, which this DSDT does not have), or `-wegnoegpu`, which only hides the GPU: it stays powered |
| The wake source left in PM1_STS and GPE0_STS at S3 resume, and to the OS by the SMI handler (0099, 0108; with rc3 and rc4, without 0108, every wake from S3 powered off) | always | nothing: the firmware cleared them, and macOS saw no reason for the wake |
| The battery and the EC wake cause read one byte at a time (0103, 0094), and the battery, the lid and the AC adapter not before the EC driver of macOS (0109, 0114, 0120), nor from rc13 the wake settings of the lid and the sleep button (`_PSW`, kept for `_REG`, 0132) | always | ECEnabler, or patches of the battery methods: the EC driver of macOS reads no wider field; nothing for the "No handler for Region [ERAM]" that macOS logged for `BAT0._STA`, `BAT1._STA`, `LID._LID`, `AC._PSR` and `LID._PSW` at every boot (with the lid taken for closed until it read it again) |
| The backlight registers and the MMIO of the xHCI controller at the BAR they have when the methods run, all 64 bits of it (0101, 0102) | always | the boot argument `npci=0x2000`, if the configuration has it, keeps macOS from moving the BARs |
| The display left to the OS at wake: only the panel timings, the backlight PWM, the hotplug detection of the ports and power to the panel for its HPD, no mode set (0104, 0107, 0110, 0111); macOS does not power the panel up nor enable its backlight itself (see below) | setup: *Compatibility* → *macOS* → *Light the display up at wake*: off (default: on) | nothing: the firmware sets the panel up at 1920×1080 and macOS sets it up again; with the option off, the panel power-up and its backlight from a Lilu plugin for Azul, or from SSDT-PNLWAK |
| The release in the firmware revision of the UEFI system table, from rc15: X << 24 \| Y << 16 \| Z << 8 \| N for vX.Y.Z-rcN; `ioreg -p IODeviceTree -n efi -l \| grep firmware-revision` reads it little-endian, `<0f0a0301>` for v1.3.10-rc15 ([docs/update.md](update.md#versions-variants-downgrades)) | always | nothing: OpenCore replaces the SMBIOS, whose BIOS version names the release, and the system table said 0x00010000 for every release |
| The firmware screen at the 2880×1620 of the panel, for the OpenCore picker and the boot of macOS (0105-0107) | setup: *Hardware* → *Intel graphics* → *Firmware screen resolution*: *Panel, up to 2880 x 1620* (default: at most 1920 x 1080, scaled) | nothing |

## In the OpenCore configuration

**From rc12, `Booter` → `Quirks` needs `RebuildAppleMemoryMap` and
`SyncRuntimePermissions` on and `EnableWriteUnprotector` off**: without
them macOS restarts the laptop at the resume from S3 (below).

After the update, and with the setup options of the table set:

- *ACPI processor objects* on *Processor*: remove the SSDT that declares
  `Processor` objects, or the CPUs are declared twice, and from rc12
  `SSDT-PLUG` too: the firmware gives the first thread, `\_SB.CP00`,
  the `_DSM` with `plugin-type`, and the one of `SSDT-PLUG` would be a
  second `_DSM` there. Up to rc11, keep `SSDT-PLUG` with the path of the
  first CPU set to `\_SB.CP00`;
- *C-state configuration lock* off: `Kernel` → `Quirks` →
  `AppleXcpmCfgLock` to false;
- the HPET: remove the renames and the SSDT of the IRQ fix;
- the `_OSI` to `XOSI` rename and `SSDT-XOSI`, if there: remove them. With
  the rename the firmware's `_OSI ("Darwin")` becomes `XOSI ("Darwin")`,
  to which `SSDT-XOSI` says no (yes only to Windows names), and what is
  *under macOS* above stays off. The firmware asks `_OSI` nothing else on
  this laptop (its checks of the Windows versions, in `GOS`, are never
  called), so the rename has nothing to turn on;
- ECEnabler and any battery patches: the battery methods read the EC one
  byte at a time (0103). No other EC field wider than 8 bits is read under
  macOS: `WAKE` is never read and `BAET` only by the charge-behaviour
  methods of Linux;
- `npci=0x2000`: try without it. The ACPI methods that use the BARs of the
  GPU and of the xHCI controller follow them where macOS puts them (0101,
  0102); if macOS hangs at *PCI configuration begin* without it, put it
  back;
- an SSDT that calls `\_SI._SST` in `_PTS`/`_WAK`, if there: remove it;
- an SSDT that powers the NVIDIA GPU off and `-wegnoegpu`, if there: not
  needed from rc10, which powers it off under macOS (0115). To keep it
  powered, e.g. for the Kepler drivers of OpenCore Legacy Patcher, turn
  *NVIDIA GPU off under macOS* off, rather than renaming `_OSI`;
- with *Light the display up at wake* off: what powers the panel up and
  enables its backlight when macOS lights the display up, which macOS
  does not do (below);
- `SSDT-PNLF` and `SSDT-ALS0`, from rc12: the firmware has
  `\_SB.PCI0.GFX0.PNLF` and `\_SB.ALS0`, present with *Panel under
  macOS* on *Built-in display*, and the devices of the SSDTs would be
  second ones whatever the option. The renames of the GPU device are not
  needed for them (WhateverGreen names it `IGPU` in the I/O Registry).
  SMCLightSensor is not needed either way: the W541 has no ambient light
  sensor, `ALS0` is a stub, and macOS keeps the brightness across
  restarts without it;
- the `_Q14`/`_Q15` renames and their SSDT, which keeps the brightness
  keys from notifying the OS (`BRCT` 0), from rc12 with *External
  display*: the firmware does it. With *Built-in display* the keys go to
  macOS as ACPI events, for BrightnessKeys.kext;
- the `_PRW` renames to S0 (`0D 03` and `0D 04` to `0D 00`), from rc12:
  the `_PRW` of those devices is a method now, the renames find nothing,
  and *USB, audio and LAN wake* says what macOS may arm;
- `SSDT-USBX`, from rc12: the firmware has `\_SB.USBX`;
- `DeviceProperties` → `Add`, from rc12, with *Device properties for
  macOS* on: the firmware gives the same properties (those of
  `configs/macos/DeviceProperties.plist`; from rc14, with *Panel under
  macOS* on *Built-in display*, the framebuffer of
  `configs/macos/DeviceProperties-builtin.plist`). Leave the section empty: a
  property from both, with different values, is not well defined, and to
  try other values in OpenCore turn the option off. Other values for good
  go in that file, and from there into a new patch (`tools/devprops2asl.py`);
- `Booter` → `Quirks`, needed from rc12: `RebuildAppleMemoryMap` and
  `SyncRuntimePermissions` on, `EnableWriteUnprotector` off. The firmware
  has a memory attributes table (MAT; `OCABC: MAT support is 1` in the
  log of a DEBUG OpenCore, seen with the payload of rc12 in QEMU), for
  which OpenCore's documentation has these. With the quirks of the
  configuration up to rc11 (`EnableWriteUnprotector` on, the other two
  off) macOS restarts the laptop at the resume from S3, with no panic
  report, and `pmset -g log` reads `Failure during wake:
  IGPU(),HDEF(),SATA(AppleIntelPchSeriesAHCI) : Some drivers failed to
  handle setPowerState` (seen on the W541 with rc12);
- `Booter` → `Quirks` → `ProtectMemoryRegions`, from rc15: the one
  reserved range with `EFI_MEMORY_RUNTIME`, the com buffer of SMMSTORE,
  which the runtime variable services write, is runtime services data
  (`edk2/0029`), which macOS maps. Up to rc14, without the quirk, macOS
  restarted right after boot.efi, with no panic report. Try without it;
- `Booter` → `Quirks` → `ProvideCustomSlide` and `EnableSafeModeSlide`,
  from rc15: the payload and the memory where the DXE core starts are at
  1 GiB (`edk2/0030`), and the memory from 1 MiB to 1 GiB is free, so
  every slide of the kernel fits (boot.efi puts the kernel collection,
  about 100 MB, at 1 MiB plus 2 MiB times a slide of 0 to 255): a DEBUG
  OpenCore should log "All slides are usable! You can disable
  ProvideCustomSlide!". Try
  without both, in safe mode too (`-x`, or Shift at the picker), where
  boot.efi takes slide 0. Up to rc14 the slides below 41 were taken;
- `UEFI` → `Quirks` → `ReleaseUsbOwnership`: not needed, EDK2 hands the
  USB controllers over at ExitBootServices. Try it with a configuration
  that boots at hand;
- still needed: the USB map and the rest of the configuration.

Update the firmware, and change these options, with the OS shut down or
restarted, not hibernated, whatever the OS: an OS resumed from
hibernation keeps the ACPI tables of the firmware it was hibernated on.

The two display options, which by default leave the display as before:

- *Firmware screen resolution* on *Panel, up to 2880 x 1620*: the boot
  logo, the setup, the OpenCore picker and the boot of macOS run at the
  resolution of the panel instead of 1920×1080 scaled by 1.5. The
  framebuffer takes 18.7 MB of the graphics stolen memory (32 MB with
  `mrc.bin`, 64 MB by default with the native RAM init); the setup draws
  2.25 times the pixels, and its text is smaller: raise the scale in
  *Graphical UI Configuration*, OpenCore's with `UIScale`. From rc4: with
  rc3 the setup opened on a black screen at this resolution (the
  [CHANGELOG](../CHANGELOG.md#v1310) has the way out);
- *Light the display up at wake* off: at wake from S3 the firmware sets
  only the panel timings and the backlight PWM, and the graphics driver
  of the OS sets the display up, as it does anyway right after: the wake
  is faster and the backlight comes on once. With an OS that has no
  driver for the Intel GPU (a plain framebuffer) the screen stays black
  after wake: leave it on there. Under macOS it takes something more on
  the OS side. macOS drives the panel of the W541, on DDI D, as a
  DisplayPort sink: it checks its HPD at wake, trains the link and runs
  the pipe, but it never powers the panel up through the panel power
  sequencer nor enables the backlight; with the option on, libgfxinit
  does both. With rc5 the panel had no power at all and HPD was low; from
  rc6 it has VDD at wake and the firmware waits for its HPD, up to the
  200 ms power-up delay (0110, 0111, 0118), so HPD is high when the OS
  takes over. The rest:
  - a Lilu plugin for AppleIntelFramebufferAzul that, after `LightUpDP`,
    powers the panel up through the sequencer and then enables the
    backlight, and before `DisableDisplay` turns off the backlight only,
    so that the panel keeps power and HPD: the dark wakes of macOS stay
    dark;
  - or SSDT-PNLWAK, with the rename of `_WAK` to `ZWAK`: it powers the
    panel up with its backlight in `_WAK`, at every wake from S3, the
    dark wakes too. rc7 did the same from the firmware (0112), and rc8
    no longer does.

  The forced VDD stays until the next sleep: macOS does not touch the
  sequencer.

## The panel as built-in display

Tried on the W541 with rc12 (`nri`), macOS 14.8.9 and OpenCore 1.0.8:
with a laptop framebuffer macOS drives the panel as its built-in display
("Internal", AppleBacklightDisplay, `PNLF` with AppleIntelPanelA), sleeps
when the lid closes (clamshell) and lights the panel up again at wake.
It takes:

- *Compatibility* → *macOS* → *Panel under macOS* on *Built-in display*
  (`PNLF`, `ALS0` and the brightness keys as ACPI events, 0129), with
  BrightnessKeys.kext;
- *Light the display up at wake* off, and AzulFix 1.1.7 or later, which
  powers the panel up and enables its backlight on the built-in
  connector (`port-number` 0);
- for `PciRoot(0x0)/Pci(0x2,0x0)`, in `DeviceProperties` of OpenCore or,
  from rc14, from the firmware with *Device properties for macOS* on
  (0133, `configs/macos/DeviceProperties-builtin.plist`):

  | Property | Value |
  |---|---|
  | `AAPL,ig-platform-id` | `0600260A` (0x0A260006) |
  | `device-id` | `12040000` (0x0412) |
  | `framebuffer-patch-enable` | `01000000` |
  | `framebuffer-con0-enable` | `01000000` |
  | `framebuffer-con0-alldata` | `030608000200000030000000`: index 3, busId 0x06 (DDI D), pipe 8, LVDS, flags 0x30 |
  | `enable-max-pixel-clock-override` | `01000000` |
  | `max-pixel-clock-frequency` | `8074D21A` (450 MHz) |

  without the `force-online` and `con2` properties of the desktop
  framebuffer. The panel is on DDI D (eDP on DP-D in the VBT, `DP3` for
  libgfxinit), and the laptop framebuffers of Haswell have their
  built-in connector, con0, on DDI A (LVDS, busId 0x00): the patch moves
  it.

Notes:

- the W541 has no ambient light sensor: `ALS0` is a stub, and
  SMCLightSensor is not needed; macOS keeps the brightness across
  restarts without it;
- HiDPI goes up to 1440×810: on this setup macOS creates no scaled mode
  larger than the native 2880×1620. `scale-resolutions` needs Apple's
  12-byte entries (width, height, flags 1); the 16-byte entries of
  one-key-hidpi are ignored.

## Native NVRAM

macOS keeps its NVRAM variables (the startup disk, `boot-args`,
`csr-active-config`, the Bluetooth pairings) as UEFI variables, and the
firmware keeps those in the `SMMSTORE` region of the flash: 512 KiB, of
which EDK2 uses 256 KiB for the variable store, written at runtime through
SMM, the same path as `efivarfs` under Linux. An OpenCore configuration
does not need emulated NVRAM there:

- `NVRAM` → `WriteFlash`: true;
- no `OpenVariableRuntimeDxe.efi` among the drivers, the emulated NVRAM
  of OpenCore, and `NVRAM` → `LegacySchema` empty (older versions of
  OpenCore had the key `LegacyEnable` for it: false);
- no `LogoutHook` and no `nvram.plist` on the EFI partition.

*Reset NVRAM* in the OpenCore picker (`ResetNvramEntry.efi`) deletes the
variables of Apple and OpenCore and the boot entries (`Boot####`, kept
with `--preserve-boot`), not those of the setup of the firmware: the
settings stay.

To check it under macOS:

```sh
sudo nvram ouro-test=1
# restart, then:
nvram ouro-test        # ouro-test 1
sudo nvram -d ouro-test
```

EDK2 reclaims the space of deleted and replaced variables at boot, not
while the OS runs: with the store full, a variable written under macOS is
refused until the next boot. A store filled by macOS has not been tried.

## Not done

- the EHCI controllers stay visible, with both variants. v1.3.10-rc1 hid
  them in the `nri` variant, and with it a USB drive plugged in was mostly
  not found, under Linux and macOS (under Linux, whenever the xHCI
  controller was in runtime suspend), and USB 3.0 drives ran at USB 2.0
  speed (the SuperSpeed link went to compliance mode).

## Linux and Windows

The parts under macOS do not apply to them. Linux answers `_OSI
("Darwin")` only on Apple hardware, and may say once in its log that it
ignored the query.

- With *ACPI processor objects* on *Processor*, Linux lists the CPUs as
  `LNXCPU` devices instead of `ACPI0007`, with the same tables; the
  `_DSM` of the first one answers only Apple's UUID, which they do not
  use, and `PNLF` is not there for them (`_STA` 0);
- the CFG Lock: Linux and Windows do not need it either way;
- what changes for every OS: the wake source stays in PM1_STS and
  GPE0_STS at S3 resume, as with the OEM firmware (Linux reads and clears
  the power button status itself and reports the wakeup); the battery is
  read one byte at a time, with the same values; the backlight and xHCI
  methods find the BARs where the OS put them, where Linux leaves them;
- *Light the display up at wake* off needs the graphics driver of the OS
  (i915, the Windows Intel driver): with a plain framebuffer the screen
  stays black after wake. From rc6 the panel has VDD forced on at wake
  with it off; i915 takes it over (`VDD left on by BIOS` in its debug
  log) and turns it off when it no longer needs it.
