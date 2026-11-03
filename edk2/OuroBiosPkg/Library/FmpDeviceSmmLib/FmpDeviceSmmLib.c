/** @file
  Provides firmware device specific services to support updates of a firmware
  image stored in a firmware device.

  This implementation uses SmmStoreLib to update the flash through coreboot's
  SMMSTORE handler, which serves the whole flash on a boot that starts with
  update capsules.  The image must carry an RMAP manifest (appended by
  AppendRmapManifest.py) naming the FMAP regions to write; each of them must
  be where the running firmware's FMAP has it, and one of the regions that
  PcdFmpDeviceSmmAllowedRegions lets an update write, if it names any.
  Everything else, in particular the regions written once per machine (the
  variable store, vital product data, event log) and the regions the flash
  descriptor protects, stays as it is.  An image without a manifest, or for
  another flash layout, is refused: such a firmware is installed with an
  external tool.

  A manifest with the two RW slots of vboot (RW_SECTION_A and RW_SECTION_B)
  updates only the slot that is not running, with the other regions it
  names, then asks vboot, in its nvdata in RW_NVRAM, to try that slot on the
  next boots: an update cut short, or a slot that does not verify or boot,
  leaves the old slot to boot from.  A flash with both slots is only
  updated that way: a manifest without them, or with one alone, is refused.

  Copyright (c) Microsoft Corporation.<BR>
  Copyright (c) 2018 - 2019, Intel Corporation. All rights reserved.<BR>
  Copyright (c) 2025, 3mdeb Sp. z o.o. All rights reserved.<BR>

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <PiDxe.h>
#include <Guid/FirmwareInfoGuid.h>
#include <Guid/SystemResourceTable.h>
#include <LastAttemptStatus.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/FmpDeviceLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PcdLib.h>
#include <Library/SmmStoreLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Coreboot.h>

#include "FmpDeviceSmmFlashRetry.h"
#include "FmpDeviceSmmManifest.h"
#include "FmpDeviceSmmStatus.h"
#include "FmpDeviceSmmUpdatePolicy.h"
#include "FmpDeviceSmmVboot.h"

//
// Minimal FMAP parsing to locate and compare the flash map before updating.
//
#define FMAP_SIGNATURE  "__FMAP__"
#define FMAP_VER_MAJOR  1
#define FMAP_NAME_LEN   32

#pragma pack(1)
typedef struct {
  CHAR8     Signature[8];
  UINT8     VerMajor;
  UINT8     VerMinor;
  UINT64    Base;
  UINT32    Size;
  CHAR8     Name[FMAP_NAME_LEN];
  UINT16    AreaCount;
} FMAP_HEADER;

typedef struct {
  UINT32    Offset;
  UINT32    Size;
  CHAR8     Name[FMAP_NAME_LEN];
  UINT16    Flags;
} FMAP_AREA;
#pragma pack()

#define SMMSTORE_FLASH_RETRY_STALL_US  500

//
// Last attempt status of this library, reported in the ESRT: the image has
// no manifest, an invalid one, or isn't the size of the flash; the regions
// of the manifest are not where the running firmware has them; the flash
// could not be written.
//
#define LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE    (LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MIN_ERROR_CODE_VALUE + 0)
#define LAST_ATTEMPT_STATUS_SMMSTORE_LAYOUT_MISMATCH  (LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MIN_ERROR_CODE_VALUE + 1)
#define LAST_ATTEMPT_STATUS_SMMSTORE_FLASH_FAILED     (LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MIN_ERROR_CODE_VALUE + 2)

//
// The two RW slots of vboot, as manifest region names.
//
STATIC CONST CHAR8  mVbootSlotNames[2][REGION_MANIFEST_NAME_LEN] = { "RW_SECTION_A", "RW_SECTION_B" };

/**
  Delay between flash operation attempts.

  @param[in] Attempt  Failed attempt number.
**/
STATIC
VOID
StallBetweenFlashAttempts (
  IN UINTN  Attempt
  )
{
  if ((gBS != NULL) && (gBS->Stall != NULL)) {
    gBS->Stall ((Attempt + 1) * SMMSTORE_FLASH_RETRY_STALL_US);
  }
}

/**
  Read bytes from flash.

  @param[in]     Lba       Flash block number.
  @param[in]     Offset    Offset within the block.
  @param[in,out] NumBytes  Requested and actual byte count.
  @param[out]    Buffer    Destination buffer.

  @return Status returned by SmmStoreLib.
**/
STATIC
EFI_STATUS
ReadAnyBlock (
  IN     EFI_LBA  Lba,
  IN     UINTN    Offset,
  IN OUT UINTN    *NumBytes,
  OUT    UINT8    *Buffer
  )
{
  return SmmStoreLibReadAnyBlock (Lba, Offset, NumBytes, Buffer);
}

/**
  Write bytes to flash.

  @param[in]     Lba       Flash block number.
  @param[in]     Offset    Offset within the block.
  @param[in,out] NumBytes  Requested and actual byte count.
  @param[in]     Buffer    Source buffer.

  @return Status returned by SmmStoreLib.
**/
STATIC
EFI_STATUS
WriteAnyBlock (
  IN     EFI_LBA  Lba,
  IN     UINTN    Offset,
  IN OUT UINTN    *NumBytes,
  IN     UINT8    *Buffer
  )
{
  return SmmStoreLibWriteAnyBlock (Lba, Offset, NumBytes, Buffer);
}

/**
  Erase a flash block.

  @param[in] Lba  Flash block number.

  @return Status returned by SmmStoreLib.
**/
STATIC
EFI_STATUS
EraseAnyBlock (
  IN EFI_LBA  Lba
  )
{
  return SmmStoreLibEraseAnyBlock (Lba);
}

STATIC CONST FMP_DEVICE_FLASH_IO  mFlashIo = {
  ReadAnyBlock,
  WriteAnyBlock,
  EraseAnyBlock,
  StallBetweenFlashAttempts
};

/**
  Read bytes from flash with retry handling.

  @param[in]     Lba       Flash block number.
  @param[in]     Offset    Offset within the block.
  @param[in,out] NumBytes  Requested and actual byte count.
  @param[out]    Buffer    Destination buffer.

  @return Status returned by the retry helper.
**/
STATIC
EFI_STATUS
ReadAnyBlockWithRetry (
  IN     EFI_LBA  Lba,
  IN     UINTN    Offset,
  IN OUT UINTN    *NumBytes,
  OUT    VOID     *Buffer
  )
{
  return FmpDeviceFlashReadWithRetry (&mFlashIo, Lba, Offset, NumBytes, Buffer);
}

/**
  Erase, write and verify a flash block with retry handling.

  @param[in]  Lba           Flash block number.
  @param[in]  Expected      Block contents to program.
  @param[out] VerifyBuffer  Scratch buffer for readback.
  @param[in]  BlockSize     Flash block size.

  @return Status returned by the retry helper.
**/
STATIC
EFI_STATUS
ProgramAnyBlockWithRetry (
  IN  EFI_LBA      Lba,
  IN  CONST UINT8  *Expected,
  OUT UINT8        *VerifyBuffer,
  IN  UINTN        BlockSize
  )
{
  return FmpDeviceFlashProgramWithRetry (&mFlashIo, Lba, Expected, VerifyBuffer, BlockSize);
}

STATIC
EFI_STATUS
ReadFlashRange (
  IN  UINTN  BlockSize,
  IN  UINTN  FlashSize,
  IN  UINTN  Offset,
  IN  UINTN  Length,
  OUT UINT8  *Buffer
  );

STATIC
EFI_STATUS
FindFmapRegion (
  IN  CONST FMAP_HEADER  *FmapHeader,
  IN  CONST FMAP_AREA    *Areas,
  IN  UINTN              AreaCount,
  IN  CONST CHAR8        Name[REGION_MANIFEST_NAME_LEN],
  OUT UINTN              *RegionOffset,
  OUT UINTN              *RegionSize
  );

/**
  Calculate the byte size of a validated FMAP.

  @param[in] FmapHeader  FMAP header.

  @return Size of the FMAP header and area table.
**/
STATIC
UINTN
FmapSize (
  IN CONST FMAP_HEADER  *FmapHeader
  )
{
  return sizeof (*FmapHeader) + ((UINTN)FmapHeader->AreaCount * sizeof (FMAP_AREA));
}

/**
  Check whether a character is printable in an FMAP name.

  @param[in] Character  Character to check.

  @retval TRUE   Character is printable.
  @retval FALSE  Character is not printable.
**/
STATIC
BOOLEAN
FmapIsGraph (
  IN CHAR8  Character
  )
{
  return (Character > ' ') && (Character <= '~');
}

/**
  Validate an FMAP name as a printable, NUL-terminated string.

  @param[in] Name  FMAP name to validate.

  @retval TRUE   The name is valid.
  @retval FALSE  The name is invalid.
**/
STATIC
BOOLEAN
FmapNameIsValid (
  IN CONST CHAR8  Name[FMAP_NAME_LEN]
  )
{
  UINTN  Index;

  for (Index = 0; Index < FMAP_NAME_LEN; ++Index) {
    if (Name[Index] == '\0') {
      return TRUE;
    }

    if (!FmapIsGraph (Name[Index])) {
      return FALSE;
    }
  }

  return FALSE;
}

