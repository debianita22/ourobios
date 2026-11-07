/** @file
  This file include all platform action which can be customized
  by IBV/OEM.

Copyright (c) 2015 - 2023, Intel Corporation. All rights reserved.<BR>
SPDX-License-Identifier: BSD-2-Clause-Patent

**/

#include "PlatformBootManager.h"
#include "PlatformConsole.h"
#include <Protocol/FirmwareVolume2.h>
#include <Protocol/PlatformBootManager.h>

/**
  Signal EndOfDxe event and install SMM Ready to lock protocol.

**/
VOID
InstallReadyToLock (
  VOID
  )
{
  EFI_STATUS                Status;
  EFI_HANDLE                Handle;
  EFI_SMM_ACCESS2_PROTOCOL  *SmmAccess;

  DEBUG ((DEBUG_INFO, "InstallReadyToLock  entering......\n"));
  //
  // Inform the SMM infrastructure that we're entering BDS and may run 3rd party code hereafter
  // Since PI1.2.1, we need signal EndOfDxe as ExitPmAuth
  //
  EfiEventGroupSignal (&gEfiEndOfDxeEventGroupGuid);
  DEBUG ((DEBUG_INFO, "All EndOfDxe callbacks have returned successfully\n"));

  //
  // Install DxeSmmReadyToLock protocol in order to lock SMM
  //
  Status = gBS->LocateProtocol (&gEfiSmmAccess2ProtocolGuid, NULL, (VOID **)&SmmAccess);
  if (!EFI_ERROR (Status)) {
    Handle = NULL;
    Status = gBS->InstallProtocolInterface (
                    &Handle,
                    &gEfiDxeSmmReadyToLockProtocolGuid,
                    EFI_NATIVE_INTERFACE,
                    NULL
                    );
    ASSERT_EFI_ERROR (Status);
  }

  DEBUG ((DEBUG_INFO, "InstallReadyToLock  end\n"));
  return;
}

/**
  Return the index of the load option in the load option array.

  The function consider two load options are equal when the
  OptionType, Attributes, Description, FilePath and OptionalData are equal.

  @param Key    Pointer to the load option to be found.
  @param Array  Pointer to the array of load options to be found.
  @param Count  Number of entries in the Array.

  @retval -1          Key wasn't found in the Array.
  @retval 0 ~ Count-1 The index of the Key in the Array.
**/
INTN
PlatformFindLoadOption (
  IN CONST EFI_BOOT_MANAGER_LOAD_OPTION  *Key,
  IN CONST EFI_BOOT_MANAGER_LOAD_OPTION  *Array,
  IN UINTN                               Count
  )
{
  UINTN  Index;

  for (Index = 0; Index < Count; Index++) {
    if ((Key->OptionType == Array[Index].OptionType) &&
        (Key->Attributes == Array[Index].Attributes) &&
        (StrCmp (Key->Description, Array[Index].Description) == 0) &&
        (CompareMem (Key->FilePath, Array[Index].FilePath, GetDevicePathSize (Key->FilePath)) == 0) &&
        (Key->OptionalDataSize == Array[Index].OptionalDataSize) &&
        (CompareMem (Key->OptionalData, Array[Index].OptionalData, Key->OptionalDataSize) == 0))
    {
      return (INTN)Index;
    }
  }

  return -1;
}

