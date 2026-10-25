# macOS with OpenCore

ouroBIOS boots macOS through OpenCore as any UEFI firmware does: OpenCore
and its configuration live on the disk, and the firmware knows nothing
about them. Part of what an OpenCore configuration for the W541 adds,
though, makes up for choices of the firmware. From v1.3.10 the firmware
does some of it itself, under macOS only or behind a setup option, so that
the configuration can drop it. This page lists what, and what stays in
OpenCore.

- [What the firmware does](#what-the-firmware-does)
- [In the OpenCore configuration](#in-the-opencore-configuration)
- [Not done](#not-done)
- [Linux and Windows](#linux-and-windows)

## What the firmware does

"Under macOS" means when the OS answers `_OSI ("Darwin")`, which macOS
does and Linux and Windows do not on this laptop.

| | When | What OpenCore did for it |
|---|---|---|
| The CPU threads as `Processor` objects, `\_SB.CP00`-`\_SB.CP07` (patches 0090, 0091) | setup: *General* → *Advanced* → *ACPI processor objects*: *Processor* (default: *Device*, the ACPI 6.0 form) | an SSDT that declares `Processor` objects for the ACPI0007 devices: without one, macOS finds no CPU and stops early in the boot |
| CFG Lock off (0089, 0091) | setup: *Energy Saver* → *Processor* → *C-state configuration lock*: off (default: on) | the kernel quirk `AppleXcpmCfgLock` |
| The HPET shown, with IRQ 0 and 8, and the 8254 timer without IRQ 0, as on a Mac (0095) | under macOS | renames and an SSDT for the HPET and the 8254: the IRQ fix (*FixHPET* of SSDTTime) |
| The backlight level of the brightness keys put back at wake (0096) | under macOS | nothing: the resume path starts the backlight at 50% and macOS kept it there until a brightness key |
| The two EHCI controllers hidden (0097) | `nri` variant: the native RAM init puts every USB port on the xHCI controller | an SSDT that turns them off, if the configuration had one |
| Model, serial number, type and OEM name of the battery as strings (0092) | always | nothing: they were buffers, which ACPICA converts and an OS need not |
| No CPU notification at every read of the power source, `_PSR` (0093) | always | nothing |
| The EC wake cause read as one byte (0094) | always | ECEnabler, which the battery methods still need |

## In the OpenCore configuration

After the update, and with the two setup options set:

- *ACPI processor objects* on *Processor*: remove the SSDT that declares
  `Processor` objects, or the CPUs are declared twice. XCPM still needs
  `plugin-type` on the first thread: OpenCore's `SSDT-PLUG` sample, with
  the path of the first CPU set to `\_SB.CP00`;
- *C-state configuration lock* off: `Kernel` → `Quirks` →
  `AppleXcpmCfgLock` to false;
- the HPET: remove the renames and the SSDT of the IRQ fix;
- still needed: a way to read the EC fields wider than 8 bits, ECEnabler
  or the battery patches (the battery methods of the EC read 16 bits),
  the backlight device (`PNLF`), the USB map and the rest of the
  configuration.

The firmware's own `Processor` objects carry no `_DSM`: `plugin-type` is a
macOS property and stays in OpenCore.

## Not done

From an analysis of what macOS might want, left out until it shows on the
laptop:

- the firmware's framebuffer stays at 1920×1080, which the panel fitter
  scales to the 2880×1620 panel, and OpenCore and the boot of macOS start
  from that mode. At the native resolution the setup would draw 2.25 times
  the pixels; to try if the panel stays black when macOS takes over the
  display;
- at wake libgfxinit sets the panel up again, under every OS, as at boot.
  To change if macOS shows a black or corrupt screen after sleep.

## Linux and Windows

The parts under macOS do not apply to them. Linux answers `_OSI
("Darwin")` only on Apple hardware, and may say once in its log that it
ignored the query.

- With *ACPI processor objects* on *Processor*, Linux lists the CPUs as
  `LNXCPU` devices instead of `ACPI0007`, with the same tables;
- the CFG Lock: Linux and Windows do not need it either way;
- with the `nri` variant, `lspci` no longer shows `00:1a.0` and `00:1d.0`,
  the EHCI controllers.