/**
  This function requests firmware information on the first call, caches it and
  returns on all calls afterwards.

  @param[out] Info  Place to store a pointer to firmware information.

  @retval EFI_SUCCESS            Info points to firmware information.
  @retval EFI_INVALID_PARAMETER  Info is NULL.
**/
STATIC
EFI_STATUS
GetFwInfo (
  OUT FIRMWARE_INFO  **Info
  )
{
  STATIC FIRMWARE_INFO  Storage;
  STATIC BOOLEAN        Initialized;

  EFI_HOB_GUID_TYPE  *GuidHob;

  if (Info == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  if (!Initialized) {
    GuidHob = GetFirstGuidHob (&gEfiFirmwareInfoHobGuid);
    if (GuidHob == NULL) {
      DEBUG ((DEBUG_ERROR, "%a(): failed to query firmware information\n", __func__));
      return EFI_UNSUPPORTED;
    }

    Storage     = *(FIRMWARE_INFO *)GET_GUID_HOB_DATA (GuidHob);
    Initialized = TRUE;
  }

  *Info = &Storage;
  return EFI_SUCCESS;
}

/**
  Locate an FMAP header within a memory buffer.

  @param[in]  Image       Start of the buffer to scan.
  @param[in]  ImageSize   Size of the buffer.
  @param[out] FmapOffset  Offset of the FMAP header if found.
  @param[out] FmapLength  Total length of the FMAP (header + areas).

  @retval EFI_SUCCESS      FMAP was found and validated.
  @retval EFI_NOT_FOUND    FMAP not present or malformed.
**/
STATIC
EFI_STATUS
LocateFmapInImage (
  IN  CONST UINT8  *Image,
  IN  UINTN        ImageSize,
  OUT UINTN        *FmapOffset,
  OUT UINTN        *FmapLength
  )
{
  UINTN         Offset;
  CONST UINTN   HeaderSize = sizeof (FMAP_HEADER);
  CONST UINT32  MinAreas   = 1;
  UINTN         MapSize;

  if ((Image == NULL) || (FmapOffset == NULL) || (FmapLength == NULL)) {
    return EFI_NOT_FOUND;
  }

  if (ImageSize < HeaderSize) {
    return EFI_NOT_FOUND;
  }

  for (Offset = 0; Offset <= (ImageSize - HeaderSize); ++Offset) {
    CONST FMAP_HEADER  *Hdr = (CONST FMAP_HEADER *)(Image + Offset);

    if (CompareMem (Hdr->Signature, FMAP_SIGNATURE, sizeof (Hdr->Signature)) != 0) {
      continue;
    }

    if (Hdr->VerMajor != FMAP_VER_MAJOR) {
      continue;
    }

    MapSize = FmapSize (Hdr);
    if ((Hdr->AreaCount < MinAreas) || (Hdr->Size < MapSize)) {
      continue;
    }

    if (MapSize > (ImageSize - Offset)) {
      continue;
    }

    if (!FmapNameIsValid (Hdr->Name)) {
      continue;
    }

    *FmapOffset = Offset;
    *FmapLength = MapSize;
    return EFI_SUCCESS;
  }

  return EFI_NOT_FOUND;
}

/**
  Load the current flash FMAP using the capsule's FMAP "FMAP" area as a hint.

  This is used to detect layout changes between the image being flashed and the
  currently running firmware image.

  @param[in]  BlockSize           Flash block size.
  @param[in]  FlashSize           Total flash size.
  @param[in]  CapsuleFmapHeader   Pointer to FMAP header from the capsule image.
  @param[in]  CapsuleFmapAreas    Pointer to FMAP areas from the capsule image.
  @param[out] FlashFmapHeader     Pointer to FMAP header parsed from flash.
  @param[out] FlashFmapAreas      Pointer to FMAP areas parsed from flash.
  @param[out] FlashFmapBuffer     Allocated buffer that backs FlashFmapHeader/Areas.

  @retval EFI_SUCCESS            Flash FMAP was loaded and parsed successfully.
  @retval EFI_OUT_OF_RESOURCES   Failed to allocate required buffers.
  @retval EFI_NOT_FOUND          Flash FMAP could not be located/parsed.
  @retval EFI_DEVICE_ERROR       Flash read failed.
  @retval EFI_INVALID_PARAMETER  Invalid input parameters.
**/
STATIC
EFI_STATUS
LoadFlashFmap (
  IN  UINTN              BlockSize,
  IN  UINTN              FlashSize,
  IN  CONST FMAP_HEADER  *CapsuleFmapHeader,
  IN  CONST FMAP_AREA    *CapsuleFmapAreas,
  OUT FMAP_HEADER        **FlashFmapHeader,
  OUT FMAP_AREA          **FlashFmapAreas,
  OUT VOID               **FlashFmapBuffer
  )
{
  EFI_STATUS   Status;
  CONST CHAR8  FmapAreaName[16] = "FMAP";
  UINTN        FmapAreaOffset;
  UINTN        FmapAreaSize;
  VOID         *Buffer;
  UINTN        FoundOffset;
  UINTN        FoundLength;

  if ((CapsuleFmapHeader == NULL) || (CapsuleFmapAreas == NULL) || (FlashFmapHeader == NULL) || (FlashFmapAreas == NULL) || (FlashFmapBuffer == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  *FlashFmapHeader = NULL;
  *FlashFmapAreas  = NULL;
  *FlashFmapBuffer = NULL;

  Status = FindFmapRegion (
             CapsuleFmapHeader,
             CapsuleFmapAreas,
             CapsuleFmapHeader->AreaCount,
             FmapAreaName,
             &FmapAreaOffset,
             &FmapAreaSize
             );
  if (EFI_ERROR (Status) || (FmapAreaSize < sizeof (FMAP_HEADER))) {
    return EFI_NOT_FOUND;
  }

  Buffer = AllocatePool (FmapAreaSize);
  if (Buffer == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }

  Status = ReadFlashRange (BlockSize, FlashSize, FmapAreaOffset, FmapAreaSize, Buffer);
  if (EFI_ERROR (Status)) {
    FreePool (Buffer);
    return EFI_DEVICE_ERROR;
  }

  Status = LocateFmapInImage (Buffer, FmapAreaSize, &FoundOffset, &FoundLength);
  if (EFI_ERROR (Status) || (FoundOffset > FmapAreaSize) || (FoundLength > (FmapAreaSize - FoundOffset))) {
    FreePool (Buffer);
    return EFI_NOT_FOUND;
  }

  *FlashFmapHeader = (FMAP_HEADER *)((UINT8 *)Buffer + FoundOffset);
  *FlashFmapAreas  = (FMAP_AREA *)((UINT8 *)(*FlashFmapHeader) + sizeof (FMAP_HEADER));
  *FlashFmapBuffer = Buffer;
  return EFI_SUCCESS;
}

/**
  Find an FMAP area by name.

  @param[in]  FmapHeader     Pointer to FMAP header.
  @param[in]  Areas          Pointer to the first FMAP area.
  @param[in]  AreaCount      Number of FMAP areas.
  @param[in]  Name           Region name to look for (16-byte, zero padded).
  @param[out] RegionOffset   Flash offset of the region.
  @param[out] RegionSize     Size of the region.

  @retval EFI_SUCCESS     Region found.
  @retval EFI_NOT_FOUND   Region not found.
**/
STATIC
EFI_STATUS
FindFmapRegion (
  IN  CONST FMAP_HEADER  *FmapHeader,
  IN  CONST FMAP_AREA    *Areas,
  IN  UINTN              AreaCount,
  IN  CONST CHAR8        Name[16],
  OUT UINTN              *RegionOffset,
  OUT UINTN              *RegionSize
  )
{
  UINT64  Base;
  UINTN   Index;
  CHAR8   FmapName[33];
  CHAR8   ManifestName[REGION_MANIFEST_NAME_LEN + 1];

  if ((FmapHeader == NULL) || (Areas == NULL) || (Name == NULL) ||
      (RegionOffset == NULL) || (RegionSize == NULL))
  {
    return EFI_INVALID_PARAMETER;
  }

  for (Index = 0; Index < AreaCount; ++Index) {
    //
    // Manifest names are 16-byte, zero-padded strings, while FMAP uses 32-byte
    // names. Convert both to NUL-terminated strings and compare.
    //
    CopyMem (FmapName, Areas[Index].Name, 32);
    FmapName[32] = '\0';
    CopyMem (ManifestName, Name, REGION_MANIFEST_NAME_LEN);
    ManifestName[REGION_MANIFEST_NAME_LEN] = '\0';

    if (AsciiStrCmp (FmapName, ManifestName) != 0) {
      continue;
    }

    Base = FmapHeader->Base;
    if ((Base > MAX_UINTN) || (Areas[Index].Offset > (MAX_UINTN - (UINTN)Base))) {
      return EFI_COMPROMISED_DATA;
    }

    *RegionOffset = (UINTN)Base + Areas[Index].Offset;
    *RegionSize   = Areas[Index].Size;
    return EFI_SUCCESS;
  }

  return EFI_NOT_FOUND;
}

/**
  Provide a function to install the Firmware Management Protocol instance onto a
  device handle when the device is managed by a driver that follows the UEFI
  Driver Model.  If the device is not managed by a driver that follows the UEFI
  Driver Model, then EFI_UNSUPPORTED is returned.

  @param[in] FmpInstaller  Function that installs the Firmware Management
                           Protocol.

  @retval EFI_SUCCESS      The device is managed by a driver that follows the
                           UEFI Driver Model.  FmpInstaller must be called on
                           each Driver Binding Start().
  @retval EFI_UNSUPPORTED  The device is not managed by a driver that follows
                           the UEFI Driver Model.
  @retval other            The Firmware Management Protocol for this firmware
                           device is not installed.  The firmware device is
                           still locked using FmpDeviceLock().
**/
EFI_STATUS
EFIAPI
RegisterFmpInstaller (
  IN FMP_DEVICE_LIB_REGISTER_FMP_INSTALLER  Function
  )
{
  return EFI_UNSUPPORTED;
}

/**
  Provide a function to uninstall the Firmware Management Protocol instance from a
  device handle when the device is managed by a driver that follows the UEFI
  Driver Model.  If the device is not managed by a driver that follows the UEFI
  Driver Model, then EFI_UNSUPPORTED is returned.

  @param[in] FmpUninstaller  Function that installs the Firmware Management
                             Protocol.

  @retval EFI_SUCCESS      The device is managed by a driver that follows the
                           UEFI Driver Model.  FmpUninstaller must be called on
                           each Driver Binding Stop().
  @retval EFI_UNSUPPORTED  The device is not managed by a driver that follows
                           the UEFI Driver Model.
  @retval other            The Firmware Management Protocol for this firmware
                           device is not installed.  The firmware device is
                           still locked using FmpDeviceLock().
**/
EFI_STATUS
EFIAPI
RegisterFmpUninstaller (
  IN FMP_DEVICE_LIB_REGISTER_FMP_UNINSTALLER  Function
  )
{
  return EFI_UNSUPPORTED;
}

/**
  Set the device context for the FmpDeviceLib services when the device is
  managed by a driver that follows the UEFI Driver Model.  If the device is not
  managed by a driver that follows the UEFI Driver Model, then EFI_UNSUPPORTED
  is returned.  Once a device context is set, the FmpDeviceLib services
  operate on the currently set device context.

  @param[in]      Handle   Device handle for the FmpDeviceLib services.
                           If Handle is NULL, then Context is freed.
  @param[in, out] Context  Device context for the FmpDeviceLib services.
                           If Context is NULL, then a new context is allocated
                           for Handle and the current device context is set and
                           returned in Context.  If Context is not NULL, then
                           the current device context is set.

  @retval EFI_SUCCESS      The device is managed by a driver that follows the
                           UEFI Driver Model.
  @retval EFI_UNSUPPORTED  The device is not managed by a driver that follows
                           the UEFI Driver Model.
  @retval other            The Firmware Management Protocol for this firmware
                           device is not installed.  The firmware device is
                           still locked using FmpDeviceLock().
**/
EFI_STATUS
EFIAPI
FmpDeviceSetContext (
  IN EFI_HANDLE  Handle,
  IN OUT VOID    **Context
  )
{
  return EFI_UNSUPPORTED;
}

/**
  Returns the size, in bytes, of the firmware image currently stored in the
  firmware device.  This function is used to by the GetImage() and
  GetImageInfo() services of the Firmware Management Protocol.  If the image
  size can not be determined from the firmware device, then 0 must be returned.

  @param[out] Size  Pointer to the size, in bytes, of the firmware image
                    currently stored in the firmware device.

  @retval EFI_SUCCESS            The size of the firmware image currently
                                 stored in the firmware device was returned.
  @retval EFI_INVALID_PARAMETER  Size is NULL.
  @retval EFI_UNSUPPORTED        The firmware device does not support reporting
                                 the size of the currently stored firmware image.
  @retval EFI_DEVICE_ERROR       An error occurred attempting to determine the
                                 size of the firmware image currently stored in
                                 in the firmware device.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetSize (
  OUT UINTN  *Size
  )
{
  EFI_STATUS     Status;
  FIRMWARE_INFO  *FwInfo;

  if (Size == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  Status = GetFwInfo (&FwInfo);
  if (!EFI_ERROR (Status)) {
    *Size = FwInfo->ImageSize;
  }

  return Status;
}

/**
  Returns the GUID value used to fill in the ImageTypeId field of the
  EFI_FIRMWARE_IMAGE_DESCRIPTOR structure that is returned by the GetImageInfo()
  service of the Firmware Management Protocol.  If EFI_UNSUPPORTED is returned,
  then the ImageTypeId field is set to gEfiCallerIdGuid.  If EFI_SUCCESS is
  returned, then ImageTypeId is set to the Guid returned from this function.

  @param[out] Guid  Double pointer to a GUID value that is updated to point to
                    to a GUID value.  The GUID value is not allocated and must
                    not be modified or freed by the caller.

  @retval EFI_SUCCESS      EFI_FIRMWARE_IMAGE_DESCRIPTOR ImageTypeId GUID is set
                           to the returned Guid value.
  @retval EFI_UNSUPPORTED  EFI_FIRMWARE_IMAGE_DESCRIPTOR ImageTypeId GUID is set
                           to gEfiCallerIdGuid.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetImageTypeIdGuidPtr (
  OUT EFI_GUID  **Guid
  )
{
  EFI_STATUS     Status;
  FIRMWARE_INFO  *FwInfo;

  if (Guid == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  Status = GetFwInfo (&FwInfo);
  if (!EFI_ERROR (Status)) {
    *Guid = &FwInfo->Type;
  }

  return Status;
}

/**
  Returns values used to fill in the AttributesSupported and AttributesSettings
  fields of the EFI_FIRMWARE_IMAGE_DESCRIPTOR structure that is returned by the
  GetImageInfo() service of the Firmware Management Protocol.  The following
  bit values from the Firmware Management Protocol may be combined:
    IMAGE_ATTRIBUTE_IMAGE_UPDATABLE
    IMAGE_ATTRIBUTE_RESET_REQUIRED
    IMAGE_ATTRIBUTE_AUTHENTICATION_REQUIRED
    IMAGE_ATTRIBUTE_IN_USE
    IMAGE_ATTRIBUTE_UEFI_IMAGE

  @param[out] Supported  Attributes supported by this firmware device.
  @param[out] Setting    Attributes settings for this firmware device.

  @retval EFI_SUCCESS            The attributes supported by the firmware
                                 device were returned.
  @retval EFI_INVALID_PARAMETER  Supported is NULL.
  @retval EFI_INVALID_PARAMETER  Setting is NULL.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetAttributes (
  OUT UINT64  *Supported,
  OUT UINT64  *Setting
  )
{
  if ((Supported == NULL) || (Setting == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  *Supported = IMAGE_ATTRIBUTE_IMAGE_UPDATABLE |
               IMAGE_ATTRIBUTE_RESET_REQUIRED |
               IMAGE_ATTRIBUTE_AUTHENTICATION_REQUIRED |
               IMAGE_ATTRIBUTE_IN_USE;
  *Setting = *Supported;
  return EFI_SUCCESS;
}

/**
  Returns the value used to fill in the LowestSupportedVersion field of the
  EFI_FIRMWARE_IMAGE_DESCRIPTOR structure that is returned by the GetImageInfo()
  service of the Firmware Management Protocol.  If EFI_SUCCESS is returned, then
  the firmware device supports a method to report the LowestSupportedVersion
  value from the currently stored firmware image.  If the value can not be
  reported for the firmware image currently stored in the firmware device, then
  EFI_UNSUPPORTED must be returned.  EFI_DEVICE_ERROR is returned if an error
  occurs attempting to retrieve the LowestSupportedVersion value for the
  currently stored firmware image.

  @note It is recommended that all firmware devices support a method to report
        the LowestSupportedVersion value from the currently stored firmware
        image.

  @param[out] LowestSupportedVersion  LowestSupportedVersion value retrieved
                                      from the currently stored firmware image.

  @retval EFI_SUCCESS       The lowest supported version of currently stored
                            firmware image was returned in LowestSupportedVersion.
  @retval EFI_UNSUPPORTED   The firmware device does not support a method to
                            report the lowest supported version of the currently
                            stored firmware image.
  @retval EFI_DEVICE_ERROR  An error occurred attempting to retrieve the lowest
                            supported version of the currently stored firmware
                            image.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetLowestSupportedVersion (
  OUT UINT32  *LowestSupportedVersion
  )
{
  EFI_STATUS     Status;
  FIRMWARE_INFO  *FwInfo;

  if (LowestSupportedVersion == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  Status = GetFwInfo (&FwInfo);
  if (!EFI_ERROR (Status)) {
    *LowestSupportedVersion = FwInfo->LowestSupportedVersion;
  }

  return Status;
}

/**
  Returns the Null-terminated Unicode string that is used to fill in the
  VersionName field of the EFI_FIRMWARE_IMAGE_DESCRIPTOR structure that is
  returned by the GetImageInfo() service of the Firmware Management Protocol.
  The returned string must be allocated using EFI_BOOT_SERVICES.AllocatePool().

  @note It is recommended that all firmware devices support a method to report
        the VersionName string from the currently stored firmware image.

  @param[out] VersionString  The version string retrieved from the currently
                             stored firmware image.

  @retval EFI_SUCCESS            The version string of currently stored
                                 firmware image was returned in Version.
  @retval EFI_INVALID_PARAMETER  VersionString is NULL.
  @retval EFI_UNSUPPORTED        The firmware device does not support a method
                                 to report the version string of the currently
                                 stored firmware image.
  @retval EFI_DEVICE_ERROR       An error occurred attempting to retrieve the
                                 version string of the currently stored
                                 firmware image.
  @retval EFI_OUT_OF_RESOURCES   There are not enough resources to allocate the
                                 buffer for the version string of the currently
                                 stored firmware image.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetVersionString (
  OUT CHAR16  **VersionString
  )
{
  EFI_STATUS     Status;
  FIRMWARE_INFO  *FwInfo;

  if (VersionString == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  Status = GetFwInfo (&FwInfo);
  if (!EFI_ERROR (Status)) {
    *VersionString = (CHAR16 *)AllocateCopyPool (
                                 sizeof (FwInfo->VersionStr),
                                 FwInfo->VersionStr
                                 );
    if (*VersionString == NULL) {
      Status = EFI_OUT_OF_RESOURCES;
    }
  }

  return Status;
}

/**
  Returns the value used to fill in the Version field of the
  EFI_FIRMWARE_IMAGE_DESCRIPTOR structure that is returned by the GetImageInfo()
  service of the Firmware Management Protocol.  If EFI_SUCCESS is returned, then
  the firmware device supports a method to report the Version value from the
  currently stored firmware image.  If the value can not be reported for the
  firmware image currently stored in the firmware device, then EFI_UNSUPPORTED
  must be returned.  EFI_DEVICE_ERROR is returned if an error occurs attempting
  to retrieve the LowestSupportedVersion value for the currently stored firmware
  image.

  @note It is recommended that all firmware devices support a method to report
        the Version value from the currently stored firmware image.

  @param[out] Version  The version value retrieved from the currently stored
                       firmware image.

  @retval EFI_SUCCESS       The version of currently stored firmware image was
                            returned in Version.
  @retval EFI_UNSUPPORTED   The firmware device does not support a method to
                            report the version of the currently stored firmware
                            image.
  @retval EFI_DEVICE_ERROR  An error occurred attempting to retrieve the version
                            of the currently stored firmware image.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetVersion (
  OUT UINT32  *Version
  )
{
  EFI_STATUS     Status;
  FIRMWARE_INFO  *FwInfo;

  if (Version == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  Status = GetFwInfo (&FwInfo);
  if (!EFI_ERROR (Status)) {
    *Version = FwInfo->Version;
  }

  return Status;
}

/**
  Returns the value used to fill in the HardwareInstance field of the
  EFI_FIRMWARE_IMAGE_DESCRIPTOR structure that is returned by the GetImageInfo()
  service of the Firmware Management Protocol.  If EFI_SUCCESS is returned, then
  the firmware device supports a method to report the HardwareInstance value.
  If the value can not be reported for the firmware device, then EFI_UNSUPPORTED
  must be returned.  EFI_DEVICE_ERROR is returned if an error occurs attempting
  to retrieve the HardwareInstance value for the firmware device.

  @param[out] HardwareInstance  The hardware instance value for the firmware
                                device.

  @retval EFI_SUCCESS       The hardware instance for the current firmware
                            device is returned in HardwareInstance.
  @retval EFI_UNSUPPORTED   The firmware device does not support a method to
                            report the hardware instance value.
  @retval EFI_DEVICE_ERROR  An error occurred attempting to retrieve the hardware
                            instance value.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetHardwareInstance (
  OUT UINT64  *HardwareInstance
  )
{
  if (HardwareInstance == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  *HardwareInstance = 0;
  return EFI_SUCCESS;
}

/**
  Returns a copy of the firmware image currently stored in the firmware device.

  @note It is recommended that all firmware devices support a method to retrieve
        a copy currently stored firmware image.  This can be used to support
        features such as recovery and rollback.

  @param[out]     Image     Pointer to a caller allocated buffer where the
                            currently stored firmware image is copied to.
  @param[in, out] ImageSize Pointer the size, in bytes, of the Image buffer.
                            On return, points to the size, in bytes, of firmware
                            image currently stored in the firmware device.

  @retval EFI_SUCCESS            Image contains a copy of the firmware image
                                 currently stored in the firmware device, and
                                 ImageSize contains the size, in bytes, of the
                                 firmware image currently stored in the
                                 firmware device.
  @retval EFI_BUFFER_TOO_SMALL   The buffer specified by ImageSize is too small
                                 to hold the firmware image currently stored in
                                 the firmware device. The buffer size required
                                 is returned in ImageSize.
  @retval EFI_INVALID_PARAMETER  The Image is NULL.
  @retval EFI_INVALID_PARAMETER  The ImageSize is NULL.
  @retval EFI_UNSUPPORTED        The operation is not supported.
  @retval EFI_DEVICE_ERROR       An error occurred attempting to retrieve the
                                 firmware image currently stored in the firmware
                                 device.
**/
EFI_STATUS
EFIAPI
FmpDeviceGetImage (
  OUT    VOID   *Image,
  IN OUT UINTN  *ImageSize
  )
{
  //
  // This seems useful only if FMP device is part of the running firmware.
  //
  return EFI_UNSUPPORTED;
}

/**
  Whether the platform lets an update write every region of a manifest
  (PcdFmpDeviceSmmAllowedRegions).

  @param[in] Entries     Manifest entries.
  @param[in] EntryCount  Number of entries.

  @retval TRUE   Every region may be written.
  @retval FALSE  A region may not: the image is refused.
**/
STATIC
BOOLEAN
ManifestRegionsAllowed (
  IN CONST REGION_MANIFEST_ENTRY  *Entries,
  IN UINTN                        EntryCount
  )
{
  EFI_STATUS  Status;
  UINTN       Refused;
  CHAR8       RegionName[REGION_MANIFEST_NAME_LEN + 1];

  Status = FmpDeviceCheckManifestRegions (
             Entries,
             EntryCount,
             (CONST CHAR8 *)PcdGetPtr (PcdFmpDeviceSmmAllowedRegions),
             &Refused
             );
  if (Status == EFI_ACCESS_DENIED) {
    CopyMem (RegionName, Entries[Refused].RegionName, REGION_MANIFEST_NAME_LEN);
    RegionName[REGION_MANIFEST_NAME_LEN] = '\0';
    DEBUG ((
      DEBUG_ERROR,
      "%a(): manifest region '%a' is not one an update may write (PcdFmpDeviceSmmAllowedRegions)\n",
      __func__,
      RegionName
      ));
  } else if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a(): manifest regions not checked: %r\n", __func__, Status));
  }

  return !EFI_ERROR (Status);
}

/**
  Checks if a new firmware image is valid for the firmware device.  This
  function allows firmware update operation to validate the firmware image
  before FmpDeviceSetImage() is called.

  @param[in]  Image           Points to a new firmware image.
  @param[in]  ImageSize       Size, in bytes, of a new firmware image.
  @param[out] ImageUpdatable  Indicates if a new firmware image is valid for
                              a firmware update to the firmware device.  The
                              following values from the Firmware Management
                              Protocol are supported:
                                IMAGE_UPDATABLE_VALID
                                IMAGE_UPDATABLE_INVALID
                                IMAGE_UPDATABLE_INVALID_TYPE
                                IMAGE_UPDATABLE_INVALID_OLD
                                IMAGE_UPDATABLE_VALID_WITH_VENDOR_CODE

  @retval EFI_SUCCESS            The image was successfully checked.  Additional
                                 status information is returned in
                                 ImageUpdatable.
  @retval EFI_INVALID_PARAMETER  Image is NULL.
  @retval EFI_INVALID_PARAMETER  ImageUpdatable is NULL.
**/
EFI_STATUS
EFIAPI
FmpDeviceCheckImage (
  IN  CONST VOID  *Image,
  IN  UINTN       ImageSize,
  OUT UINT32      *ImageUpdatable
  )
{
  UINT32  LastAttemptStatus;

  return FmpDeviceCheckImageWithStatus (Image, ImageSize, ImageUpdatable, &LastAttemptStatus);
}

/**
  Checks if a new firmware image is valid for the firmware device.  This
  function allows firmware update operation to validate the firmware image
  before FmpDeviceSetImage() is called.

  @param[in]  Image               Points to a new firmware image.
  @param[in]  ImageSize           Size, in bytes, of a new firmware image.
  @param[out] ImageUpdatable      Indicates if a new firmware image is valid for
                                  a firmware update to the firmware device.  The
                                  following values from the Firmware Management
                                  Protocol are supported:
                                    IMAGE_UPDATABLE_VALID
                                    IMAGE_UPDATABLE_INVALID
                                    IMAGE_UPDATABLE_INVALID_TYPE
                                    IMAGE_UPDATABLE_INVALID_OLD
                                    IMAGE_UPDATABLE_VALID_WITH_VENDOR_CODE
  @param[out] LastAttemptStatus   A pointer to a UINT32 that holds the last attempt
                                  status to report back to the ESRT table in case
                                  of error.

                                  The return status code must fall in the range of
                                  LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MIN_ERROR_CODE_VALUE to
                                  LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MAX_ERROR_CODE_VALUE.

                                  If the value falls outside this range, it will be converted
                                  to LAST_ATTEMPT_STATUS_ERROR_UNSUCCESSFUL.

  @retval EFI_SUCCESS            The image was successfully checked.  Additional
                                 status information is returned in
                                 ImageUpdatable.
  @retval EFI_INVALID_PARAMETER  Image is NULL.
  @retval EFI_INVALID_PARAMETER  ImageUpdatable is NULL.
**/
EFI_STATUS
EFIAPI
FmpDeviceCheckImageWithStatus (
  IN  CONST VOID  *Image,
  IN  UINTN       ImageSize,
  OUT UINT32      *ImageUpdatable,
  OUT UINT32      *LastAttemptStatus
  )
{
  EFI_STATUS                   Status;
  UINTN                        FwSize;
  UINTN                        BlockSize;
  UINTN                        ManifestEntries;
  UINTN                        FirmwareImageSize;
  CONST REGION_MANIFEST_ENTRY  *ManifestList;

  if ((Image == NULL) || (ImageUpdatable == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  *LastAttemptStatus = LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE;
  *ImageUpdatable    = IMAGE_UPDATABLE_INVALID;

  Status = FmpDeviceGetSize (&FwSize);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a(): FmpDeviceGetSize() failed with: %r\n", __func__, Status));
    return Status;
  }

  FirmwareImageSize = ImageSize;
  ManifestList      = NULL;
  ManifestEntries   = 0;

  Status = FmpDeviceLocateRegionManifest (
             Image,
             ImageSize,
             &ManifestEntries,
             &ManifestList,
             &FirmwareImageSize
             );
  if (Status == EFI_NOT_FOUND) {
    //
    // Without a manifest the whole flash would be rewritten, the regions
    // that belong to the machine included: refuse the image.
    //
    DEBUG ((DEBUG_ERROR, "%a(): image without a region manifest\n", __func__));
    return EFI_ABORTED;
  } else if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a(): invalid region manifest: %r\n", __func__, Status));
    return EFI_ABORTED;
  } else if (FirmwareImageSize != FwSize) {
    DEBUG ((
      DEBUG_ERROR,
      "%a(): manifest image size (0x%x) doesn't match firmware size (0x%x)\n",
      __func__,
      FirmwareImageSize,
      FwSize
      ));
    return EFI_ABORTED;
  }

  if (!ManifestRegionsAllowed (ManifestList, ManifestEntries)) {
    return EFI_ABORTED;
  }

  Status = SmmStoreLibGetBlockSize (&BlockSize);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a(): SmmStoreLibGetBlockSize() failed with: %r\n", __func__, Status));
    return Status;
  }

  if (FwSize % BlockSize != 0) {
    DEBUG ((
      DEBUG_ERROR,
      "%a(): firmware size (0x%x) is not a multiple of block size (0x%x)\n",
      __func__,
      FwSize,
      BlockSize
      ));
    return EFI_ABORTED;
  }

  *LastAttemptStatus = LAST_ATTEMPT_STATUS_SUCCESS;
  *ImageUpdatable    = IMAGE_UPDATABLE_VALID;
  return EFI_SUCCESS;
}

/**
  Updates a firmware device with a new firmware image.  This function returns
  EFI_UNSUPPORTED if the firmware image is not updatable.  If the firmware image
  is updatable, the function should perform the following minimal validations
  before proceeding to do the firmware image update.
    - Validate that the image is a supported image for this firmware device.
      Return EFI_ABORTED if the image is not supported.  Additional details
      on why the image is not a supported image may be returned in AbortReason.
    - Validate the data from VendorCode if is not NULL.  Firmware image
      validation must be performed before VendorCode data validation.
      VendorCode data is ignored or considered invalid if image validation
      fails.  Return EFI_ABORTED if the VendorCode data is invalid.

  VendorCode enables vendor to implement vendor-specific firmware image update
  policy.  Null if the caller did not specify the policy or use the default
  policy.  As an example, vendor can implement a policy to allow an option to
  force a firmware image update when the abort reason is due to the new firmware
  image version is older than the current firmware image version or bad image
  checksum.  Sensitive operations such as those wiping the entire firmware image
  and render the device to be non-functional should be encoded in the image
  itself rather than passed with the VendorCode.  AbortReason enables vendor to
  have the option to provide a more detailed description of the abort reason to
  the caller.

  @param[in]  Image             Points to the new firmware image.
  @param[in]  ImageSize         Size, in bytes, of the new firmware image.
  @param[in]  VendorCode        This enables vendor to implement vendor-specific
                                firmware image update policy.  NULL indicates
                                the caller did not specify the policy or use the
                                default policy.
  @param[in]  Progress          A function used to report the progress of
                                updating the firmware device with the new
                                firmware image.
  @param[in]  CapsuleFwVersion  The version of the new firmware image from the
                                update capsule that provided the new firmware
                                image.
  @param[out] AbortReason       A pointer to a pointer to a Null-terminated
                                Unicode string providing more details on an
                                aborted operation. The buffer is allocated by
                                this function with
                                EFI_BOOT_SERVICES.AllocatePool().  It is the
                                caller's responsibility to free this buffer with
                                EFI_BOOT_SERVICES.FreePool().

  @retval EFI_SUCCESS            The firmware device was successfully updated
                                 with the new firmware image.
  @retval EFI_ABORTED            The operation is aborted.  Additional details
                                 are provided in AbortReason.
  @retval EFI_INVALID_PARAMETER  The Image was NULL.
  @retval EFI_UNSUPPORTED        The operation is not supported.
**/
EFI_STATUS
EFIAPI
FmpDeviceSetImage (
  IN  CONST VOID                                     *Image,
  IN  UINTN                                          ImageSize,
  IN  CONST VOID                                     *VendorCode        OPTIONAL,
  IN  EFI_FIRMWARE_MANAGEMENT_UPDATE_IMAGE_PROGRESS  Progress           OPTIONAL,
  IN  UINT32                                         CapsuleFwVersion,
  OUT CHAR16                                         **AbortReason
  )
{
  UINT32  LastAttemptStatus;

  return FmpDeviceSetImageWithStatus (
           Image,
           ImageSize,
           VendorCode,
           Progress,
           CapsuleFwVersion,
           AbortReason,
           &LastAttemptStatus
           );
}

/**
  Advances progress of the operation by a single step, converts the steps to
  percents and invokes a callback if there is one.

  @param[in]      Callback              External callback for progress reporting
                                        or NULL if there is none.
  @param[in]      TotalSteps            Total number of flashing steps.
  @param[in, out] Step                  Current step number.
  @param[in, out] ShouldReportProgress  A flag indicating whether progress needs
                                        to be reported.
**/
STATIC
VOID
IncrementProgress (
  IN      EFI_FIRMWARE_MANAGEMENT_UPDATE_IMAGE_PROGRESS  Callback OPTIONAL,
  IN      UINTN                                          TotalSteps,
  IN OUT  UINTN                                          *Step,
  IN OUT  BOOLEAN                                        *ShouldReportProgress
  )
{
  EFI_STATUS  Status;
  UINTN       Progress;

  if (!*ShouldReportProgress) {
    return;
  }

  if (Callback == NULL) {
    *ShouldReportProgress = FALSE;
    return;
  }

  ++*Step;
  Progress = (*Step * 100) / TotalSteps;

  //
  // Value of 0 means "progress reporting is not supported", so avoid using it.
  //
  if (Progress == 0) {
    Progress = 1;
  }

  Status = Callback (Progress);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "%a(): progress callback failed with: %r\n", __func__, Status));
    *ShouldReportProgress = FALSE;
  }
}