/**
  Get the FV device path for a file identified by FileGuid.

  @param  FileGuid   The GUID of the file to locate.

  @return   A pointer to device path structure or NULL when not found.
**/
EFI_DEVICE_PATH_PROTOCOL *
BdsGetFvFileDevicePath (
  IN EFI_GUID  *FileGuid
  )
{
  UINTN                          FvHandleCount;
  EFI_HANDLE                     *FvHandleBuffer;
  UINTN                          Index;
  EFI_STATUS                     Status;
  EFI_FIRMWARE_VOLUME2_PROTOCOL  *Fv;
  UINTN                          Size;
  UINT32                         AuthenticationStatus;
  EFI_DEVICE_PATH_PROTOCOL       *DevicePath;
  EFI_FV_FILETYPE                FoundType;
  EFI_FV_FILE_ATTRIBUTES         FileAttributes;

  Status = EFI_SUCCESS;
  gBS->LocateHandleBuffer (
         ByProtocol,
         &gEfiFirmwareVolume2ProtocolGuid,
         NULL,
         &FvHandleCount,
         &FvHandleBuffer
         );

  for (Index = 0; Index < FvHandleCount; Index++) {
    Size = 0;
    gBS->HandleProtocol (
           FvHandleBuffer[Index],
           &gEfiFirmwareVolume2ProtocolGuid,
           (VOID **)&Fv
           );
    Status = Fv->ReadFile (
                   Fv,
                   FileGuid,
                   NULL,
                   &Size,
                   &FoundType,
                   &FileAttributes,
                   &AuthenticationStatus
                   );
    if (!EFI_ERROR (Status)) {
      //
      // Found the shell file
      //
      break;
    }
  }

  if (EFI_ERROR (Status)) {
    if (FvHandleCount) {
      FreePool (FvHandleBuffer);
    }

    return NULL;
  }

  DevicePath = DevicePathFromHandle (FvHandleBuffer[Index]);

  if (FvHandleCount) {
    FreePool (FvHandleBuffer);
  }

  return DevicePath;
}

/**
  Register a boot option using a file GUID in the FV.

  @param FileGuid     The file GUID name in FV.
  @param Description  The boot option description.
  @param Attributes   The attributes used for the boot option loading.
**/
VOID
PlatformRegisterFvBootOption (
  EFI_GUID  *FileGuid,
  CHAR16    *Description,
  UINT32    Attributes
  )
{
  EFI_STATUS                         Status;
  UINTN                              OptionIndex;
  EFI_BOOT_MANAGER_LOAD_OPTION       NewOption;
  EFI_BOOT_MANAGER_LOAD_OPTION       *BootOptions;
  UINTN                              BootOptionCount;
  MEDIA_FW_VOL_FILEPATH_DEVICE_PATH  FileNode;
  EFI_DEVICE_PATH_PROTOCOL           *DevicePath;

  DevicePath = BdsGetFvFileDevicePath (FileGuid);
  if (DevicePath == NULL) {
    return;
  }

  EfiInitializeFwVolDevicepathNode (&FileNode, FileGuid);
  DevicePath = AppendDevicePathNode (
                 DevicePath,
                 (EFI_DEVICE_PATH_PROTOCOL *)&FileNode
                 );
  if (DevicePath == NULL) {
    return;
  }

  Status = EfiBootManagerInitializeLoadOption (
             &NewOption,
             LoadOptionNumberUnassigned,
             LoadOptionTypeBoot,
             Attributes,
             Description,
             DevicePath,
             NULL,
             0
             );
  if (DevicePath != NULL) {
    FreePool (DevicePath);
  }
  if (!EFI_ERROR (Status)) {
    BootOptions = EfiBootManagerGetLoadOptions (&BootOptionCount, LoadOptionTypeBoot);

    OptionIndex = PlatformFindLoadOption (&NewOption, BootOptions, BootOptionCount);

    if (OptionIndex == -1) {
      Status = EfiBootManagerAddLoadOptionVariable (&NewOption, (UINTN)-1);
      ASSERT_EFI_ERROR (Status);
    }

    EfiBootManagerFreeLoadOption (&NewOption);
    EfiBootManagerFreeLoadOptions (BootOptions, BootOptionCount);
  }
}

/**
  Delete the boot options that start the file FileGuid of a firmware volume:
  the ones PlatformRegisterFvBootOption made, whatever their description.

  @param FileGuid   The GUID of the file in the firmware volume.
**/
STATIC
VOID
PlatformRemoveFvBootOption (
  IN EFI_GUID  *FileGuid
  )
{
  EFI_BOOT_MANAGER_LOAD_OPTION  *BootOptions;
  UINTN                         BootOptionCount;
  UINTN                         Index;
  EFI_DEVICE_PATH_PROTOCOL      *Node;
  EFI_GUID                      *NodeGuid;

  BootOptions = EfiBootManagerGetLoadOptions (&BootOptionCount, LoadOptionTypeBoot);
  for (Index = 0; Index < BootOptionCount; Index++) {
    for (Node = BootOptions[Index].FilePath; !IsDevicePathEnd (Node); Node = NextDevicePathNode (Node)) {
      NodeGuid = EfiGetNameGuidFromFwVolDevicePathNode ((MEDIA_FW_VOL_FILEPATH_DEVICE_PATH *)Node);
      if ((NodeGuid != NULL) && CompareGuid (NodeGuid, FileGuid)) {
        EfiBootManagerDeleteLoadOptionVariable (BootOptions[Index].OptionNumber, LoadOptionTypeBoot);
        break;
      }
    }
  }

  EfiBootManagerFreeLoadOptions (BootOptions, BootOptionCount);
}

