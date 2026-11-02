# Moving the payload to TianoCore EDK II

The payload is MrChromebox's EDK II, branch `uefipayload_2608`, at
`6c14abf865e0`: the stable tag `edk2-stable202608` of TianoCore
(`2970e5699ba6`, 2026-08-12) and 100 commits of MrChromebox on top of it,
then the 44 patches of [`patches/edk2`](../patches/edk2) and the 18 of
[`patches/lvglpkg`](../patches/lvglpkg). This page lists those 100
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
| Boot manager and boot options | 3 | 3 | 0 | 2 | 0 | 8 |
| Capsule updates and the ESRT | 6 | 1 | 1 | 0 | 0 | 8 |
| Secure Boot, TPM and crypto | 9 | 1 | 1 | 0 | 0 | 11 |
| Memory protection | 1 | 6 | 0 | 2 | 0 | 9 |
| Drivers for storage, USB, graphics and the console | 2 | 1 | 6 | 12 | 1 | 22 |
| Platform plumbing for coreboot | 4 | 4 | 5 | 2 | 1 | 16 |
| **all** | 39 | 23 | 17 | 19 | 2 | 100 |

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
| `4373c47` | ShellPkg: disable startup script, mapping print; show welcome banner | drop | cosmetic |
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
| `2686758` | UefiPayloadPkg: Enroll Keys for SecureBoot | package | EnrollDefaultKeys; or SecureBootDefaultKeysDxe with a provisioning step of the package |
| `c111515` | UefiPayloadPkg/SecurityPkg/OvmfPkg: Add TPM 1.2/2.0 support | carry | TPM 1.2 and 2.0 in UefiPayloadPkg; edk2/0019 and 0042 build on it |
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
| `214b236` | UefiPayloadPkg: Increase FD size | package | .fdf |
| `6cf55e1` | UefiCpuPkg: Disable MTRR programming for UefiPayloadPkg | drop | if step (a) shows that upstream's MtrrLib leaves coreboot's MTRRs alone, as coreboot's Kconfig help says of c4fdec0a83d6 |
| `96303b7` | MdeModulePkg: Don't remove rejected PCI devices | carry |  |
| `7f7b9c7` | UefiPayloadPkg: drop Platform override config | package |  |
| `9701a6f` | MdeModulePkg/FaultTolerantWrite: Don't check for block alignment | carry | SMMSTORE blocks |
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