/**
  Read an arbitrary flash range into a buffer.

  @param[in]  BlockSize  Flash block size, in bytes.
  @param[in]  FlashSize  Total flash size, in bytes.
  @param[in]  Offset     Offset from the start of flash, in bytes.
  @param[in]  Length     Number of bytes to read.
  @param[out] Buffer     Destination buffer for the flash contents.

  @retval EFI_SUCCESS            The range was read successfully.
  @retval EFI_DEVICE_ERROR       A read failed.
  @retval EFI_INVALID_PARAMETER  Input parameters were invalid.
**/
STATIC
EFI_STATUS
ReadFlashRange (
  IN  UINTN  BlockSize,
  IN  UINTN  FlashSize,
  IN  UINTN  Offset,
  IN  UINTN  Length,
  OUT UINT8  *Buffer
  )
{
  EFI_STATUS  Status;
  UINTN       Remaining;
  UINTN       Cursor;

  if ((Buffer == NULL) || (BlockSize == 0)) {
    return EFI_INVALID_PARAMETER;
  }

  if (Length == 0) {
    return EFI_SUCCESS;
  }

  if ((Offset >= FlashSize) || (Length > (FlashSize - Offset))) {
    return EFI_INVALID_PARAMETER;
  }

  Remaining = Length;
  Cursor    = 0;

  while (Remaining > 0) {
    UINTN  Lba;
    UINTN  OffsetInBlock;
    UINTN  Chunk;
    UINTN  NumBytes;

    Lba           = (Offset + Cursor) / BlockSize;
    OffsetInBlock = (Offset + Cursor) % BlockSize;
    Chunk         = MIN (Remaining, BlockSize - OffsetInBlock);

    NumBytes = Chunk;
    Status   = ReadAnyBlockWithRetry (Lba, OffsetInBlock, &NumBytes, Buffer + Cursor);
    if (EFI_ERROR (Status) || (NumBytes != Chunk)) {
      return EFI_DEVICE_ERROR;
    }

    Cursor    += Chunk;
    Remaining -= Chunk;
  }

  return EFI_SUCCESS;
}