/**
  A switch of the firmware setup. CfrSetupMenuDxe keeps the options of the
  coreboot setup menu (CFR) as variables of gEficorebootNvDataGuid, named
  after the option, 0 or 1 for a switch: off only when the variable is there
  and zero, so that an option the setup does not know, or has not written
  yet, counts as on.

  @param Name   The name of the option.

  @retval TRUE   On, or not there.
  @retval FALSE  Off.
**/
STATIC
BOOLEAN
PlatformSetupSwitch (
  IN CONST CHAR16  *Name
  )
{
  EFI_STATUS  Status;
  UINT64      Value;
  UINTN       Size;

  Value  = 0;
  Size   = sizeof (Value);
  Status = gRT->GetVariable ((CHAR16 *)Name, &gEficorebootNvDataGuid, NULL, &Size, &Value);
  if (EFI_ERROR (Status)) {
    return TRUE;
  }

  return Value != 0;
}

/**
  Is Secure Boot on? The SecureBoot variable, as the image verification
  sets it: 1 with the keys enrolled and user mode.

  @retval TRUE   On.
  @retval FALSE  Off, or no such variable.
**/
STATIC
BOOLEAN
PlatformSecureBootOn (
  VOID
  )
{
  EFI_STATUS  Status;
  UINT8       SecureBoot;
  UINTN       Size;

  SecureBoot = 0;
  Size       = sizeof (SecureBoot);
  Status     = gRT->GetVariable (EFI_SECURE_BOOT_MODE_NAME, &gEfiGlobalVariableGuid, NULL, &Size, &SecureBoot);
  return !EFI_ERROR (Status) && (SecureBoot == SECURE_BOOT_MODE_ENABLE);
}

/**
  Is this the boot option of a USB drive? Its device path has a USB node,
  the test BmBoot uses to put the USB drives first, and no MAC node, the
  mark of a network boot option for BmGetNetworkDescription(): a USB
  network adapter keeps its PXE and HTTP options, as the setup help says.

  @param Option   The boot option.

  @retval TRUE   A USB drive.
  @retval FALSE  Another device, or a network boot through a USB adapter.
**/
STATIC
BOOLEAN
PlatformIsUsbDriveOption (
  IN CONST EFI_BOOT_MANAGER_LOAD_OPTION  *Option
  )
{
  EFI_DEVICE_PATH_PROTOCOL  *Node;
  BOOLEAN                   Usb;

  if (Option->FilePath == NULL) {
    return FALSE;
  }

  Usb = FALSE;
  for (Node = Option->FilePath; !IsDevicePathEnd (Node); Node = NextDevicePathNode (Node)) {
    if (DevicePathType (Node) != MESSAGING_DEVICE_PATH) {
      continue;
    }

    if (DevicePathSubType (Node) == MSG_MAC_ADDR_DP) {
      return FALSE;
    }

    if (DevicePathSubType (Node) == MSG_USB_DP) {
      Usb = TRUE;
    }
  }

  return Usb;
}

