<p align="center">
  <img src="assets/ourobios.svg" width="128" height="128" alt="ouroBIOS">
</p>

<h1 align="center">ouroBIOS</h1>

<p align="center"><b>REBORN BY DESIGN.</b><br>
<sub>COREBOOT &middot; EDK II &middot; THINKPAD W541 &middot; THINKCENTRE M920X</sub></p>

[![MRC release](https://img.shields.io/github/v/release/debianita22/ourobios?include_prereleases&sort=semver&filter=*-mrc&style=flat-square&label=mrc)](https://github.com/debianita22/ourobios/releases)
[![NRI release](https://img.shields.io/github/v/release/debianita22/ourobios?include_prereleases&sort=semver&filter=*-nri&style=flat-square&label=nri)](https://github.com/debianita22/ourobios/releases)
[![M920x release](https://img.shields.io/github/v/release/debianita22/ourobios?include_prereleases&sort=semver&filter=*-m920x-fsp&style=flat-square&label=m920x)](https://github.com/debianita22/ourobios/releases)
[![Check](https://img.shields.io/github/actions/workflow/status/debianita22/ourobios/check.yml?branch=main&style=flat-square&label=check)](https://github.com/debianita22/ourobios/actions/workflows/check.yml)
[![Build](https://img.shields.io/github/actions/workflow/status/debianita22/ourobios/build.yml?style=flat-square&label=build)](https://github.com/debianita22/ourobios/actions/workflows/build.yml)
[![License](https://img.shields.io/github/license/debianita22/ourobios?style=flat-square)](LICENSE)

---

ouroBIOS is a [coreboot](https://www.coreboot.org) firmware for the **Lenovo
ThinkPad W541** (Intel Haswell, Lynx Point QM87, NVIDIA Quadro K2100M), with
the [EDK II](https://github.com/mrchromebox/edk2) UEFI payload. GitHub Actions
builds it from a pinned upstream coreboot commit plus the patches in this
repository and publishes two complete flash images per version:

| Release | RAM initialization | Status |
|---|---|---|
| `vX.Y.Z-mrc` | Intel `mrc.bin`, the blob from the coreboot 24.08 image that ran on this W541 ([blobs/README.md](blobs/README.md)) | the conservative choice |
| `vX.Y.Z-nri` | coreboot's native RAM init (NRI), no `mrc.bin` ([docs/raminit.md](docs/raminit.md)) | a release with the `mrc` one from v1.3.9 (a pre-release before), although upstream still labels it *[NOT COMPLETE]*: how it compares with `mrc.bin` on the W541 is in [docs/raminit.md](docs/raminit.md#on-the-w541) ([Libreboot](https://libreboot.org/docs/install/w541_external.html) ships it on the W541 too) |

Everything else is the same in the two variants.

From v1.4.0 each version also has a release for the **Lenovo ThinkCentre
M920x Tiny** (Intel Coffee Lake, Q370), `vX.Y.Z-m920x-fsp`: RAM
initialized by Intel's FSP-M, the same payload, setup menu, vboot slots and
capsule updates, a pre-release until it is confirmed on the machine. Its
board, flash map and blobs are in [`boards/m920x`](boards/m920x), how to
install, update and recover it in [docs/m920x.md](docs/m920x.md); the rest
of this page is about the W541.

The name: *ouro* is the ouroboros, the snake that bites its own tail, a cycle
of transformation and renewal; *BIOS* is what it replaces, the firmware that
starts the machine. A laptop past the end of its vendor's support gets a new
life from an independent firmware: the cycle of hardware evolution. The logo,
[`assets/ourobios.svg`](assets/ourobios.svg), is that ouroboros as a printed
circuit with an infinity inside, 16 x 16 pixels so that it reads in the
firmware too: it is the boot splash and the badge of the setup's menu bar,
and `tools/logo.py` turns it into the LVGL image, the splash and PNGs. The
firmware reports itself as `ouroBIOS-vX.Y.Z-<variant>` (coreboot's
`CONFIG_LOCALVERSION`: in the *About* card of the setup, and in SMBIOS as
`CBET4000 ouroBIOS-vX.Y.Z-<variant>`, the prefix that Linux's
`thinkpad_acpi` looks for) and as *ouroBIOS* to the UEFI system table.

> [!WARNING]
> Flashing firmware can leave the laptop unable to boot. Keep a backup of the
> whole flash and have an external SPI programmer at hand before you start:
> see [docs/flashing.md](docs/flashing.md).

## What a release contains

| File | Use |
|---|---|
| `w541-coreboot-<version>-<variant>.rom` | complete 12 MiB flash image: descriptor, GbE, Intel ME and coreboot |
| `…-4mb-chip.rom` | last 4 MiB of the image: the read-only part and slot B (up to v1.2.x all of coreboot), enough to boot, for an external programmer on the 4 MiB chip |
| `…-8mb-chip.rom` | first 8 MiB of the image: descriptor, GbE and ME **of the machine the blobs come from**, for the 8 MiB chip |
| `….cap` | signed UEFI capsule (from v1.2.0): updates a laptop that runs a release with the same flash map and read-only part (v1.3.9 or later; v1.3.0-v1.3.8 install the capsules of v1.3.0-v1.3.8, v1.2.x those of v1.2.x) from Linux, without flashrom ([docs/update.md](docs/update.md)) |
| `….cab` | the same capsule as an fwupd package (from v1.2.2), signed for fwupd with the same key ([docs/update.md](docs/update.md#fwupd)) |
| `….config` | the complete coreboot configuration |
| `…-layout.txt` | flash map (FMAP) and CBFS contents |
| `ourobios.xml.gz`, `….jcat` | mrc release only (from v1.3.4): the signed metadata of the project's fwupd remote, with the `.cab` of both variants (from v1.4.0 also of the M920x) ([docs/update.md](docs/update.md#the-fwupd-remote)) |
| `…-sbom.md` | software bill of materials (from v1.4.0): versions, licenses and SHA-256 of every component and binary blob, and how much of the image is open source (`tools/sbom.py`) |
| `….cdx.json` | the same as CycloneDX 1.5 JSON (from v1.4.0) |
| `SHA256SUMS` | checksums (from v1.4.0 also in the notes of the release) |

The W541 flash is two chips seen as one 12 MiB space. The layout is
[`configs/w541.fmd`](configs/w541.fmd):

| Range | Chip | Contents |
|---|---|---|
| `0x000000-0x000FFF` | 8 MiB | Intel flash descriptor (IFD), all regions unlocked |
| `0x001000-0x002FFF` | 8 MiB | GbE, with the MAC address of the machine the blobs come from |
| `0x003000-0x4FFFFF` | 8 MiB | Intel ME 9.1, reduced with `me_cleaner -S` (ROMP and BUP only, AltMeDisable set) |
| `0x500000-0x597FFF` | 8 MiB | regions coreboot writes at runtime, empty in the image: `RW_MRC_CACHE` (RAM training), `SMMSTORE` (UEFI variables and settings), `RO_VPD`, `RW_ELOG` (event log) |
| `0x5A0000-0x5BFFFF` | 8 MiB | `RW_NVRAM` (vboot's state) and `RECOVERY_MRC_CACHE`, empty in the image |
| `0x5C0000-0x88FFFF` | both | `RW_SECTION_A`: slot A, romstage, ramstage and payload, signed |
| `0x890000-0xB5FFFF` | 4 MiB | `RW_SECTION_B`: slot B, the same |
| `0xB60000-0xBFFFFF` | 4 MiB | `WP_RO`: `FMAP`, vboot's root key (GBB), bootblock with verstage, `mrc.bin`, microcode |

From v1.3.0 coreboot's vboot verifies a slot before it runs it, and a
capsule writes the slot that is not running: an update cut short, or one
that does not boot, falls back to the old slot
([docs/vboot.md](docs/vboot.md)). The regions written at runtime sit on the
8 MiB chip, at the same offsets as up to v1.2.x (when `0x598000-0x7FFFFF`
was unused and `0x800000-0xBFFFFF` held all of coreboot), as in the
coreboot 24.08 build the laptop ran and in Libreboot's images for this
board: coreboot's default map would put them on the 4 MiB chip, where
saving the RAM training is not proven to work, and S3 resume depends on it.
The 4 MiB chip holds the read-only part and slot B, so `…-4mb-chip.rom`
boots for recovery with an external programmer.

The first 5 MiB are byte-identical to `legacy/coreboot-4.22/coreboot.rom`,
the image this project started from: `tools/verify-rom.sh` stops a release
otherwise. On a W541 that already runs coreboot, an update rewrites only the
BIOS region (`flashrom --ifd -i bios`), so the descriptor, the ME and the MAC
address on the machine stay as they are.

Inside coreboot:

- coreboot `26.09-438-g206078d6d990` plus the [patch series](patches/), EDK2
  from MrChromebox pinned to a tested commit plus its own
  [patches](patches/README.md#edk2-and-lvglpkg), with the boot splash in
  `assets/`;
- libgfxinit for the Intel GPU (no Intel VBIOS is executed);
- the NVIDIA K2100M VBIOS, handed to the operating system through the ACPI
  `_ROM` method of the GPU, with runtime power management (the GPU is switched
  off when idle), its power state kept across suspend, and the Optimus key
  the Windows NVIDIA driver asks for (`blobs/opvk.inc`). The W541 has no
  display mux: the panel, mini DisplayPort and VGA are wired to the Intel
  GPU, the dock's DisplayPort to the NVIDIA one (its VBIOS lists that single
  connector), so there is no "discrete only" mode in any firmware;
- CPU microcode from coreboot's `intel-microcode`, also referenced by the FIT;
- a setup menu laid out like System Preferences (Esc at power-on): a grid
  of icons on a dark desktop whose wallpaper follows the hour of the day
  (night, dawn, day, dusk, evening), under a translucent menu bar and dock;
  one icon per category, then the boot entries; each category opens a
  window of settings grouped on cards, with switches and drop-down menus.
  The arrow keys, the TrackPoint and the touchpad move around:

  | Category | Settings |
  |---|---|
  | *General* | *About this ThinkPad*: model, machine type, serial number and UUID (from the VPD), processor, memory, firmware and EC versions, the state of the Intel ME (from v1.4.0-rc4, also in SMBIOS); *Boot*: the iPXE and CSMWrap boot entries, and from v1.4.0-rc4 the USB drives in the boot order and the boot menu prompt; *Sound*: beeps (from v1.4.0-rc4 the keyboard beep too) and volume; links to the time and date, firmware update, boot splash and UI pages |
  | *Energy Saver* | battery charge thresholds (OS controlled, 100%, 80%, 60%), Intel SpeedStep, Turbo Boost, C-states, CPU PL1/PL2 limits, cooling policy (active or passive), USB always on (from v1.4.0-rc4 *AC and battery* charges on battery too), power-on with AC attached (from v1.4.0-rc4), power-on after power failure |
  | *Security* | *Flash protection*: BIOS Lock (flash writable only by the firmware, off by default) and Firmware protection (the read-only part locked at every boot, on by default); memory cleared at power-on, Intel VT-x, VT-d (from v1.4.0-rc4 with the ExpressCard and Thunderbolt ports untrusted for the OS, off by default), the Intel ME interface, Secure Boot, supervisor password (asked for before the setup menu opens) |
  | *Keyboard* | Fn/Ctrl swap, F1-F12 or special keys, sticky Fn, keyboard backlight, TrackPoint, touchpad |
  | *Hardware* | *NVIDIA graphics*: the GPU and the tuning of its PCIe link; *Intel graphics*: graphics stolen memory (native RAM init only: `mrc.bin` reserves a fixed 32 MiB), aperture and the firmware screen resolution; *Storage*: the SATA ports besides the drive bay; *Expansion ports*: ExpressCard and Thunderbolt; *Wireless*: Wi-Fi, Bluetooth, WWAN |
  | *Compatibility* | *macOS*: the options that take the place of parts of an OpenCore configuration (ACPI processor objects as *Processor*, the C-state configuration lock, the NVIDIA GPU off under macOS, the panel, the display audio, the device properties; [docs/macos.md](docs/macos.md)); *Advanced*: NMI |

  Settings live in UEFI variables in the `SMMSTORE` flash region and apply
  at the next boot. XMP memory profiles are not supported: the memory runs
  at its JEDEC timings;
- the serial number, machine type model and UUID of the laptop in the
  `RO_VPD` flash region, written once with `tools/vpd.py` and reported in
  SMBIOS as the Lenovo firmware did
  ([docs/flashing.md](docs/flashing.md#serial-number-and-machine-type-vpd));
- an event log in the `RW_ELOG` flash region (boots, wake sources, entries
  into S3 and S5, power failures, watchdog resets), read with
  `tools/elog.py` or coreboot's `elogtool`, and POST codes kept in CMOS, so
  that the boot after a hang logs where it stopped
  ([docs/flashing.md](docs/flashing.md#diagnosing-a-hang));
- verified boot with two RW slots (from v1.3.0): vboot checks the RSA-4096
  signature of a slot before it runs it, and boots the other one if it does
  not verify or does not boot ([docs/vboot.md](docs/vboot.md));
- firmware updates with signed UEFI capsules (from v1.2.0): `tools/update.py`
  stages the capsule of a release on the EFI system partition, and at the
  next boot the firmware checks its signature and version and writes the
  slot that is not running, keeping settings, VPD and event log, also with
  *BIOS Lock* and *Firmware protection* on; from v1.3.6 on a screen of its
  own, where the ouroboros of the logo fills up and a map of the flash
  shows each 4 KiB block as it is written;
  the version is in the ESRT, and from v1.2.2 each release has an fwupd
  package too, `fwupdmgr install`; from v1.3.4 the project's fwupd remote
  (`configs/fwupd/ourobios.conf`) offers each release to `fwupdmgr update`,
  GNOME Software and KDE Discover, and from v1.3.6 a testing remote
  (`configs/fwupd/ourobios-testing.conf`) the release candidates too;
  without an OS, the *Firmware Update* page
  of the setup installs the capsule from a USB drive and, from v1.3.4, goes
  back to the release in the other slot
  ([docs/update.md](docs/update.md));
- network boot with iPXE (from v1.3.6): the *iPXE Network Boot* entry of
  the boot menu (Esc at power-on) drives the Intel I217 Ethernet
  controller itself (iPXE with its Intel driver, no UEFI network stack),
  does PXE and HTTP and runs iPXE scripts; Ctrl-B at its banner opens its
  shell. The entry goes at the end of the boot order, after the disks and
  the UEFI Shell; *General* → *Boot* in the setup turns it off;
- legacy BIOS boot with CSMWrap (from v1.3.6): the *CSMWrap Legacy Boot*
  entry of the boot menu starts [CSMWrap](https://github.com/CSMWrap/CSMWrap),
  which runs the CSM and the VGA BIOS of SeaBIOS as a UEFI application:
  SeaBIOS's own drivers for SATA (AHCI), NVMe and USB drives behind INT
  13h, its boot menu on Esc, INT 10h on the firmware's framebuffer (there
  is no Intel VBIOS in this firmware), E820, ACPI and SMBIOS from the
  firmware, for the operating systems and tools that do not boot from
  UEFI. It keeps one logical processor for itself (a quad-core i7 shows 7
  of its 8 threads to the legacy OS). A legacy BIOS runs unsigned code, so
  while Secure Boot is on the entry goes and the firmware refuses to start
  CSMWrap, however it is chosen; *General* → *Boot* in the setup turns it
  off;
- macOS with OpenCore (from v1.3.10): in the setup (*Compatibility* →
  *macOS*) the CPUs as `Processor` objects with `plugin-type`, CFG Lock
  off, the device properties of the W541 (framebuffer, audio layout), the
  panel as external display (brightness keys from the firmware) or
  built-in (PNLF, ALS0) and the USB, audio and LAN wake, and, under macOS
  only, the USB power properties (USBX), the HPET and 8254 interrupts of
  a Mac, the backlight level kept across sleep and the NVIDIA GPU powered
  off, which OpenCore configurations otherwise add or patch in
  ([docs/macos.md](docs/macos.md));
- fixes for wake from suspend (lid, Fn), the Fn hotkeys, Bluetooth and WWAN
  state on resume, xHCI ports, USB over-current mapping, PCIe interrupts, the
  backlight, HDMI/DisplayPort audio clocks, the battery `_UID` and the AES-NI
  lock; from v1.4.0-rc4 the EC events that the Lenovo firmware reports to
  the OS (dock, thermal and battery alarms, NumLock) and its software mute;
  plus fixes and additions to the native RAM init of the `nri` variant
  ([docs/raminit.md](docs/raminit.md)), from v1.4.0-rc4 the rank mapping
  fix of upstream change 96694 among them.
  [patches/](patches/) lists them all.

> [!NOTE]
> The NVIDIA GPU is **disabled by default**, as in upstream coreboot. Turn it
> on in the setup menu: *Hardware* → *NVIDIA graphics* → *NVIDIA discrete GPU*.

> [!WARNING]
> Suspend to RAM (S3): with the images up to v1.0.6 the laptop sleeps and
> does not come back: a change in coreboot's cache-as-RAM setup loses one
> line of the region on Haswell, and `mrc.bin` hung on it while restoring
> the memory on resume (POST code `0x3a`, ten lines into its log). Patch
> 0043, from v1.0.7, fills the region as before: resume works (tested on
> v1.0.9 with RTC, power button and lid wake). If a resume still stops,
> [docs/flashing.md](docs/flashing.md#diagnosing-a-hang) shows how to find
> where, and suspend-to-idle (`mem_sleep_default=s2idle`) works meanwhile.

## Flashing

On a W541 that already runs coreboot with an unlocked flash (as the 4.22 image
in `legacy/`), from Linux, the whole BIOS region:

```sh
sha256sum -c SHA256SUMS --ignore-missing
sudo modprobe -r spi_intel_platform spi_intel             # flashrom must not go through /dev/mtd0
sudo flashrom -p internal -r backup-$(date +%F).rom      # whole 12 MiB: keep it off the laptop
ls -l backup-*.rom                                        # must be 12582912 bytes
sudo flashrom -p internal --ifd -i bios -w w541-coreboot-v1.3.9-nri.rom
```

The UEFI settings and boot entries start from scratch after that. A laptop
that already runs ouroBIOS v1.0.3 or later keeps them with the command of
[docs/flashing.md](docs/flashing.md#from-v12x-to-v130), which writes every
region but the ones with the settings; v1.3.9, the first release with the
current read-only part, goes in that way too, once, with *Firmware
protection* off ([docs/flashing.md](docs/flashing.md#from-v13x-to-v139)).
Before you reboot, read [docs/flashing.md](docs/flashing.md): boot loader
fallback path, serial number and machine type in the VPD (and how to keep
them across updates), external flashing and recovery.

From v1.3.9 on the laptop, the next releases install with their capsule,
keeping settings, boot entries and VPD, with *BIOS Lock* on or off
([docs/update.md](docs/update.md)):

```sh
sudo python3 tools/update.py stage --latest && sudo systemctl reboot
```

## Building

Debian or Ubuntu:

```sh
sudo apt install build-essential bison flex gnat libncurses-dev zlib1g-dev m4 \
    curl git python3 uuid-dev imagemagick libssl-dev pkg-config nasm xxd
git clone https://github.com/debianita22/ourobios.git
cd ourobios
tools/build.sh                      # both W541 variants, into dist/
tools/build.sh --board m920x        # the M920x (docs/m920x.md); --board all: every board
```

`tools/build.sh` fetches coreboot at the pinned commit into `work/coreboot`,
applies `patches/series`, copies the blobs (checked against their
`SHA256SUMS`), fetches MrChromebox's EDK2 at the commit of the defconfigs
(with the submodules the payload uses: OpenSSL, the brotli of BaseTools,
LvglPkg and its LVGL; in the paths of the others it leaves the empty
include folders their `.dec` files list, which BaseTools wants to find,
so a `prepare` of a release before rc19 on that tree needs those folders
removed first) and applies `patches/edk2` and `patches/lvglpkg`,
writes the font of the
update screen from those of LvglPkg (`tools/ui-font.py`), fetches iPXE at
the commit coreboot pins (which must be `IPXE_COMMIT` of `tools/build.sh`)
and CSMWrap at the commit `tools/build.sh` pins and builds the latter with
the system compiler (`nasm`, `xxd`), builds the coreboot cross toolchain
the first time (30-60 minutes, then reused), builds each variant and runs
`tools/verify-rom.sh` on it. The EDK2 payload is built once (from
v1.3.10-rc18): nothing in it depends on the variant, whose GUID it reads
from the coreboot table at every boot, so the second variant gets the
payload of the first, after a check that the two `.config` differ only in
the RAM init, the name and the GUID of the ESRT. Useful options:

```sh
tools/build.sh --variant mrc                  # one variant
tools/build.sh --version v1.0.0-local         # version string and file names
tools/build.sh --with NAME roms               # plus patches/optional/NAME.patch
tools/build.sh prepare config                 # the trees, the patches and the .config only
tools/build.sh menu                           # after roms: the setup menu, each option in one card
tools/build.sh smoke                          # after roms: the payload in QEMU
tools/build.sh update-test                    # capsule updates with vboot A/B in QEMU
tools/build.sh repro                          # after roms: built again, compared bit by bit
tools/build.sh --help                         # the other commands and the options
```

The builds are reproducible (from v1.3.6): the date in the ROM is the date
of the commit, the payload has no debug directory in its PE images, and
CI builds each release a second time from scratch, CSMWrap and iPXE
included, on another runner, and compares the two bit by bit
(`tools/ci.sh compare`; `tools/build.sh repro` does the same on one
machine). The same ROM needs the same compilers:
coreboot's cross toolchain, whose versions the coreboot commit fixes, and
for the payload, iPXE and CSMWrap the GCC and binutils of the build
machine, GitHub's Ubuntu 24.04 runner (the `-layout.txt` of a release
names them, after v1.3.6-rc2). From a checkout of a release tag,
`tools/build.sh --version vX.Y.Z roms` then gives the stages, the payload
and the other CBFS files of the release; the whole `.rom` compares byte
for byte only with the project's vboot key (`VBOOT_SIGNING_KEY`: the
slots are signed), without which the slots are signed with vboot's test
keys and `config` in CBFS says so. `--release` also wants the capsule
key.

`smoke` puts the EDK2 payload of each variant, as built, into a coreboot
image for QEMU's q35 and boots it with `tools/qemu-smoke.py` (once per
payload: a variant with the same payload, byte for byte, as one already
tested is not tested again): coreboot must
reach the payload, the payload must draw, Esc must open the setup, and the
setup must open a page and go back, without a reset. Then, in two more
boots, the UEFI Shell writes a test variable with `setvar`: it must be in
the SMMSTORE store of the emulated flash, and after the reboot the second
write must find and delete the first copy, leaving one. Then the two boot
entries of the firmware volume, each chosen with `BootNext` from the
Shell: iPXE, with an e1000 on QEMU's user network, must get an address
from its DHCP, download the script the DHCP names over TFTP and run it
(the script chains a second one, whose TFTP request in the traffic dump
is the proof); CSMWrap, with two CPUs and a SATA disk, must boot the
disk's master boot record, which writes a line on the serial port. Last,
on a fresh copy of the image with an EFI system partition, the payload
boots `tools/efi/rt-reloc-test.c`, which does to the runtime services what
boot.efi of macOS does without OpenCore's `AvoidRuntimeDefrag`: after
`ExitBootServices()` and `SetVirtualAddressMap()` it copies their code and
data elsewhere, fills the old copies with 0xCC and calls them only through
page tables with the virtual addresses. Every service must answer, the two
variables it writes must be in the store of the emulated flash with their
data, nothing may write to the old copies, and `ResetSystem()` must reset;
a physical address that the payload or SMM still used at runtime would
fail it, as v1.3.10-rc15 does. Then, on another fresh copy with an EFI
system partition, `tools/efi/secure-boot-test.c`, signed with a certificate
issued by a CA made for the run: at the first boot (the Microsoft keys just
enrolled, Secure Boot off) it prints the ESRT, loads the embedded images
(all accepted), puts the CA in db in custom mode as EnrollDefaultKeys does,
sets `SecureBootEnable` and resets; the second boot happens only if the
payload verified its signature (the chain to the CA, through CryptoDxe),
and then the shim signed by Microsoft (Debian's or Ubuntu's `shim-signed`,
found in the system or downloaded with `apt-get download`; without it the
case is skipped) must load, an image signed by a certificate in no
database, an unsigned one and one signed by a second child of the CA whose
Authenticode hash (`tools/pe-hash.py`) the first boot put in dbx must be
refused, while the same image with another hash, signed by that child,
must load. The ESRT must carry the one
entry of the variant, with the GUID the payload reads from the coreboot
table: the second variant, whose payload is the first one's byte for byte,
runs this step only, on its own q35 image. Last, with the TPM 1.2 of
`swtpm` (the q35 image is built with `CONFIG_TPM1`, as the W541), the
payload boots to the Shell and the TCPA log in RAM must have the separator
of every PCR and, in PCR 7, the measurements of `SecureBoot`, `PK`, `KEK`,
`db` and `dbx` the variable driver makes when EnrollDefaultKeys writes
them at the first boot, each with the SHA-1 of its event data: with a TPM
1.2 they are made only then, and v1.3.10-rc19 lost them (its TPM driver
started after the keys). It needs `qemu-system-x86`, `mtools`, `clang`,
`lld`, `openssl`, `sbsign` (`sbsigntool`) and `swtpm`; screenshots and the
serial console go to `work/smoke-<variant>`. Nothing of the W541 itself
runs there: it checks the payload and coreboot's common code, not the
board.

`update-test` checks the update path the same way, with
`tools/qemu-update.py`: four coreboot images for q35 with vboot's two RW
slots and its nvdata in flash, built from a git worktree of the tree with
`patches/test/q35-update-test.patch` (never in a W541 ROM), an EDK2 payload
of the project's patches built for debugging and trusting a key made for the
test only, and their capsules, made as those of the releases. The capsules
go on an EFI system partition, as `update.py stage` puts them, and QEMU
boots from off at every reset: each capsule must write only the slot that
is not running, vboot must try it and the payload confirm it, a capsule of
the release already in the other slot must write nothing to the slots, and
vboot must go back to the old slot when the new one does not verify or does
not reach the payload; from the setup (keys sent by QEMU), *Go back to* must
switch to the other slot without writing it, and a UEFI application
started from the disk (`tools/efi/slot-lock-test.c`) must be refused, before
and after `ExitBootServices()`; a full `RW_NVRAM`, a power cut halfway
through a slot and a capsule on a USB drive must leave a laptop that boots
and finishes the update; a capsule that names the two slots only, as those
of the M920x, must leave `RW_MRC_CACHE` as it was; the ESRT is checked at
every boot
([docs/vboot.md](docs/vboot.md#how-it-is-tested)). It needs
`qemu-system-x86`, `mtools`, `clang` and `lld`; the serial console goes to
`work/update-test/out`.

## Continuous integration and releases

| Workflow | When | What |
|---|---|---|
| [`check.yml`](.github/workflows/check.yml) | every push and pull request | `tools/ci-check.sh` (shellcheck, actionlint, blob checksums, patch series, defconfigs); the series applied to the pinned coreboot and EDK2, and the configuration of every board and variant checked |
| [`build.yml`](.github/workflows/build.yml) | tag `vX.Y.Z`, *Run workflow*, push to `ci-test/**` | the ROMs of every board with the coreboot toolchain (cached), verified, their setup menu checked (`menu`), their payloads booted in QEMU (`smoke`), their capsules signed, their bill of materials made (`tools/sbom.py`); in parallel, the ROMs built a second time from scratch on another runner (`repro`) and compared bit by bit with the first (`compare`), and the capsule update with vboot A/B in QEMU (`update-test`); the files of each release checked (`tools/ci.sh check`) and published as `vX.Y.Z-mrc`, `vX.Y.Z-nri` and, from v1.4.0, `vX.Y.Z-m920x-fsp` |
| [`upstream.yml`](.github/workflows/upstream.yml) | every Monday | opens an issue when the series no longer applies on coreboot `main`, a patch was merged upstream, a coreboot release is out, or MrChromebox's EDK2 branch moved |

A release is made by pushing a version tag (`git tag v1.0.0 && git push origin
v1.0.0`) or with *Run workflow* and a version. It needs the repository secret
`CAPSULE_SIGNING_KEY`, the key that signs the capsules, and
`VBOOT_SIGNING_KEY`, the one that signs the RW slots
([keys/README.md](keys/README.md)); test builds go without them (vboot's
test keys). Versions with a hyphen
(`v1.1.0-rc1`) or the *prerelease* box give pre-releases only. The notes of
each include the section of [`CHANGELOG.md`](CHANGELOG.md) for the version
(`## v1.1.0` for `v1.1.0-rc1` too), and a release build stops at once without it.
Only the `mrc` release can be the latest: the fwupd remote takes its metadata,
with the `.cab` of every board, from the latest release. A pre-release that
works on the machines becomes a release without rebuilding it:

```sh
gh release edit v1.0.0-mrc --repo debianita22/ourobios --prerelease=false --latest
gh release edit v1.0.0-nri --repo debianita22/ourobios --prerelease=false --latest=false
gh release edit v1.4.0-m920x-fsp --repo debianita22/ourobios --prerelease=false --latest=false
```

## Repository layout

| Path | Contents |
|---|---|
| `CHANGELOG.md` | what changes in each release |
| `blobs/` | IFD, GbE, ME, `mrc.bin` and VBIOS images of the W541 ([blobs/README.md](blobs/README.md)) |
| `boards/` | one folder per board for `tools/build.sh --board`: `board.sh` (variants, flash, chips, the checks of `verify-rom.sh`); the W541 one points at `configs/` and `blobs/`, the M920x one has its defconfig, flash map, blobs, the hash of its first 12 MiB and the interface of its read-only part ([docs/m920x.md](docs/m920x.md)) |
| `assets/` | the logo, `ourobios.svg`, and the boot splash of each board made from it (`tools/logo.py splash`): `bootsplash.bmp` for the W541, `bootsplash-m920x.bmp` for the M920x |
| `configs/` | `w541-mrc.defconfig` and `w541-nri.defconfig`, the flash map `w541.fmd`, the interface of the read-only part already on the laptops (`ro-interface.txt`), the OpenCore device properties of this W541 for patches 0128 and 0133 (`macos/`), the fwupd remotes (`fwupd/ourobios.conf`, the releases; `fwupd/ourobios-testing.conf`, the candidates too) |
| `patches/` | the series applied to coreboot, the patches to EDK2 and its LvglPkg, the q35 patches of the update test and of the setup screenshots; `optional/` for patches to build in with `--with`, none at the moment ([patches/README.md](patches/README.md)) |
| `tools/` | `build.sh`, the build; `verify-rom.sh`, the checks on a ROM; `ci-check.sh`, `ci.sh` and `upstream.sh`, the CI, the releases and the upstream check; `cfr-dump.sh` and `q35-cfr-rom.sh`, the setup menu of a build (`build.sh menu`) and its screenshots (`qemu-setup-shots.py`); `update.py`, the capsule update from Linux and the flash protection of the running boot; `fwupd-cab.py`, the fwupd package and the metadata of the remote; `vpd.py`, the serial number and machine type; `elog.py`, which reads the event log from a flash dump; `idle-report.py`, package C-states, power, memory traffic and device power states at idle; `hw-report.py`, PASS, WARN or FAIL for each area of a running machine, the automated part of the release tests ([docs/testing.md](docs/testing.md)); `pm-regs.py`, the power management registers the firmware left; `ddr-report.py`, the memory controller as the RAM init left it, and two of its dumps compared; `mem-latency.c`, how long a read from the memory takes; `peg-report.py`, the PCIe link to the NVIDIA GPU; `qemu-smoke.py`, the payload booted in QEMU (with `efi/rt-reloc-test.c`, the runtime services moved as boot.efi of macOS moves them, and `efi/secure-boot-test.c`, the ESRT and Secure Boot image verification, with `pe-hash.py`, the Authenticode hash of a PE image; the TPM 1.2 of swtpm and its measurement log); `qemu-update.py`, capsule updates with vboot A/B in QEMU (with `efi/slot-lock-test.c`, a UEFI application for it); `logo.py`, the logo as an LVGL image or a PNG; `sbom.py`, the software bill of materials of a ROM read from the image itself (versions, licenses, SHA-256 of the binaries, how much is open source), in Markdown or CycloneDX |
| `keys/` | the certificate of the key that signs the capsules, and vboot's public keys ([keys/README.md](keys/README.md)) |
| `legacy/coreboot-4.22/` | the coreboot 4.22 image and configuration this project started from, built from the same blobs |
| `docs/` | [flashing and recovery](docs/flashing.md), [updates with capsules](docs/update.md), [verified boot and A/B](docs/vboot.md), [the native RAM init](docs/raminit.md), [macOS with OpenCore](docs/macos.md), [the ThinkCentre M920x](docs/m920x.md), [release testing](docs/testing.md), [what was evaluated and left for later](docs/roadmap.md) |
| `.github/` | the workflows ([Continuous integration and releases](#continuous-integration-and-releases)) and the issue forms in `ISSUE_TEMPLATE/`: bug report, feature request and hardware report, which ask for the firmware version, how it was written, the `tools/hw-report.py` report and the coreboot log |

## Binary blobs

The images contain proprietary binaries that are not covered by the GPL: the
Intel flash descriptor, ME firmware and `mrc.bin`, the GbE configuration and
the NVIDIA VBIOS and the NVIDIA Optimus key (`blobs/opvk.inc`, from the
Lenovo DSDT); on the M920x the descriptor, GbE configuration and CSME
firmware (`boards/m920x/blobs/`) and Intel's FSP, from coreboot's
`3rdparty/fsp`. They are published here by the owner of the machines they
come from; their redistribution terms are those of Intel, Lenovo and
NVIDIA.

## License

The scripts, configurations and patches are GPL-2.0, like coreboot
([LICENSE](LICENSE)). The binary blobs keep their own licenses (see above).
The images also carry, built from source at the commits each release
names, MrChromebox's EDK2 (BSD-2-Clause-Patent), iPXE (GPL-2.0-or-later
for the build with the Intel driver) and CSMWrap (LGPL-2.1) with SeaBIOS
(LGPL-3.0). The setup and the update screen draw their text with Montserrat
(SIL Open Font License 1.1) and icons of Font Awesome Free (CC BY 4.0), as
LvglPkg has them.