/**
  Update a flash range using Image as the source.

  This helper preserves bytes outside the requested range within any partially
  covered flash block by read-modify-writing the full block.

  @param[in]      BlockSize            Flash block size, in bytes.
  @param[in]      Image                Source image buffer.
  @param[in]      ImageSize            Size of Image, in bytes.
  @param[in]      RangeOffset          Offset within Image for the update range, in bytes.
  @param[in]      RangeSize            Size of the update range, in bytes.
  @param[in,out]  BlockBuffer          Scratch buffer, at least BlockSize bytes.
  @param[out]     VerifyBuffer         Scratch buffer for flash readback.
  @param[in]      Progress             Optional progress callback.
  @param[in]      TotalSteps           Total number of progress reporting steps.
  @param[in,out]  Step                 Current step counter for progress reporting.
  @param[in,out]  ShouldReportProgress Progress reporting enabled flag.

  @retval EFI_SUCCESS            The range was updated successfully.
  @retval EFI_DEVICE_ERROR       A read/erase/write failed.
  @retval EFI_INVALID_PARAMETER  Input parameters were invalid.
**/
STATIC
EFI_STATUS
UpdateFlashRangeFromImage (
  IN      UINTN                                          BlockSize,
  IN      CONST UINT8                                    *Image,
  IN      UINTN                                          ImageSize,
  IN      UINTN                                          RangeOffset,
  IN      UINTN                                          RangeSize,
  IN OUT  VOID                                           *BlockBuffer,
  OUT     VOID                                           *VerifyBuffer,
  IN      EFI_FIRMWARE_MANAGEMENT_UPDATE_IMAGE_PROGRESS  Progress OPTIONAL,
  IN      UINTN                                          TotalSteps,
  IN OUT  UINTN                                          *Step,
  IN OUT  BOOLEAN                                        *ShouldReportProgress
  )
{
  EFI_STATUS  Status;
  UINTN       Offset;
  UINTN       RangeEnd;
  UINTN       Segment;

  if ((Image == NULL) || (BlockBuffer == NULL) || (VerifyBuffer == NULL) || (Step == NULL) || (ShouldReportProgress == NULL) || (BlockSize == 0)) {
    return EFI_INVALID_PARAMETER;
  }

  if (RangeSize == 0) {
    return EFI_SUCCESS;
  }

  if ((RangeOffset + RangeSize) > ImageSize) {
    return EFI_INVALID_PARAMETER;
  }

  RangeEnd = RangeOffset + RangeSize;
  Segment  = 0;

  for (Offset = RangeOffset; Offset < RangeEnd; Segment++) {
    UINTN  Lba;
    UINTN  BlockBase;
    UINTN  StartInBlock;
    UINTN  EndInBlock;
    UINTN  SegmentLen;
    UINTN  NumBytes;
    UINT8  *FlashBlock;

    Lba       = Offset / BlockSize;
    BlockBase = Lba * BlockSize;

    StartInBlock = Offset - BlockBase;
    EndInBlock   = MIN (BlockSize, RangeEnd - BlockBase);
    SegmentLen   = EndInBlock - StartInBlock;

    FlashBlock = (UINT8 *)BlockBuffer;

    if ((StartInBlock == 0) && (EndInBlock == BlockSize)) {
      //
      // Whole-block update: ignore read errors for the compare optimization.
      //
      NumBytes = BlockSize;
      Status   = ReadAnyBlockWithRetry (Lba, 0, &NumBytes, FlashBlock);
      if (!EFI_ERROR (Status) && (NumBytes == BlockSize)) {
        if (CompareMem (FlashBlock, Image + BlockBase, BlockSize) == 0) {
          FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_SAME);
          IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);
          IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);
          Offset += SegmentLen;
          continue;
        }
      }

      Status = ProgramAnyBlockWithRetry (Lba, Image + BlockBase, VerifyBuffer, BlockSize);
      if (EFI_ERROR (Status)) {
        FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_FAILED);
        return EFI_DEVICE_ERROR;
      }

      FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_WRITTEN);
      IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);

      IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);
      Offset += SegmentLen;
      continue;
    }

    //
    // Partial-block update: must preserve the rest of the flash block.
    //
    NumBytes = BlockSize;
    Status   = ReadAnyBlockWithRetry (Lba, 0, &NumBytes, FlashBlock);
    if (EFI_ERROR (Status) || (NumBytes != BlockSize)) {
      FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_FAILED);
      return EFI_DEVICE_ERROR;
    }

    if (CompareMem (FlashBlock + StartInBlock, Image + BlockBase + StartInBlock, SegmentLen) == 0) {
      FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_SAME);
      IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);
      IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);
      Offset += SegmentLen;
      continue;
    }

    CopyMem (FlashBlock + StartInBlock, Image + BlockBase + StartInBlock, SegmentLen);

    Status = ProgramAnyBlockWithRetry (Lba, FlashBlock, VerifyBuffer, BlockSize);
    if (EFI_ERROR (Status)) {
      FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_FAILED);
      return EFI_DEVICE_ERROR;
    }

    FmpStatusBlock (Segment, FIRMWARE_UPDATE_BLOCK_WRITTEN);
    IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);

    IncrementProgress (Progress, TotalSteps, Step, ShouldReportProgress);
    Offset += SegmentLen;
  }

  return EFI_SUCCESS;
}

