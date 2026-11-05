# What the M920x gives the next four items of the roadmap

Measured on the M920x of the port on 2026-11-05 under v1.6.0-rc6, Linux
7.0.14: an i3-8100 (4 cores, no Hyper-Threading), 32 GB in channel 0
and 8 GB in channel 1 of DDR4-2400 (dual-channel only over the first
16 GB, single-channel for the other 24), the ME in soft disable. For
[docs/roadmap.md](../../../roadmap.md): the memory clear on every core,
the device switches, Hyper-Threading, the firmware watchdog.

## Clearing the memory on every core

What ramstage does today, from `cbmem -1` and `cbmem -T` of a boot where
Linux asked for the clear (TCG MOR):

| | |
|---|---|
| Ranges cleared | `0-0x5000`, `0xa000-0xa0000`, `0xc0000-0x75ae7000` (1.97 GB), `0x100000000-0xa7c800000` (40.74 GB), then `0x5000-0xa000`: 42.72 GB |
| Time | 1997 ms of "exec" at the exit of `BS_DEV_INIT`: 21.4 GB/s on the boot processor |
| The other processors | up long before: *Attempting to start 3 APs* and *bsp_do_flight_plan done after 477 msecs* at `BS_DEV_INIT_CHIPS`, about 3 s earlier |

What one core and four can do on this memory, measured in Linux with
2 GiB per thread, touched first, then zeroed, the threads pinned one per
core:

| Threads | `memset` | `rep stosb` |
|---|---|---|
| 1 | 35.3 GB/s | 29.3 GB/s |
| 2 | 17.4 GB/s each, about 35 GB/s together | 15.4 each |
| 4 | 11.4 GB/s each, about 45 GB/s together | 9.3 each |

So one core already saturates the two channels of this machine (38.4
GB/s peak), and the firmware's 21.4 GB/s average is mostly the memory
itself: the 24 GB that sit on one channel alone cannot go faster than
about 19 GB/s, whichever the number of processors (16 GB at 35 GB/s and
26.7 GB at 19 GB/s make 1.9 s, what is measured). What the next step
can expect:

- on this machine, a gain of a few tenths of a second at most, in the
  first 16 GB; a test build with one, two and four processors should
  run on a machine with two equal DIMMs, where four cores can take the
  clear from about 21 GB/s to the 35-38 GB/s of the channels (32 GB in
  0.9 s instead of 1.5);
- the single-processor path has headroom of its own: Linux clears at
  29-35 GB/s on one core where ramstage does 21, so the loop of
  `memset_pae()` (one 2 MiB window at a time, a page-table write and a
  TLB flush for each) and `memset` of the 32-bit ramstage are worth a
  look before the processors are added (`rep stosb` with ERMS, which
  this processor has, no FSRM);
- the elog init that follows (`started elog init` at 8.53 s, after the
  clear) and `BS_WRITE_TABLES` are untouched by it.

The program: `memclr.c`, a thread per core that allocates its 2 GiB with
`aligned_alloc`, fills it, then times `memset(b, 0, n)` or `rep stosb`
with `CLOCK_MONOTONIC`; the per-thread figure is the one to read, the
threads run at once.

## Device switches

The M920x already has *Hardware* → *Devices* (front and rear USB, audio,
Ethernet, Wi-Fi, the riser slot, the PEG port); the roadmap item is the
W541. What the M920x shows of how such switches look on a Cannon Point
PCH, as a reference for the W541's Lynx Point:

| Device | Where | On the M920x |
|---|---|---|
| Ethernet | `00:1f.6` I219-LM, the PCH's own controller | `onboard_ethernet`: the FSP-S UPD (`PchLanEnable`), the device gone from the bus, the OS sees nothing; the W541's Lynx Point has the `BUC` bit in the RTC well instead, which needs the Sandy Bridge-style reset |
| Wi-Fi | `02:00.0` Intel 3165 on root port `00:1c.0`, its Bluetooth on USB2 port 14 of the xHCI | `onboard_wlan`: the root port and the USB port together, else the Bluetooth half stays |
| Audio | `00:1f.3` cAVS, Realtek ALC233 codec | `onboard_audio` hides the controller; a microphone-only soft switch would be the pin configuration of the codec: on this one the front microphone jacks are nodes `0x19` and `0x1a` (`0x02a11020`, `0x02a11030`), the headphone jack `0x21`, the internal speaker `0x14`, the rear line pins `0x17`, `0x18`, `0x1b` not connected (`0x411111f0`); a pin set to `0x411111f0` in the verb table is gone for every OS |
| USB | xHCI `00:14.0`: 16 USB2 ports on bus 1, 10 USB3 on bus 2; the keyboard on port 2 here, Bluetooth on port 14 | `front_usb`, `rear_usb`: the port bitmaps of the FSP-S UPDs (`PortUsb20Enable`, `PortUsb30Enable`), which the devicetree pairs with the physical ports; the W541's camera and fingerprint reader are USB devices the same way, through the EHCI/xHCI port disable of Lynx Point |
| SATA, root ports | `00:17.0` AHCI; root ports `00:1b.0` (NVMe) and `00:1c.0` (Wi-Fi), the others hidden | the FSP-S UPDs per port |

`lspci -nn`, `lspci -tv`, `lsusb -t`, the pins of
`/proc/asound/card0/codec#0`, `lscpu` and the DIMMs of the machine are
in [devices-m920x-fsp.txt](devices-m920x-fsp.txt).

## Hyper-Threading

Nothing to measure here: the i3-8100 has four cores and one thread each
(`lscpu`: *Thread(s) per core: 1*, though CPUID advertises `ht`), so
`hyper_threading` of the M920x, the FSP-M UPD `HyperThreading`, changes
nothing on this processor; the MADT lists four local APICs. The W541's
item (the `SOFT_RESET_DATA` bit of Lynx Point) needs the W541, or an
M920x with an i5-8500T/i7 that has two threads per core.

## The firmware watchdog

The two timers of the PCH, read from the ports while rc6 ran, nothing
written:

| Register | Value | Meaning |
|---|---|---|
| `OC_WDT_CTL` (ACPI base + 0x54 = 0x1854) | `0x00002000` | the overclocking watchdog is there and off: enable (bit 14) 0, timeout (bits 9:0) 0, force-all (bit 15) 0, no reset status; bit 13 (*no ICC survivability*) set. FSP-M and FSP-S of Coffee Lake leave it off |
| `TCO1_CNT` (TCO base 0x400 + 8) | `0x1800` | the TCO timer halted (`TMR_HLT`, bit 11) and locked (`TCO_LOCK`, bit 12): as the roadmap says, not usable from a slot |
| `TCO2_STS` | `0x0000` | no second timeout, no boot status |
| `TCO_TMR`, `TCO_RLD` | 4, 4 | the default reload |
| ACPI | no `WDAT` table | the OS has no firmware watchdog to drive; `iTCO_wdt` is not loaded (the TCO is locked), Linux runs its NMI watchdog only |

So the next step of the roadmap stands as written: the OC watchdog is
reachable, off, and nothing else holds it; the open questions (what it
resets on Cannon Point-H, whether the enable survives that reset) need
the armed test with a long timeout, which is the owner's. A read of
`OC_WDT_CTL` at `BS_PAYLOAD_BOOT` in the test build will say whether
FSP-S touched it in between.
