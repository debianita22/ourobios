/** @file
  The lock of TCG Secure MOR (MemoryOverwriteRequestControlLock) of a
  coreboot payload: coreboot keeps it in SMM (SMMSTORE_CMD_MOR_LOCK) and,
  while it holds, refuses the writes of the variable store that would clear
  the request of the OS to clear the memory at the next boot. This driver
  gives it to the variable driver, which offers it to the OS, as
  EDKII_PLATFORM_MOR_LOCK_PROTOCOL.

  Installed only when coreboot keeps the lock in this boot: built with
  SMMSTORE_MOR_LOCK, and with the flash written by SMM alone (BIOS Lock on).
  Without it the variable driver reports the lock as unsupported, as before.

  Copyright (c) 2026, Domenico D'Arrigo. All rights reserved.<BR>
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Guid/EventGroup.h>
#include <Library/DebugLib.h>
#include <Library/SmmStoreLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeLib.h>
#include <Protocol/PlatformMorLock.h>

STATIC EFI_EVENT  mVirtualAddressChangeEvent;

/**
  Whether coreboot keeps the lock in this boot.

  @retval EFI_SUCCESS      It does.
  @retval EFI_UNSUPPORTED  It does not.
**/
STATIC
EFI_STATUS
EFIAPI
MorLockSupported (
  VOID
  )
{
  return EFI_ERROR (SmmStoreLibMorLock (SMMSTORE_MOR_LOCK_STATUS, NULL)) ? EFI_UNSUPPORTED : EFI_SUCCESS;
}

/**
  Lock until the next boot.

  @param[in] Key  EDKII_PLATFORM_MOR_LOCK_KEY_SIZE bytes, or NULL.

  @retval EFI_SUCCESS  Locked.
  @retval Others       Not locked.
**/
STATIC
EFI_STATUS
EFIAPI
MorLockLock (
  IN CONST UINT8  *Key OPTIONAL
  )
{
  return SmmStoreLibMorLock (Key == NULL ? SMMSTORE_MOR_LOCK_WITHOUT_KEY : SMMSTORE_MOR_LOCK_WITH_KEY, Key);
}

/**
  Unlock with the key of the lock.

  @param[in] Key  EDKII_PLATFORM_MOR_LOCK_KEY_SIZE bytes.

  @retval EFI_SUCCESS  Unlocked.
  @retval Others       Still locked.
**/
STATIC
EFI_STATUS
EFIAPI
MorLockUnlock (
  IN CONST UINT8  *Key
  )
{
  return SmmStoreLibMorLock (SMMSTORE_MOR_UNLOCK_WITH_KEY, Key);
}

STATIC EDKII_PLATFORM_MOR_LOCK_PROTOCOL  mPlatformMorLock = {
  MorLockSupported,
  MorLockLock,
  MorLockUnlock
};

/**
  The library and the protocol in virtual mode.

  @param[in]  Event    Event whose notification function is being invoked
  @param[in]  Context  Unused
**/
STATIC
VOID
EFIAPI
MorLockVirtualAddressChange (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  SmmStoreLibVirtualAddressChange (EfiConvertPointer);
  EfiConvertPointer (0x0, (VOID **)&mPlatformMorLock.Supported);
  EfiConvertPointer (0x0, (VOID **)&mPlatformMorLock.Lock);
  EfiConvertPointer (0x0, (VOID **)&mPlatformMorLock.Unlock);
}

/**
  Installs EDKII_PLATFORM_MOR_LOCK_PROTOCOL when coreboot keeps the lock.

  @param[in]  ImageHandle  The image handle of the driver
  @param[in]  SystemTable  The system table

  @retval EFI_SUCCESS      Installed.
  @retval EFI_UNSUPPORTED  No lock in this boot: the driver unloads.
**/
EFI_STATUS
EFIAPI
MorLockSmmStoreDxeEntryPoint (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  Handle;

  Status = SmmStoreLibInitialize ();
  if (EFI_ERROR (Status)) {
    return EFI_UNSUPPORTED;
  }

  Status = SmmStoreLibMorLock (SMMSTORE_MOR_LOCK_STATUS, NULL);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_INFO, "MorLockSmmStoreDxe: no MOR lock in coreboot this boot: %r\n", Status));
    SmmStoreLibDeinitialize ();
    return EFI_UNSUPPORTED;
  }

  Status = gBS->CreateEventEx (
                  EVT_NOTIFY_SIGNAL,
                  TPL_NOTIFY,
                  MorLockVirtualAddressChange,
                  NULL,
                  &gEfiEventVirtualAddressChangeGuid,
                  &mVirtualAddressChangeEvent
                  );
  if (EFI_ERROR (Status)) {
    SmmStoreLibDeinitialize ();
    return EFI_UNSUPPORTED;
  }

  Handle = NULL;
  Status = gBS->InstallProtocolInterface (
                  &Handle,
                  &gEdkiiPlatformMorLockProtocolGuid,
                  EFI_NATIVE_INTERFACE,
                  &mPlatformMorLock
                  );
  DEBUG ((DEBUG_INFO, "MorLockSmmStoreDxe: MOR lock of coreboot: %r\n", Status));
  if (EFI_ERROR (Status)) {
    gBS->CloseEvent (mVirtualAddressChangeEvent);
    SmmStoreLibDeinitialize ();
    return EFI_UNSUPPORTED;
  }

  return EFI_SUCCESS;
}