/**
  Ask vboot to try a slot: append the updated nvdata record to RW_NVRAM, or
  write it at the start of the region after erasing it if it is full.

  @param[in] BlockSize   Flash block size.
  @param[in] NvOffset    Flash offset of RW_NVRAM.
  @param[in] NvSize      Size of RW_NVRAM.
  @param[in] NextOffset  Offset in RW_NVRAM of the first erased record, NvSize
                         if there is none.
  @param[in] Record      The record to write.

  @retval EFI_SUCCESS       The record is in the flash.
  @retval EFI_VOLUME_FULL   The region is full and not made of whole blocks
                            that can be erased.
  @retval EFI_DEVICE_ERROR  A write, an erase or the readback failed.
**/
STATIC
EFI_STATUS
VbootWriteNvRecord (
  IN UINTN        BlockSize,
  IN UINTN        NvOffset,
  IN UINTN        NvSize,
  IN UINTN        NextOffset,
  IN CONST UINT8  Record[VBOOT_NV_RECORD_SIZE]
  )
{
  EFI_STATUS  Status;
  UINTN       Lba;
  UINTN       NumBytes;
  UINT8       Readback[VBOOT_NV_RECORD_SIZE];

  if ((BlockSize == 0) || ((BlockSize % VBOOT_NV_RECORD_SIZE) != 0)) {
    return EFI_INVALID_PARAMETER;
  }

  if (NextOffset + VBOOT_NV_RECORD_SIZE > NvSize) {
    if (((NvOffset % BlockSize) != 0) || ((NvSize % BlockSize) != 0)) {
      return EFI_VOLUME_FULL;
    }

    for (Lba = NvOffset / BlockSize; Lba < (NvOffset + NvSize) / BlockSize; Lba++) {
      if (EFI_ERROR (EraseAnyBlock (Lba))) {
        return EFI_DEVICE_ERROR;
      }
    }

    NextOffset = 0;
  }

  Lba      = (NvOffset + NextOffset) / BlockSize;
  NumBytes = VBOOT_NV_RECORD_SIZE;
  Status   = WriteAnyBlock (Lba, (NvOffset + NextOffset) % BlockSize, &NumBytes, (UINT8 *)Record);
  if (EFI_ERROR (Status) || (NumBytes != VBOOT_NV_RECORD_SIZE)) {
    return EFI_DEVICE_ERROR;
  }

  NumBytes = VBOOT_NV_RECORD_SIZE;
  Status   = ReadAnyBlockWithRetry (Lba, (NvOffset + NextOffset) % BlockSize, &NumBytes, Readback);
  if (EFI_ERROR (Status) || (NumBytes != VBOOT_NV_RECORD_SIZE) ||
      (CompareMem (Readback, Record, VBOOT_NV_RECORD_SIZE) != 0))
  {
    return EFI_DEVICE_ERROR;
  }

  return EFI_SUCCESS;
}

/**
  This code finds variable in storage blocks (Volatile or Non-Volatile).

  @param[in]      VariableName               Name of Variable to be found.
  @param[in]      VendorGuid                 Variable vendor GUID.
  @param[out]     Attributes                 Attribute value of the variable found.
  @param[in, out] DataSize                   Size of Data found. If size is less than the
                                             data, this value contains the required size.
  @param[out]     Data                       Data pointer.

  @return EFI_INVALID_PARAMETER     Invalid parameter.
  @return EFI_SUCCESS               Find the specified variable.
  @return EFI_NOT_FOUND             Not found.
  @return EFI_BUFFER_TO_SMALL       DataSize is too small for the result.
**/
STATIC
EFI_STATUS
EFIAPI
GetVariableHook (
  IN      CHAR16    *VariableName,
  IN      EFI_GUID  *VendorGuid,
  OUT     UINT32    *Attributes OPTIONAL,
  IN OUT  UINTN     *DataSize,
  OUT     VOID      *Data
  )
{
  DEBUG ((DEBUG_INFO, "%a(): %g:%S\n", __func__, VendorGuid, VariableName));
  return EFI_NOT_AVAILABLE_YET;
}

/**
  This code Finds the Next available variable.

  @param[in, out] VariableNameSize           Size of the variable name.
  @param[in, out] VariableName               Pointer to variable name.
  @param[in, out] VendorGuid                 Variable Vendor Guid.

  @return EFI_INVALID_PARAMETER     Invalid parameter.
  @return EFI_SUCCESS               Find the specified variable.
  @return EFI_NOT_FOUND             Not found.
  @return EFI_BUFFER_TO_SMALL       DataSize is too small for the result.
**/
STATIC
EFI_STATUS
EFIAPI
GetNextVariableNameHook (
  IN OUT  UINTN     *VariableNameSize,
  IN OUT  CHAR16    *VariableName,
  IN OUT  EFI_GUID  *VendorGuid
  )
{
  DEBUG ((DEBUG_INFO, "%a(): %g:%S\n", __func__, VendorGuid, VariableName));
  return EFI_NOT_AVAILABLE_YET;
}

