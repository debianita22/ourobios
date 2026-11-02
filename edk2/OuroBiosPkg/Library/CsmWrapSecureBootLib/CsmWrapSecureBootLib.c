/** @file
  Refuse CSMWrap, the legacy BIOS in the firmware volume, while Secure Boot
  is on.

  Images from a firmware volume are not checked against the Secure Boot
  databases: DxeImageVerificationLib lets them run (IMAGE_FROM_FV,
  ALWAYS_EXECUTE). PlatformBootManagerLib deletes the CSMWrap boot option
  while Secure Boot is on, but a Boot#### or BootNext variable written from
  the OS can still name the file, and CSMWrap then starts unsigned code, a
  master boot record, before the OS. This Security2 handler denies the file
  whenever the SecureBoot variable is 1, however it is started.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Guid/GlobalVariable.h>
#include <Guid/ImageAuthentication.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/PcdLib.h>
#include <Library/SecurityManagementLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>

/**
  Does the device path name the CSMWrap file of a firmware volume?

  @param File   The device path of the image, or NULL.

  @retval TRUE   It has a firmware volume file node with PcdCsmWrapFile.
  @retval FALSE  It has not.
**/
STATIC
BOOLEAN
IsCsmWrap (
  IN CONST EFI_DEVICE_PATH_PROTOCOL  *File
  )
{
  CONST EFI_DEVICE_PATH_PROTOCOL  *Node;
  EFI_GUID                        *NameGuid;

  if (File == NULL) {
    return FALSE;
  }

  for (Node = File; !IsDevicePathEnd (Node); Node = NextDevicePathNode (Node)) {
    NameGuid = EfiGetNameGuidFromFwVolDevicePathNode ((CONST MEDIA_FW_VOL_FILEPATH_DEVICE_PATH *)Node);
    if ((NameGuid != NULL) && CompareGuid (NameGuid, (EFI_GUID *)PcdGetPtr (PcdCsmWrapFile))) {
      return TRUE;
    }
  }

  return FALSE;
}

/**
  Is Secure Boot on? The SecureBoot variable, as AuthVariableLib keeps it:
  1 with a platform key enrolled and Secure Boot enabled.

  @retval TRUE   On.
  @retval FALSE  Off, or no such variable.
**/
STATIC
BOOLEAN
SecureBootOn (
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
  The Security2 handler: CSMWrap is denied while Secure Boot is on, every
  other image goes on to the other handlers.

  @retval EFI_SUCCESS        Not CSMWrap, or Secure Boot is off.
  @retval EFI_ACCESS_DENIED  CSMWrap while Secure Boot is on: not loaded.
**/
STATIC
EFI_STATUS
EFIAPI
CsmWrapSecureBootHandler (
  IN  UINT32                          AuthenticationStatus,
  IN  CONST EFI_DEVICE_PATH_PROTOCOL  *File,
  IN  VOID                            *FileBuffer,
  IN  UINTN                           FileSize,
  IN  BOOLEAN                         BootPolicy
  )
{
  if (IsCsmWrap (File) && SecureBootOn ()) {
    DEBUG ((DEBUG_WARN, "CsmWrapSecureBootLib: CSMWrap refused: Secure Boot is on\n"));
    return EFI_ACCESS_DENIED;
  }

  return EFI_SUCCESS;
}

/**
  Register the handler for the images that are loaded.

  @param ImageHandle  The image handle of the driver.
  @param SystemTable  The EFI system table.

  @return The status of RegisterSecurity2Handler.
**/
EFI_STATUS
EFIAPI
CsmWrapSecureBootLibConstructor (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  return RegisterSecurity2Handler (
           CsmWrapSecureBootHandler,
           EFI_AUTH_OPERATION_VERIFY_IMAGE | EFI_AUTH_OPERATION_IMAGE_REQUIRED
           );
}