/**
  EDKII_PLATFORM_BOOT_MANAGER_PROTOCOL.RefreshAllBootOptions(), installed
  only with the usb_boot switch of the setup off: the boot options that the
  boot manager makes for the devices it finds, without the USB drives. The
  boot manager then deletes the USB drive options it made before, once, and
  does not make them again: no flash write at every boot.

  The boot manager frees BootOptions and later frees the returned array
  with EfiBootManagerFreeLoadOptions(), so each kept option is a copy of its
  own, OptionalData included: that is the GUID that marks an option made by
  the boot manager, so the kept options still match theirs in NV.

  @param[in]  BootOptions              The options the boot manager found.
  @param[in]  BootOptionsCount         The number of BootOptions.
  @param[out] UpdatedBootOptions       The options to use instead.
  @param[out] UpdatedBootOptionsCount  The number of UpdatedBootOptions.

  @retval EFI_SUCCESS            UpdatedBootOptions has the options to use.
  @retval EFI_UNSUPPORTED        No USB drive: the boot manager keeps its own.
  @retval EFI_INVALID_PARAMETER  A parameter is NULL.
  @retval EFI_OUT_OF_RESOURCES   No memory for the copies.
**/
STATIC
EFI_STATUS
EFIAPI
PlatformRefreshAllBootOptions (
  IN  CONST EFI_BOOT_MANAGER_LOAD_OPTION  *BootOptions,
  IN  CONST UINTN                         BootOptionsCount,
  OUT       EFI_BOOT_MANAGER_LOAD_OPTION  **UpdatedBootOptions,
  OUT       UINTN                         *UpdatedBootOptionsCount
  )
{
  EFI_STATUS                    Status;
  EFI_BOOT_MANAGER_LOAD_OPTION  *Kept;
  UINTN                         KeptCount;
  UINTN                         Index;

  if ((UpdatedBootOptions == NULL) || (UpdatedBootOptionsCount == NULL) ||
      ((BootOptions == NULL) && (BootOptionsCount != 0)))
  {
    return EFI_INVALID_PARAMETER;
  }

  for (Index = 0; Index < BootOptionsCount; Index++) {
    if (PlatformIsUsbDriveOption (&BootOptions[Index])) {
      break;
    }
  }

  if (Index == BootOptionsCount) {
    return EFI_UNSUPPORTED;
  }

  //
  // Zeroed: an entry that fails half way is still safe to free.
  //
  Kept = AllocateZeroPool (BootOptionsCount * sizeof (EFI_BOOT_MANAGER_LOAD_OPTION));
  if (Kept == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }

  KeptCount = 0;
  for (Index = 0; Index < BootOptionsCount; Index++) {
    if (PlatformIsUsbDriveOption (&BootOptions[Index])) {
      DEBUG ((DEBUG_INFO, "%a: usb_boot off, no option for %s\n", __func__, BootOptions[Index].Description));
      continue;
    }

    //
    // EfiBootManagerInitializeLoadOption() makes its own copies of the
    // description, the device path and OptionalData.
    //
    Status = EfiBootManagerInitializeLoadOption (
               &Kept[KeptCount],
               BootOptions[Index].OptionNumber,
               BootOptions[Index].OptionType,
               BootOptions[Index].Attributes,
               BootOptions[Index].Description,
               BootOptions[Index].FilePath,
               BootOptions[Index].OptionalData,
               BootOptions[Index].OptionalDataSize
               );
    KeptCount++;
    if (EFI_ERROR (Status) ||
        (Kept[KeptCount - 1].Description == NULL) ||
        (Kept[KeptCount - 1].FilePath == NULL) ||
        ((BootOptions[Index].OptionalDataSize != 0) && (Kept[KeptCount - 1].OptionalData == NULL)))
    {
      EfiBootManagerFreeLoadOptions (Kept, KeptCount);
      return EFI_ERROR (Status) ? Status : EFI_OUT_OF_RESOURCES;
    }
  }

  *UpdatedBootOptions      = Kept;
  *UpdatedBootOptionsCount = KeptCount;
  return EFI_SUCCESS;
}

STATIC EDKII_PLATFORM_BOOT_MANAGER_PROTOCOL  mPlatformBootManager = {
  EDKII_PLATFORM_BOOT_MANAGER_PROTOCOL_REVISION,
  PlatformRefreshAllBootOptions
};

/**
  With the usb_boot switch of the setup off, install the filter that keeps
  the USB drives out of the boot options the boot manager makes by itself;
  a USB network adapter keeps its network boot options. On, or on a board
  whose setup has no such switch, nothing is installed and the boot manager
  works as before.

  It is not a security boundary: Boot#### options made by the user or an
  OS, Boot From File in the Boot Maintenance Manager of the setup, the UEFI
  Shell (and its startup.nsh), CSMWrap and the platform recovery
  (\EFI\BOOT\BOOTX64.EFI of any media, once every Boot#### has failed) can
  still start from USB.
**/
STATIC
VOID
PlatformInstallUsbBootFilter (
  VOID
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  Handle;

  if (PlatformSetupSwitch (L"usb_boot")) {
    return;
  }

  Handle = NULL;
  Status = gBS->InstallMultipleProtocolInterfaces (
                  &Handle,
                  &gEdkiiPlatformBootManagerProtocolGuid,
                  &mPlatformBootManager,
                  NULL
                  );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a: %r, the USB drives stay in the boot options\n", __func__, Status));
  }
}