/**
  This code sets variable in storage blocks (Volatile or Non-Volatile).

  @param[in] VariableName                     Name of Variable to be found.
  @param[in] VendorGuid                       Variable vendor GUID.
  @param[in] Attributes                       Attribute value of the variable found
  @param[in] DataSize                         Size of Data found. If size is less than the
                                              data, this value contains the required size.
  @param[in] Data                             Data pointer.

  @return EFI_INVALID_PARAMETER           Invalid parameter.
  @return EFI_SUCCESS                     Set successfully.
  @return EFI_OUT_OF_RESOURCES            Resource not enough to set variable.
  @return EFI_NOT_FOUND                   Not found.
  @return EFI_WRITE_PROTECTED             Variable is read-only.
**/
STATIC
EFI_STATUS
EFIAPI
SetVariableHook (
  IN CHAR16    *VariableName,
  IN EFI_GUID  *VendorGuid,
  IN UINT32    Attributes,
  IN UINTN     DataSize,
  IN VOID      *Data
  )
{
  DEBUG ((
    DEBUG_INFO,
    "%a(): %g:%S, 0x%x bytes, 0x%x\n",
    __func__,
    VendorGuid,
    VariableName,
    DataSize,
    Attributes
    ));
  return EFI_NOT_AVAILABLE_YET;
}

/**
  This code returns information about the EFI variables.

  @param[in]  Attributes                     Attributes bitmask to specify the type of variables
                                             on which to return information.
  @param[out] MaximumVariableStorageSize     Pointer to the maximum size of the storage space available
                                             for the EFI variables associated with the attributes specified.
  @param[out] RemainingVariableStorageSize   Pointer to the remaining size of the storage space available
                                             for EFI variables associated with the attributes specified.
  @param[out] MaximumVariableSize            Pointer to the maximum size of an individual EFI variables
                                             associated with the attributes specified.

  @return EFI_SUCCESS                   Query successfully.
**/
STATIC
EFI_STATUS
EFIAPI
QueryVariableInfoHook (
  IN  UINT32  Attributes,
  OUT UINT64  *MaximumVariableStorageSize,
  OUT UINT64  *RemainingVariableStorageSize,
  OUT UINT64  *MaximumVariableSize
  )
{
  DEBUG ((DEBUG_INFO, "%a(): 0x%x\n", __func__, Attributes));
  return EFI_NOT_AVAILABLE_YET;
}

