# edk2/: the project's package for EDK II

`OuroBiosPkg` is the payload of ouroBIOS as a package built against
upstream TianoCore EDK II, the payload of the ROMs from v1.6.0
([docs/edk2-migration.md](../docs/edk2-migration.md#steps-b-and-c-the-package-and-the-carried-patches)):
with [`patches/tianocore`](../patches/README.md#tianocore-edk-ii-for-the-package)
on the tree of `EDK2_UPSTREAM_TAG` (`tools/build.sh`) and LvglPkg next to
it, it has the same sources, file for file, as MrChromebox's EDK II at
`EDK2_MRCHROMEBOX_COMMIT` with `patches/edk2`, the payload up to v1.5.0.

| File | What it is |
|---|---|
| `OuroBiosPkg.dec` | the package; its modules keep the GUIDs, PCDs and library classes of `UefiPayloadPkg.dec`, which `patches/tianocore` extends as MrChromebox's tree does |
| `OuroBiosPkg.dsc.patch` | the platform: `UefiPayloadPkg.dsc` of MrChromebox's tree with the project's patches, its own name and GUID, the modules of the package under `OuroBiosPkg/`, as a patch on `UefiPayloadPkg.dsc` of the TianoCore tree |
| `OuroBiosPkg.fdf.patch` | the flash device, the same way |
| `CfrSetupMenuDxe/`, `Library/CfrHelpersLib/` | the setup menu from coreboot's CFR options (MrChromebox's, with `edk2/0002`, `0003` and `0028`) |
| `BootSplashConfigDxe/`, `Library/BootSplashLib/` | the boot splash and its setting |
| `UserAuthPkg/` | the supervisor password of the setup (`edk2/0006`) |
| `EnrollDefaultKeys/` | the default Secure Boot keys at the first boot: Microsoft's *Windows OEM Devices PK*, the two KEKs, the five db certificates and Microsoft's dbx; `keys/` with the files and `UpdateMicrosoftDbx.py`, which refreshes the dbx |
| `FirmwareUpdateDxe/`, `Library/UpdateScreenLib/` | the *Firmware Update* page of the setup (`edk2/0013`, `0020`, `0038`) and the screen of a capsule update (`edk2/0026`); `UpdateScreenFont.c` is made by `tools/ui-font.py` from LvglPkg's fonts when the package is staged |
| `MorControlDxe/`, `MorLockSmmStoreDxe/` | TCG MOR and its lock in SMM (`edk2/0040`, `0043`) |
| `Library/Tcg*PhysicalPresence*/` | the physical presence libraries of the TPM 1.2 and 2.0 (MrChromebox's `c111515`) |
| `Library/CsmWrapSecureBootLib/` | CSMWrap refused while Secure Boot is on (`edk2/0025`) |
| `EcAcpiBatteryStatusDxe/`, `Library/CbfsLib/` | the battery on the front page, files read from coreboot's CBFS |
| `Library/PlatformBootManagerLib/` | the boot policy of the platform: consoles, boot options, the hotkeys, the splash, capsules on disk, iPXE and CSMWrap entries, the vboot slot calls. TianoCore's tag has the library, but nearly all of it is MrChromebox's commits and the project's patches, so the package carries it whole, as MrChromebox's tree with `patches/edk2` has it (`PACKAGE_MOVED` of `tools/edk2-import.py`), and the platform maps `PlatformBootManagerLib` to it |
| `Library/FmpDeviceSmmLib/` | the capsules written into the flash through SMMSTORE: the FMAP regions of the manifest, only those of `PcdFmpDeviceSmmAllowedRegions` (`edk2/0045`), one vboot slot at a time (`edk2/0015`), the firmware GUID of coreboot's table (`edk2/0033`), and its host unit tests (`UnitTest/`). Carried whole for the same reason as `PlatformBootManagerLib` (`PACKAGE_MOVED`) |
| `Test/` | `UefiPayloadPkgHostTest.dsc`, the platform of the host unit tests of `FmpDeviceSmmLib`: `tools/build.sh edk2-unit-test` builds and runs them, in `check.yml` and before the update test of `build.yml` |
| `PlatformGopPolicy/`, `SdMmcPciGliDxe/`, `SdhciNonPciDxe/`, `UfsPlatformDxe/` | MrChromebox's modules for hardware these boards do not have (built only with their switches, or not at all), to leave out later ([docs/edk2-migration.md](../docs/edk2-migration.md)) |
| `FSDrivers/` | file system drivers, binaries of MrChromebox's tree with their license files: ext4 of rEFInd 0.12.0 (GPL-2.0), exFAT and ext2 of EfiFs 1.10 (GPL-3.0, from GRUB), NTFS of ntfs-3g (GPL-2.0); the boards build with ext4 only (`EXTRA_FS_DRIVERS=FALSE`) |

`tools/edk2-import.py` makes all of it, and `patches/tianocore`, from
MrChromebox's tree: the commits of MrChromebox between the stable tag and
the commit of the defconfigs and the patches of `patches/edk2`, each
restricted to the files that TianoCore's tree has, go to
`patches/tianocore`; the directories of `UefiPayloadPkg` that TianoCore
does not have (but `Include/`, whose headers the modules take from
`UefiPayloadPkg.dec`), those of `PACKAGE_MOVED` and `FSDrivers` go to the
package, with their paths rewritten; MrChromebox's binary network drivers of Realtek and ASIX (only
with `NETWORK_PXE_BOOT`) stay out, iPXE and CSMWrap are where coreboot's
Makefile puts them (`UefiPayloadPkg/NetworkDrivers`, `UefiPayloadPkg/LegacyBoot`
of the edk2 tree). Before it writes, it checks that the tag with the new
series gives MrChromebox's tree with `patches/edk2` in every other file;
`--check` (in `edk2-upstream.yml`) checks the files of the repository the
same way. A change to the payload goes to `patches/edk2` and the import is
run again.

`tools/build.sh` stages the package in
`payloads/external/edk2/workspace/packages` of the coreboot tree
(`EDK2_PACKAGES_SUBDIR`): `OuroBiosPkg` with each `OuroBiosPkg.<ext>.patch`
applied to `UefiPayloadPkg.<ext>` of the TianoCore tree to make
`OuroBiosPkg.<ext>`, and LvglPkg at `LVGLPKG_COMMIT` with
`patches/lvglpkg` and LVGL at `LVGL_COMMIT` (v9.6, in place of the v9.5.0
of LvglPkg's submodule). coreboot builds it with `EDK2_PACKAGE_CONFIG`: a custom
repository, TianoCore at the tag, `CONFIG_EDK2_PLATFORM_DSC` and
`CONFIG_EDK2_PACKAGES_PATH` (patch 0216, a path relative to the coreboot
tree), with the options of MrChromebox's tree (patch 0217). A platform
kept as a patch says what it changes, and one that no longer applies to a
new stable tag stops the build there, where it has to be looked at again
(`tools/upstream.sh tianocore` says so every week).

The defconfigs of the boards have those lines (step (d)): the ROMs are
built from it. `tools/build.sh edk2-upstream` builds it into a q35 image
and runs the steps of `qemu-smoke.py --upstream` on it;
`tools/build.sh edk2-parity` builds the payload of the first variant of
each board from it and from MrChromebox's tree, which must be the same
byte for byte.

The files of `OuroBiosPkg` are CRLF where those of EDK II are
(`.gitattributes` keeps them as they are), and keep the licenses of the
files they come from: BSD-2-Clause-Patent, but the binaries of `FSDrivers`
(above).