EFI_HANDLE BootManagerEntryNotifyHandle1;
EFI_HANDLE BootManagerEntryNotifyHandle2;
EFI_HANDLE BootManagerContinueNotifyHandle;

VOID
PlatformUnregisterBootManagerEntryNotifyCallback (
  VOID
  )
{
  EFI_STATUS                         Status;
  EFI_SIMPLE_TEXT_INPUT_EX_PROTOCOL  *SimpleEx;

  Status = gBS->LocateProtocol (
                  &gEfiSimpleTextInputExProtocolGuid,
                  NULL,
                  (VOID **)&SimpleEx
                  );
  if (!EFI_ERROR (Status)) {
    Status = SimpleEx->UnregisterKeyNotify (SimpleEx, BootManagerEntryNotifyHandle1);
    Status = SimpleEx->UnregisterKeyNotify (SimpleEx, BootManagerEntryNotifyHandle2);
    Status = SimpleEx->UnregisterKeyNotify (SimpleEx, BootManagerContinueNotifyHandle);
  }
}

EFI_STATUS
EFIAPI
BootManagerContinueNotifyCallback (
  EFI_KEY_DATA *KeyData
  )
{
  //
  // The user chose to boot directly, so clear the boot prompt text just like
  // when entering the Boot Manager Menu.
  //
  BootLogoClearProgress ();

  return EFI_SUCCESS;
}

EFI_STATUS
EFIAPI
BootManagerEntryNotifyCallback (
  EFI_KEY_DATA *KeyData
  )
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  Black;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  White;

  //
  // We can't call UnregisterKeyNotify () from this handler,
  // so work around it by only updating the progress message once
  //
  static UINTN UpdateProgressMessage = 1;

  Black.Blue = Black.Green = Black.Red = Black.Reserved = 0;
  White.Blue = White.Green = White.Red = White.Reserved = 0xFF;

  if (UpdateProgressMessage) {
    BootLogoUpdateProgress (
      White,
      Black,
      L"Entering Setup, Please Wait...",
      White,
      0,
      0
      );
    UpdateProgressMessage = 0;
  }

  return EFI_SUCCESS;
}

VOID
PlatformRegisterBootManagerEntryNotifyCallback (
  VOID
  )
{
  EFI_STATUS                         Status;
  EFI_SIMPLE_TEXT_INPUT_EX_PROTOCOL  *SimpleEx;
  EFI_KEY_DATA                       KeyData;

  Status = gBS->LocateProtocol (
                  &gEfiSimpleTextInputExProtocolGuid,
                  NULL,
                  (VOID **)&SimpleEx
                  );
  if (EFI_ERROR (Status)) {
    return;
  }

  KeyData.Key.UnicodeChar         = CHAR_NULL;
  KeyData.KeyState.KeyShiftState  = 0;
  KeyData.KeyState.KeyToggleState = 0;

  if (FixedPcdGetBool (PcdBootManagerEscape)) {
    KeyData.Key.ScanCode = SCAN_ESC;
  } else {
    KeyData.Key.ScanCode = SCAN_F2;
  }

  Status = SimpleEx->RegisterKeyNotify (
                       SimpleEx,
                       &KeyData,
                       BootManagerEntryNotifyCallback,
                       &BootManagerEntryNotifyHandle1
                       );

  KeyData.Key.ScanCode = SCAN_DOWN;

  if (!EFI_ERROR (Status)) {
    Status = SimpleEx->RegisterKeyNotify (
                         SimpleEx,
                         &KeyData,
                         BootManagerEntryNotifyCallback,
                         &BootManagerEntryNotifyHandle2
                         );
  }

  //
  // Clear the boot prompt text when the user presses ENTER to boot directly.
  //
  KeyData.Key.ScanCode    = SCAN_NULL;
  KeyData.Key.UnicodeChar = CHAR_CARRIAGE_RETURN;

  if (!EFI_ERROR (Status)) {
    Status = SimpleEx->RegisterKeyNotify (
                         SimpleEx,
                         &KeyData,
                         BootManagerContinueNotifyCallback,
                         &BootManagerContinueNotifyHandle
                         );
  }
}