/**
  Updates a firmware device with a new firmware image.  This function returns
  EFI_UNSUPPORTED if the firmware image is not updatable.  If the firmware image
  is updatable, the function should perform the following minimal validations
  before proceeding to do the firmware image update.
    - Validate that the image is a supported image for this firmware device.
      Return EFI_ABORTED if the image is not supported.  Additional details
      on why the image is not a supported image may be returned in AbortReason.
    - Validate the data from VendorCode if is not NULL.  Firmware image
      validation must be performed before VendorCode data validation.
      VendorCode data is ignored or considered invalid if image validation
      fails.  Return EFI_ABORTED if the VendorCode data is invalid.

  VendorCode enables vendor to implement vendor-specific firmware image update
  policy.  Null if the caller did not specify the policy or use the default
  policy.  As an example, vendor can implement a policy to allow an option to
  force a firmware image update when the abort reason is due to the new firmware
  image version is older than the current firmware image version or bad image
  checksum.  Sensitive operations such as those wiping the entire firmware image
  and render the device to be non-functional should be encoded in the image
  itself rather than passed with the VendorCode.  AbortReason enables vendor to
  have the option to provide a more detailed description of the abort reason to
  the caller.

  @param[in]  Image             Points to the new firmware image.
  @param[in]  ImageSize         Size, in bytes, of the new firmware image.
  @param[in]  VendorCode        This enables vendor to implement vendor-specific
                                firmware image update policy.  NULL indicates
                                the caller did not specify the policy or use the
                                default policy.
  @param[in]  Progress          A function used to report the progress of
                                updating the firmware device with the new
                                firmware image.
  @param[in]  CapsuleFwVersion  The version of the new firmware image from the
                                update capsule that provided the new firmware
                                image.
  @param[out] AbortReason       A pointer to a pointer to a Null-terminated
                                Unicode string providing more details on an
                                aborted operation. The buffer is allocated by
                                this function with
                                EFI_BOOT_SERVICES.AllocatePool().  It is the
                                caller's responsibility to free this buffer with
                                EFI_BOOT_SERVICES.FreePool().
  @param[out] LastAttemptStatus A pointer to a UINT32 that holds the last attempt
                                status to report back to the ESRT table in case
                                of error. This value will only be checked when this
                                function returns an error.

                                The return status code must fall in the range of
                                LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MIN_ERROR_CODE_VALUE to
                                LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MAX_ERROR_CODE_VALUE.

                                If the value falls outside this range, it will be converted
                                to LAST_ATTEMPT_STATUS_ERROR_UNSUCCESSFUL.

  @retval EFI_SUCCESS            The firmware device was successfully updated
                                 with the new firmware image.
  @retval EFI_ABORTED            The operation is aborted.  Additional details
                                 are provided in AbortReason.
  @retval EFI_INVALID_PARAMETER  The Image was NULL.
  @retval EFI_UNSUPPORTED        The operation is not supported.
**/
STATIC
EFI_STATUS
WriteImage (
  IN  CONST VOID                                     *Image,
  IN  UINTN                                          ImageSize,
  IN  CONST VOID                                     *VendorCode        OPTIONAL,
  IN  EFI_FIRMWARE_MANAGEMENT_UPDATE_IMAGE_PROGRESS  Progress           OPTIONAL,
  IN  UINT32                                         CapsuleFwVersion,
  OUT CHAR16                                         **AbortReason,
  OUT UINT32                                         *LastAttemptStatus
  )
{
  EFI_STATUS                   Status;
  UINTN                        BlockSize;
  UINTN                        EntryIndex;
  UINTN                        RangeSteps;
  UINTN                        TotalSteps;
  UINTN                        Step;
  BOOLEAN                      ShouldReportProgress;
  VOID                         *ReadBuffer;
  VOID                         *VerifyBuffer;
  UINTN                        ManifestEntryCount;
  CONST REGION_MANIFEST_ENTRY  *ManifestEntries;
  UINTN                        BaseImageSize;
  CONST FMAP_HEADER            *FmapHeader;
  CONST FMAP_AREA              *FmapAreas;
  UINTN                        FmapOffset;
  UINTN                        FmapLength;
  VOID                         *FlashFmapBuffer;
  FMAP_HEADER                  *FlashFmapHeader;
  FMAP_AREA                    *FlashFmapAreas;
  BOOLEAN                      VariableStorePreserved;
  UINTN                        VariableStoreOffset;
  UINTN                        VariableStoreSize;
  BOOLEAN                      LayoutMismatch;
  EFI_STATUS                   FlashFmapStatus;
  UINTN                        MismatchIndex;
  UINTN                        CapsuleRegionOffset;
  UINTN                        CapsuleRegionSize;
  UINTN                        FlashRegionOffset;
  UINTN                        FlashRegionSize;
  CONST CHAR8                  SmmStoreRegionName[REGION_MANIFEST_NAME_LEN] = "SMMSTORE";
  CONST CHAR8                  NvRegionName[REGION_MANIFEST_NAME_LEN]       = "RW_NVRAM";
  BOOLEAN                      FlashHasSlots;
  UINTN                        SlotOffset;
  UINTN                        SlotSize;
  BOOLEAN                      AbUpdate;
  UINTN                        AbIndex[2];
  UINTN                        TargetSlot;
  UINTN                        RegionNumber;
  UINTN                        RegionCount;
  UINTN                        NvOffset;
  UINTN                        NvSize;
  UINTN                        NvNext;
  UINT8                        *NvBuffer;
  UINT8                        NvRecord[VBOOT_NV_RECORD_SIZE];

  *LastAttemptStatus = LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE;
  ReadBuffer         = NULL;
  VerifyBuffer       = NULL;
  TotalSteps         = 0;
  AbUpdate           = FALSE;
  FlashHasSlots      = FALSE;
  TargetSlot         = 0;
  NvOffset           = 0;
  NvSize             = 0;
  NvNext             = 0;

  //
  // FmpDeviceCheckImageWithStatus() has already validated the image, so not
  // repeating the checks.  However, could move the checks here to be able to
  // report abort reason which can't be done in FmpDeviceCheckImageWithStatus().
  //

  Status = SmmStoreLibGetBlockSize (&BlockSize);
  if (EFI_ERROR (Status)) {
    DEBUG ((
      DEBUG_ERROR,
      "%a(): SmmStoreLibGetBlockSize() failed with: %r\n",
      __func__,
      Status
      ));
    return Status;
  }

  //
  // The manifest names the regions to write, the FMAP of the image says
  // where they are.
  //
  BaseImageSize          = ImageSize;
  ManifestEntryCount     = 0;
  ManifestEntries        = NULL;
  FmapHeader             = NULL;
  FmapAreas              = NULL;
  FmapOffset             = 0;
  FmapLength             = 0;
  FlashFmapBuffer        = NULL;
  FlashFmapHeader        = NULL;
  FlashFmapAreas         = NULL;
  VariableStorePreserved = FALSE;
  VariableStoreOffset    = 0;
  VariableStoreSize      = 0;

  Status = FmpDeviceLocateRegionManifest (
             Image,
             ImageSize,
             &ManifestEntryCount,
             &ManifestEntries,
             &BaseImageSize
             );
  if (Status == EFI_NOT_FOUND) {
    DEBUG ((DEBUG_ERROR, "%a(): image without a region manifest\n", __func__));
    return EFI_ABORTED;
  } else if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "%a(): invalid region manifest: %r\n", __func__, Status));
    return EFI_ABORTED;
  } else {
    DEBUG ((
      DEBUG_INFO,
      "%a(): found region manifest (%u entr%a), base image size 0x%x\n",
      __func__,
      (UINT32)ManifestEntryCount,
      (ManifestEntryCount == 1) ? "y" : "ies",
      (UINT32)BaseImageSize
      ));
  }

  //
  // FmpDeviceCheckImageWithStatus() has checked them too: again where they
  // are written.
  //
  if (!ManifestRegionsAllowed (ManifestEntries, ManifestEntryCount)) {
    return EFI_ABORTED;
  }

  Status = LocateFmapInImage (Image, BaseImageSize, &FmapOffset, &FmapLength);
  if (!EFI_ERROR (Status) && (FmapOffset <= BaseImageSize) && (FmapLength <= (BaseImageSize - FmapOffset))) {
    FmapHeader = (CONST FMAP_HEADER *)((CONST UINT8 *)Image + FmapOffset);
    FmapAreas  = (CONST FMAP_AREA *)((CONST UINT8 *)FmapHeader + sizeof (FMAP_HEADER));

    DEBUG ((
      DEBUG_INFO,
      "%a(): found FMAP at 0x%x (%u areas)\n",
      __func__,
      (UINT32)FmapOffset,
      (UINT32)FmapHeader->AreaCount
      ));
  }

  if ((ManifestEntryCount == 0) || (FmapHeader == NULL) || (FmapHeader->AreaCount == 0)) {
    DEBUG ((DEBUG_ERROR, "%a(): manifest without a valid FMAP\n", __func__));
    return EFI_ABORTED;
  }

  for (EntryIndex = 0; EntryIndex < ManifestEntryCount; ++EntryIndex) {
    UINTN  RegionOffset;
    UINTN  RegionSize;
    CHAR8  RegionName[REGION_MANIFEST_NAME_LEN + 1];

    Status = FindFmapRegion (
               FmapHeader,
               FmapAreas,
               FmapHeader->AreaCount,
               ManifestEntries[EntryIndex].RegionName,
               &RegionOffset,
               &RegionSize
               );
    if (EFI_ERROR (Status) || (RegionSize == 0) ||
        (RegionOffset > BaseImageSize) || (RegionSize > (BaseImageSize - RegionOffset)))
    {
      CopyMem (
        RegionName,
        ManifestEntries[EntryIndex].RegionName,
        REGION_MANIFEST_NAME_LEN
        );
      RegionName[REGION_MANIFEST_NAME_LEN] = 0;
      DEBUG ((DEBUG_ERROR, "%a(): invalid manifest region '%a'\n", __func__, RegionName));
      return EFI_ABORTED;
    }

    Status = FmpDeviceGetFlashRangeStepCount (RegionOffset, RegionSize, BlockSize, &RangeSteps);
    if (EFI_ERROR (Status) || (TotalSteps > (MAX_UINTN - RangeSteps))) {
      DEBUG ((DEBUG_ERROR, "%a(): invalid progress range for manifest region\n", __func__));
      return EFI_ABORTED;
    }

    TotalSteps += RangeSteps;
  }

  if (TotalSteps == 0) {
    return EFI_ABORTED;
  }

  ReadBuffer = AllocatePool (BlockSize);
  if (ReadBuffer == NULL) {
    DEBUG ((DEBUG_ERROR, "%a(): failed to allocate read buffer\n", __func__));
    return EFI_OUT_OF_RESOURCES;
  }

  VerifyBuffer = AllocatePool (BlockSize);
  if (VerifyBuffer == NULL) {
    DEBUG ((DEBUG_ERROR, "%a(): failed to allocate verify buffer\n", __func__));
    FreePool (ReadBuffer);
    return EFI_OUT_OF_RESOURCES;
  }

  //
  // Validate manifest regions against the FMAP before flashing.
  //
  LayoutMismatch      = FALSE;
  MismatchIndex       = MAX_UINTN;
  CapsuleRegionOffset = 0;
  CapsuleRegionSize   = 0;
  FlashRegionOffset   = 0;
  FlashRegionSize     = 0;
  FlashFmapStatus     = LoadFlashFmap (
                          BlockSize,
                          BaseImageSize,
                          FmapHeader,
                          FmapAreas,
                          &FlashFmapHeader,
                          &FlashFmapAreas,
                          &FlashFmapBuffer
                          );
  if (EFI_ERROR (FlashFmapStatus)) {
    LayoutMismatch = TRUE;
    DEBUG ((DEBUG_WARN, "%a(): failed to load flash FMAP: %r\n", __func__, FlashFmapStatus));
  } else {
    Status = FindFmapRegion (
               FlashFmapHeader,
               FlashFmapAreas,
               FlashFmapHeader->AreaCount,
               SmmStoreRegionName,
               &VariableStoreOffset,
               &VariableStoreSize
               );
    if (!EFI_ERROR (Status) && (VariableStoreSize != 0) &&
        (VariableStoreOffset < BaseImageSize) &&
        (VariableStoreSize <= (BaseImageSize - VariableStoreOffset)))
    {
      VariableStorePreserved = TRUE;
    } else {
      DEBUG ((DEBUG_WARN, "%a(): current SMMSTORE range is unavailable or invalid\n", __func__));
    }

    FlashHasSlots = TRUE;
    for (EntryIndex = 0; EntryIndex < ARRAY_SIZE (mVbootSlotNames); ++EntryIndex) {
      Status = FindFmapRegion (
                 FlashFmapHeader,
                 FlashFmapAreas,
                 FlashFmapHeader->AreaCount,
                 mVbootSlotNames[EntryIndex],
                 &SlotOffset,
                 &SlotSize
                 );
      if (EFI_ERROR (Status)) {
        FlashHasSlots = FALSE;
      }
    }
  }

  for (EntryIndex = 0; EntryIndex < ManifestEntryCount; ++EntryIndex) {
    UINTN  RegionOffset;
    UINTN  RegionSize;
    CHAR8  RegionName[REGION_MANIFEST_NAME_LEN + 1];

    Status = FindFmapRegion (
               FmapHeader,
               FmapAreas,
               FmapHeader->AreaCount,
               ManifestEntries[EntryIndex].RegionName,
               &RegionOffset,
               &RegionSize
               );
    if (EFI_ERROR (Status)) {
      goto InvalidImage;
    }

    CopyMem (
      RegionName,
      ManifestEntries[EntryIndex].RegionName,
      REGION_MANIFEST_NAME_LEN
      );
    RegionName[REGION_MANIFEST_NAME_LEN] = 0;
    DEBUG ((
      DEBUG_INFO,
      "%a(): manifest region '%a' capsule 0x%x+0x%x\n",
      __func__,
      RegionName,
      (UINT32)RegionOffset,
      (UINT32)RegionSize
      ));

    if (!LayoutMismatch) {
      Status = FindFmapRegion (
                 FlashFmapHeader,
                 FlashFmapAreas,
                 FlashFmapHeader->AreaCount,
                 ManifestEntries[EntryIndex].RegionName,
                 &FlashRegionOffset,
                 &FlashRegionSize
                 );
      if (EFI_ERROR (Status) || (FlashRegionOffset != RegionOffset) || (FlashRegionSize != RegionSize)) {
        LayoutMismatch      = TRUE;
        MismatchIndex       = EntryIndex;
        CapsuleRegionOffset = RegionOffset;
        CapsuleRegionSize   = RegionSize;
        if (EFI_ERROR (Status)) {
          FlashRegionOffset = 0;
          FlashRegionSize   = 0;
        }
      } else if (VariableStorePreserved &&
                 FmpDeviceFlashRangesOverlap (
                   FlashRegionOffset,
                   FlashRegionSize,
                   VariableStoreOffset,
                   VariableStoreSize
                   ))
      {
        VariableStorePreserved = FALSE;
      }
    }
  }

  //
  // The two slots of vboot: the flash must have the nvdata of vboot too.
  //
  AbUpdate = FmpVbootFindSlots (ManifestEntries, ManifestEntryCount, &AbIndex[0], &AbIndex[1]);
  if (AbUpdate && !LayoutMismatch) {
    Status = FindFmapRegion (
               FlashFmapHeader,
               FlashFmapAreas,
               FlashFmapHeader->AreaCount,
               NvRegionName,
               &NvOffset,
               &NvSize
               );
    if (EFI_ERROR (Status) || (NvSize < VBOOT_NV_RECORD_SIZE) || ((NvSize % VBOOT_NV_RECORD_SIZE) != 0) ||
        (NvOffset >= BaseImageSize) || (NvSize > (BaseImageSize - NvOffset)))
    {
      DEBUG ((DEBUG_ERROR, "%a(): vboot slots, but no RW_NVRAM in the flash\n", __func__));
      LayoutMismatch = TRUE;
    }
  }

  if (!LayoutMismatch && !FmpVbootManifestFitsFlash (ManifestEntries, ManifestEntryCount, FlashHasSlots)) {
    DEBUG ((DEBUG_ERROR, "%a(): the flash has both vboot slots, a manifest without both is refused\n", __func__));
    goto InvalidImage;
  }

  if (FlashFmapBuffer != NULL) {
    FreePool (FlashFmapBuffer);
    FlashFmapBuffer = NULL;
  }

  if (LayoutMismatch) {
    //
    // The regions of the manifest are not where the image puts them in the
    // flash, or the FMAP of the flash could not be read.  Refuse the update:
    // writing the whole BIOS region instead would also replace what the
    // manifest leaves alone, such as the variable store and the vital
    // product data, with what the image has there.
    //
    CHAR8  RegionName[REGION_MANIFEST_NAME_LEN + 1];

    if (MismatchIndex != MAX_UINTN) {
      CopyMem (
        RegionName,
        ManifestEntries[MismatchIndex].RegionName,
        REGION_MANIFEST_NAME_LEN
        );
      RegionName[REGION_MANIFEST_NAME_LEN] = 0;
      DEBUG ((
        DEBUG_ERROR,
        "%a(): FMAP layout mismatch for '%a': flash 0x%x+0x%x vs capsule 0x%x+0x%x\n",
        __func__,
        RegionName,
        (UINT32)FlashRegionOffset,
        (UINT32)FlashRegionSize,
        (UINT32)CapsuleRegionOffset,
        (UINT32)CapsuleRegionSize
        ));
    } else {
      DEBUG ((DEBUG_ERROR, "%a(): the FMAP of the flash is unreadable\n", __func__));
    }

    FreePool (VerifyBuffer);
    FreePool (ReadBuffer);
    *LastAttemptStatus = LAST_ATTEMPT_STATUS_SMMSTORE_LAYOUT_MISMATCH;
    return EFI_ABORTED;
  }

  if (AbUpdate) {
    //
    // Write the slot that is not running, and only that one.
    //
    NvBuffer = AllocatePool (NvSize);
    if (NvBuffer == NULL) {
      FreePool (VerifyBuffer);
      FreePool (ReadBuffer);
      return EFI_OUT_OF_RESOURCES;
    }

    Status = ReadFlashRange (BlockSize, BaseImageSize, NvOffset, NvSize, NvBuffer);
    if (EFI_ERROR (Status)) {
      FreePool (NvBuffer);
      *LastAttemptStatus = LAST_ATTEMPT_STATUS_SMMSTORE_FLASH_FAILED;
      goto IoError;
    }

    if (!FmpVbootNvFindCurrent (NvBuffer, NvSize, NvRecord, &NvNext)) {
      DEBUG ((DEBUG_WARN, "%a(): no valid vboot nvdata, assuming slot A runs\n", __func__));
    }

    FreePool (NvBuffer);
    if ((NvNext + VBOOT_NV_RECORD_SIZE > NvSize) && (((NvOffset % BlockSize) != 0) || ((NvSize % BlockSize) != 0))) {
      DEBUG ((DEBUG_ERROR, "%a(): RW_NVRAM is full and cannot be erased\n", __func__));
      FreePool (VerifyBuffer);
      FreePool (ReadBuffer);
      *LastAttemptStatus = LAST_ATTEMPT_STATUS_SMMSTORE_LAYOUT_MISMATCH;
      return EFI_ABORTED;
    }

    TargetSlot = 1 - FmpVbootNvTriedSlot (NvRecord);
    FmpStatusSlots (TargetSlot);
    DEBUG ((
      DEBUG_INFO,
      "%a(): vboot runs slot %c, updating slot %c\n",
      __func__,
      (TargetSlot == 0) ? 'B' : 'A',
      (TargetSlot == 0) ? 'A' : 'B'
      ));

    TotalSteps = 0;
    for (EntryIndex = 0; EntryIndex < ManifestEntryCount; ++EntryIndex) {
      UINTN  RegionOffset;
      UINTN  RegionSize;

      if (EntryIndex == AbIndex[1 - TargetSlot]) {
        continue;
      }

      Status = FindFmapRegion (
                 FmapHeader,
                 FmapAreas,
                 FmapHeader->AreaCount,
                 ManifestEntries[EntryIndex].RegionName,
                 &RegionOffset,
                 &RegionSize
                 );
      if (EFI_ERROR (Status) ||
          EFI_ERROR (FmpDeviceGetFlashRangeStepCount (RegionOffset, RegionSize, BlockSize, &RangeSteps)))
      {
        goto InvalidImage;
      }

      TotalSteps += RangeSteps;
    }
  }

  ShouldReportProgress = TRUE;
  Step                 = 0;
  *LastAttemptStatus   = LAST_ATTEMPT_STATUS_SMMSTORE_FLASH_FAILED;
  RegionNumber         = 0;
  RegionCount          = AbUpdate ? ManifestEntryCount - 1 : ManifestEntryCount;
  FmpStatusTotal (TotalSteps / 2, BlockSize);

  DEBUG ((DEBUG_INFO, "%a(): manifest-guided update over %u region(s)\n", __func__, (UINT32)ManifestEntryCount));

  for (EntryIndex = 0; EntryIndex < ManifestEntryCount; ++EntryIndex) {
    UINTN  RegionOffset;
    UINTN  RegionSize;

    if (AbUpdate && (EntryIndex == AbIndex[1 - TargetSlot])) {
      continue;
    }

    Status = FindFmapRegion (
               FmapHeader,
               FmapAreas,
               FmapHeader->AreaCount,
               ManifestEntries[EntryIndex].RegionName,
               &RegionOffset,
               &RegionSize
               );
    if (EFI_ERROR (Status) || (RegionOffset > BaseImageSize) ||
        (RegionSize > (BaseImageSize - RegionOffset)) ||
        EFI_ERROR (FmpDeviceGetFlashRangeStepCount (RegionOffset, RegionSize, BlockSize, &RangeSteps)))
    {
      goto InvalidImage;
    }

    FmpStatusRegion (
      ManifestEntries[EntryIndex].RegionName,
      REGION_MANIFEST_NAME_LEN,
      RegionNumber++,
      RegionCount,
      RangeSteps / 2
      );
    Status = UpdateFlashRangeFromImage (
               BlockSize,
               (CONST UINT8 *)Image,
               BaseImageSize,
               RegionOffset,
               RegionSize,
               ReadBuffer,
               VerifyBuffer,
               Progress,
               TotalSteps,
               &Step,
               &ShouldReportProgress
               );
    if (EFI_ERROR (Status)) {
      goto IoError;
    }
  }

  if (AbUpdate) {
    //
    // The slot is written and verified: try it on the next boots.
    //
    FmpStatusPhase (FIRMWARE_UPDATE_PHASE_FINISHING);
    FmpVbootNvSetTryNext (NvRecord, TargetSlot, VBOOT_AB_TRY_COUNT);
    Status = VbootWriteNvRecord (BlockSize, NvOffset, NvSize, NvNext, NvRecord);
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_ERROR, "%a(): writing the vboot nvdata failed: %r\n", __func__, Status));
      goto IoError;
    }

    DEBUG ((DEBUG_INFO, "%a(): vboot tries slot %c next\n", __func__, (TargetSlot == 0) ? 'A' : 'B'));
  }

  FreePool (VerifyBuffer);
  FreePool (ReadBuffer);

  *LastAttemptStatus = LAST_ATTEMPT_STATUS_SUCCESS;

  //
  // A manifest region overlapping the SMMSTORE region that backs EFI variables
  // leaves the running coreboot SMI handler and EDK variable services with
  // stale assumptions about the store, so replace the services with failure
  // stubs in that case.
  //
  // Otherwise the variable services keep working, which lets FmpDxe persist
  // the final last-attempt state before the mandatory reset.
  //
  // If there was an error, it's unclear whether these stubs would be of any
  // help, so they are employed only on successful flashing.
  //

  if (FmpDeviceShouldDisableVariableServices (VariableStorePreserved)) {
    gRT->GetVariable         = GetVariableHook;
    gRT->GetNextVariableName = GetNextVariableNameHook;
    gRT->SetVariable         = SetVariableHook;
    gRT->QueryVariableInfo   = QueryVariableInfoHook;

    gRT->Hdr.CRC32 = 0;
    gBS->CalculateCrc32 (
           (UINT8 *)&gRT->Hdr,
           gRT->Hdr.HeaderSize,
           &gRT->Hdr.CRC32
           );
  }

  return EFI_SUCCESS;

