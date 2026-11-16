/** @file
  Arm the locks of the platform before an image that is not part of the
  firmware runs ahead of a boot.

  The payload arms coreboot's locks (the setup options, the switch to the
  other firmware slot) when a boot option is started, at ReadyToBoot, so that
  the setup, which runs before, can change what they protect. The boot
  manager also runs other code before that: the option ROMs of the devices,
  and the Driver#### and SysPrep#### load options, which an OS can create.
  Such an image ran with the locks open and could write the settings as the
  setup does, for the next boot.

  This Security2 handler sees every image before it is loaded. For the first
  one that does not come from a firmware volume, before ReadyToBoot, it arms
  the locks and signals gUefiPayloadThirdPartyImageEventGroupGuid. The setup
  then cannot save in that boot, and says so. So that it can save at all on
  a machine where such an image runs at every boot, a boot that the OS or the
  setup asked to end in the firmware setup (EFI_OS_INDICATIONS_BOOT_TO_FW_UI)
  refuses those images until a boot option is started: the locks stay open
  for the setup, and nothing but the firmware ran before it. But for one
  kind: the option ROM of a display controller is loaded in such a boot too,
  without arming anything, since on a machine without integrated graphics
  its driver is the screen of the setup. It comes from the flash of a card
  in the machine, not from a variable that an OS writes, and Secure Boot
  checks it when it is on.

  It is linked after DxeImageVerificationLib: an image that Secure Boot
  refuses does not get here, as the handlers run in the order in which they
  are registered and stop at the first that fails.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <PiDxe.h>
#include <Guid/EventGroup.h>
#include <Guid/GlobalVariable.h>
#include <Guid/ThirdPartyImage.h>
#include <IndustryStandard/Pci22.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/SecurityManagementLib.h>
#include <Library/SmmStoreLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Protocol/FirmwareVolume2.h>
#include <Protocol/PciIo.h>

//
// A boot option was started: the platform armed the locks itself.
//
STATIC BOOLEAN  mReadyToBoot;
//
// This boot was asked to end in the firmware setup.
//
STATIC BOOLEAN  mFirmwareUi;
//
// The locks were armed here.
//
STATIC BOOLEAN  mArmed;

/**
  Does the image come from a firmware volume? As DxeImageVerificationLib
  decides it (IMAGE_FROM_FV).

  @param[in] File  The device path of the image, or NULL.

  @retval TRUE   The device path leads to a firmware volume.
  @retval FALSE  It does not, or there is none.
**/
STATIC
BOOLEAN
ImageFromFirmwareVolume (
  IN CONST EFI_DEVICE_PATH_PROTOCOL  *File
  )
{
  EFI_STATUS                Status;
  EFI_HANDLE                DeviceHandle;
  EFI_DEVICE_PATH_PROTOCOL  *TempDevicePath;

  if (File == NULL) {
    return FALSE;
  }

  DeviceHandle   = NULL;
  TempDevicePath = (EFI_DEVICE_PATH_PROTOCOL *)File;
  Status         = gBS->LocateDevicePath (
                          &gEfiFirmwareVolume2ProtocolGuid,
                          &TempDevicePath,
                          &DeviceHandle
                          );
  if (EFI_ERROR (Status)) {
    return FALSE;
  }

  Status = gBS->OpenProtocol (
                  DeviceHandle,
                  &gEfiFirmwareVolume2ProtocolGuid,
                  NULL,
                  NULL,
                  NULL,
                  EFI_OPEN_PROTOCOL_TEST_PROTOCOL
                  );
  return (BOOLEAN)!EFI_ERROR (Status);
}

/**
  Is the image the driver in the option ROM of a display controller? PciBusDxe
  loads the images of an option ROM with the device path of the PCI device
  and one node after it, the range of the image in the ROM.

  @param[in] File  The device path of the image, or NULL.

  @retval TRUE   The device path is that of a PCI device of the display
                 class, then a relative offset range node.
  @retval FALSE  It is not.
**/
STATIC
BOOLEAN
ImageFromDisplayOptionRom (
  IN CONST EFI_DEVICE_PATH_PROTOCOL  *File
  )
{
  EFI_STATUS                Status;
  EFI_HANDLE                DeviceHandle;
  EFI_DEVICE_PATH_PROTOCOL  *Node;
  EFI_PCI_IO_PROTOCOL       *PciIo;
  UINT8                     BaseClass;

  if (File == NULL) {
    return FALSE;
  }

  DeviceHandle = NULL;
  Node         = (EFI_DEVICE_PATH_PROTOCOL *)File;
  Status       = gBS->LocateDevicePath (&gEfiPciIoProtocolGuid, &Node, &DeviceHandle);
  if (EFI_ERROR (Status) ||
      (DevicePathType (Node) != MEDIA_DEVICE_PATH) ||
      (DevicePathSubType (Node) != MEDIA_RELATIVE_OFFSET_RANGE_DP) ||
      !IsDevicePathEnd (NextDevicePathNode (Node)))
  {
    return FALSE;
  }

  Status = gBS->HandleProtocol (DeviceHandle, &gEfiPciIoProtocolGuid, (VOID **)&PciIo);
  if (EFI_ERROR (Status)) {
    return FALSE;
  }

  Status = PciIo->Pci.Read (PciIo, EfiPciIoWidthUint8, PCI_CLASSCODE_OFFSET + 2, 1, &BaseClass);
  return (BOOLEAN)(!EFI_ERROR (Status) && (BaseClass == PCI_CLASS_DISPLAY));
}