/**
  Do the platform specific action before the console is connected.

  Such as:
    Update console variable;
    Register new Driver#### or Boot####;
    Signal ReadyToLock event.
**/
VOID
EFIAPI
PlatformBootManagerBeforeConsole (
  VOID
  )
{
  EFI_INPUT_KEY                 Enter;
  EFI_INPUT_KEY                 CustomKey;
  EFI_INPUT_KEY                 Down;
  EFI_BOOT_MANAGER_LOAD_OPTION  BootOption;
  BOOLEAN                       ConsoleInitialized;

  //
  // Before any refresh of the boot options: the setup may keep the USB
  // drives out of them (usb_boot).
  //
  PlatformInstallUsbBootFilter ();

  //
  // Register ENTER as CONTINUE key
  //
  Enter.ScanCode    = SCAN_NULL;
  Enter.UnicodeChar = CHAR_CARRIAGE_RETURN;
  EfiBootManagerRegisterContinueKeyOption (0, &Enter, NULL);

  if (FixedPcdGetBool (PcdBootManagerEscape)) {
    //
    // Map Esc to Boot Manager Menu
    //
    CustomKey.ScanCode    = SCAN_ESC;
    CustomKey.UnicodeChar = CHAR_NULL;
  } else {
    //
    // Map Esc to Boot Manager Menu
    //
    CustomKey.ScanCode    = SCAN_F2;
    CustomKey.UnicodeChar = CHAR_NULL;
  }

  EfiBootManagerGetBootManagerMenu (&BootOption);
  EfiBootManagerAddKeyOptionVariable (NULL, (UINT16)BootOption.OptionNumber, 0, &CustomKey, NULL);

  //
  // Also add Down key to Boot Manager Menu since some serial terminals don't support F2 key.
  //
  Down.ScanCode    = SCAN_DOWN;
  Down.UnicodeChar = CHAR_NULL;
  EfiBootManagerGetBootManagerMenu (&BootOption);
  EfiBootManagerAddKeyOptionVariable (NULL, (UINT16)BootOption.OptionNumber, 0, &Down, NULL);

  //
  // Apply the update capsules of this boot, if any: the whole flash must not
  // stay writable for option ROMs, Driver#### options or an OS.
  //
  ConsoleInitialized = PlatformProcessCapsules ();

  //
  // Register a callback to show a message when the Boot Manager Menu hotkey is pressed.
  //
  PlatformRegisterBootManagerEntryNotifyCallback ();

  //
  // Before EndOfDxe closes Variable Policy: the report of the option lock
  // stays read-only to the OS (PlatformCapsule.c).
  //
  PlatformRegisterOptionLockPolicy ();

  //
  // Install ready to lock.
  // This needs to be done before option rom dispatched.
  //
  InstallReadyToLock ();

  //
  // Dispatch deferred images after EndOfDxe event and ReadyToLock installation.
  //
  EfiBootManagerDispatchDeferredImages ();

  if (!ConsoleInitialized) {
    PlatformConsoleInit ();
  }
}