InvalidImage:
  *LastAttemptStatus = LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE;
  if (FlashFmapBuffer != NULL) {
    FreePool (FlashFmapBuffer);
  }

  if (VerifyBuffer != NULL) {
    FreePool (VerifyBuffer);
  }

  if (ReadBuffer != NULL) {
    FreePool (ReadBuffer);
  }

  DEBUG ((DEBUG_ERROR, "%a(): capsule metadata is invalid\n", __func__));
  return EFI_ABORTED;

IoError:
  //
  // There are several reasons why we might end up in here:
  //  - an actual issue with the flash chip which is unlikely to allow any
  //    recovery via software
  //  - a bug in SMMSTORE SMI handler of coreboot
  //  - any bug of the firmware or its configuration which has resulted in the
  //    system not being ready for a full flash update
  //
  // The last case can be caused at least by:
  //  - coreboot not lifting flash protections
  //  - Intel ME not being disabled
  //
  // This situation is atypical and can leave the flash chip in an
  // unpredictable state which can be fully functional, unbootable or something
  // in between.
  //
  // Being optimistic that the firmware is still functional, we're leaving
  // variable services available under assumption that SMMSTORE region hasn't
  // been moved withing the firmware image (most updates don't modify layout).
  // Note that the store can even be recreated on the next boot depending on
  // the damage that it has sustained.  It's also possible that we hit
  // protected range and nothing of any worth has been modified.
  //
  // If the firmware ends up unbootable, then, in general, external flashing
  // via a programmer needs to be employed to recover the device.
  //
  if (VerifyBuffer != NULL) {
    FreePool (VerifyBuffer);
  }

  FreePool (ReadBuffer);
  DEBUG ((DEBUG_ERROR, "%a(): flashing has failed at step 0x%x/0x%x\n", __func__, Step, TotalSteps));
  return EFI_DEVICE_ERROR;
}

/**
  Updates a firmware device with a new firmware image, and publishes what
  is written for the update screen: WriteImage(), from the version running
  to CapsuleFwVersion, then the result.

  @param[in]  Image             Points to the new firmware image.
  @param[in]  ImageSize         Size, in bytes, of the new firmware image.
  @param[in]  VendorCode        Vendor-specific update policy, or NULL.
  @param[in]  Progress          A function used to report the progress of
                                updating the firmware device with the new
                                firmware image.
  @param[in]  CapsuleFwVersion  The version of the new firmware image from the
                                update capsule that provided the new firmware
                                image.
  @param[out] AbortReason       Details on an aborted operation.
  @param[out] LastAttemptStatus The last attempt status to report in the ESRT
                                when this function returns an error.

  @return What WriteImage() returns.
**/
EFI_STATUS
EFIAPI
FmpDeviceSetImageWithStatus (
  IN  CONST VOID                                     *Image,
  IN  UINTN                                          ImageSize,
  IN  CONST VOID                                     *VendorCode        OPTIONAL,
  IN  EFI_FIRMWARE_MANAGEMENT_UPDATE_IMAGE_PROGRESS  Progress           OPTIONAL,
  IN  UINT32                                         CapsuleFwVersion,
  OUT CHAR16                                         **AbortReason,
  OUT UINT32                                         *LastAttemptStatus
  )
{
  EFI_STATUS  Status;
  UINT32      Version;

  if (EFI_ERROR (FmpDeviceGetVersion (&Version))) {
    Version = 0;
  }

  FmpStatusBegin (Version, CapsuleFwVersion);
  Status = WriteImage (Image, ImageSize, VendorCode, Progress, CapsuleFwVersion, AbortReason, LastAttemptStatus);
  if (!EFI_ERROR (Status)) {
    FmpStatusPhase (FIRMWARE_UPDATE_PHASE_DONE);
  } else if (Status == EFI_OUT_OF_RESOURCES) {
    FmpStatusFailed (FIRMWARE_UPDATE_REASON_OTHER);
  } else if (Status == EFI_DEVICE_ERROR) {
    FmpStatusFailed (FIRMWARE_UPDATE_REASON_FLASH);
  } else if (*LastAttemptStatus == LAST_ATTEMPT_STATUS_SMMSTORE_INVALID_IMAGE) {
    FmpStatusFailed (FIRMWARE_UPDATE_REASON_INVALID);
  } else if (*LastAttemptStatus == LAST_ATTEMPT_STATUS_SMMSTORE_LAYOUT_MISMATCH) {
    FmpStatusFailed (FIRMWARE_UPDATE_REASON_LAYOUT);
  } else if (*LastAttemptStatus == LAST_ATTEMPT_STATUS_SMMSTORE_FLASH_FAILED) {
    FmpStatusFailed (FIRMWARE_UPDATE_REASON_FLASH);
  } else {
    FmpStatusFailed (FIRMWARE_UPDATE_REASON_OTHER);
  }

  return Status;
}

/**
  Lock the firmware device that contains a firmware image.  Once a firmware
  device is locked, any attempts to modify the firmware image contents in the
  firmware device must fail.

  @note It is recommended that all firmware devices support a lock method to
        prevent modifications to a stored firmware image.

  @note A firmware device lock mechanism is typically only cleared by a full
        system reset (not just sleep state/low power mode).

  @retval  EFI_SUCCESS      The firmware device was locked.
  @retval  EFI_UNSUPPORTED  The firmware device does not support locking
**/
EFI_STATUS
EFIAPI
FmpDeviceLock (
  VOID
  )
{
  return EFI_UNSUPPORTED;
}

/**
  Constructor that performs required initialization.

  Also tells the ESRT (EsrtFmpDxe) and the setup (FirmwareUpdateDxe) which
  FMP instance is the system firmware: this one, with the GUID FmpDxe
  publishes, from the same places FmpDxe takes it from (coreboot's table,
  the FILE_GUID of FmpDxe without it).  Set here rather than built in, the
  same payload serves every firmware coreboot describes.

  @param ImageHandle  The image handle of the process.
  @param SystemTable  The EFI System Table pointer.

  @retval EFI_SUCCESS  Initialization was successful.
**/
EFI_STATUS
EFIAPI
FmpDeviceSmmLibConstructor (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS     Status;
  FIRMWARE_INFO  *FwInfo;
  EFI_GUID       *Guid;
  UINTN          Size;

  SmmStoreLibInitialize ();
  FmpStatusInstall ();

  Guid = &gEfiCallerIdGuid;
  if (!EFI_ERROR (GetFwInfo (&FwInfo))) {
    Guid = &FwInfo->Type;
  }

  Size   = sizeof (EFI_GUID);
  Status = PcdSetPtrS (PcdSystemFmpCapsuleImageTypeIdGuid, &Size, Guid);
  ASSERT_EFI_ERROR (Status);
  return EFI_SUCCESS;
}
