/** @file
  TCG MOR (Memory Overwrite Request) of the coreboot payload, by the coreboot
  setup option "clear_dram_on_boot" (CFR, gEficorebootNvDataGuid).

  Only with "When the OS asks" (2) does the variable
  MemoryOverwriteRequestControl exist: coreboot reads it in ramstage and
  clears the memory before the payload when bit 0 is set, and this driver
  creates it and, as SecurityPkg's TcgMor does, clears bit 0 at ReadyToBoot,
  before the next OS starts. With the other settings coreboot clears the
  memory at every boot (Always, 1, the default) or never (Never, 0), whatever
  the OS asks: the variable is deleted and locked, as the variable driver
  without SMM does when the platform does not honor MOR, so that no OS counts
  on it. The setting counts only when this coreboot reads it: it lists the
  option in its setup data (CFR) and does not suppress it, which it does when
  built without SECURITY_CLEAR_DRAM_ON_REGULAR_BOOT; a setting that another
  firmware saved stays in SMMSTORE. The variable driver leaves MOR to this
  driver (PcdTcgMorWithoutSmm). It offers MemoryOverwriteRequestControlLock
  when this variable exists and coreboot keeps the lock in SMM
  (MorLockSmmStoreDxe: SMMSTORE_MOR_LOCK, with BIOS Lock on); otherwise the
  lock stays unsupported, as it cannot be made secure outside SMM.

  No TPer reset of self-encrypting drives here, unlike TcgMor.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Guid/CfrSetupMenuGuid.h>
#include <Guid/MemoryOverwriteControl.h>
#include <Library/CfrHelpersLib.h>
#include <Library/DebugLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/VariablePolicyHelperLib.h>
#include <Protocol/VariablePolicy.h>

//
// Values of clear_dram_on_boot (coreboot's security/memory/memory.c)
//
#define CLEAR_DRAM_ALWAYS      1
#define CLEAR_DRAM_OS_REQUEST  2

#define MOR_ATTRIBUTES  (EFI_VARIABLE_NON_VOLATILE | EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS)

/**
  The setting of clear_dram_on_boot, which CfrSetupMenuDxe keeps as a UINT32
  variable of gEficorebootNvDataGuid.

  @return The setting, CLEAR_DRAM_ALWAYS when there is none.
**/
STATIC
UINT32
MorClearDramMode (
  VOID
  )
{
  EFI_STATUS  Status;
  UINT32      Value;
  UINTN       Size;

  Size   = sizeof (Value);
  Status = gRT->GetVariable (L"clear_dram_on_boot", &gEficorebootNvDataGuid, NULL, &Size, &Value);
  if (EFI_ERROR (Status) || (Size != sizeof (Value))) {
    return CLEAR_DRAM_ALWAYS;
  }

  return Value;
}

/**
  Whether this coreboot reads clear_dram_on_boot: the option is in its setup
  data (CFR) and not suppressed.

  @retval TRUE   coreboot honors the setting.
  @retval FALSE  coreboot has no such option, or does not use it.
**/
STATIC
BOOLEAN
MorCorebootReadsSetting (
  VOID
  )
{
  VOID                *DefaultValue;
  CFR_OPTION_NUMERIC  *Option;

  if (EFI_ERROR (CfrOptionGetDefaultValue (NULL, "clear_dram_on_boot", &DefaultValue, NULL))) {
    return FALSE;
  }

  Option = BASE_CR (DefaultValue, CFR_OPTION_NUMERIC, default_value);
  return (Option->flags & CFR_OPTFLAG_SUPPRESS) == 0;
}