/**
  Do the platform specific action after the console is connected.

  Such as:
    Dynamically switch output mode;
    Signal console ready platform customized event;
    Run diagnostics like memory testing;
    Connect certain devices;
    Dispatch additional option roms.
**/
VOID
EFIAPI
PlatformBootManagerAfterConsole (
  VOID
  )
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  Black;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  White;
  EFI_STATUS                     Status;

  Black.Blue = Black.Green = Black.Red = Black.Reserved = 0;
  White.Blue = White.Green = White.Red = White.Reserved = 0xFF;

  //
  // Custom splash needs filesystems connected first. Default (or disabled)
  // can draw immediately so ConnectAll console churn does not precede the logo.
  //
  if (BootSplashRequiresConnect ()) {
    EfiBootManagerConnectAll ();
    EfiBootManagerRefreshAllBootOption ();
    BootSplashApply ();
  } else {
    BootSplashApply ();
    EfiBootManagerConnectAll ();
    EfiBootManagerRefreshAllBootOption ();
  }

  //
  // The firmware boots: a new vboot slot is kept.
  //
  PlatformMarkFirmwareGood ();

  //
  // Process TPM PPI request
  //
  Status=TcgPhysicalPresenceLibProcessRequest (); // Check for TPM1.2 First
  if (EFI_ERROR (Status)) {
	  Tcg2PhysicalPresenceLibProcessRequest (NULL); //Check for TPM2.0
  }

  //
  // Register the UEFI Shell if the firmware volume has it; a build without
  // it (SHELL_TYPE NONE) deletes the option that an older one made, which
  // would only fail.
  //
  if (BdsGetFvFileDevicePath (&gUefiShellFileGuid) != NULL) {
    PlatformRegisterFvBootOption (&gUefiShellFileGuid, L"UEFI Shell", LOAD_OPTION_ACTIVE);
  } else {
    PlatformRemoveFvBootOption (&gUefiShellFileGuid);
  }

  //
  // Register iPXE if the binary is present in the firmware volume and the
  // setup has not turned it off (ipxe_boot); off, the option goes.
  //
  if ((PcdGetPtr (PcdiPXEFile) != NULL) && (PcdGetPtr (PcdiPXEOptionName) != NULL)) {
    if (PlatformSetupSwitch (L"ipxe_boot")) {
      PlatformRegisterFvBootOption (
        (EFI_GUID *)PcdGetPtr (PcdiPXEFile),
        (CHAR16 *)PcdGetPtr (PcdiPXEOptionName),
        LOAD_OPTION_ACTIVE
        );
    } else {
      PlatformRemoveFvBootOption ((EFI_GUID *)PcdGetPtr (PcdiPXEFile));
    }
  }

  //
  // Register CSMWrap, the legacy BIOS, if the binary is present in the
  // firmware volume, Secure Boot is off (a legacy BIOS runs unsigned code)
  // and the setup has not turned it off (csmwrap_boot); otherwise the
  // option goes.
  //
  if ((PcdGetPtr (PcdCsmWrapFile) != NULL) && (PcdGetPtr (PcdCsmWrapOptionName) != NULL)) {
    if (!PlatformSecureBootOn () && PlatformSetupSwitch (L"csmwrap_boot")) {
      PlatformRegisterFvBootOption (
        (EFI_GUID *)PcdGetPtr (PcdCsmWrapFile),
        (CHAR16 *)PcdGetPtr (PcdCsmWrapOptionName),
        LOAD_OPTION_ACTIVE
        );
    } else {
      PlatformRemoveFvBootOption ((EFI_GUID *)PcdGetPtr (PcdCsmWrapFile));
    }
  }

  //
  // The setup may hide the prompt (boot_menu_prompt); the keys registered
  // in PlatformBootManagerBeforeConsole() work either way.
  //
  if (PlatformSetupSwitch (L"boot_menu_prompt")) {
    if (FixedPcdGetBool (PcdBootManagerEscape)) {
      if (FixedPcdGetBool (PcdSerialTerminalPrintEnabled)) {
        Print (
          L"\n"
          L"    Esc              to enter Setup Option Menu.\n"
          L"    ENTER            to boot directly.\n"
          L"\n"
          );
      } else {
        BootLogoUpdateProgress (
          White,
          Black,
          L"Press ESC for Boot Options/Settings",
          White,
          0,
          0
          );
      }
    } else {
      if (FixedPcdGetBool (PcdSerialTerminalPrintEnabled)) {
        Print (
          L"\n"
          L"    F2 or Down      to enter Setup Option Menu.\n"
          L"    ENTER           to boot directly.\n"
          L"\n"
          );
      } else {
        BootLogoUpdateProgress (
          White,
          Black,
          L"Press F2 or Down for Boot Options/Settings",
          White,
          0,
          0
          );
      }
    }
  }
}

/**
  This function is called each second during the boot manager waits the timeout.

  @param TimeoutRemain  The remaining timeout.
**/
VOID
EFIAPI
PlatformBootManagerWaitCallback (
  UINT16  TimeoutRemain
  )
{
  if (TimeoutRemain == 0) {
    PlatformUnregisterBootManagerEntryNotifyCallback ();
    BootLogoClearProgress ();
  }

  return;
}

/**
  The function is called when no boot option could be launched,
  including platform recovery options and options pointing to applications
  built into firmware volumes.

  If this function returns, BDS attempts to enter an infinite loop.
**/
VOID
EFIAPI
PlatformBootManagerUnableToBoot (
  VOID
  )
{
  return;
}
