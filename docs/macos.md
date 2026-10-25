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
- [Not done](#not-done)
- [Linux and Windows](#linux-and-windows)

## What the firmware does

"Under macOS" means when the OS answers `_OSI ("Darwin")`, which macOS
does and Linux and Windows do not on this laptop. A configuration that
renames `_OSI` to `XOSI` hides that answer from the firmware: see
[below](#in-the-opencore-configuration).

| | When | What OpenCore did for it |
|---|---|---|
| The CPU threads as `Processor` objects, `\_SB.CP00`-`\_SB.CP07` (patches 0090, 0091) | setup: *General* → *Advanced* → *ACPI processor objects*: *Processor* (default: *Device (ACPI0007)*, the form ACPI asks for since 6.3) | an SSDT that declares `Processor` objects for the ACPI0007 devices: without one, macOS finds no CPU and stops early in the boot |
| CFG Lock off (0089, 0091) | setup: *Energy Saver* → *Processor* → *C-state configuration lock*: off (default: on) | the kernel quirk `AppleXcpmCfgLock` |
| The HPET shown, with IRQ 0 and 8, and the 8254 timer without IRQ 0, as on a Mac (0095) | under macOS | renames and an SSDT for the HPET and the 8254: the IRQ fix (*FixHPET* of SSDTTime) |
| The last backlight level put back at wake (0096) | under macOS | nothing: the resume path starts the backlight at 50% and macOS kept it there until a brightness key |
| The sleep LEDs (power button and logo pulsing, moon on) and the wake on lid opening, before S3 (0100) | under macOS | an SSDT that calls `\_SI._SST`, if the configuration had one: macOS does not call it |
| The wake source left in PM1_STS and GPE0_STS at S3 resume, and to the OS by the SMI handler (0099, 0108; with rc3 and rc4, without 0108, every wake from S3 powered off) | always | nothing: the firmware cleared them, and macOS saw no reason for the wake |
| The battery and the EC wake cause read one byte at a time (0103, 0094) | always | ECEnabler, or patches of the battery methods: the EC driver of macOS reads no wider field |
| The backlight registers and the MMIO of the xHCI controller at the BAR they have when the methods run, all 64 bits of it (0101, 0102) | always | the boot argument `npci=0x2000`, if the configuration has it, keeps macOS from moving the BARs |
| The display left to the OS at wake: only the panel timings and the backlight PWM, no mode set (0104, 0107) | setup: *Hardware* → *Graphics* → *Light the display up at wake*: off (default: on) | nothing: the firmware sets the panel up at 1920×1080 and macOS sets it up again |
| The firmware screen at the 2880×1620 of the panel, for the OpenCore picker and the boot of macOS (0105-0107) | setup: *Hardware* → *Graphics* → *Firmware screen resolution*: *Panel, up to 2880 x 1620* (default: at most 1920 x 1080, scaled) | nothing |

## In the OpenCore configuration

After the update, and with the setup options of the table set:

- *ACPI processor objects* on *Processor*: remove the SSDT that declares
  `Processor` objects, or the CPUs are declared twice. XCPM still needs
  `plugin-type` on the first thread: OpenCore's `SSDT-PLUG` sample, with
  the path of the first CPU set to `\_SB.CP00`;
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
- still needed: the backlight device (`PNLF`), the USB map and the rest
  of the configuration.

The firmware's own `Processor` objects carry no `_DSM`: `plugin-type` is a
macOS property and stays in OpenCore.

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
  after wake: leave it on there.

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
  `LNXCPU` devices instead of `ACPI0007`, with the same tables;
- the CFG Lock: Linux and Windows do not need it either way;
- what changes for every OS: the wake source stays in PM1_STS and
  GPE0_STS at S3 resume, as with the OEM firmware (Linux reads and clears
  the power button status itself and reports the wakeup); the battery is
  read one byte at a time, with the same values; the backlight and xHCI
  methods find the BARs where the OS put them, where Linux leaves them;
- *Light the display up at wake* off needs the graphics driver of the OS
  (i915, the Windows Intel driver): with a plain framebuffer the screen
  stays black after wake.
