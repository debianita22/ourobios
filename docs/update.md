# Firmware updates with UEFI capsules

Each release also has a signed UEFI capsule per variant,
`w541-coreboot-vX.Y.Z-mrc.cap` and `-nri.cap`. A W541 that already runs
v1.3.9 or later installs it from Linux, without flashrom (v1.3.0-v1.3.8,
with the read-only part before v1.3.9, install the capsules of
v1.3.0-v1.3.8 only, and v1.2.x, with the flash map before vboot, those of
v1.2.x: see [The first time](#the-first-time)):

```sh
curl -LO https://raw.githubusercontent.com/debianita22/ourobios/main/tools/update.py
sudo python3 update.py status
sudo python3 update.py stage --latest
sudo systemctl reboot
```

At the next boot the firmware checks the capsule, writes it with a progress
bar under the logo (about a minute), and starts again on the new version.
From v1.3.0 it writes the RW slot that is not running, and vboot goes back
to the old one if the new one does not verify or does not boot
([docs/vboot.md](vboot.md)). From v1.3.4, with the project's remote set up
once, `fwupdmgr update`, GNOME Software and KDE Discover stage the capsule
in the same way ([The fwupd remote](#the-fwupd-remote)).

- [What changes and what stays](#what-changes-and-what-stays)
- [The first time](#the-first-time)
- [tools/update.py](#toolsupdatepy)
- [What happens at boot](#what-happens-at-boot)
- [From the setup, with a USB drive](#from-the-setup-with-a-usb-drive)
- [fwupd](#fwupd)
- [Versions, variants, downgrades](#versions-variants-downgrades)
- [Going back](#going-back)
- [Without tools/update.py](#without-toolsupdatepy)
- [If it goes wrong](#if-it-goes-wrong)
- [How it works](#how-it-works)
- [The signing key](#the-signing-key)

## What changes and what stays

A capsule carries the whole image of the release, 12 MiB on the W541 and
24 MiB on the M920x, but the firmware writes only the regions that the
manifest of the capsule names, `update.py info FILE.cap` lists them
([flash map](flashing.md), [of the M920x](m920x.md#flash-layout)):

| Region | |
|---|---|
| `RW_SECTION_A` or `RW_SECTION_B` | **written**, the slot that is not running: the new firmware |
| the other slot | kept: the firmware that runs now, where vboot goes back if the new one fails |
| `RW_MRC_CACHE` | W541 (and M920x up to v1.4.0-rc3): **erased**, the first boot trains the memory again, a few seconds longer. M920x from rc4: kept, the new slot trains again only if the cache was made with another FSP-M, processor or Hyper-Threading setting ([docs/m920x.md](m920x.md#updates)) |
| `RW_NVRAM` | a record appended: *try* the new slot, two tries |
| `WP_RO` | kept: bootblock, vboot's root key, `mrc.bin` (W541) |
| `SMMSTORE` | kept: settings, boot entries, Secure Boot keys, supervisor password |
| `RO_VPD` | kept: serial number, machine type, UUID |
| `RW_ELOG` | kept: event log |
| descriptor, GbE, ME | kept |

(Up to v1.2.x: `COREBOOT`, the whole 4 MiB chip, and `RW_MRC_CACHE`.) The
manifest of a W541 capsule is `RW_MRC_CACHE RW_SECTION_A RW_SECTION_B`,
that of an M920x one from rc4 `RW_SECTION_A RW_SECTION_B`.

So, unlike flashrom, a capsule needs no `tools/vpd.py copy` and resets no
setting. Blocks that are already identical are not written again.
*BIOS Lock* and *Firmware protection* can stay on: the firmware writes the
capsule itself, from SMM, and never `WP_RO`.

## The first time

The capsules of v1.3.9 and later need a firmware with the same flash map
and the same read-only part, v1.3.9 or later (the lowest version they
accept, `CONFIG_DRIVERS_EFI_MAIN_FW_LSV` of the defconfigs, is v1.3.9:
`update.py status` prints it). Install it once with flashrom: from
v1.0.3-v1.3.8 as in [docs/flashing.md](flashing.md#from-v13x-to-v139)
(settings, boot entries and VPD stay), from other firmware as in
[docs/flashing.md](flashing.md#internal-update) (VPD copied into the image
first, *BIOS Lock* off). From there on, every update can be a capsule.
`update.py status` tells whether the running firmware applies them
(*mappa*: *vboot*, or *senza vboot* for v1.2.x), and `stage` refuses a
capsule for the other map or for the other read-only part (v1.3.0-v1.3.8
have their own ESRT GUIDs, and install the capsules of those releases).

v1.2.0 to v1.2.2 apply the capsules of v1.2.x, which rewrite the whole
4 MiB chip, without A/B.

## tools/update.py

Python 3 and nothing else; it needs root, an EFI boot and the EFI system
partition (ESP) mounted (`/boot/efi`, `/efi`; elsewhere: `--esp DIR`).
Take the one of the release, or a later one: an `update.py` from before
v1.4.0-rc4 refuses the M920x capsules from rc4, which name two regions
(*la capsula scrive ..., attese ...*), and the notes of each release
download it from the commit of that release.

| Command | |
|---|---|
| `status` | running variant and version, the lowest version it accepts, the result of the last update, the capsule waiting for the next boot; also the state of the Intel ME (from the SMBIOS strings of the firmware: on the M920x from rc4, on the W541 from the first release with patch 0181) and of the flash protection: `WP_RO`, *BIOS Lock*, whether the slots can be written ([Flash protection](#flash-protection)) |
| `stage --latest` | downloads the newest release of the running variant from GitHub (`--pre`: the release candidates and other pre-releases too; the `nri` releases up to v1.3.8, published as pre-releases, count as releases), checks its `SHA256SUMS` |
| `stage FILE.cap` | a capsule already downloaded |
| `cancel` | removes the waiting capsule and the request |
| `info FILE.cap` | variant, version, regions and signer of a capsule (or of the fwupd package, `FILE.cab`) |
| `other-slot flash.bin FILE.rom` | an image to write with flashrom, two or three regions only: the slot of a release in the slot that is not running, vboot asked to try it, and an empty `RW_MRC_CACHE` where the capsule of that release empties it, or with `--retrain` ([A release from its image](#a-release-from-its-image-in-the-other-slot)) |
| `rollback FLASH.bin` | back to the release in the slot that is not running, the one before the last update: see [Going back](#going-back) |
| `vboot FLASH.bin` | from a copy of the flash (`sudo flashrom -p internal -r FLASH.bin`): the slot of the next boot and its tries, the slot of this boot and of the one before, and whether vboot found one broken ([docs/vboot.md](vboot.md)) |
| `vboot-work FILE` | what vboot decided at this boot, from its work buffer in CBMEM (`sudo cbmem -r 0x78007343 > FILE`; [docs/vboot.md](vboot.md)) |
| `vars FLASH.bin` | the UEFI variables in the `SMMSTORE` region of a copy of the flash: names, GUIDs, attributes and sizes, never the data (`--grep REGEX`, `--all` for the deleted ones too) |
| `protection` | the flash protection of this boot on the M920x and the W541, read from the registers of the SPI controller and never written: each Protected Range mapped onto the regions of the flash map, *BIOS Lock*, the locks, whether a capsule and flashrom can write ([Flash protection](#flash-protection)) |

`stage` checks what the firmware would check, so that a reboot is not
wasted: the variant (an `nri` capsule is refused on `mrc`), the version (not
below the lowest accepted one; the same or an older one only with
`--allow-older`), the regions, the AC adapter (`--on-battery` to skip), and,
with `openssl` installed and `keys/capsule-signing.pem` next to the script
(a clone of the repository) or `--cert`, the signature. Then it copies the
capsule to `\EFI\UpdateCapsule\w541-coreboot.cap` on the ESP and sets the
*capsule on disk* bit of the `OsIndications` UEFI variable. `--reboot`
restarts straight away.

Then restart or shut down, do not hibernate: at the next power-on the
firmware would apply the update, and the OS resume on the new firmware
from an image made on the old one, with its ACPI tables.

After the reboot, `update.py status` shows the new version and, under
*ultimo* (last), the result of the update. Releases before v1.3.0 (and
v1.3.0-rc1 and rc2) never put the result in the ESRT: there *ultimo* stays
*nessun aggiornamento con capsula*. Without root it prints only the
version: the ESRT, the ME and the flash protection need it.

### Flash protection

On the M920x and the W541, `sudo python3 update.py protection` tells what
can write the flash in this boot, from the registers of the SPI controller
(`00:1f.5` on the M920x; on the W541 the one of Lynx Point, below):
the Protected Ranges, mapped onto the regions of the flash map that this
boot used (CBMEM; `--flash FILE` takes the names from a copy of the flash
or a release), the *BIOS Lock* bits of `BIOS_CNTL`, the locks (FLOCKDN, the
PR locks), the access of the CPU to the regions of the descriptor, and the
two options of *Security* → *Flash protection* as saved in `SMMSTORE`,
which apply from the next boot or S3 resume. It only reads: PCI
configuration space, the registers of the controller and the flash as the
CPU maps it below 4 GiB (`/dev/mem`), without loading or unloading a
module; under the kernel lockdown of Secure Boot the registers are
refused, and it says so.
On ci-151, with both options off:

```text
BIOS_CNTL:   0x8b: BIOSWE 1, BLE 1, EISS 0, BILD 1
blocchi:     FLOCKDN 1, PR bloccati PR0, PR1, PR2, PR3, PR4 (DLOCK 0x00001f00), PRR34_LOCKDN 1, WRSDIS 1, descrittore attivo
PR, GPR0:    tutti vuoti
opzioni:     Firmware protection 0, BIOS Lock 0 (in SMMSTORE: valgono dal prossimo avvio o ripresa da S3)
WP_RO:       NON protetta (Firmware protection spenta, anche nel setup)
BIOS Lock:   spento: il sistema puo' scrivere il flash
capsula:     si': nessun PR sugli slot, RW_NVRAM e SMMSTORE
flashrom:    si' sugli slot (BIOS Lock spento, nessun PR)
```

With *Firmware protection* on, `WP_RO` (`0x1700000-0x17FFFFF`) must be in
a locked Protected Range with writes off: then flashrom cannot write the
BIOS region whole (turn the option off first), while capsules, and
`other-slot` with *BIOS Lock* off, which write the slots only, still
work. `--expect-ro on` (or `off`) makes it a check for scripts: exit 0
when `WP_RO` is as expected, 1 when not, 2 when it cannot tell (no
`WP_RO` in the map, registers that cannot be read, no root). The
Protected Ranges hold only for the CPU: the other masters of the flash
(ME, GbE) follow the descriptor, which the release images leave writable
by everyone. `status` prints the short form of the same: the `WP_RO:`,
`BIOS Lock:` and `slot RW:` lines.

On the W541 (from the `update.py` of v1.4.0-rc4) the controller is behind
the LPC bridge, `00:1f.0`: `protection` checks that its RCBA is enabled and
where Lynx Point puts it, then reads one 4 KiB page of `/dev/mem` at
RCBA+0x3000, with the registers of the SPI controller (FRAP, the flash
regions, PR0-PR4, FLOCKDN) and GCS and BUC (BILD, Top Swap), never the data
or opcode registers. *BIOS Lock* counts as on with SMM_BWP set, or with BLE
set and BIOSWE clear (setting BIOSWE then raises an SMI, which clears it
again). With *Firmware protection* on, PR0 should read `0x8bff0b60`:
`0xb60000-0xbfffff`, `WP_RO`, protected until the next reset or S3 resume,
where coreboot sets it again. Many distribution kernels are built with
`IO_STRICT_DEVMEM`, and the page is also held by `intel-spi` and `iTCO_wdt`:
the registers are then refused, and `protection` says why, still shows *BIOS
Lock* (from PCI configuration space) and the saved options (from the BIOS
window of the flash), and exits 2 with `--expect-ro`; for this one check,
boot once with `iomem=relaxed`, then drop it. None of it has run on a W541
yet: the values are what the code predicts.

## What happens at boot

With the bit set, coreboot gives the payload write access to the whole flash
for that boot only, and the payload, before anything else runs:

1. clears the bit, so that the next boot is a normal one whatever happens;
2. on battery, waits up to a minute for the AC adapter or for a charge of at
   least 25%, otherwise postpones the update (the capsule stays on the ESP:
   `update.py stage` again to retry);
3. reads and deletes the files in `\EFI\UpdateCapsule` of every EFI system
   partition and USB drive;
4. verifies each capsule: signature, variant, version, flash layout;
5. finds the slot that is running in `RW_NVRAM`, writes the other one and
   asks vboot to try it at the next boot;
6. shows the result and restarts after a three-second countdown.

From v1.3.6 the update has a screen of its own (patch `edk2/0026`; the
firmware that is running draws it, so an update made from v1.3.6-rc3 or
older still shows the bar): the ouroboros of the logo is the progress,
lighting up from its head around to its tail, and the bar under it is a map
of the region being written, one column per 4 KiB block: blue rewritten,
green already as in the capsule (not written), grey still to do, white the
block being written. Around them the versions and the slots (*v1.3.6-rc3 ·
slot B › v1.3.6 · slot A*), what is being done (looking for the capsule,
checking its signature, clearing the memory training data when the capsule
names it, writing the slot, asking vboot to try it), the percentage, how
much was rewritten and how much was already there, the time left, and at
the bottom *Do not turn off the laptop or unplug the AC adapter*. At the
end the snake winks and the screen
says what happens if the new slot does not start; after a failure it shows
where (the block, in red on the map) and that the slot in use was not
touched.

The next boot runs the new slot; when it reaches the boot logo, the payload
tells vboot that it works. If it does not verify, or two boots in a row do
not get that far, vboot boots the old slot: `update.py status` then shows
the old version.

A capsule that fails a check writes nothing: the laptop restarts on the old
firmware, and `update.py status` shows why (*firma non valida*: signature,
*versione non accettata*: version, *immagine non valida*: no region
manifest or the wrong size, *mappa del flash diversa*: a capsule for
another flash layout). If there is no capsule to apply, the firmware gives
the write access back and boots on.

## From the setup, with a USB drive

From v1.2.2, without an OS: *System Preferences* (Esc at power-on) →
*System Configuration* → *Firmware Update* (from v1.3.10 also *General* →
*Firmware Update*) shows the installed version, the
lowest version a capsule may have, and the result of the last update
(version and *successful*, or why it was refused).

1. Copy the `.cap` of the release into the folder `EFI/UpdateCapsule` of a
   USB drive formatted FAT (FAT32), and nothing else in that folder.
2. Connect the drive and the AC adapter, open *Firmware Update* and choose
   *Update from a USB drive*.
3. The setup checks the file (a capsule of the variant that runs, not older
   than the lowest accepted version, the only file in `EFI\UpdateCapsule` of
   the USB drives and of the ESP) and asks to confirm, with the two
   versions. *Yes* restarts: the firmware applies the capsule as in
   [What happens at boot](#what-happens-at-boot), signature check included,
   deletes the file from the drive and starts again on the new version.

If the setup refuses (*No update found*, *not an update for this firmware*,
*older than the oldest accepted update*, *N files*), nothing is changed.

## fwupd

From v1.2.2 each release also has `w541-coreboot-vX.Y.Z-mrc.cab` (and
`-nri.cab`): the same capsule as an fwupd package, with its metadata (the
ESRT GUID of the variant, the version in fwupd's *quad* format) and a
`firmware.jcat` that signs both with the capsule key. fwupd checks the
variant, the version and the AC adapter, copies the capsule unchanged to
`\EFI\UpdateCapsule\fwupd-<GUID>.cap` and sets the same `OsIndications`
bit as `tools/update.py`: the firmware applies it in the same way, and after
the reboot `fwupdmgr get-devices` shows the new version and `fwupdmgr
get-history` the result. The project certificate must be in `/etc/pki/fwupd`
first, once:

```sh
sudo install -m 644 keys/capsule-signing.pem /etc/pki/fwupd/ourobios.pem
sudo systemctl restart fwupd
sudo fwupdmgr install --allow-reinstall w541-coreboot-vX.Y.Z-mrc.cab
```

Without it fwupd does not trust the metadata of the package, so it does not
take the version format from it, and the install stops at *Firmware version
formats were different, device was 'number' and release is 'quad'*
(before any signature message: the ESRT gives fwupd a bare number, the
package says how to read it). The same certificate serves the remote below.

### The fwupd remote

From v1.3.4 the mrc release also has `ourobios.xml.gz`, the metadata of the
project's fwupd remote: the `.cab` of both variants of that release, with
their address and checksums, signed by the capsule key
(`ourobios.xml.gz.jcat`). The remote,
[`configs/fwupd/ourobios.conf`](../configs/fwupd/ourobios.conf), downloads
it from the latest release, so that `fwupdmgr update`, GNOME Software and
KDE Discover offer each new release to the variant that runs. Once, from a
clone of the repository:

```sh
sudo install -m 644 configs/fwupd/ourobios.conf /etc/fwupd/remotes.d/
sudo install -m 644 keys/capsule-signing.pem /etc/pki/fwupd/ourobios.pem
sudo systemctl restart fwupd
fwupdmgr refresh
```

Then, at each release:

```sh
fwupdmgr get-updates                       # ouroBIOS (mrc) System Update, New version: ...
fwupdmgr update
sudo systemctl reboot
```

fwupd loads the metadata only with a signature from a trusted certificate,
downloads the `.cab` from the release, checks its SHA-256 against the
metadata and installs it only if its own `firmware.jcat` is from a trusted
certificate too: the one in `/etc/pki/fwupd` serves both (fwupd puts the
certificates of `/etc/pki/fwupd` and `/etc/pki/fwupd-metadata` in one
trust store, verified with 2.0.20: either directory alone works).
`fwupd-refresh.timer`, GNOME Software and Discover refresh the metadata
about once a day.

The release candidates are not in that remote: `releases/latest` is the
latest release that is not a pre-release. They are in the *testing* remote,
[`configs/fwupd/ourobios-testing.conf`](../configs/fwupd/ourobios-testing.conf):
the same metadata, from the assets of the fixed
[`testing`](https://github.com/debianita22/ourobios/releases/tag/testing)
entry of the releases page, which every release replaces with its own
when it is the highest so far, candidates included (v1.3.7-rc1 after
v1.3.6; v1.3.6-rc3 not after v1.3.6). It is off until turned on, next to
the other, with the same certificate:

```sh
sudo install -m 644 configs/fwupd/ourobios-testing.conf /etc/fwupd/remotes.d/
sudo fwupdmgr enable-remote ourobios-testing     # fwupdmgr disable-remote to stop
fwupdmgr get-updates
```

With both on, a release is one package to fwupd (same `.cab`, same
checksums), and each candidate, with its own version
([Versions, variants, downgrades](#versions-variants-downgrades)), comes
from the testing remote alone. (Up to v1.3.6, the first release with the
four-byte version, the two remotes described the version in different
formats, and whoever followed the candidates kept the other remote off.)

- The project remote offers releases; the candidates come from the testing
  remote, `update.py stage` or their `.cab` by hand. From v1.3.6 each
  candidate has a version of its own, below its release (v1.3.7-rc2 is
  1.3.6.2, v1.3.7 is 1.3.7.0), so from a candidate `fwupdmgr update` offers
  the release. A candidate up to v1.3.6-rc1 had the version of its release
  (v1.3.5-rc2 and v1.3.5 are both 1.3.5): from one of those `fwupdmgr
  update` waits for a later release, and `fwupdmgr reinstall` installs the
  release now, as `update.py stage --latest` does.
- The metadata of a release has its nri too: a laptop that runs nri is
  offered nri, and an mrc one mrc.
- Without the certificate the refresh fails (*signatures were required,
  but none supplied*) and a `.cab` by hand stops at *Firmware version
  formats were different* (see above). Do not set `OnlyTrusted=false`
  instead.
- To remove it: delete the two files and restart fwupd.

Tested here with fwupd 2.0.20, its daemon on a simulated ESRT (v1.3.3) and
a copy of the release pages on a local server, with the redirect of
`releases/latest/download`: `fwupdmgr refresh`, `get-updates` (1.3.4, from
the metadata of v1.3.4-rc1 signed by a test key) and `update`, which
downloaded the `.cab` of the v1.3.4-rc1 release from GitHub and staged the
capsule with the `OsIndications` bit; then, with the metadata of
v1.3.4-rc2 as published, `refresh` and `reinstall` from the remote, the
capsule in the ESP identical to the `.cap` of the release. Refused: a
`.cab` with another checksum (*checksum invalid*), the metadata and the
package without the certificate.

### A package by hand

fwupd installs only packages signed by a certificate in `/etc/pki/fwupd`, so
trust the project certificate once:

```sh
sudo install -m 644 keys/capsule-signing.pem /etc/pki/fwupd/ourobios.pem
sudo systemctl restart fwupd
fwupdmgr get-devices                       # System Firmware, version 16908289 (= 1.2.1)
sudo fwupdmgr install w541-coreboot-v1.2.2-mrc.cab
sudo systemctl reboot
```

`--allow-older` and `--allow-reinstall` as in
[Versions, variants, downgrades](#versions-variants-downgrades). Tested
here with fwupd 2.0.20 on a simulated ESRT (the staging; the boot side is
the one of `tools/update.py`).

- Without the certificate fwupd refuses the package (*firmware signature
  missing or not trusted*, or *version formats were different*): do not set
  `OnlyTrusted=false` instead.
- A certificate in `/etc/pki/fwupd` is trusted for any device, not only for
  the firmware: whoever holds the project key could sign a package that fwupd
  would install on that computer for another device, and the remote could
  offer it, if the same person could also publish a release of the project.
  Remove the files when you no longer need them.
- The releases are not on LVFS: without the remote, download the `.cab` of
  the release.
- `tools/update.py info FILE.cab` checks a package: capsule, metadata,
  signatures; `tools/fwupd-cab.py check-metadata --cert
  keys/capsule-signing.pem ourobios.xml.gz` the metadata of the remote.

## Versions, variants, downgrades

The version in the capsule and in the firmware's ESRT entry is the release
number as four bytes, X.Y.Z.R (fwupd's *quad* format, from v1.3.6): a
release vX.Y.Z is X.Y.Z.0 (v1.3.7 is `0x01030700`, 1.3.7.0), and its
candidate N is the release before it with R = N (v1.3.7-rc2 is
`0x01030602`, 1.3.6.2; v1.4.0-rc1 is 1.3.255.1), so the candidates sort
after the release before and before the one they lead to, and fwupd offers
each rc, and then the release, as an update. The setup and `tools/update.py`
print the tag (v1.3.7-rc2); `fwupdmgr` the four numbers.
Up to v1.3.6-rc1 the number was X.Y.Z with Z in the low 16 bits and no
room for the candidate (v1.3.6-rc1 is `0x01030006`): read as quad that is
1.3.0.6, below every later number, so a W541 on one of those updates as
usual. The setup and `tools/update.py` still print those numbers by their
tag (`0x01030005` is v1.3.5; a candidate of then has the number of its
release), and `tools/update.py` still reads their `.cab` (*triplet*
format).

From v1.3.10-rc15 the UEFI system table carries the release too, as its
firmware revision (`tools/build.sh` gives it to EDK2 as
`PcdFirmwareRevision`; before, it was 0x00010000 for every release):
X << 24 | Y << 16 | Z << 8 | N for vX.Y.Z-rcN, N = 0 for vX.Y.Z
(v1.3.10-rc15 is `0x01030A0F`, v1.3.10 is `0x01030A00`), and 0 for a
build that is not a release. Unlike the number of the ESRT, a candidate
has the X.Y.Z of the release it leads to: it reads as the tag, but sorts
after that release. It is where an OS that does not see the SMBIOS of the
firmware can read the release: macOS through OpenCore, `ioreg -p
IODeviceTree -n efi -l | grep firmware-revision`, four bytes
little-endian (`<0f0a0301>` for rc15); also the `ver` command of a UEFI
shell. Linux has the release in the SMBIOS (`cat
/sys/class/dmi/id/bios_version`) and the number of the ESRT in
`/sys/firmware/efi/esrt/entries/entry0/fw_version`; the `efi: EFI v2.7
by ouroBIOS` line of its log is the revision of the UEFI specification,
not of the firmware.

The firmware refuses capsules older than its lowest supported version,
v1.3.9 from v1.3.9 on (v1.3.0 in v1.3.0-v1.3.8, v1.2.0 in v1.2.x): an older
release goes back with flashrom. Older capsules from that version up
install with `--allow-older`. The lowest supported version is at or above
v1.3.6 (`0x01030600`) or at most v1.3.0, never in between: there the two
layouts overlap (v1.3.5 was `0x01030005`, below v1.3.5 in the new one,
`0x01030500`), and `tools/ci-check.sh` refuses such a value.

`mrc` and `nri` are different firmware for the ESRT (each its own GUID):
a capsule installs only on its own variant. The ThinkCentre M920x
(`m920x-fsp`, from v1.4.0) is one more, with its own GUID: a W541 capsule
is refused there and the other way round, and the rest of this page applies
to it with its `m920x-coreboot-vX.Y.Z-fsp` files ([docs/m920x.md](m920x.md)). The GUIDs change whenever a
release needs something a capsule does not write: with the flash map in
v1.3.0, and with the read-only part in v1.3.9 (one cache-as-RAM layout for
both variants, [docs/flashing.md](flashing.md#from-v13x-to-v139)), so
fwupd and `update.py` do not offer a v1.3.0 package to a v1.2.x firmware,
nor a v1.3.9 one to v1.3.0-v1.3.8; both go in once with flashrom. To switch
variant, flash the other image with flashrom
([docs/flashing.md](flashing.md#internal-update)), or, from v1.3.9 behind
the `mrc` read-only part, try the other variant's slot
([A release from its image](#a-release-from-its-image-in-the-other-slot)).

## A release from its image, in the other slot

`update.py other-slot` prepares an image with the slot of a release, from
its `.rom`, `.cap` or `.cab`, in the slot that is not running, and a
record in `RW_NVRAM` that asks vboot to try that slot with two tries;
flashrom then writes those regions only (`--fmap` reads the map from the
image), with the read-only part, the settings, the VPD and the event log
untouched. The memory training goes as with the capsule of that release:
on the W541, and for the M920x releases before v1.4.0-rc4, the image has
an empty `RW_MRC_CACHE`, which flashrom writes too; on the M920x from rc4
the cache stays, and the slot trains again only if the cache does not fit
it. `--retrain` empties it anyway, for a slot that did not start with the
saved training. For a release the capsule path does not offer: an older
one, a local build, a CI build. *BIOS Lock* must be off (flashrom says
*BIOS region SMM protection is enabled* otherwise, and writes nothing;
`update.py` warns first); *Firmware protection* can stay on, it covers the
read-only part only.

```sh
sudo modprobe -r spi_intel_platform spi_intel              # M920x: spi_intel_pci spi_intel
sudo flashrom -p internal -r flash.bin
python3 tools/update.py other-slot flash.bin w541-coreboot-v1.3.8-mrc.rom
sudo flashrom -p internal --fmap -i RW_SECTION_B -i RW_MRC_CACHE -i RW_NVRAM -w other-slot.rom
sudo systemctl reboot
```

`other-slot` prints the flashrom command of the case: on the M920x from
rc4 it is `--fmap -i RW_SECTION_B -i RW_NVRAM` (and `-i RW_MRC_CACHE`
after `--retrain`), with the slot letter of the case. Reboot right after
flashrom, without suspending: `RW_NVRAM` already asks for the other slot,
and a resume from S3 goes through vboot.

As after a capsule, if the slot does not reach the payload twice in a row
(power off and on at each hang), vboot goes back to the slot that ran.

It refuses a slot that cannot start behind the read-only part on the
laptop, and for a reason, not a policy: the read-only part leaves vboot's
data, the early console and the caches for romstage at the cache-as-RAM
addresses of its build (`configs/ro-interface.txt`), and a slot that looks
for them elsewhere dies before its first POST code (tried on a W541: an
`nri` slot behind the `mrc` read-only part of v1.3.0, last POST `0x21`,
then vboot's fallback). Up to v1.3.8 each variant's read-only part has its
own layout, so only the same variant; from v1.3.9 the layout is one for
both ([docs/vboot.md](vboot.md#the-read-only-part-of-v139)), but another
than before, so only releases from v1.3.9, and the other variant only
behind the `mrc` read-only part, the one that holds `mrc.bin`. `--force`
writes it anyway.

## Going back

After an update the slot that is not running still holds the release
before it, until the next update writes over it. `update.py rollback`
goes back to that release:

```sh
sudo modprobe -r spi_intel_platform spi_intel
sudo flashrom -p internal -r flash.bin
sudo python3 update.py rollback --dry-run flash.bin
sudo python3 update.py rollback flash.bin
sudo systemctl reboot
```

From the copy of the flash, taken in the boot that runs it, it finds the
slot this boot came from in `RW_NVRAM` and the release in the other one,
downloads the capsule of that release from GitHub (`--capsule FILE` for
one already downloaded), checks that it carries the same release for that
slot, and stages it with the same checks as `stage`. The firmware applies
it as any capsule: it finds the slot already written, so it writes
nothing there, clears `RW_MRC_CACHE` if the capsule names it (a W541 one,
an M920x one before v1.4.0-rc4) and asks vboot to try that slot, with two
tries; if it does not boot, vboot comes back to the slot of
now. `--dry-run` stops before staging and says how many 4 KiB blocks of
the slot differ from the release (none, normally).

It refuses when the other slot holds the same release, a newer one (vboot
already came back from it: `stage` tries it again), the other variant
(flashrom), or no whole release (empty, damaged or half written), and
when the copy of the flash is not of the running boot. Going back further
than the other slot works as before: `stage --allow-older FILE.cap`, which
writes the older release into the slot that is not running.

### From the setup

From v1.3.4, without an OS: *System Preferences* (Esc at power-on) →
*System Configuration* → *Firmware Update* shows the slot that runs and the
release in the other one (*Other slot*). *Go back to* that release asks to
confirm, then restarts into it as `update.py rollback` does: vboot tries the
slot at the next two boots and comes back to the slot of now if it does not
boot. On the W541 only `RW_MRC_CACHE` is cleared, so the first boot
trains the memory again, a few seconds with a dark screen; on the M920x,
when the slot that runs is v1.4.0-rc4 or later, nothing is cleared (patch
0179), and the other slot trains again only if the saved training does
not fit it, up to a minute with a dark screen. Do not turn the computer
off during that first start: vboot counts it as a failed try. Settings,
boot entries and Secure Boot keys stay.

The setup checks what a capsule would: it refuses an empty or damaged slot,
the release that runs, the other variant and a release older than the
oldest accepted update; vboot checks the signature at the next boot. With a
newer release in the other slot (after going back), the entry reads *Switch
to* that release.

Only the setup can do it: the firmware refuses the switch once it starts a
boot option (an OS loader, the UEFI Shell), after `ExitBootServices()` and
after a resume from suspend, so an OS goes back only with a signed capsule
and its checks. What runs before the boot options, a `Driver####` or
`SysPrep####` option or the option ROM of a device, can still ask for it
(with Secure Boot it must be signed), but from v1.3.4 coreboot checks the
release of the other slot itself, as the setup does: the same variant, not
older than the lowest supported version of the running release (patch
0065). Without *BIOS Lock*, flashrom from the OS can rewrite the vboot data
anyway.

## Without tools/update.py

Any tool that delivers capsules on disk works the same way:

- fwupd: its remote or the `.cab` of the release, see [fwupd](#fwupd). For v1.2.0 and
  v1.2.1, which have no `.cab`, `sudo fwupdtool install-blob
  w541-coreboot-vX.Y.Z-mrc.cap` with the *System Firmware* device should
  stage the capsule the same way (not tested).
- By hand: copy the capsule into `EFI/UpdateCapsule/` on the ESP and set bit
  2 (`0x4`) of `OsIndications-8be4df61-93ca-11d2-aa0d-00e098032b8c` in
  efivarfs, keeping the other bits (4 bytes of attributes `07 00 00 00`, then
  the 8-byte value, in one write; `chattr -i` first if the file is
  immutable).

## If it goes wrong

- *Battery too low, firmware update postponed*: connect the AC adapter, then
  `sudo python3 update.py stage FILE.cap` (or `--latest`) and reboot again.
- *Firmware update failed (Security Violation)*: the capsule is not signed by
  the key of the project. *(Aborted)*: version below the lowest supported, a
  capsule without the region manifest, or one for another flash layout.
  *(Not Ready)*: a capsule for the other variant.
- *Firmware update requested, but the flash is not writable in this boot*:
  the request was set in a way coreboot did not see (for instance an
  `OsIndications` variable left half-written by a crash); the laptop boots
  on, stage the capsule again.
- *No firmware update found*: the bit was set but there was no file on an
  ESP; the laptop boots on.
- Power lost while writing: from v1.3.0 the slot being written does not
  verify, and vboot boots the old one; stage the capsule again. Up to
  v1.2.x the 4 MiB chip may be incomplete and the laptop may not start:
  recover it with an external programmer and the `-4mb-chip.rom` of a
  release, as in [docs/flashing.md](flashing.md#recovery).
- The new version does not show up after the update: vboot went back to the
  old slot (the new one did not verify, or did not boot twice). *ultimo*
  still shows the update as done: it is the result of writing the slot, not
  of booting it; `update.py status` adds a *nota* when the version that runs
  is not the one of the last capsule.
  `update.py vboot` on a copy of the flash shows which release is in each
  slot; a copy taken in the first boot after going back also shows
  *precedente: slot X, fallito* when the new slot did not verify (the next
  boot overwrites it). `cbmem -c` of that boot (*try_count used up; falling
  back*) tells the case of the two tries.

- On the M920x from v1.4.0-rc4, where the training stays: a new slot that
  does not start twice in a row with the saved one sends vboot back to
  the old slot like any other failure. Write it once more with the cache
  emptied, `update.py other-slot --retrain` with the image of the release
  ([A release from its image](#a-release-from-its-image-in-the-other-slot)),
  so that it trains; then the next updates keep the new training.

The event log (`tools/elog.py`, `elogtool`) shows the reboots of an update.

## How it works

- coreboot (`DRIVERS_EFI_FW_INFO`) tells the payload the GUID and the version
  of the firmware, which the EDK2 payload publishes in the ESRT through
  FmpDxe, as the system firmware (`fw_type` 1, patch `edk2/0011`); Linux
  shows it in `/sys/firmware/efi/esrt`. The ESRT is built again at every
  boot (EsrtFmpDxe, patch `edk2/0018`), with the version and the result of
  the last capsule (`last_attempt_version`, `last_attempt_status`), which
  FmpDxe keeps in its `FmpState` variable, under its own FILE_GUID. From
  v1.3.10-rc18 that FILE_GUID is one fixed GUID for both variants
  (`EDK2_CAPSULE_MAIN_FW_GUID` of the defconfigs, patch 0135: the payload
  no longer depends on the variant, which the ESRT takes from the coreboot
  table, patch `edk2/0033`); until rc17 it was the GUID of the variant, so
  the first boot of rc18 shows no last attempt, until the next capsule.
- `OsIndicationsSupported` announces capsules on disk. When `OsIndications`
  asks for them, coreboot (`DRIVERS_EFI_CAPSULE_ON_DISK_SUPPORT`) switches
  its SMMSTORE handler to the whole flash for that boot only.
- The payload (patches `edk2/0008-0013`) applies the capsules on disk before
  EndOfDxe, the point after which FmpDxe refuses to write: the payload has no
  PEI phase that could load them on a later boot. FmpDxe checks the PKCS#7
  signature against the certificate built into the ROM
  (`keys/capsule-signing.pem`) and the version against the lowest supported
  one; `FmpDeviceSmmLib` writes the regions listed by the manifest appended
  to the image (`RW_MRC_CACHE RW_SECTION_A RW_SECTION_B`, `CAPSULE_REGIONS`
  in `tools/build.sh`, or `BOARD_CAPSULE_REGIONS` of the board:
  `RW_SECTION_A RW_SECTION_B` on the M920x from v1.4.0-rc4), through the
  SMMSTORE handler: of the two slots only the one that is not running,
  then a record in `RW_NVRAM` with *try next* and two tries (patch
  `edk2/0015`). An image without a manifest, or whose regions are not
  where the running firmware's flash map has them, is refused: upstream,
  such an image rewrites the whole BIOS region, settings and VPD included.
  The payload writes whatever regions a signed manifest names: the list is
  checked by the build and `update.py` (`info`, `stage`), not by the
  payload, so fwupd and the setup trust the signature alone
  ([docs/roadmap.md](roadmap.md)).
- After writing, the payload restarts. Without anything to write, it gives
  the whole-flash access back to coreboot (patch 0050) before Driver####
  options, option ROMs or the OS run, or restarts if that fails. It asks the
  SMMSTORE handler whether the flash is writable rather than trusting
  `OsIndications`, so that a variable store crafted to look different to
  coreboot and to the payload cannot leave it writable for the OS. coreboot
  also closes the decision on S3 resume (patch 0052): upstream, the SMM
  handler is reloaded on resume with the decision pending, the payload
  never runs, and the OS could take it and write the flash past the BIOS
  lock.
- Capsules in memory (`UpdateCapsule()` at runtime, then a warm reset) go
  through the same checks; with `Clear memory at power-on`, coreboot keeps
  them out of the clearing (patch 0048). Whether the memory survives the
  reset with `mrc.bin` or the native RAM init is untested: capsules on disk
  are the supported way.

## The signing key

The ROMs trust one certificate, `keys/capsule-signing.pem`: an RSA-3072
self-signed certificate made by `tools/capsule-key.sh`. Its private key is
the GitHub Actions secret `CAPSULE_SIGNING_KEY` of the repository, the only
place `tools/build.sh` reads it from; a release `vX.Y.Z` does not build
without it, and the build checks that the key matches the certificate, that
the payload trusts the certificate, and the capsule it signed
(`tools/update.py info`). Keep an offline copy of the key: without it, the
next release has to be flashed with flashrom.

To change key (see `keys/README.md`): make a new pair with
`tools/capsule-key.sh`, put the certificate in `keys/` and the key in the
secret, and release. That release is signed with the new key, so the
firmware in the field, which trusts the old one, refuses it: install it once
with flashrom. Or, to stay with capsules, sign one transition release with
the old key and the new certificate inside. fwupd needs the new certificate
too, in `/etc/pki/fwupd`: until then its remote refuses the metadata of the
releases signed with the new key.