/**
  The Security2 handler: before a boot option is started, the first image
  that is not part of the firmware arms the locks, or is refused in a boot
  that goes to the firmware setup.

  The locks are armed here, with the SMIs of SmmStoreLib, and not by the
  modules that take the event: their notifications wait for the TPL to drop,
  and nothing says that it does before the image is started.

  @retval EFI_SUCCESS        The image may be loaded.
  @retval EFI_ACCESS_DENIED  Not part of the firmware, nor the option ROM of
                             a display controller, in a boot that goes to the
                             firmware setup: not loaded.
**/
STATIC
EFI_STATUS
EFIAPI
ThirdPartyImageLockHandler (
  IN  UINT32                          AuthenticationStatus,
  IN  CONST EFI_DEVICE_PATH_PROTOCOL  *File,
  IN  VOID                            *FileBuffer,
  IN  UINTN                           FileSize,
  IN  BOOLEAN                         BootPolicy
  )
{
  EFI_STATUS  Status;

  if (mReadyToBoot || ImageFromFirmwareVolume (File)) {
    return EFI_SUCCESS;
  }

  if (mFirmwareUi) {
    if (ImageFromDisplayOptionRom (File)) {
      DEBUG ((DEBUG_INFO, "ThirdPartyImageLockLib: the option ROM of a display controller, for the setup\n"));
      return EFI_SUCCESS;
    }

    DEBUG ((DEBUG_WARN, "ThirdPartyImageLockLib: image refused: this boot goes to the setup\n"));
    return EFI_ACCESS_DENIED;
  }

  if (mArmed) {
    return EFI_SUCCESS;
  }

  mArmed = TRUE;
  Status = SmmStoreLibInitialize ();
  if (!EFI_ERROR (Status)) {
    Status = SmmStoreLibVbootLockSlots ();
    DEBUG ((DEBUG_INFO, "ThirdPartyImageLockLib: switch to the other firmware slot locked: %r\n", Status));
    Status = SmmStoreLibOptionLock ();
    DEBUG ((DEBUG_INFO, "ThirdPartyImageLockLib: setup options write-locked: %r\n", Status));
  }

  EfiEventGroupSignal (&gUefiPayloadThirdPartyImageEventGroupGuid);
  return EFI_SUCCESS;
}

/**
  At EndOfDxe, before the boot manager loads anything that is not part of the
  firmware and before it clears the request: was this boot asked to end in
  the firmware setup?

  @param[in] Event    The event.
  @param[in] Context  Not used.
**/
STATIC
VOID
EFIAPI
ThirdPartyImageLockEndOfDxe (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  EFI_STATUS  Status;
  UINT64      OsIndications;
  UINTN       Size;

  OsIndications = 0;
  Size          = sizeof (OsIndications);
  Status        = gRT->GetVariable (
                         EFI_OS_INDICATIONS_VARIABLE_NAME,
                         &gEfiGlobalVariableGuid,
                         NULL,
                         &Size,
                         &OsIndications
                         );
  mFirmwareUi = (BOOLEAN)(!EFI_ERROR (Status) && (Size == sizeof (OsIndications)) &&
                          ((OsIndications & EFI_OS_INDICATIONS_BOOT_TO_FW_UI) != 0));
  gBS->CloseEvent (Event);
}

/**
  A boot option is started: from here the platform keeps the locks.

  @param[in] Event    The event.
  @param[in] Context  Not used.
**/
STATIC
VOID
EFIAPI
ThirdPartyImageLockReadyToBoot (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  mReadyToBoot = TRUE;
  gBS->CloseEvent (Event);
}

/**
  Register the handler for the images that are loaded, and the two events.
  Without the events no image is refused and the first one that is not part
  of the firmware arms the locks, which is the safe side of both.

  @param[in] ImageHandle  The image handle of the driver.
  @param[in] SystemTable  The EFI system table.

  @return The status of RegisterSecurity2Handler.
**/
EFI_STATUS
EFIAPI
ThirdPartyImageLockLibConstructor (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;
  EFI_EVENT   Event;

  Status = gBS->CreateEventEx (
                  EVT_NOTIFY_SIGNAL,
                  TPL_CALLBACK,
                  ThirdPartyImageLockEndOfDxe,
                  NULL,
                  &gEfiEndOfDxeEventGroupGuid,
                  &Event
                  );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "ThirdPartyImageLockLib: no EndOfDxe event: %r\n", Status));
  }

  Status = EfiCreateEventReadyToBootEx (TPL_CALLBACK, ThirdPartyImageLockReadyToBoot, NULL, &Event);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "ThirdPartyImageLockLib: no ReadyToBoot event: %r\n", Status));
  }

  return RegisterSecurity2Handler (ThirdPartyImageLockHandler, EFI_AUTH_OPERATION_VERIFY_IMAGE);
}