/**
  Clears bit 0 of MemoryOverwriteRequestControl before the OS starts: the
  memory was cleared by coreboot, and the OS sets the bit again while it
  holds secrets.

  @param[in]  Event    Event whose notification function is being invoked
  @param[in]  Context  Unused
**/
STATIC
VOID
EFIAPI
MorOnReadyToBoot (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  EFI_STATUS  Status;
  UINT8       Mor;
  UINTN       Size;

  gBS->CloseEvent (Event);

  Size   = sizeof (Mor);
  Status = gRT->GetVariable (MEMORY_OVERWRITE_REQUEST_VARIABLE_NAME, &gEfiMemoryOverwriteControlDataGuid, NULL, &Size, &Mor);
  if (EFI_ERROR (Status) || (Size != sizeof (Mor)) || (MOR_CLEAR_MEMORY_VALUE (Mor) == 0)) {
    return;
  }

  Mor   &= (UINT8)~MOR_CLEAR_MEMORY_BIT_MASK;
  Status = gRT->SetVariable (MEMORY_OVERWRITE_REQUEST_VARIABLE_NAME, &gEfiMemoryOverwriteControlDataGuid, MOR_ATTRIBUTES, sizeof (Mor), &Mor);
  DEBUG ((EFI_ERROR (Status) ? DEBUG_ERROR : DEBUG_INFO, "MorControlDxe: request of the OS cleared: %r\n", Status));
}

/**
  Creates, keeps or removes MemoryOverwriteRequestControl by the setting of
  clear_dram_on_boot.

  @param[in]  ImageHandle  The image handle of the driver
  @param[in]  SystemTable  The system table

  @retval EFI_SUCCESS  Always: without MOR the platform still boots
**/
EFI_STATUS
EFIAPI
MorControlDxeEntryPoint (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS                      Status;
  EDKII_VARIABLE_POLICY_PROTOCOL  *VariablePolicy;
  EFI_EVENT                       Event;
  UINT8                           Mor;
  UINTN                           Size;

  if ((MorClearDramMode () != CLEAR_DRAM_OS_REQUEST) || !MorCorebootReadsSetting ()) {
    //
    // Not honored: no variable, and none that the OS or another module can
    // create, as the variable driver does without PcdTcgMorWithoutSmm.
    //
    gRT->SetVariable (MEMORY_OVERWRITE_REQUEST_VARIABLE_NAME, &gEfiMemoryOverwriteControlDataGuid, 0, 0, NULL);
    Status = gBS->LocateProtocol (&gEdkiiVariablePolicyProtocolGuid, NULL, (VOID **)&VariablePolicy);
    if (!EFI_ERROR (Status)) {
      Status = RegisterBasicVariablePolicy (
                 VariablePolicy,
                 &gEfiMemoryOverwriteControlDataGuid,
                 MEMORY_OVERWRITE_REQUEST_VARIABLE_NAME,
                 VARIABLE_POLICY_NO_MIN_SIZE,
                 VARIABLE_POLICY_NO_MAX_SIZE,
                 VARIABLE_POLICY_NO_MUST_ATTR,
                 VARIABLE_POLICY_NO_CANT_ATTR,
                 VARIABLE_POLICY_TYPE_LOCK_NOW
                 );
    }

    DEBUG ((EFI_ERROR (Status) ? DEBUG_ERROR : DEBUG_INFO, "MorControlDxe: MOR not offered, locked: %r\n", Status));
    return EFI_SUCCESS;
  }

  Size   = sizeof (Mor);
  Status = gRT->GetVariable (MEMORY_OVERWRITE_REQUEST_VARIABLE_NAME, &gEfiMemoryOverwriteControlDataGuid, NULL, &Size, &Mor);
  if (EFI_ERROR (Status) || (Size != sizeof (Mor))) {
    //
    // A variable of another size is replaced, as TcgMor does with one it
    // cannot read
    //
    Mor    = 0;
    Status = gRT->SetVariable (MEMORY_OVERWRITE_REQUEST_VARIABLE_NAME, &gEfiMemoryOverwriteControlDataGuid, MOR_ATTRIBUTES, sizeof (Mor), &Mor);
    DEBUG ((EFI_ERROR (Status) ? DEBUG_ERROR : DEBUG_INFO, "MorControlDxe: MOR created: %r\n", Status));
    return EFI_SUCCESS;
  }

  DEBUG ((DEBUG_INFO, "MorControlDxe: MemoryOverwriteRequestControl 0x%02x\n", Mor));
  if (MOR_CLEAR_MEMORY_VALUE (Mor) != 0) {
    EfiCreateEventReadyToBootEx (TPL_CALLBACK, MorOnReadyToBoot, NULL, &Event);
  }

  return EFI_SUCCESS;
}
