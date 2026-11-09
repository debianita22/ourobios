# Moving the payload to TianoCore EDK II

Up to v1.5.0 the payload was MrChromebox's EDK II, branch
`uefipayload_2608`, at `6c14abf865e0`: the stable tag `edk2-stable202608`
of TianoCore (`2970e5699ba6`, 2026-08-12) and 100 commits of MrChromebox on
top of it, then the patches of [`patches/edk2`](../patches/edk2) (43 in
v1.5.0, 53 now) and those of [`patches/lvglpkg`](../patches/lvglpkg) (18
then, 20 now). From
v1.6.0 it is the same sources on the TianoCore tag ([step (d)](#step-d-the-boards-on-the-package)).
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
to be confirmed as each one is ported. *Now* says where each commit is
since steps (b) and (c), made by `tools/edk2-import.py`: the patch of
`patches/tianocore` with its changes to TianoCore's packages, the package
(its new modules, and its platform for the `.dsc` and `.fdf` of
`UefiPayloadPkg`), LvglPkg, or binaries left out.

| | package | carry | upstream | drop | merged | total |
|---|---|---|---|---|---|---|
| Setup menu and the other screens of the firmware | 10 | 10 | 6 | 0 | 0 | 26 |
| Boot manager and boot options | 1 | 5 | 0 | 2 | 0 | 8 |
| Capsule updates and the ESRT | 3 | 3 | 2 | 0 | 0 | 8 |
| Secure Boot, TPM and crypto | 9 | 1 | 1 | 0 | 0 | 11 |
| Memory protection | 1 | 6 | 0 | 2 | 0 | 9 |
| Drivers for storage, USB, graphics and the console | 2 | 3 | 7 | 9 | 1 | 22 |
| Platform plumbing for coreboot | 3 | 6 | 6 | 0 | 1 | 16 |
| **all** | 29 | 34 | 22 | 13 | 2 | 100 |

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
|---|---|---|---|---|
| SMMSTORE | passes (`0ea5ae5`) | coreboot reaches the payload, the Shell writes a variable to SMMSTORE and rewrites it after a reboot, leaving one valid copy; FTW sets up its work space on the erased region | |
| runtime services | gap (`0ea5ae5`) | SmmStoreLib keeps the arguments of its SMM calls in runtime services data (`AllocatePages()` below 4 GiB) and gives SMM their physical address: macOS's boot.efi moves that memory after ExitBootServices(), SMM reads the old place and SetVariable() returns `EFI_DEVICE_ERROR`, as ouroBIOS did up to v1.3.10-rc15 | coreboot's patch 0134 (a page after the block of the com buffer), `edk2/0029` (the com buffer as runtime MMIO, the arguments in it after SetVirtualAddressMap()) and `edk2/0044` (there from the start, for the WSMT): carried, and proposed to coreboot and TianoCore together |
| TPM 1.2 | gap (`0ea5ae5`) | UefiPayloadPkg has no TCG driver: no `EFI_TCG_PROTOCOL`, and nothing of the payload is measured | MrChromebox's `c111515` and `5dc4840`, with `edk2/0019` and `0042` |
| authenticated variables | gap (`ced8b20`) | `SmmStoreFvbRuntimeDxe` formats an erased SMMSTORE with `gEfiVariableGuid`, also with `SECURE_BOOT_ENABLE`: the variable driver then works without authenticated variables, and Secure Boot has nowhere to keep PK, KEK, db and dbx | the line of `2686758` in `SmmStoreFvbRuntimeDxe.c`, to propose upstream: for example the authenticated GUID when the payload has `SECURE_BOOT_ENABLE` |
| authenticated store kept | passes (`574cb3b`) | the test turns the store that the payload formatted into one with `gEfiAuthenticatedVariableGuid` and no variables (`auth_convert`), the format that MrChromebox's payload, and so ouroBIOS's, gives an erased store since `2686758`: the upstream payload keeps it, its variable driver says it works with that format and setvar writes in it. A board's store in that format (`update.py vars` on a dump of the flash says which) is not lost to it | |
| Secure Boot on an authenticated store | passes (`574cb3b`) | with `SECURE_BOOT_ENABLE` and such a store, AuthVariableLib writes `CustomMode`, `certdb` and `VendorKeysNv`: of Secure Boot, upstream lacks the format of an erased store and the default keys | |

Three more things the runs show:

- the Shell of TianoCore waits 5 s for `startup.nsh`
  (`PcdShellDefaultDelay`) and reads a key each second; MrChromebox's
  `4373c47` took the script out; the boards' payload has no Shell, and
  `edk2/0060` reverts the commit;
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
  not have: 70 commits of MrChromebox (21 have nothing else; two commits
  and their reverts cancel out, `CANCELLED` of `edk2-import.py`; five
  change only `PlatformBootManagerLib`, which the package carries whole
  with `FmpDeviceSmmLib`, `PACKAGE_MOVED`) and 30 of the project's 52
  patches (13 change only the package or its platform, nine only one of
  those two libraries). The numbers of the patches left out stay unused,
  so the others keep theirs.
  The tag with the series is MrChromebox's tree with `patches/edk2` in
  every file but those (`edk2-import.py` checks it before it writes, and
  `--check` in `edk2-upstream.yml` checks the files of the repository).
- **The package**: the directories of `UefiPayloadPkg` that TianoCore
  does not have (the setup and its CFR, the splash, the password, the
  default Secure Boot keys, the update screen, MOR, the TPM's physical
  presence libraries, and MrChromebox's modules for hardware these boards
  do not have), with `FSDrivers`, and `PlatformBootManagerLib` and
  `FmpDeviceSmmLib`, which TianoCore has but which are mostly
  MrChromebox's and the project's work, carried whole; the platform,
  `UefiPayloadPkg.dsc` and
  `.fdf` of MrChromebox's tree with the project's patches and the paths
  of the package, as patches on TianoCore's. LvglPkg is a package of its
  own next to it, at the commit of MrChromebox's submodule with
  `patches/lvglpkg`, and LVGL in it at `LVGL_COMMIT` of `tools/build.sh`
  (v9.6 from v1.6.0) in both trees; the binary network drivers of Realtek and ASIX
  (`0ec988f`, only with `NETWORK_PXE_BOOT`) stay out.
  After v1.6.2-rc1 the package also takes what only its modules use out
  of TianoCore's packages: MrChromebox's `TimeDateSettingsDxe`, which his
  tree has in `MdeModulePkg` (`OTHER_MOVED` of `edk2-import.py`); the
  headers of its libraries, GUIDs and protocols (`PACKAGE_HEADERS`); and
  their declarations, which leave `UefiPayloadPkg.dec` and
  `MdeModulePkg.dec` in every patch of the series for `OuroBiosPkg.dec`
  (`PACKAGE_DECLS`; `edk2-import.py` stops if a file outside the package
  and its platform names one). The PCDs among them (the serial console
  of the boot manager, Secure Boot by default, the categories of the
  setup, the regions of the capsules) are in the package's token space,
  `gOuroBiosPkgTokenSpaceGuid`: all FixedAtBuild, constants in the code,
  so the payload does not change (`edk2-parity`). Those of iPXE and
  CSMWrap stay in `UefiPayloadPkg.dec`: coreboot's Makefile sets the names
  of their boot options by that name (`--pcd
  gUefiPayloadPkgTokenSpaceGuid.PcdiPXEOptionName`). `patches/tianocore`
  loses 11 patches that had nothing else: `0032`, `0047`, `0058`, `0064`,
  `0068` and `0077` of MrChromebox, and `0081`, `0088`, `0097`, `0098` and
  `0111` of `patches/edk2`.
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
  runs it with the import check. With the defconfigs of v1.6.0 (`0fb378d`,
  2026-11-02) both boards build the same 11 534 336 bytes either way: the
  W541 (`mrc`, whose payload `nri` shares) SHA-256 `9eca1a4374ba7cbe...`,
  the M920x `ab90569e4320baf7...`; the full build of `ci-test/next` with
  the payload from the package passes the smoke and update tests as v1.5.0 did.
- **What is watched**: `tools/upstream.sh edk2` says when MrChromebox's
  branch moves past `EDK2_MRCHROMEBOX_COMMIT` (to take his commits: the
  constant moved, `patches/edk2` rebased, the import again), `tianocore`
  when TianoCore has a newer stable tag (whether the series and the
  platform still apply), `dbx` reads the dbx of the package.
- **Going back**: the defconfigs with `CONFIG_EDK2_TAG_OR_REV` of
  MrChromebox in place of the package's lines build the payload of v1.5.0's
  base again (`tools/build.sh` follows the defconfigs).

What comes next, each with the payload's tests: the series shorter, commit
by commit, as the tables below say: the *package* ones out of TianoCore's
packages into `OuroBiosPkg` (a `PlatformBootManagerLib` of its own, for
one), the *upstream* ones proposed to TianoCore, the *drop* ones left out
(the drivers for hardware these boards do not have first); when a change
lives only in the package or the series, `patches/edk2` and the import
retire. Done so far, with no change to the payload: the first *drop*
ones, the two commits that MrChromebox reverted (`88b95ba` with
`6aa87d0`, `bf10b5c` with `4258973`), which `edk2-import.py` leaves out
in pairs after checking that they cancel out; the first *package* ones,
`PlatformBootManagerLib` and `FmpDeviceSmmLib`, which the package now
carries whole, as MrChromebox's tree with `patches/edk2` has them, and
which take fourteen patches out of the series and part of twelve
others.

The other *drop* ones, as looked at for v1.6.0:

- **Out of the payload already**, kept out by build switches that the
  boards leave off: the platform GOP policy (`076933b`, `1f9ab46`,
  `a3657a3`, only with `USE_PLATFORM_GOP`), the UFS platform driver
  (`b26a387`, only with `UFS_ENABLE`) and the network drivers of Realtek
  and ASIX (`0ec988f`, only with `NETWORK_PXE_BOOT` or `NETWORK_ENABLE`).
  Leaving them out changes no byte of the payload, but while
  `patches/edk2` is where the changes are made, it takes a revert there
  before `edk2/0026` (whose context in `UefiPayloadPkg.dec` has the GUID
  of the GOP policy, so a revert at the end cannot be taken out of the
  series with the commits) and `edk2-import.py` leaving the commits and
  the revert out together:
  one patch more in `patches/edk2` for two less in `patches/tianocore`,
  and a number out of order. They wait for `patches/edk2` to retire, when
  they are lines out of the series.
- **In the payload**, each with its own test. Done after v1.6.0-rc5:
  `9174049` (SdMmcPciGliDxe, the SDHCI of Genesys Logic) and `5342f42`
  (SdhciNonPciDxe, the SDHCI off the PCI bus, with its record in
  `CbParseLib` and `NonDiscoverablePciDeviceDxe`, which only it fed), two
  drivers in the volume for controllers these boards do not have, left
  out by `edk2/0054` and `edk2/0055` (the payload of the W541 9,357 bytes
  smaller, that of the M920x 8,863, with the smoke test and `edk2-parity`
  passed on the build of the branch): `tools/edk2-import.py` keeps their
  directories out of TianoCore's tree (`LEFT_OUT`), so the commit that
  adds each and the patch that removes it take no number in
  `patches/tianocore`, and the other numbers stay; what `5342f42` adds
  outside its directory stays in `tianocore/0060`, and `tianocore/0120`
  takes it out again, because `94a236511` (the boot media record) is
  written against it. Done after v1.6.2-rc1: `d7597bb` (HS400 enhanced strobe, in the
  `SdMmcPciHcDxe` that drives the SD reader of the W541), reverted by
  `edk2/0059`, the commit and its revert out of `patches/tianocore`
  together (`REVERTED`); the same for `4373c47` (the start of the UEFI
  Shell, which the boards' payload does not have), reverted by
  `edk2/0060`. `b8d0242` stays, moved to
  *upstream*: besides the UFS fix, which is not built, it guards
  `BmEnumerateBootOptions()` against a block device without a device
  path, which every board wants. `0a270f8` stays too, moved to *carry*: on the
  M920x it is what keeps BAR 0 of the SPI controller (0xfe010000, above
  the ECAM window) out of the root bridge aperture, which otherwise would
  grow over the reserved ECAM and fail with the whole PCI bus (PCI-09 of
  `tools/hw-report.py` shows that BAR as the one left out). `6cf55e1`
  stays as well, moved to *carry*: `c4fdec0a83d6` and the MTRR series
  before it are in the TianoCore tag, but they only stop `MtrrLib` from
  trampling what is there; `CpuDxe` still writes the MTRRs whenever a
  driver changes the cache type of a range, and `MpInitLib` copies them to
  every AP. With the PCD the MTRRs the OS finds are the ones coreboot set
  (on the M920x the write-combining framebuffer at 0xc0000000 among them);
  without it they would be the payload's. `1287861` (the Secure Boot
  pages of the setup) stays, as *carry*, by the owner's choice. That ends
  the commits left to the owner's decision. Where each *upstream* commit
  stands in TianoCore (none merged, four open pull requests of
  MrChromebox's, half of `b8d0242` merged after the tag, four proposed by
  Star Labs and closed): [docs/upstream/edk2-series.md](upstream/edk2-series.md).

## Setup menu and the other screens of the firmware

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `0c433f7` | UefiPayloadPkg/MdeModulePkg: Add boot progress text support | carry |  | `tianocore/0006`, package |
| `83eb1e6` | MdeModulePkg/UiApp: Rework Frontpage layout and SMBIOS display | carry | UiApp: or a UiApp of the package's own | `tianocore/0007` |
| `8814b15` | MdeModulePkg: Rework Boot Menu and Boot Manager UI | carry | BootManagerUiLib, BootMaintenanceManagerUiLib | `tianocore/0008` |
| `b6b0b66` | MdeModulePkg/UefiPayloadPkg: Improve Device Manager presentation | carry | DeviceManagerUiLib | `tianocore/0014`, package |
| `565124c` | MdeModulePkg: Add Logo position PCD and BGRT support | upstream | logo position PCD, BGRT | `tianocore/0015`, package |
| `4844b23` | MdeModulePkg: Be more verbose about SecureBoot and the reason why the boot failed | upstream | why a boot was refused by Secure Boot | `tianocore/0018` |
| `fc55cf0` | UefiPayloadPkg: Implement CFR support | upstream | checked after v1.6.2-rc1: CfrSetupMenuDxe and its helpers are the package's; what stays on the tag is the reader of coreboot's CFR records in `CbParseLib` and their format (`Coreboot.h`, `CfrSetupMenuGuid.h`), which belongs next to the rest of the coreboot tables | `tianocore/0025`, package |
| `b795f86` | MdeModulePkg/DisplayEngineDxe: Change the delimiter for ONE_OF | carry |  | `tianocore/0026` |
| `435706b` | UefiPayloadPkg/PlatformBootMgr: update progress message on menu entry | package | PlatformBootManagerLib of the package | package |
| `c3aa08f` | MdeModulePkg/UefiPayloadPkg: Add Time/Date Settings driver | package | a driver of its own, plus a hook in UiApp | package (`TimeDateSettingsDxe`, `OuroBiosPkg.dec`) |
| `0c79020` | MdeModulePkg: Fix Frontpage banner layout | carry | as 83eb1e6 | `tianocore/0033` |
| `c9d88a0` | MdeModulePkg/UefiPayloadPkg: Add Frontpage battery status support | carry | checked after v1.6.2-rc1: EcAcpiBatteryStatusDxe is the package's; the hook in UiApp stays with the UiApp of `83eb1e6` | `tianocore/0034`, package |
| `b06ce7e` | UefiPayloadPkg: Add password protection for setup menu access | package | UserAuthPkg: the supervisor password | package |
| `9b3274a` | MdeModulePkg/SetupBrowserDxe: Sync ordered lists before action callback | upstream | a fix of SetupBrowserDxe | `tianocore/0036` |
| `1fb7d11` | UefiPayloadPkg/PlatformBootManager: Clear boot prompt on ENTER | package | as 435706b | package |
| `f168fd0` | MdeModulePkg/SecurityPkg: Use HII popup for setup dialogs | carry | the HII popups the graphical setup draws (also edk2/0006) | `tianocore/0041` |
| `1287861` | SecurityPkg/SecureBootConfigDxe: Overhaul Secure Boot setup UI | carry | kept by the owner after v1.6.2-rc1: the reworked Secure Boot pages stay instead of the standard SecureBootConfigDxe ones | `tianocore/0042` |
| `ad284e9` | MdeModulePkg/FileExplorerLib: Add "Up one level" navigation | upstream |  | `tianocore/0043` |
| `17671bf` | UefiPayloadPkg: Add LVGL display engine support | carry | checked after v1.6.2-rc1: LvglPkg on its own; the changes to `UsbMouseAbsolutePointerDxe` (the pointer of the LVGL setup) stay on the tag | `tianocore/0046`, package, LvglPkg |
| `dfb8d33` | UefiPayloadPkg: Add NVRAM-controlled bootsplash with Setup UI | package | BootSplashConfigDxe | package (`OuroBiosPkg.dec`) |
| `240f748` | UefiPayloadPkg/CfrSetupMenuDxe: Add support for LOCK_AT_BOOT CFR flag | upstream | checked after v1.6.2-rc1: the LOCK_AT_BOOT flag in `CfrSetupMenuGuid.h`, with the CFR format of `fc55cf0` | `tianocore/0063`, package |
| `5764265` | UefiPayloadPkg/CfrSetupMenuDxe: grey out READONLY CFR options | package |  | package |
| `afe0e87` | UefiPayloadPkg: Copy custom bootsplash BMP to the ESP | package |  | package (`OuroBiosPkg.dec`) |
| `5d4fdf6` | UefiPayloadPkg/BootSplashConfigDxe: Document BMP format requirements | package |  | package |
| `b91131a` | UefiPayloadPkg/CfrSetupMenuDxe: Fix SubForm parsing | package |  | package |
| `1817a2b` | UefiPayloadPkg: Unregister the setup hotkey before clearing the prompt | package | as 435706b | package |

## Boot manager and boot options

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `d8205d0` | MdeModulePkg/UefiPayloadPkg: Add PrioritizeInternal boot device support | carry | PRIORITIZE_INTERNAL | `tianocore/0005`, package |
| `4a4c3a1` | MdeModulePkg: Improve boot descriptions and skip duplicate eMMC | carry |  | `tianocore/0009` |
| `4373c47` | ShellPkg: disable startup script, mapping print; show welcome banner | drop | the boards' payload has no Shell (`SHELL_TYPE NONE` from v1.6.0), so nothing of it is in their ROMs; a build with the Shell starts as TianoCore's | left out (`edk2/0060`) |
| `6676ad7` | UefiPayloadPkg/MdeModulePkg: Platform setup and boot defaults | carry | checked after v1.6.2-rc1: the PCD defaults are the package's; the changes to `BootManagerUiLib` and `BmBoot.c` stay with `8814b15` | `tianocore/0016`, package |
| `0ec988f` | UefiPayloadPkg: Add network and PXE boot support | drop | the UEFI network stack: the boards boot from the network with iPXE's own driver, so NetworkPkg's PXE driver is not in the payload (not exposed to CVE-2026-97631, fixed on TianoCore's master by `560ed9b` on 2026-10-15, after `edk2-stable202608`) | package, binaries left out |
| `9c5e2da` | PlatformBootManagerLib: Refactor BdsGetShellFvDevicePath | package |  | package |
| `b581d3b` | UefiPayloadPkg: Add iPXE network boot option support | carry | checked after v1.6.2-rc1: the iPXE entry is in the package's `PlatformBootManagerLib`; what stays on the tag are the two PCDs of `UefiPayloadPkg.dec` that coreboot's Makefile sets with `--pcd`, so they keep its token space | `tianocore/0031` |
| `6c14abf` | MdeModulePkg: Add Auto Boot Fall-Through option | carry | the setting next to *Auto Boot Time-out* (v1.4.1) | `tianocore/0079` |

## Capsule updates and the ESRT

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `d6fbc7b` | UefiPayloadPkg: Add FMP_DEVICE_PKCS7_PCD_INC define | package |  | package |
| `5a0c064` | UefiPayloadPkg/FmpDeviceSmmLib: Add FMAP-based scoped capsule flashing | carry | checked after v1.6.2-rc1: FmpDeviceSmmLib is the package's; `AppendRmapManifest.py` stays in `UefiPayloadPkg/Tools`, where `tools/build.sh` runs it in either tree | `tianocore/0050`, package |
| `04272be` | UefiPayloadPkg: Configure capsule update build options | package |  | package |
| `775376a` | UefiPayloadPkg: Add graphical capsule update progress | package | with edk2/0026, the update screen | package |
| `6e839af` | UefiPayloadPkg/FmpDeviceSmmLib: Harden scoped capsule flashing | carry | checked after v1.6.2-rc1: as `5a0c064`: `AppendRmapManifest.py` and `UefiPayloadPkg.ci.yaml` | `tianocore/0052`, package |
| `6c7b28d` | UefiPayloadPkg/Fmp: Keep capsule updates resilient through progress and reset | upstream | checked after v1.6.2-rc1: in `FmpDxe`, `DxeCapsuleLib` and `ResetSystemLib` of TianoCore: nothing of it is the package's | `tianocore/0053` |
| `cc69856` | MdeModulePkg/UefiPayloadPkg: Keep ESRT durable across hibernate and FMP sync | upstream | ESRT across hibernation | `tianocore/0054` |
| `a447cf5` | MdeModulePkg/UefiPayloadPkg: Harden capsule progress UI and update cleanup | carry | MdeModulePkg part of the progress UI | `tianocore/0055`, package |

## Secure Boot, TPM and crypto

The OpenSSL of CryptoPkg is 3.5.7 at `edk2-stable202608`, and still on
TianoCore's `master` on 2026-11-03 (`011eca2e8f`). Most of the CVEs that
3.5.8 and 3.5.9 fix are in parts that CryptoPkg configures out of its
OpenSSL (`no-quic`, `no-dtls`, `no-cms`, `no-cmp`, `no-sm2`, `no-siv`), or
in TLS, which CryptoDxe links for its crypto protocol and no module of
the payload uses (TlsDxe comes with NetworkPkg, which the payload leaves
out); the payload verifies signatures and computes hashes, and holds no
key of its own. The one it can reach is CVE-2026-35189, the memory that
OpenSSL allocates for the relative names of CRL distribution points as it
looks at every certificate it verifies, those of a signed image or of a
capsule too: at worst a boot that stops on a crafted signature. It comes
with the stable tag that takes the new OpenSSL.

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `2686758` | UefiPayloadPkg: Enroll Keys for SecureBoot | package | EnrollDefaultKeys; or SecureBootDefaultKeysDxe with a provisioning step of the package. Its line in SmmStoreFvbRuntimeDxe.c, an authenticated store, goes upstream ([step (a)](#step-a-edk2-stable202608-in-qemu)) | `tianocore/0019`, package |
| `c111515` | UefiPayloadPkg/SecurityPkg/OvmfPkg: Add TPM 1.2/2.0 support | carry | TPM 1.2 and 2.0 in UefiPayloadPkg; edk2/0019 and 0042 build on it; without it no TCG protocol ([step (a)](#step-a-edk2-stable202608-in-qemu)) | `tianocore/0021`, package |
| `db6619a` | UefiPayloadPkg: Use OvmfPkg PlatformSecureLib when Secure Boot enabled | package | a library mapping of the .dsc | package |
| `51d7f47` | SecureBoot: Update revocation DBX to version 20260402 | package | data | package |
| `a8b5b11` | UefiPayloadPkg/EnrollDefaultKeys: Provision default key reference variables | package |  | package |
| `77242a1` | UefiPayloadPkg: Add option to enable Secure Boot default after key enrollment | package |  | package (`OuroBiosPkg.dec`) |
| `5dc4840` | UefiPayloadPkg: Map Tpm2HelpLib for TPM-enabled builds | package |  | package |
| `af5e96c` | SecureBoot: update DBX to version 20260707 | package | data | package |
| `0d39245` | CryptoPkg/BaseCryptLib: Ignore foreign buffers in runtime free/realloc | upstream | CryptoPkg at runtime | `tianocore/0070` |
| `acc37b2` | UefiPayloadPkg/EnrollDefaultKeys: Add Microsoft DBX baseline artifacts | package | the dbx files (upstream.sh dbx compares them) | package |
| `f7cbaab` | UefiPayloadPkg: Append DBX updates to the retained baseline | package |  | package (`OuroBiosPkg.dec`) |

## Memory protection

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `45aec95` | UefiPayloadPkg: align DXE images for page protections | package | .dsc | package |
| `bf10b5c` | UefiCpuPkg: Gate AP exception stacks on PcdCpuStackGuard | drop | reverted by 4258973 | left out with its revert (0048 unused) |
| `4258973` | Revert "UefiCpuPkg: Gate AP exception stacks on PcdCpuStackGuard" | drop | reverts bf10b5c | left out with bf10b5c (0057 unused) |
| `abbfa17` | MdePkg: Add PE/COFF NX_COMPAT Flag | carry | the six together, or none | `tianocore/0071` |
| `3321e5a` | MdeModulePkg: Split DisableNullDetectionAtTheEndOfDxe Into Two | carry |  | `tianocore/0072` |
| `8b0cd75` | MdeModulePkg: Add Compatibility Mode Functionality | carry |  | `tianocore/0073` |
| `d124d93` | MdeModulePkg: DXE: Adjust Setting Memory Protections With Compat Mode | carry |  | `tianocore/0074` |
| `3b1c619` | MdeModulePkg: Enter Compat Mode When non-NX_COMPAT App Loaded | carry |  | `tianocore/0075` |
| `9c0cb3a` | MdeModulePkg: Add Compat Mode Allowed PCD | carry |  | `tianocore/0076` |

## Drivers for storage, USB, graphics and the console

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `6128cce` | UefiPayloadPkg/GraphicsOutputDxe: Allow for framebuffer at an offset from BAR | upstream |  | `tianocore/0003` |
| `564cb49` | BaseSerialPortLib16550: Avoid reinitializing serial port or setting attributes | carry |  | `tianocore/0004` |
| `e32b60d` | UefiPayloadPkg: Add and use EXT2/EXT4, exFAT, NTFS filesystem drivers | package | ext4 only (the boards build with EXTRA_FS_DRIVERS=FALSE) | package |
| `a091558` | MdeModulePkg/SdMmcPciHcDxe: add Bayhub support | carry | the SD reader of the W541 is an O2 Micro OZ777, 1217:8520, its `BHT_PCI_DEV_ID_FJ2` (`lspci -nn` on a W541, [roadmap](roadmap.md#card-reader-of-the-w541)) | `tianocore/0010` |
| `4c76525` | MdeModulePkg/Usb/Keyboard.c: remove Get/SetConfig calls | upstream | USB keyboards that fail the requests | `tianocore/0011` |
| `076933b` | UefiPayloadPkg: Add and use PlatformGopPolicy | drop | no GOP driver: libgfxinit sets the mode | `tianocore/0013`, package |
| `88b95ba` | UefiPayloadPkg: Add AmdPcoSdhciDxe driver for AMD Picasso eMMC | drop | reverted by 6aa87d0 | left out with its revert (0022 unused) |
| `42865d9` | MdeModulePkg: Improve USB error handling for faulting devices | upstream |  | `tianocore/0023` |
| `9174049` | UefiPayload: Add new SdMmcPciGli driver | drop | no such controller | left out (`edk2/0054`) |
| `b26a387` | UefiPayloadPkg/UfsPlatformDxe: Add new UFS platform driver | drop | UFS_ENABLE=FALSE | package |
| `b8d0242` | MdeModulePkg: UFS pass-through fix and boot enumeration filter | upstream | looked at after v1.6.2-rc1: the UFS half is not built (`UFS_ENABLE=FALSE`), but the `BmBoot.c` half also skips a block device without a device path in `BmEnumerateBootOptions()`, a guard against a NULL dereference that every board benefits from; not reverted, to be proposed upstream with the LUN filter | `tianocore/0029` |
| `a79398a` | PcRtcEntry: Don't assert if RTC init fails | upstream |  | `tianocore/0037` |
| `dde0798` | FatPkg: Fix FAT32 mount on small 4K-sector ESP partitions | upstream |  | `tianocore/0040` |
| `97a12e8` | MdeModulePkg/ScsiDiskDxe: Don't fail media detection on FUA query error | merged | in master after the tag | `tianocore/0044` |
| `6aa87d0` | Revert "UefiPayloadPkg: Add AmdPcoSdhciDxe driver for AMD Picasso eMMC" | drop | reverts 88b95ba | left out with 88b95ba (0059 unused) |
| `5342f42` | UefiPayloadPkg: Add SdhciNonPciDxe for non-PCI SDHCI | drop | no such controller | left out (`edk2/0055`); `tianocore/0060` keeps its record and parser, `tianocore/0120` takes them out |
| `acf9505` | MdeModulePkg/Usb: Warm reset downstream SuperSpeed ports | upstream |  | `tianocore/0061` |
| `d7597bb` | MdeModulePkg/SdMmcPciHcDxe: add HS400 Enhanced Strobe for Intel eMMC | drop | no eMMC | left out from v1.6.2 (`edk2/0059`, its revert; `REVERTED` of `edk2-import.py`, `tianocore/0062` unused) |
| `c205ceb` | MdeModulePkg/SdMmcPciHcDxe: Don't force EmbeddedSlot for Bayhub | carry | as a091558: Libreboot's fix for SD boot on the W541 | `tianocore/0065` |
| `81c562f` | UefiPayloadPkg: Add CbfsLib to read files from coreboot's CBFS | package | if a module of the package reads CBFS | package (`OuroBiosPkg.dec`) |
| `1f9ab46` | UefiPayloadPkg/PlatformGopPolicy: Load GOP driver and VBT from CBFS | drop | as 076933b | `tianocore/0069`, package |
| `a3657a3` | UefiPayloadPkg: Conditionally use GraphicsDriverDxe in apriori dxe | drop | as 076933b | package |

## Platform plumbing for coreboot

| Commit | Subject | Becomes | Note | Now |
|---|---|---|---|---|
| `214b236` | UefiPayloadPkg: Increase FD size | package | .fdf; or `-D FD_SIZE` and `NUM_BLOCKS` of the build, which win over the .fdf ([step (a)](#step-a-edk2-stable202608-in-qemu)) | package |
| `6cf55e1` | UefiCpuPkg: Disable MTRR programming for UefiPayloadPkg | carry | checked after v1.6.2-rc1: upstream's `MtrrLib` no longer tramples coreboot's MTRRs (`c4fdec0a83d6` and the series before it, in the tag), but `CpuDxe` (`gDS->SetMemorySpaceAttributes()`) and `MpInitLib` (the copy to the APs) still write them; the PCD keeps coreboot's MTRRs as they are, and dropping it would change what the OS finds. Upstream refused this form ([#12227](https://github.com/tianocore/edk2/pull/12227), closed: the maintainer of `MtrrLib` wants the callers to skip the MTRRs, not a switch in the library). The `.uni` hunk is also wrong: it gives the new PCD the prompt and help of `PcdCpuNumberOfReservedVariableMtrrs` and the other way round | `tianocore/0001`, package |
| `96303b7` | MdeModulePkg: Don't remove rejected PCI devices | carry |  | `tianocore/0002` |
| `7f7b9c7` | UefiPayloadPkg: drop Platform override config | package |  | package |
| `9701a6f` | MdeModulePkg/FaultTolerantWrite: Don't check for block alignment | carry | SMMSTORE blocks; in [step (a)](#step-a-edk2-stable202608-in-qemu) FTW sets up its work space on the 512 KiB SMMSTORE without it, a fault tolerant write (a reclaim of the store) is still to be seen | `tianocore/0017` |
| `2deb904` | UefiPayloadPkg: Check more ACPI tables | carry |  | `tianocore/0020` |
| `0a270f8` | UefiPayloadPkg/Library/PciHostBridgeLib: Add warning for coreboot/EDK2 incompability | carry | not only a warning: when the root bridge aperture would grow over reserved memory to take a memory BAR of bus 0, the BAR stays out of it, and the payload's drivers then cannot reach that device. Needed on the M920x (checked after v1.6.2-rc1, PCI-09 of `tools/hw-report.py`): BAR 0 of the SPI controller `00:1f.5`, fixed at 0xfe010000, sits above the ECAM window (0xe0000000-0xefffffff, reserved memory from v1.6.0, `edk2/0052`); without the check the aperture would grow from 0xbecb9000 over the ECAM to 0xfe010fff, and `PciHostBridgeDxe` would fail on the reserved range, the whole PCI bus with it. The W541 has no such BAR. Kept; for upstream, the check as a fix of the aperture rather than a warning | `tianocore/0024` |
| `4b57ca5` | UefiPayloadPkg: Set PcdCpuFeaturesInitOnS3Resume to FALSE for coreboot | package | a PCD of the .dsc | package |
| `252f6d2` | UefiPayloadPkg: Extend SmmStoreLib for 64-bit MMIO store | upstream | SmmStoreLib | `tianocore/0028` |
| `1c39058` | UefiPayloadPkg/Library/CbParseLib: Populate root bridges info from HOB | upstream | CbParseLib | `tianocore/0035` |
| `c981e5d` | UefiPayloadEntry: Fix use of uninitialized memory | merged | in master after the tag | `tianocore/0038` |
| `40a1b7a` | UefiPayloadPkg/PciPlatformDxe: Fix BAR restore leak and uninit CodeType | upstream |  | `tianocore/0045` |
| `e27ef54` | UefiPayloadPkg/ResetSystemLib: Select S5 sleep type from CPUID | upstream | ResetSystemLib | `tianocore/0049` |
| `0453b7a` | UefiPayloadPkg/ResetSystemLib: Use full CF9 sequence for cold reset | upstream | ResetSystemLib | `tianocore/0056` |
| `b061f7a` | MdeModulePkg: Use warm reset for setup-initiated resets | carry |  | `tianocore/0066` |
| `94a2365` | UefiPayloadPkg: Pass coreboot boot media params to DXE | upstream | checked after v1.6.2-rc1: the boot media record of coreboot in `CbParseLib`, `SblParseLib` and `UefiPayloadEntry` | `tianocore/0067` |
