# Moving the payload to TianoCore EDK II

Up to v1.5.1 the payload was MrChromebox's EDK II, branch
`uefipayload_2608`, at `6c14abf865e0`: the stable tag `edk2-stable202608`
of TianoCore (`2970e5699ba6`, 2026-08-12) and 100 commits of MrChromebox on
top of it, then the 44 patches of [`patches/edk2`](../patches/edk2) and the
18 of [`patches/lvglpkg`](../patches/lvglpkg). From v1.6.0 it is the same
sources on the TianoCore tag ([step (d)](#step-d-the-boards-on-the-package)).
This page lists those 100
commits with what each becomes when the payload moves to TianoCore, in the
order of [the roadmap](roadmap.md#edk-ii-from-tianocore): (a) TianoCore as
it is in QEMU (`tools/build.sh edk2-upstream`); (b) the setup and the
other modules of the project in a package of its own, `OuroBiosPkg`, built
against the TianoCore tree; (c) the changes to TianoCore's own packages,
carried as patches or proposed upstream; (d) the pins on the stable tags.

What each commit becomes:

- **package**: new modules or settings of the payload, which go into
  `OuroBiosPkg` (its `.dsc` and `.fdf`, derived from those of
  `UefiPayloadPkg`) without touching TianoCore's packages;
- **carry**: a change to a TianoCore package that the project needs and
  upstream has no equivalent of: a patch of the series, with its reason;
- **upstream**: a fix that belongs in TianoCore: proposed there, carried
  until a stable tag has it;
- **drop**: hardware or features the W541 and the M920x do not have, or
  a pair that cancels out;
- **merged**: already in TianoCore's `master` after the tag (checked at
  `a89ea17`, 2026-11-02, 604 commits after it): it comes with the next
  stable tag.

These are first readings from the subjects and the files of each commit,
to be confirmed as each one is ported.

| | package | carry | upstream | drop | merged | total |
|---|---|---|---|---|---|---|
| Setup menu and the other screens of the firmware | 14 | 7 | 4 | 1 | 0 | 26 |
| Boot manager and boot options | 4 | 3 | 0 | 1 | 0 | 8 |
| Capsule updates and the ESRT | 6 | 1 | 1 | 0 | 0 | 8 |
| Secure Boot, TPM and crypto | 9 | 1 | 1 | 0 | 0 | 11 |
| Memory protection | 1 | 6 | 0 | 2 | 0 | 9 |
| Drivers for storage, USB, graphics and the console | 2 | 1 | 6 | 12 | 1 | 22 |
| Platform plumbing for coreboot | 4 | 4 | 5 | 2 | 1 | 16 |
| **all** | 40 | 23 | 17 | 18 | 2 | 100 |

## Step (a): `edk2-stable202608` in QEMU

`tools/build.sh edk2-upstream` (the workflow
[`edk2-upstream.yml`](../.github/workflows/edk2-upstream.yml)) builds the
payload of `edk2-stable202608` as it is into two q35 images with this
tree's coreboot, an SMMSTORE of 512 KiB as on the W541 and the W541's
TPM 1.2: one as coreboot's Makefile builds it for `EDK2_REPO_OFFICIAL`,
one with `-D SECURE_BOOT_ENABLE=TRUE`. `qemu-smoke.py --upstream` runs
each step on its own. The steps that fail for a gap below are
`EDK2_UPSTREAM_GAPS` in `tools/build.sh`, each with the text of its
failure: they do not fail the job; one that passes, or that fails for
another reason, does, and the list and this page are revised.

| Step | With `edk2-stable202608` | Why | What closes it |
|---|---|---|---|
| SMMSTORE | passes (`0ea5ae5`) | coreboot reaches the payload, the Shell writes a variable to SMMSTORE and rewrites it after a reboot, leaving one valid copy; FTW sets up its work space on the erased region | |
| runtime services | gap (`0ea5ae5`) | SmmStoreLib keeps the arguments of its SMM calls in runtime services data (`AllocatePages()` below 4 GiB) and gives SMM their physical address: macOS's boot.efi moves that memory after ExitBootServices(), SMM reads the old place and SetVariable() returns `EFI_DEVICE_ERROR`, as ouroBIOS did up to v1.3.10-rc15 | coreboot's patch 0134 (a page after the block of the com buffer), `edk2/0029` (the com buffer as runtime MMIO, the arguments in it after SetVirtualAddressMap()) and `edk2/0044` (there from the start, for the WSMT): carried, and proposed to coreboot and TianoCore together |
| TPM 1.2 | gap (`0ea5ae5`) | UefiPayloadPkg has no TCG driver: no `EFI_TCG_PROTOCOL`, and nothing of the payload is measured | MrChromebox's `c111515` and `5dc4840`, with `edk2/0019` and `0042` |
| authenticated variables | gap (`ced8b20`) | `SmmStoreFvbRuntimeDxe` formats an erased SMMSTORE with `gEfiVariableGuid`, also with `SECURE_BOOT_ENABLE`: the variable driver then works without authenticated variables, and Secure Boot has nowhere to keep PK, KEK, db and dbx | the line of `2686758` in `SmmStoreFvbRuntimeDxe.c`, to propose upstream: for example the authenticated GUID when the payload has `SECURE_BOOT_ENABLE` |
| authenticated store kept | passes (`574cb3b`) | the test turns the store that the payload formatted into one with `gEfiAuthenticatedVariableGuid` and no variables (`auth_convert`), the format that MrChromebox's payload, and so ouroBIOS's, gives an erased store since `2686758`: the upstream payload keeps it, its variable driver says it works with that format and setvar writes in it. A board's store in that format (`update.py vars` on a dump of the flash says which) is not lost to it | |
| Secure Boot on an authenticated store | passes (`574cb3b`) | with `SECURE_BOOT_ENABLE` and such a store, AuthVariableLib writes `CustomMode`, `certdb` and `VendorKeysNv`: of Secure Boot, upstream lacks the format of an erased store and the default keys | |

Three more things the runs show:

- the Shell of TianoCore waits 5 s for `startup.nsh`
  (`PcdShellDefaultDelay`) and reads a key each second; MrChromebox's
  `4373c47` takes the script out, and in the package the PCD at 0 takes
  out the wait;
- `AcpiPlatform.efi` does not start (`EFI_ABORTED`): it installs the ACPI
  tables of a firmware volume of the payload, which has none, since the
  tables are coreboot's. The same driver is in MrChromebox's branch;
- with `SECURE_BOOT_ENABLE` the DEBUG payload does not fit the 7 MiB FD of
  `UefiPayloadPkg.fdf`, which keeps the DXE volume unpacked: GenFv does
  not make `PLDFV` (`c8609ee`). `-D FD_SIZE=0x00C00000 -D NUM_BLOCKS=0xC00`
  on the build's command line wins over the `.fdf`'s `DEFINE`
  (`_GetMacroValue` in `GenFds/FdfParser.py`) and builds it (`ced8b20`),
  so MrChromebox's `214b236` and the project's `edk2/0024` become a
  setting of the package.

## Steps (b) and (c): the package and the carried patches

The payload of the ROMs is in CI on the TianoCore tag, with the same
sources: [`edk2/OuroBiosPkg`](../edk2/README.md), the package, and
[`patches/tianocore`](../patches/README.md#tianocore-edk-ii-for-the-package),
the patches carried on the tag, which `tools/edk2-import.py` makes from
MrChromebox's tree at the commit of the defconfigs:

- **The carried series**: each of the commits below and each patch of
  `patches/edk2`, in order, without the files that TianoCore's tree does
  not have: 79 commits of MrChromebox (21 have nothing else) and 31 of
  the project's 44 patches (13 change only the package or its platform).
  The tag with the series is MrChromebox's tree with `patches/edk2` in
  every file but those (`edk2-import.py` checks it before it writes, and
  `--check` in `edk2-upstream.yml` checks the files of the repository).
- **The package**: the directories of `UefiPayloadPkg` that TianoCore
  does not have (the setup and its CFR, the splash, the password, the
  default Secure Boot keys, the update screen, MOR, the TPM's physical
  presence libraries, and MrChromebox's modules for hardware these boards
  do not have), with `FSDrivers`; the platform, `UefiPayloadPkg.dsc` and
  `.fdf` of MrChromebox's tree with the project's patches and the paths
  of the package, as patches on TianoCore's. LvglPkg is a package of its
  own next to it, at the commit of MrChromebox's submodule with
  `patches/lvglpkg`; the binary network drivers of Realtek and ASIX
  (`0ec988f`, only with `NETWORK_PXE_BOOT`) stay out.
- **Build**: coreboot's `payloads/external/edk2/Makefile` with patch 0216
  (`EDK2_PLATFORM_DSC`, and `EDK2_PACKAGES_PATH`, relative to the
  coreboot tree) and 0217 (the options of MrChromebox's tree, the LVGL
  renderer among them, for a custom repository): `EDK2_PACKAGE_CONFIG` of
  `tools/build.sh`, a custom repository on TianoCore at the tag, the
  package's platform, Secure Boot. The package keeps the output
  directory and the FD name of `UefiPayloadPkg` (`Build/UefiPayloadPkgX64`,
  `UEFIPAYLOAD`), which the Makefile expects, and iPXE and CSMWrap where
  the Makefile copies them in the edk2 tree.
- **Tests**: `edk2-upstream` builds the package into its third q35 image,
  with the boards' options and the steps of `--upstream`, which the
  upstream tag fails for the gaps above: the package passes all six
  (`2f219ab`): the variables in SMMSTORE across a reboot, the runtime
  services moved as boot.efi moves them, `ResetSystem()` from the virtual
  pages included (`edk2/0031`, in the platform), the TPM 1.2 log replayed
  against the PCRs with the default keys measured in PCR 7, an erased
  store formatted as authenticated and AuthVariableLib's variables on it
  and on one already authenticated; `tools/build.sh edk2-parity`
  builds the payload of the first variant of each board from the package
  and from MrChromebox's tree, with the same options, and the two must
  be the same byte for byte (if not, `tools/fv-diff.py` says which
  modules differ and where).
- **A change to the payload** goes to `patches/edk2`, on MrChromebox's
  tree, and the import is run again (`tools/edk2-import.py`, then the
  `edk2-upstream` workflow): the two stay the same sources.
- **What stays**: the read-only part, the patches of coreboot outside
  `payloads/external/edk2`, the ACPI tables, the setup's options (CFR)
  and their names, the variable store and its format: nothing changes for
  OpenCore or the OSes.

## Step (d): the boards on the package

From v1.6.0 the defconfigs of every board have the lines of
`EDK2_PACKAGE_CONFIG` (`tools/build.sh`) in place of MrChromebox's commit:
a custom repository, TianoCore at `edk2-stable202608`, the package's
platform and packages path, Secure Boot. `tools/build.sh prepare` fetches
TianoCore at the tag with its submodules, applies `patches/tianocore` and
stages `OuroBiosPkg` and LvglPkg; the release notes, the layout file and
the bill of materials name the tag, the carried patches, the package and
the MrChromebox commit they come from (`EDK2_MRCHROMEBOX_COMMIT`).

- **The same payload**: `tools/build.sh edk2-parity` builds the first
  variant of each board from the package and, with the same defconfig but
  `EDK2_MRCHROMEBOX_COMMIT` in place of the package's lines, from
  MrChromebox's tree with `patches/edk2`, and stops if the two
  `UEFIPAYLOAD.fd` are not the same byte for byte; `edk2-upstream.yml`
  runs it with the import check.
- **What is watched**: `tools/upstream.sh edk2` says when MrChromebox's
  branch moves past `EDK2_MRCHROMEBOX_COMMIT` (to take his commits: the
  constant moved, `patches/edk2` rebased, the import again), `tianocore`
  when TianoCore has a newer stable tag (whether the series and the
  platform still apply), `dbx` reads the dbx of the package.
- **Going back**: the defconfigs with `CONFIG_EDK2_TAG_OR_REV` of
  MrChromebox in place of the package's lines build the payload of v1.5.1's
  base again (`tools/build.sh` follows the defconfigs).

What comes next, each with the payload's tests: the series shorter, commit
by commit, as the tables below say: the *package* ones out of TianoCore's
packages into `OuroBiosPkg` (a `PlatformBootManagerLib` of its own, for
one), the *upstream* ones proposed to TianoCore, the *drop* ones left out
(the drivers for hardware these boards do not have first); when a change
lives only in the package or the series, `patches/edk2` and the import
retire.

## Setup menu and the other screens of the firmware

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `0c433f7` | UefiPayloadPkg/MdeModulePkg: Add boot progress text support | carry |  |
| `83eb1e6` | MdeModulePkg/UiApp: Rework Frontpage layout and SMBIOS display | carry | UiApp: or a UiApp of the package's own |
| `8814b15` | MdeModulePkg: Rework Boot Menu and Boot Manager UI | carry | BootManagerUiLib, BootMaintenanceManagerUiLib |
| `b6b0b66` | MdeModulePkg/UefiPayloadPkg: Improve Device Manager presentation | carry | DeviceManagerUiLib |
| `565124c` | MdeModulePkg: Add Logo position PCD and BGRT support | upstream | logo position PCD, BGRT |
| `4844b23` | MdeModulePkg: Be more verbose about SecureBoot and the reason why the boot failed | upstream | why a boot was refused by Secure Boot |
| `fc55cf0` | UefiPayloadPkg: Implement CFR support | package | CfrSetupMenuDxe and the CFR parser: the setup menu of both boards |
| `b795f86` | MdeModulePkg/DisplayEngineDxe: Change the delimiter for ONE_OF | carry |  |
| `435706b` | UefiPayloadPkg/PlatformBootMgr: update progress message on menu entry | package | PlatformBootManagerLib of the package |
| `c3aa08f` | MdeModulePkg/UefiPayloadPkg: Add Time/Date Settings driver | package | a driver of its own, plus a hook in UiApp |
| `0c79020` | MdeModulePkg: Fix Frontpage banner layout | carry | as 83eb1e6 |
| `c9d88a0` | MdeModulePkg/UefiPayloadPkg: Add Frontpage battery status support | package | EcAcpiBatteryStatusDxe, plus a hook in UiApp |
| `b06ce7e` | UefiPayloadPkg: Add password protection for setup menu access | package | UserAuthPkg: the supervisor password |
| `9b3274a` | MdeModulePkg/SetupBrowserDxe: Sync ordered lists before action callback | upstream | a fix of SetupBrowserDxe |
| `1fb7d11` | UefiPayloadPkg/PlatformBootManager: Clear boot prompt on ENTER | package | as 435706b |
| `f168fd0` | MdeModulePkg/SecurityPkg: Use HII popup for setup dialogs | carry | the HII popups the graphical setup draws (also edk2/0006) |
| `1287861` | SecurityPkg/SecureBootConfigDxe: Overhaul Secure Boot setup UI | drop | the standard SecureBootConfigDxe pages instead, as the project's rules ask; or carry, if the LVGL renderer needs the new layout |
| `ad284e9` | MdeModulePkg/FileExplorerLib: Add "Up one level" navigation | upstream |  |
| `17671bf` | UefiPayloadPkg: Add LVGL display engine support | package | with LvglPkg: the *System Preferences* look |
| `dfb8d33` | UefiPayloadPkg: Add NVRAM-controlled bootsplash with Setup UI | package | BootSplashConfigDxe |
| `240f748` | UefiPayloadPkg/CfrSetupMenuDxe: Add support for LOCK_AT_BOOT CFR flag | package |  |
| `5764265` | UefiPayloadPkg/CfrSetupMenuDxe: grey out READONLY CFR options | package |  |
| `afe0e87` | UefiPayloadPkg: Copy custom bootsplash BMP to the ESP | package |  |
| `5d4fdf6` | UefiPayloadPkg/BootSplashConfigDxe: Document BMP format requirements | package |  |
| `b91131a` | UefiPayloadPkg/CfrSetupMenuDxe: Fix SubForm parsing | package |  |
| `1817a2b` | UefiPayloadPkg: Unregister the setup hotkey before clearing the prompt | package | as 435706b |

## Boot manager and boot options

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `d8205d0` | MdeModulePkg/UefiPayloadPkg: Add PrioritizeInternal boot device support | carry | PRIORITIZE_INTERNAL |
| `4a4c3a1` | MdeModulePkg: Improve boot descriptions and skip duplicate eMMC | carry |  |
| `4373c47` | ShellPkg: disable startup script, mapping print; show welcome banner | package | the 5 s of the Shell for `startup.nsh`: `PcdShellDefaultDelay` 0 in the package's .dsc ([step (a)](#step-a-edk2-stable202608-in-qemu)); the mapping and the banner are cosmetic |
| `6676ad7` | UefiPayloadPkg/MdeModulePkg: Platform setup and boot defaults | package | PCD defaults of the package's .dsc |
| `0ec988f` | UefiPayloadPkg: Add network and PXE boot support | drop | the UEFI network stack: the boards boot from the network with iPXE's own driver |
| `9c5e2da` | PlatformBootManagerLib: Refactor BdsGetShellFvDevicePath | package |  |
| `b581d3b` | UefiPayloadPkg: Add iPXE network boot option support | package | the iPXE entry of the firmware volume |
| `6c14abf` | MdeModulePkg: Add Auto Boot Fall-Through option | carry | the setting next to *Auto Boot Time-out* (v1.4.1) |

## Capsule updates and the ESRT

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `d6fbc7b` | UefiPayloadPkg: Add FMP_DEVICE_PKCS7_PCD_INC define | package |  |
| `5a0c064` | UefiPayloadPkg/FmpDeviceSmmLib: Add FMAP-based scoped capsule flashing | package | FmpDeviceSmmLib; edk2/0008-0011 build on it |
| `04272be` | UefiPayloadPkg: Configure capsule update build options | package |  |
| `775376a` | UefiPayloadPkg: Add graphical capsule update progress | package | with edk2/0026, the update screen |
| `6e839af` | UefiPayloadPkg/FmpDeviceSmmLib: Harden scoped capsule flashing | package |  |
| `6c7b28d` | UefiPayloadPkg/Fmp: Keep capsule updates resilient through progress and reset | package |  |
| `cc69856` | MdeModulePkg/UefiPayloadPkg: Keep ESRT durable across hibernate and FMP sync | upstream | ESRT across hibernation |
| `a447cf5` | MdeModulePkg/UefiPayloadPkg: Harden capsule progress UI and update cleanup | carry | MdeModulePkg part of the progress UI |

## Secure Boot, TPM and crypto

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `2686758` | UefiPayloadPkg: Enroll Keys for SecureBoot | package | EnrollDefaultKeys; or SecureBootDefaultKeysDxe with a provisioning step of the package. Its line in SmmStoreFvbRuntimeDxe.c, an authenticated store, goes upstream ([step (a)](#step-a-edk2-stable202608-in-qemu)) |
| `c111515` | UefiPayloadPkg/SecurityPkg/OvmfPkg: Add TPM 1.2/2.0 support | carry | TPM 1.2 and 2.0 in UefiPayloadPkg; edk2/0019 and 0042 build on it; without it no TCG protocol ([step (a)](#step-a-edk2-stable202608-in-qemu)) |
| `db6619a` | UefiPayloadPkg: Use OvmfPkg PlatformSecureLib when Secure Boot enabled | package | a library mapping of the .dsc |
| `51d7f47` | SecureBoot: Update revocation DBX to version 20260402 | package | data |
| `a8b5b11` | UefiPayloadPkg/EnrollDefaultKeys: Provision default key reference variables | package |  |
| `77242a1` | UefiPayloadPkg: Add option to enable Secure Boot default after key enrollment | package |  |
| `5dc4840` | UefiPayloadPkg: Map Tpm2HelpLib for TPM-enabled builds | package |  |
| `af5e96c` | SecureBoot: update DBX to version 20260707 | package | data |
| `0d39245` | CryptoPkg/BaseCryptLib: Ignore foreign buffers in runtime free/realloc | upstream | CryptoPkg at runtime |
| `acc37b2` | UefiPayloadPkg/EnrollDefaultKeys: Add Microsoft DBX baseline artifacts | package | the dbx files (upstream.sh dbx compares them) |
| `f7cbaab` | UefiPayloadPkg: Append DBX updates to the retained baseline | package |  |

## Memory protection

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `45aec95` | UefiPayloadPkg: align DXE images for page protections | package | .dsc |
| `bf10b5c` | UefiCpuPkg: Gate AP exception stacks on PcdCpuStackGuard | drop | reverted by 4258973 |
| `4258973` | Revert "UefiCpuPkg: Gate AP exception stacks on PcdCpuStackGuard" | drop | reverts bf10b5c |
| `abbfa17` | MdePkg: Add PE/COFF NX_COMPAT Flag | carry | the six together, or none |
| `3321e5a` | MdeModulePkg: Split DisableNullDetectionAtTheEndOfDxe Into Two | carry |  |
| `8b0cd75` | MdeModulePkg: Add Compatibility Mode Functionality | carry |  |
| `d124d93` | MdeModulePkg: DXE: Adjust Setting Memory Protections With Compat Mode | carry |  |
| `3b1c619` | MdeModulePkg: Enter Compat Mode When non-NX_COMPAT App Loaded | carry |  |
| `9c0cb3a` | MdeModulePkg: Add Compat Mode Allowed PCD | carry |  |

## Drivers for storage, USB, graphics and the console

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `6128cce` | UefiPayloadPkg/GraphicsOutputDxe: Allow for framebuffer at an offset from BAR | upstream |  |
| `564cb49` | BaseSerialPortLib16550: Avoid reinitializing serial port or setting attributes | carry |  |
| `e32b60d` | UefiPayloadPkg: Add and use EXT2/EXT4, exFAT, NTFS filesystem drivers | package | ext4 only (the boards build with EXTRA_FS_DRIVERS=FALSE) |
| `a091558` | MdeModulePkg/SdMmcPciHcDxe: add Bayhub support | drop | no such controller |
| `4c76525` | MdeModulePkg/Usb/Keyboard.c: remove Get/SetConfig calls | upstream | USB keyboards that fail the requests |
| `076933b` | UefiPayloadPkg: Add and use PlatformGopPolicy | drop | no GOP driver: libgfxinit sets the mode |
| `88b95ba` | UefiPayloadPkg: Add AmdPcoSdhciDxe driver for AMD Picasso eMMC | drop | reverted by 6aa87d0 |
| `42865d9` | MdeModulePkg: Improve USB error handling for faulting devices | upstream |  |
| `9174049` | UefiPayload: Add new SdMmcPciGli driver | drop | no such controller |
| `b26a387` | UefiPayloadPkg/UfsPlatformDxe: Add new UFS platform driver | drop | UFS_ENABLE=FALSE |
| `b8d0242` | MdeModulePkg: UFS pass-through fix and boot enumeration filter | drop | UFS |
| `a79398a` | PcRtcEntry: Don't assert if RTC init fails | upstream |  |
| `dde0798` | FatPkg: Fix FAT32 mount on small 4K-sector ESP partitions | upstream |  |
| `97a12e8` | MdeModulePkg/ScsiDiskDxe: Don't fail media detection on FUA query error | merged | in master after the tag |
| `6aa87d0` | Revert "UefiPayloadPkg: Add AmdPcoSdhciDxe driver for AMD Picasso eMMC" | drop | reverts 88b95ba |
| `5342f42` | UefiPayloadPkg: Add SdhciNonPciDxe for non-PCI SDHCI | drop | no such controller |
| `acf9505` | MdeModulePkg/Usb: Warm reset downstream SuperSpeed ports | upstream |  |
| `d7597bb` | MdeModulePkg/SdMmcPciHcDxe: add HS400 Enhanced Strobe for Intel eMMC | drop | no eMMC |
| `c205ceb` | MdeModulePkg/SdMmcPciHcDxe: Don't force EmbeddedSlot for Bayhub | drop | no such controller |
| `81c562f` | UefiPayloadPkg: Add CbfsLib to read files from coreboot's CBFS | package | if a module of the package reads CBFS |
| `1f9ab46` | UefiPayloadPkg/PlatformGopPolicy: Load GOP driver and VBT from CBFS | drop | as 076933b |
| `a3657a3` | UefiPayloadPkg: Conditionally use GraphicsDriverDxe in apriori dxe | drop | as 076933b |

## Platform plumbing for coreboot

| Commit | Subject | Becomes | Note |
|---|---|---|---|
| `214b236` | UefiPayloadPkg: Increase FD size | package | .fdf; or `-D FD_SIZE` and `NUM_BLOCKS` of the build, which win over the .fdf ([step (a)](#step-a-edk2-stable202608-in-qemu)) |
| `6cf55e1` | UefiCpuPkg: Disable MTRR programming for UefiPayloadPkg | drop | if step (a) shows that upstream's MtrrLib leaves coreboot's MTRRs alone, as coreboot's Kconfig help says of c4fdec0a83d6 |
| `96303b7` | MdeModulePkg: Don't remove rejected PCI devices | carry |  |
| `7f7b9c7` | UefiPayloadPkg: drop Platform override config | package |  |
| `9701a6f` | MdeModulePkg/FaultTolerantWrite: Don't check for block alignment | carry | SMMSTORE blocks; in [step (a)](#step-a-edk2-stable202608-in-qemu) FTW sets up its work space on the 512 KiB SMMSTORE without it, a fault tolerant write (a reclaim of the store) is still to be seen |
| `2deb904` | UefiPayloadPkg: Check more ACPI tables | carry |  |
| `0a270f8` | UefiPayloadPkg/Library/PciHostBridgeLib: Add warning for coreboot/EDK2 incompability | drop | a warning only |
| `4b57ca5` | UefiPayloadPkg: Set PcdCpuFeaturesInitOnS3Resume to FALSE for coreboot | package | a PCD of the .dsc |
| `252f6d2` | UefiPayloadPkg: Extend SmmStoreLib for 64-bit MMIO store | upstream | SmmStoreLib |
| `1c39058` | UefiPayloadPkg/Library/CbParseLib: Populate root bridges info from HOB | upstream | CbParseLib |
| `c981e5d` | UefiPayloadEntry: Fix use of uninitialized memory | merged | in master after the tag |
| `40a1b7a` | UefiPayloadPkg/PciPlatformDxe: Fix BAR restore leak and uninit CodeType | upstream |  |
| `e27ef54` | UefiPayloadPkg/ResetSystemLib: Select S5 sleep type from CPUID | upstream | ResetSystemLib |
| `0453b7a` | UefiPayloadPkg/ResetSystemLib: Use full CF9 sequence for cold reset | upstream | ResetSystemLib |
| `b061f7a` | MdeModulePkg: Use warm reset for setup-initiated resets | carry |  |
| `94a2365` | UefiPayloadPkg: Pass coreboot boot media params to DXE | package | boot media parameters for the capsule code |
