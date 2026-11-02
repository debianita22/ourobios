/** @file
  Firmware Update setup page.

  Shows the system firmware of the ESRT, the FMP instance whose image type
  is PcdSystemFmpCapsuleImageTypeIdGuid: its version, the lowest version it
  accepts and the result of its last update.

  Updates it from a USB drive: the capsule in \EFI\UpdateCapsule of a USB
  drive or of an EFI system partition is checked here (one file, for this
  firmware, not older than the lowest supported version), then a capsule on
  disk is requested in OsIndications and the system restarts.  The update
  itself, with the signature check, is the one of the capsules an OS
  stages: PlatformBootManagerLib applies it at the next boot, which coreboot
  starts with the whole flash writable.

  With vboot and two RW slots, shows which slot runs and the release in the
  other one, read from the "revision" file of each slot's CBFS, and goes back
  to that release: coreboot's SMMSTORE handler asks vboot to try the other
  slot at the next boots, as after an update, and the system restarts.
  coreboot refuses that once a boot option or an OS starts
  (PlatformBootManagerLib locks it at ReadyToBoot and ExitBootServices()), so
  here is checked what a capsule would be: not the same release, the same
  variant, not older than the lowest supported version.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Guid/BootMediaInfoGuid.h>
#include <Guid/FileInfo.h>
#include <Guid/FirmwareUpdateConfig.h>
#include <Guid/FmpCapsule.h>
#include <Guid/GlobalVariable.h>
#include <Guid/Gpt.h>
#include <Guid/HiiPlatformSetupFormset.h>
#include <IndustryStandard/SmBios.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/HiiLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PcdLib.h>
#include <Library/PrintLib.h>
#include <Library/SmmStoreLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Protocol/DevicePath.h>
#include <Protocol/FirmwareManagement.h>
#include <Protocol/HiiConfigAccess.h>
#include <Protocol/HiiPopup.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/Smbios.h>

#define CAPSULE_DIR         L"\\EFI\\UpdateCapsule"
#define CAPSULE_PROBE_SIZE  SIZE_64KB         // enough for the headers and the signature
#define FILE_INFO_SIZE      (SIZE_OF_EFI_FILE_INFO + 256 * sizeof (CHAR16))
#define FILE_NAME_LENGTH    64
#define VERSION_LENGTH      24
#define RELEASE_LENGTH      64

#define FLASH_WINDOW_SIZE   SIZE_16MB         // the flash decoded below 4 GiB
#define CBFS_ALIGNMENT      64
#define CBFS_METADATA_MAX   256
#define REVISION_MAX_SIZE   SIZE_16KB         // coreboot's build.h

//
// The FMP_PAYLOAD_HEADER of FmpPayloadHeaderLibV1, in front of the image.
//
#define FMP_PAYLOAD_HEADER_SIGNATURE  SIGNATURE_32 ('M', 'S', 'S', '1')

typedef struct {
  UINT32    Signature;
  UINT32    HeaderSize;
  UINT32    FwVersion;
  UINT32    LowestSupportedVersion;
} FMP_PAYLOAD_HEADER_V1;

//
// coreboot's flash map (FMAP) and the header of a CBFS file, whose fields are
// big-endian.
//
#pragma pack(1)
typedef struct {
  CHAR8     Signature[8];
  UINT8     VerMajor;
  UINT8     VerMinor;
  UINT64    Base;
  UINT32    Size;
  CHAR8     Name[32];
  UINT16    AreaCount;
} FMAP_HEADER;

typedef struct {
  UINT32    Offset;
  UINT32    Size;
  CHAR8     Name[32];
  UINT16    Flags;
} FMAP_AREA;

typedef struct {
  CHAR8     Magic[8];
  UINT32    Len;
  UINT32    Type;
  UINT32    AttributesOffset;
  UINT32    Offset;
} CBFS_FILE_HEADER;
#pragma pack()

typedef struct {
  VENDOR_DEVICE_PATH          VendorDevicePath;
  EFI_DEVICE_PATH_PROTOCOL    End;
} HII_VENDOR_DEVICE_PATH;

typedef struct {
  BOOLEAN    Found;
  UINT32     Version;
  UINT32     Lowest;
  UINT32     LastVersion;
  UINT32     LastStatus;
} SYSTEM_FIRMWARE_INFO;

//
// The RW slots of vboot: the one that runs, the other one, and the release in
// each (empty when there is none).
//
typedef struct {
  BOOLEAN    Found;
  CHAR16     Running;
  CHAR16     Other;
  CHAR16     RunningName[RELEASE_LENGTH];
  CHAR16     OtherName[RELEASE_LENGTH];
} SLOT_INFO;

//
// The files of the \EFI\UpdateCapsule folders that the next boot would read.
//
typedef struct {
  UINTN     Files;
  UINTN     Capsules;     // capsules for this firmware
  UINT32    Version;      // the version of the last one
  CHAR16    Name[FILE_NAME_LENGTH];
} CAPSULE_SCAN;

extern UINT8  FirmwareUpdateVfrBin[];
extern UINT8  FirmwareUpdateDxeStrings[];

STATIC EFI_HII_CONFIG_ACCESS_PROTOCOL  mConfigAccess;
STATIC EFI_HANDLE                      mDriverHandle;
STATIC EFI_HII_HANDLE                  mHiiHandle;

STATIC HII_VENDOR_DEVICE_PATH  mVendorDevicePath = {
  {
    {
      HARDWARE_DEVICE_PATH,
      HW_VENDOR_DP,
      {
        (UINT8)(sizeof (VENDOR_DEVICE_PATH)),
        (UINT8)((sizeof (VENDOR_DEVICE_PATH)) >> 8)
      }
    },
    FIRMWARE_UPDATE_FORMSET_GUID
  },
  {
    END_DEVICE_PATH_TYPE,
    END_ENTIRE_DEVICE_PATH_SUBTYPE,
    {
      (UINT8)(END_DEVICE_PATH_LENGTH),
      (UINT8)((END_DEVICE_PATH_LENGTH) >> 8)
    }
  }
};

//
// The last ESRT number in the format before X.Y.Z.R: v1.3.6-rc1
//
#define LAST_OLD_LAYOUT_VERSION  0x01030006

/**
  A version of the ESRT as the releases number it: X.Y.Z.R, one byte each.
  A release vX.Y.Z is X.Y.Z.0; its candidate N is one release below with
  R = N (v1.3.7-rc2 is 1.3.6.2), so the candidates sort after the release
  before and before the one they lead to. Shown as the tag reads: "1.3.7",
  "1.3.7-rc2". The releases up to v1.3.6-rc1 were (X << 24) | (Y << 16) | Z,
  their candidates with the number of the release: up to
  LAST_OLD_LAYOUT_VERSION, with byte 1 zero, a number is shown that way (of
  v1.3.6 there was only the rc1). A capsule of one of them can still be
  installed, back to an older release.
**/
STATIC
VOID
FormatVersion (
  IN  UINT32  Version,
  OUT CHAR16  *Buffer,
  IN  UINTN   BufferSize
  )
{
  UINT32  Release;

  if ((Version <= LAST_OLD_LAYOUT_VERSION) && ((Version & 0xFF00) == 0)) {
    if (Version == LAST_OLD_LAYOUT_VERSION) {
      StrCpyS (Buffer, BufferSize / sizeof (CHAR16), L"1.3.6-rc1");
    } else {
      UnicodeSPrint (Buffer, BufferSize, L"%u.%u.%u", Version >> 24, (Version >> 16) & 0xFF, Version & 0xFFFF);
    }

    return;
  }

  if ((Version & 0xFF) == 0) {
    UnicodeSPrint (Buffer, BufferSize, L"%u.%u.%u", Version >> 24, (Version >> 16) & 0xFF, (Version >> 8) & 0xFF);
    return;
  }

  Release = (Version & ~0xFFu) + 0x100;
  UnicodeSPrint (Buffer, BufferSize, L"%u.%u.%u-rc%u", Release >> 24, (Release >> 16) & 0xFF, (Release >> 8) & 0xFF, Version & 0xFF);
}

/**
  The LastAttemptStatus of the ESRT (UEFI 2.10, 23.4), and the codes of
  FmpDeviceSmmLib from LAST_ATTEMPT_STATUS_DEVICE_LIBRARY_MIN_ERROR_CODE_VALUE.
**/
STATIC
VOID
FormatAttemptStatus (
  IN  UINT32  Status,
  OUT CHAR16  *Buffer,
  IN  UINTN   BufferSize
  )
{
  STATIC CONST CHAR16  *Text[] = {
    L"successful",
    L"failed",
    L"failed: not enough resources",
    L"refused: version not accepted",
    L"refused: invalid capsule",
    L"refused: signature not valid",
    L"postponed: AC adapter needed",
    L"postponed: battery too low",
    L"refused: dependencies not met"
  };

  if (Status < ARRAY_SIZE (Text)) {
    StrCpyS (Buffer, BufferSize / sizeof (CHAR16), Text[Status]);
  } else if (Status == 0x1800) {
    StrCpyS (Buffer, BufferSize / sizeof (CHAR16), L"refused: image without region manifest");
  } else if (Status == 0x1801) {
    StrCpyS (Buffer, BufferSize / sizeof (CHAR16), L"refused: capsule for another flash layout");
  } else if (Status == 0x1802) {
    StrCpyS (Buffer, BufferSize / sizeof (CHAR16), L"failed: flash write error");
  } else {
    UnicodeSPrint (Buffer, BufferSize, L"failed: error 0x%x", Status);
  }
}

/**
  The system firmware of the ESRT, from its FMP instance.
**/
STATIC
VOID
GetSystemFirmwareInfo (
  OUT SYSTEM_FIRMWARE_INFO  *Info
  )
{
  EFI_STATUS                        Status;
  CONST EFI_GUID                    *Ours;
  EFI_HANDLE                        *Handles;
  UINTN                             HandleCount;
  UINTN                             Index;
  UINTN                             Item;
  EFI_FIRMWARE_MANAGEMENT_PROTOCOL  *Fmp;
  EFI_FIRMWARE_IMAGE_DESCRIPTOR     *Images;
  EFI_FIRMWARE_IMAGE_DESCRIPTOR     *Image;
  UINTN                             Size;
  UINT32                            DescriptorVersion;
  UINT8                             DescriptorCount;
  UINTN                             DescriptorSize;
  UINT32                            PackageVersion;
  CHAR16                            *PackageVersionName;

  ZeroMem (Info, sizeof (*Info));
  if (PcdGetSize (PcdSystemFmpCapsuleImageTypeIdGuid) < sizeof (EFI_GUID)) {
    return;
  }

  Ours   = (CONST EFI_GUID *)PcdGetPtr (PcdSystemFmpCapsuleImageTypeIdGuid);
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiFirmwareManagementProtocolGuid, NULL, &HandleCount, &Handles);
  if (EFI_ERROR (Status)) {
    return;
  }

  for (Index = 0; (Index < HandleCount) && !Info->Found; Index++) {
    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiFirmwareManagementProtocolGuid, (VOID **)&Fmp))) {
      continue;
    }

    Size               = 0;
    PackageVersionName = NULL;
    Status             = Fmp->GetImageInfo (Fmp, &Size, NULL, &DescriptorVersion, &DescriptorCount, &DescriptorSize, &PackageVersion, &PackageVersionName);
    if ((Status != EFI_BUFFER_TOO_SMALL) || (Size == 0)) {
      continue;
    }

    Images = AllocateZeroPool (Size);
    if (Images == NULL) {
      continue;
    }

    PackageVersionName = NULL;
    Status             = Fmp->GetImageInfo (Fmp, &Size, Images, &DescriptorVersion, &DescriptorCount, &DescriptorSize, &PackageVersion, &PackageVersionName);
    if (PackageVersionName != NULL) {
      FreePool (PackageVersionName);
    }

    if (!EFI_ERROR (Status) && (DescriptorSize >= sizeof (EFI_FIRMWARE_IMAGE_DESCRIPTOR))) {
      for (Item = 0; Item < DescriptorCount; Item++) {
        Image = (EFI_FIRMWARE_IMAGE_DESCRIPTOR *)((UINT8 *)Images + Item * DescriptorSize);
        if (CompareGuid (&Image->ImageTypeId, Ours)) {
          Info->Found   = TRUE;
          Info->Version = Image->Version;
          if (DescriptorVersion >= 2) {
            Info->Lowest = Image->LowestSupportedImageVersion;
          }

          if (DescriptorVersion >= 3) {
            Info->LastVersion = Image->LastAttemptVersion;
            Info->LastStatus  = Image->LastAttemptStatus;
          }

          break;
        }
      }
    }

    FreePool (Images);
  }

  FreePool (Handles);
}

/**
  The BIOS version of SMBIOS type 0, or NULL.
**/
STATIC
CONST CHAR8 *
GetBiosVersion (
  VOID
  )
{
  EFI_SMBIOS_PROTOCOL      *Smbios;
  EFI_SMBIOS_HANDLE        Handle;
  EFI_SMBIOS_TYPE          Type;
  EFI_SMBIOS_TABLE_HEADER  *Record;
  SMBIOS_TABLE_TYPE0       *Type0;
  CHAR8                    *String;
  UINTN                    Index;

  if (EFI_ERROR (gBS->LocateProtocol (&gEfiSmbiosProtocolGuid, NULL, (VOID **)&Smbios))) {
    return NULL;
  }

  Handle = SMBIOS_HANDLE_PI_RESERVED;
  Type   = EFI_SMBIOS_TYPE_BIOS_INFORMATION;
  if (EFI_ERROR (Smbios->GetNext (Smbios, &Handle, &Type, &Record, NULL))) {
    return NULL;
  }

  Type0 = (SMBIOS_TABLE_TYPE0 *)Record;
  if ((Record->Length < sizeof (SMBIOS_STRUCTURE) + 3) || (Type0->BiosVersion == 0)) {
    return NULL;
  }

  String = (CHAR8 *)Record + Record->Length;
  for (Index = 1; Index < Type0->BiosVersion; Index++) {
    String += AsciiStrLen (String) + 1;
    if (*String == '\0') {
      return NULL;
    }
  }

  return String;
}

/**
  The flash, as coreboot reports it: its layout, and the address where it
  ends at 4 GiB.

  @param[out] Flash  The address of the start of the flash.

  @return Its layout, or NULL if not reported or not decoded below 4 GiB.
**/
STATIC
CONST BOOT_MEDIA_INFO *
GetBootMedia (
  OUT CONST UINT8  **Flash
  )
{
  EFI_HOB_GUID_TYPE  *GuidHob;
  BOOT_MEDIA_INFO    *Media;

  GuidHob = GetFirstGuidHob (&gEfiBootMediaInfoHobGuid);
  if ((GuidHob == NULL) || (GET_GUID_HOB_DATA_SIZE (GuidHob) < sizeof (BOOT_MEDIA_INFO))) {
    return NULL;
  }

  Media = GET_GUID_HOB_DATA (GuidHob);
  if ((Media->BootMediaSize == 0) || (Media->BootMediaSize > FLASH_WINDOW_SIZE)) {
    return NULL;
  }

  *Flash = (CONST UINT8 *)(UINTN)(BASE_4GB - Media->BootMediaSize);
  return Media;
}

/**
  Where the FMAP of the running firmware puts an area.

  @retval TRUE   Found, inside the flash.
  @retval FALSE  No FMAP, or no such area.
**/
STATIC
BOOLEAN
FindFmapArea (
  IN  CONST BOOT_MEDIA_INFO  *Media,
  IN  CONST UINT8            *Flash,
  IN  CONST CHAR8            *Name,
  OUT UINT32                 *Offset,
  OUT UINT32                 *Size
  )
{
  FMAP_HEADER  Header;
  FMAP_AREA    Area;
  CHAR8        AreaName[sizeof (Area.Name) + 1];
  UINTN        Index;

  if ((Media->FmapOffset > Media->BootMediaSize) ||
      (Media->BootMediaSize - Media->FmapOffset < sizeof (Header)))
  {
    return FALSE;
  }

  CopyMem (&Header, Flash + Media->FmapOffset, sizeof (Header));
  if ((CompareMem (Header.Signature, "__FMAP__", sizeof (Header.Signature)) != 0) || (Header.VerMajor != 1) ||
      ((UINT64)Header.AreaCount * sizeof (Area) > Media->BootMediaSize - Media->FmapOffset - sizeof (Header)))
  {
    return FALSE;
  }

  for (Index = 0; Index < Header.AreaCount; Index++) {
    CopyMem (&Area, Flash + Media->FmapOffset + sizeof (Header) + Index * sizeof (Area), sizeof (Area));
    CopyMem (AreaName, Area.Name, sizeof (Area.Name));
    AreaName[sizeof (Area.Name)] = '\0';
    if ((AsciiStrCmp (AreaName, Name) == 0) && ((UINT64)Area.Offset + Area.Size <= Media->BootMediaSize)) {
      *Offset = Area.Offset;
      *Size   = Area.Size;
      return TRUE;
    }
  }

  return FALSE;
}

/**
  The value of a string #define of coreboot's build.h, without the leading
  dashes of COREBOOT_EXTRA_VERSION ("-ouroBIOS-v1.3.3-mrc").

  @retval TRUE   Found, printable and not empty.
  @retval FALSE  Not found, or too long for Value.
**/
STATIC
BOOLEAN
GetBuildDefine (
  IN  CONST CHAR8  *Text,
  IN  CONST CHAR8  *Name,
  OUT CHAR16       *Value,
  IN  UINTN        ValueLength
  )
{
  CHAR8        Prefix[48];
  CONST CHAR8  *Start;
  UINTN        Index;

  AsciiSPrint (Prefix, sizeof (Prefix), "#define %a \"", Name);
  Start = AsciiStrStr (Text, Prefix);
  if (Start == NULL) {
    return FALSE;
  }

  for (Start += AsciiStrLen (Prefix); *Start == '-'; Start++) {
  }

  for (Index = 0; (Index + 1 < ValueLength) && (Start[Index] >= ' ') && (Start[Index] <= '~') && (Start[Index] != '"'); Index++) {
    Value[Index] = (CHAR16)Start[Index];
  }

  Value[Index] = L'\0';
  return (Index > 0) && (Start[Index] == '"');
}

/**
  The release in a slot: the name that coreboot was built with
  (CONFIG_LOCALVERSION, in COREBOOT_EXTRA_VERSION of the "revision" file, its
  build.h), read from the CBFS of the slot through the flash window.  The walk
  is the one of cbfs_walk() in coreboot.

  @retval TRUE   Found, in Name.
  @retval FALSE  No CBFS with that file: an empty or damaged slot.
**/
STATIC
BOOLEAN
GetSlotRelease (
  IN  CONST UINT8  *Cbfs,
  IN  UINT32       CbfsSize,
  OUT CHAR16       *Name,
  IN  UINTN        NameLength
  )
{
  CBFS_FILE_HEADER  Header;
  CHAR8             FileName[sizeof ("revision")];
  UINT32            Offset;
  UINT32            DataOffset;
  UINT32            DataLength;
  UINT32            NameEnd;
  CHAR8             *Text;
  BOOLEAN           Found;

  Name[0] = L'\0';
  Offset  = 0;
  while ((UINT64)Offset + sizeof (Header) <= CbfsSize) {
    CopyMem (&Header, Cbfs + Offset, sizeof (Header));
    if (CompareMem (Header.Magic, "LARCHIVE", sizeof (Header.Magic)) != 0) {
      Offset += CBFS_ALIGNMENT;
      continue;
    }

    DataOffset = SwapBytes32 (Header.Offset);
    DataLength = SwapBytes32 (Header.Len);
    if ((DataOffset < sizeof (Header)) || (DataOffset > CBFS_METADATA_MAX) ||
        ((UINT64)Offset + DataOffset + DataLength > CbfsSize))
    {
      Offset += CBFS_ALIGNMENT;
      continue;
    }

    NameEnd = SwapBytes32 (Header.AttributesOffset);
    if ((NameEnd == 0) || (NameEnd > DataOffset)) {
      NameEnd = DataOffset;
    }

    if (NameEnd >= sizeof (Header) + sizeof (FileName)) {
      CopyMem (FileName, Cbfs + Offset + sizeof (Header), sizeof (FileName));
      if ((CompareMem (FileName, "revision", sizeof (FileName)) == 0) && (DataLength <= REVISION_MAX_SIZE)) {
        Text = AllocateZeroPool (DataLength + 1);
        if (Text == NULL) {
          return FALSE;
        }

        CopyMem (Text, Cbfs + Offset + DataOffset, DataLength);
        Found = GetBuildDefine (Text, "COREBOOT_EXTRA_VERSION", Name, NameLength) ||
                GetBuildDefine (Text, "COREBOOT_VERSION", Name, NameLength);
        FreePool (Text);
        if (!Found) {
          Name[0] = L'\0';
        }

        return Found;
      }
    }

    Offset = ALIGN_VALUE (Offset + DataOffset + DataLength, CBFS_ALIGNMENT);
  }

  return FALSE;
}

/**
  The RW slots of vboot (FW_MAIN_A and FW_MAIN_B in the FMAP): the one that
  runs is the one of the CBFS that coreboot reports to the payload.
**/
STATIC
VOID
GetSlotInfo (
  OUT SLOT_INFO  *Slots
  )
{
  CONST BOOT_MEDIA_INFO  *Media;
  CONST UINT8            *Flash;
  UINT32                 Offset[2];
  UINT32                 Size[2];
  UINTN                  Running;

  ZeroMem (Slots, sizeof (*Slots));
  Media = GetBootMedia (&Flash);
  if ((Media == NULL) ||
      !FindFmapArea (Media, Flash, "FW_MAIN_A", &Offset[0], &Size[0]) ||
      !FindFmapArea (Media, Flash, "FW_MAIN_B", &Offset[1], &Size[1]))
  {
    return;
  }

  for (Running = 0; Running < 2; Running++) {
    if ((Media->CbfsOffset >= Offset[Running]) && (Media->CbfsOffset - Offset[Running] < Size[Running])) {
      break;
    }
  }

  if (Running == 2) {
    return;
  }

  Slots->Found   = TRUE;
  Slots->Running = (Running == 0) ? L'A' : L'B';
  Slots->Other   = (Running == 0) ? L'B' : L'A';
  GetSlotRelease (Flash + Offset[Running], Size[Running], Slots->RunningName, ARRAY_SIZE (Slots->RunningName));
  GetSlotRelease (Flash + Offset[1 - Running], Size[1 - Running], Slots->OtherName, ARRAY_SIZE (Slots->OtherName));
}

/**
  The version in the name of a release, "...-vX.Y.Z[-rcN][-...]", numbered
  as the ESRT numbers the releases: X.Y.Z.R, one byte each. A release is
  X.Y.Z.0, its candidate N the release before with R = N (v1.3.7-rc2 is
  1.3.6.2), as tools/build.sh numbers them.

  @retval TRUE   Found.
  @retval FALSE  The name has none.
**/
STATIC
BOOLEAN
ParseReleaseVersion (
  IN  CONST CHAR16  *Name,
  OUT UINT32        *Version
  )
{
  CONST CHAR16  *Text;
  CONST CHAR16  *Digit;
  UINT32        Part[3];
  UINT32        Base;
  UINT32        Candidate;
  UINTN         Index;

  for (Text = Name; *Text != L'\0'; Text++) {
    if ((*Text != L'v') || ((Text != Name) && (Text[-1] != L'-'))) {
      continue;
    }

    ZeroMem (Part, sizeof (Part));
    Digit = Text + 1;
    for (Index = 0; Index < ARRAY_SIZE (Part); Index++) {
      if ((Index > 0) && (*Digit++ != L'.')) {
        break;
      }

      if ((*Digit < L'0') || (*Digit > L'9')) {
        break;
      }

      for ( ; (*Digit >= L'0') && (*Digit <= L'9') && (Part[Index] <= MAX_UINT8); Digit++) {
        Part[Index] = Part[Index] * 10 + (*Digit - L'0');
      }
    }

    if ((Index != ARRAY_SIZE (Part)) || (Part[0] > MAX_UINT8) || (Part[1] > MAX_UINT8) || (Part[2] > MAX_UINT8)) {
      continue;
    }

    Base      = (Part[0] << 24) | (Part[1] << 16) | (Part[2] << 8);
    Candidate = 0;
    if ((Digit[0] == L'-') && (Digit[1] == L'r') && (Digit[2] == L'c') && (Digit[3] >= L'0') && (Digit[3] <= L'9')) {
      if (Digit[3] == L'0') {
        continue;                       // no -rc0, no -rc01: not a candidate
      }

      for (Digit += 3; (*Digit >= L'0') && (*Digit <= L'9') && (Candidate <= MAX_UINT8); Digit++) {
        Candidate = Candidate * 10 + (*Digit - L'0');
      }

      if ((Candidate > MAX_UINT8) || (Base < 0x100)) {
        continue;
      }
    }

    if ((*Digit != L'\0') && (*Digit != L'-') && (*Digit != L'+')) {
      continue;
    }

    *Version = (Candidate != 0) ? Base - 0x100 + Candidate : Base;
    return TRUE;
  }

  return FALSE;
}

/**
  The variant in the name of a release: "mrc", "nri" or "fsp" after a dash,
  at the end or before the optional patches ("+...").

  @return The variant, or NULL.
**/
STATIC
CONST CHAR16 *
ReleaseVariant (
  IN CONST CHAR16  *Name
  )
{
  STATIC CONST CHAR16  *Variants[] = { L"mrc", L"nri", L"fsp" };
  CONST CHAR16         *Text;
  UINTN                Index;
  UINTN                Length;

  for (Text = Name; *Text != L'\0'; Text++) {
    if (*Text != L'-') {
      continue;
    }

    for (Index = 0; Index < ARRAY_SIZE (Variants); Index++) {
      Length = StrLen (Variants[Index]);
      if ((StrnCmp (Text + 1, Variants[Index], Length) == 0) &&
          ((Text[1 + Length] == L'\0') || (Text[1 + Length] == L'+')))
      {
        return Variants[Index];
      }
    }
  }

  return NULL;
}

/**
  Fill in the slots of vboot, and the entry that goes to the other one.
**/
STATIC
VOID
RefreshSlots (
  IN CONST SYSTEM_FIRMWARE_INFO  *Info
  )
{
  SLOT_INFO  Slots;
  CHAR16     Value[128];
  UINT32     Version;

  GetSlotInfo (&Slots);
  if (!Slots.Found) {
    return;
  }

  DEBUG ((
    DEBUG_INFO,
    "FirmwareUpdate: slot %c runs %s, slot %c holds %s\n",
    Slots.Running,
    (Slots.RunningName[0] != L'\0') ? Slots.RunningName : L"no release",
    Slots.Other,
    (Slots.OtherName[0] != L'\0') ? Slots.OtherName : L"no release"
    ));
  if (Slots.RunningName[0] != L'\0') {
    UnicodeSPrint (Value, sizeof (Value), L"%c: %s", Slots.Running, Slots.RunningName);
  } else {
    UnicodeSPrint (Value, sizeof (Value), L"%c", Slots.Running);
  }

  HiiSetString (mHiiHandle, STRING_TOKEN (STR_RUNNING_VALUE), Value, NULL);
  if (Slots.OtherName[0] == L'\0') {
    UnicodeSPrint (Value, sizeof (Value), L"%c: empty or damaged", Slots.Other);
    HiiSetString (mHiiHandle, STRING_TOKEN (STR_OTHER_VALUE), Value, NULL);
    return;
  }

  UnicodeSPrint (Value, sizeof (Value), L"%c: %s", Slots.Other, Slots.OtherName);
  HiiSetString (mHiiHandle, STRING_TOKEN (STR_OTHER_VALUE), Value, NULL);
  if (Info->Found && ParseReleaseVersion (Slots.OtherName, &Version) && (Version < Info->Version)) {
    UnicodeSPrint (Value, sizeof (Value), L"Go back to %s", Slots.OtherName);
  } else {
    UnicodeSPrint (Value, sizeof (Value), L"Switch to %s", Slots.OtherName);
  }

  HiiSetString (mHiiHandle, STRING_TOKEN (STR_SLOT_PROMPT), Value, NULL);
}

/**
  Fill in the values of the page.
**/
STATIC
VOID
RefreshInfo (
  VOID
  )
{
  SYSTEM_FIRMWARE_INFO  Info;
  CONST CHAR8           *Bios;
  CHAR16                Value[128];
  CHAR16                Version[VERSION_LENGTH];
  CHAR16                Result[64];

  Bios = GetBiosVersion ();
  if (Bios != NULL) {
    UnicodeSPrint (Value, sizeof (Value), L"%a", Bios);
    HiiSetString (mHiiHandle, STRING_TOKEN (STR_FIRMWARE_VALUE), Value, NULL);
  }

  GetSystemFirmwareInfo (&Info);
  RefreshSlots (&Info);
  if (!Info.Found) {
    return;
  }

  FormatVersion (Info.Version, Value, sizeof (Value));
  HiiSetString (mHiiHandle, STRING_TOKEN (STR_VERSION_VALUE), Value, NULL);
  FormatVersion (Info.Lowest, Value, sizeof (Value));
  HiiSetString (mHiiHandle, STRING_TOKEN (STR_LOWEST_VALUE), Value, NULL);

  if ((Info.LastVersion == 0) && (Info.LastStatus == 0)) {
    StrCpyS (Value, ARRAY_SIZE (Value), L"None");
  } else {
    FormatVersion (Info.LastVersion, Version, sizeof (Version));
    FormatAttemptStatus (Info.LastStatus, Result, sizeof (Result));
    UnicodeSPrint (Value, sizeof (Value), L"%s, %s", Version, Result);
  }

  HiiSetString (mHiiHandle, STRING_TOKEN (STR_LAST_VALUE), Value, NULL);
}

/**
  Show a message, with the popups of the display engine when it has them.

  @return The button chosen.
**/
STATIC
EFI_HII_POPUP_SELECTION
EFIAPI
ShowPopup (
  IN EFI_HII_POPUP_STYLE  Style,
  IN EFI_HII_POPUP_TYPE   Type,
  IN CONST CHAR16         *Format,
  ...
  )
{
  VA_LIST                  Marker;
  CHAR16                   Message[512];
  EFI_HII_POPUP_PROTOCOL   *HiiPopup;
  EFI_HII_POPUP_SELECTION  Selection;
  EFI_INPUT_KEY            Key;

  VA_START (Marker, Format);
  UnicodeVSPrint (Message, sizeof (Message), Format, Marker);
  VA_END (Marker);
  DEBUG ((DEBUG_INFO, "FirmwareUpdate: %s\n", Message));

  if (!EFI_ERROR (gBS->LocateProtocol (&gEfiHiiPopupProtocolGuid, NULL, (VOID **)&HiiPopup)) &&
      (HiiSetString (mHiiHandle, STRING_TOKEN (STR_POPUP_MESSAGE), Message, NULL) != 0) &&
      !EFI_ERROR (HiiPopup->CreatePopup (HiiPopup, Style, Type, mHiiHandle, STRING_TOKEN (STR_POPUP_MESSAGE), &Selection)))
  {
    return Selection;
  }

  CreatePopUp (
    EFI_LIGHTGRAY | EFI_BACKGROUND_BLUE,
    &Key,
    Message,
    L"",
    (Type == EfiHiiPopupTypeYesNo) ? L"Press Y to continue, any other key to cancel" : L"Press any key to continue",
    NULL
    );
  if (Type != EfiHiiPopupTypeYesNo) {
    return EfiHiiPopupSelectionOk;
  }

  return ((Key.UnicodeChar == L'y') || (Key.UnicodeChar == L'Y')) ? EfiHiiPopupSelectionYes : EfiHiiPopupSelectionNo;
}

/**
  Whether the next boot reads capsules from this file system: an EFI system
  partition, or a USB drive.  PlatformBootManagerLib uses the same rule.
**/
STATIC
BOOLEAN
IsCapsuleSource (
  IN EFI_HANDLE  Handle
  )
{
  VOID                      *Interface;
  EFI_DEVICE_PATH_PROTOCOL  *Node;

  if (!EFI_ERROR (gBS->HandleProtocol (Handle, &gEfiPartTypeSystemPartGuid, &Interface))) {
    return TRUE;
  }

  for (Node = DevicePathFromHandle (Handle); (Node != NULL) && !IsDevicePathEnd (Node); Node = NextDevicePathNode (Node)) {
    if ((DevicePathType (Node) == MESSAGING_DEVICE_PATH) &&
        ((DevicePathSubType (Node) == MSG_USB_DP) || (DevicePathSubType (Node) == MSG_USB_CLASS_DP) ||
         (DevicePathSubType (Node) == MSG_USB_WWID_DP)))
    {
      return TRUE;
    }
  }

  return FALSE;
}

/**
  The image type and the version of an FMP capsule with one signed image,
  as GenerateCapsule makes it, from its first bytes.

  @retval TRUE   It is one.
  @retval FALSE  It is not, or its headers don't fit in Size.
**/
STATIC
BOOLEAN
ParseCapsule (
  IN  CONST UINT8  *Buffer,
  IN  UINTN        Size,
  OUT EFI_GUID     *TypeId,
  OUT UINT32       *Version
  )
{
  CONST EFI_CAPSULE_HEADER                            *Capsule;
  CONST EFI_FIRMWARE_MANAGEMENT_CAPSULE_HEADER        *Fmp;
  CONST EFI_FIRMWARE_MANAGEMENT_CAPSULE_IMAGE_HEADER  *Image;
  CONST EFI_FIRMWARE_IMAGE_AUTHENTICATION             *Auth;
  CONST FMP_PAYLOAD_HEADER_V1                         *Payload;
  UINTN                                               FmpOffset;
  UINTN                                               ImageOffset;
  UINTN                                               AuthOffset;
  UINTN                                               PayloadOffset;
  UINTN                                               Items;
  UINT64                                              ItemOffset;

  Capsule = (CONST EFI_CAPSULE_HEADER *)Buffer;
  if ((Size < sizeof (EFI_CAPSULE_HEADER)) || !CompareGuid (&Capsule->CapsuleGuid, &gEfiFmpCapsuleGuid)) {
    return FALSE;
  }

  FmpOffset = Capsule->HeaderSize;
  if ((FmpOffset < sizeof (EFI_CAPSULE_HEADER)) || (FmpOffset > Size) ||
      (Size - FmpOffset < sizeof (EFI_FIRMWARE_MANAGEMENT_CAPSULE_HEADER)))
  {
    return FALSE;
  }

  Fmp = (CONST EFI_FIRMWARE_MANAGEMENT_CAPSULE_HEADER *)(Buffer + FmpOffset);
  if ((Fmp->Version != EFI_FIRMWARE_MANAGEMENT_CAPSULE_HEADER_INIT_VERSION) || (Fmp->PayloadItemCount == 0)) {
    return FALSE;
  }

  Items = (UINTN)Fmp->EmbeddedDriverCount + Fmp->PayloadItemCount;
  if (Size - FmpOffset < sizeof (EFI_FIRMWARE_MANAGEMENT_CAPSULE_HEADER) + Items * sizeof (UINT64)) {
    return FALSE;
  }

  //
  // The offsets of the drivers, then of the payloads, follow the header.
  //
  ItemOffset = ReadUnaligned64 (
                 (CONST UINT64 *)(Buffer + FmpOffset + sizeof (EFI_FIRMWARE_MANAGEMENT_CAPSULE_HEADER) +
                                  (UINTN)Fmp->EmbeddedDriverCount * sizeof (UINT64))
                 );
  if ((ItemOffset > Size - FmpOffset) ||
      (Size - FmpOffset - (UINTN)ItemOffset < sizeof (EFI_FIRMWARE_MANAGEMENT_CAPSULE_IMAGE_HEADER)))
  {
    return FALSE;
  }

  ImageOffset = FmpOffset + (UINTN)ItemOffset;
  Image       = (CONST EFI_FIRMWARE_MANAGEMENT_CAPSULE_IMAGE_HEADER *)(Buffer + ImageOffset);
  if ((Image->Version < EFI_FIRMWARE_MANAGEMENT_CAPSULE_IMAGE_HEADER_INIT_VERSION) ||
      ((Image->ImageCapsuleSupport & CAPSULE_SUPPORT_DEPENDENCY) != 0))
  {
    return FALSE;
  }

  AuthOffset = ImageOffset + sizeof (EFI_FIRMWARE_MANAGEMENT_CAPSULE_IMAGE_HEADER);
  if (Size - AuthOffset < OFFSET_OF (EFI_FIRMWARE_IMAGE_AUTHENTICATION, AuthInfo.CertData)) {
    return FALSE;
  }

  Auth = (CONST EFI_FIRMWARE_IMAGE_AUTHENTICATION *)(Buffer + AuthOffset);
  if ((Auth->AuthInfo.Hdr.dwLength < OFFSET_OF (WIN_CERTIFICATE_UEFI_GUID, CertData)) ||
      (Auth->AuthInfo.Hdr.dwLength > Size - AuthOffset - sizeof (UINT64)))
  {
    return FALSE;
  }

  PayloadOffset = AuthOffset + sizeof (UINT64) + Auth->AuthInfo.Hdr.dwLength;
  if (Size - PayloadOffset < sizeof (FMP_PAYLOAD_HEADER_V1)) {
    return FALSE;
  }

  Payload = (CONST FMP_PAYLOAD_HEADER_V1 *)(Buffer + PayloadOffset);
  if (Payload->Signature != FMP_PAYLOAD_HEADER_SIGNATURE) {
    return FALSE;
  }

  CopyGuid (TypeId, &Image->UpdateImageTypeId);
  *Version = Payload->FwVersion;
  return TRUE;
}

/**
  Count the files in \EFI\UpdateCapsule of a file system, and the capsules
  for this firmware among them.
**/
STATIC
VOID
ScanDirectory (
  IN     EFI_FILE_PROTOCOL  *Root,
  IN     CONST EFI_GUID     *Ours,
  IN OUT CAPSULE_SCAN       *Scan
  )
{
  EFI_STATUS         Status;
  EFI_FILE_PROTOCOL  *Dir;
  EFI_FILE_PROTOCOL  *File;
  EFI_FILE_INFO      *Info;
  UINT8              *Buffer;
  UINTN              Size;
  EFI_GUID           TypeId;
  UINT32             Version;

  if (EFI_ERROR (Root->Open (Root, &Dir, CAPSULE_DIR, EFI_FILE_MODE_READ, 0))) {
    return;
  }

  Info   = AllocatePool (FILE_INFO_SIZE);
  Buffer = AllocatePool (CAPSULE_PROBE_SIZE);
  while ((Info != NULL) && (Buffer != NULL)) {
    Size   = FILE_INFO_SIZE;
    Status = Dir->Read (Dir, &Size, Info);
    if (EFI_ERROR (Status) || (Size == 0)) {
      break;
    }

    if ((Info->Attribute & EFI_FILE_DIRECTORY) != 0) {
      continue;
    }

    Scan->Files++;
    StrnCpyS (Scan->Name, ARRAY_SIZE (Scan->Name), Info->FileName, ARRAY_SIZE (Scan->Name) - 1);
    if (EFI_ERROR (Dir->Open (Dir, &File, Info->FileName, EFI_FILE_MODE_READ, 0))) {
      continue;
    }

    Size   = (UINTN)MIN (Info->FileSize, CAPSULE_PROBE_SIZE);
    Status = File->Read (File, &Size, Buffer);
    File->Close (File);
    if (!EFI_ERROR (Status) && ParseCapsule (Buffer, Size, &TypeId, &Version) && CompareGuid (&TypeId, Ours)) {
      Scan->Capsules++;
      Scan->Version = Version;
    }
  }

  if (Info != NULL) {
    FreePool (Info);
  }

  if (Buffer != NULL) {
    FreePool (Buffer);
  }

  Dir->Close (Dir);
}

/**
  Connect the drives, then look at the capsules the next boot would read.
**/
STATIC
VOID
ScanCapsules (
  OUT CAPSULE_SCAN  *Scan
  )
{
  EFI_STATUS                       Status;
  EFI_HANDLE                       *Handles;
  UINTN                            HandleCount;
  UINTN                            Index;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL  *FileSystem;
  EFI_FILE_PROTOCOL                *Root;

  ZeroMem (Scan, sizeof (*Scan));
  if (PcdGetSize (PcdSystemFmpCapsuleImageTypeIdGuid) < sizeof (EFI_GUID)) {
    return;
  }

  //
  // A drive connected after the boot devices were: its file system too.
  //
  Status = gBS->LocateHandleBuffer (AllHandles, NULL, NULL, &HandleCount, &Handles);
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < HandleCount; Index++) {
      gBS->ConnectController (Handles[Index], NULL, NULL, TRUE);
    }

    FreePool (Handles);
  }

  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &HandleCount, &Handles);
  if (EFI_ERROR (Status)) {
    return;
  }

  for (Index = 0; Index < HandleCount; Index++) {
    if (!IsCapsuleSource (Handles[Index]) ||
        EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiSimpleFileSystemProtocolGuid, (VOID **)&FileSystem)) ||
        EFI_ERROR (FileSystem->OpenVolume (FileSystem, &Root)))
    {
      continue;
    }

    ScanDirectory (Root, (CONST EFI_GUID *)PcdGetPtr (PcdSystemFmpCapsuleImageTypeIdGuid), Scan);
    Root->Close (Root);
  }

  FreePool (Handles);
}

/**
  Check the capsule on the USB drive, then request it and restart.
**/
STATIC
VOID
UpdateFromDrive (
  VOID
  )
{
  EFI_STATUS            Status;
  UINT64                Value;
  UINTN                 Size;
  SYSTEM_FIRMWARE_INFO  Info;
  CAPSULE_SCAN          Scan;
  CHAR16                New[VERSION_LENGTH];
  CHAR16                Old[VERSION_LENGTH];

  Size = sizeof (Value);
  if (EFI_ERROR (gRT->GetVariable (EFI_OS_INDICATIONS_SUPPORT_VARIABLE_NAME, &gEfiGlobalVariableGuid, NULL, &Size, &Value)) ||
      ((Value & EFI_OS_INDICATIONS_FILE_CAPSULE_DELIVERY_SUPPORTED) == 0))
  {
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"This firmware does not install update capsules from a drive.");
    return;
  }

  GetSystemFirmwareInfo (&Info);
  if (!Info.Found) {
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"The system firmware is not in the EFI System Resource Table: it cannot be updated with a capsule.");
    return;
  }

  ScanCapsules (&Scan);
  if (Scan.Files == 0) {
    ShowPopup (
      EfiHiiPopupStyleInfo,
      EfiHiiPopupTypeOk,
      L"No update found.\nCopy the .cap file of a release into the folder EFI\\UpdateCapsule of a FAT USB drive, connect the drive and try again."
      );
    return;
  }

  if (Scan.Files > 1) {
    ShowPopup (
      EfiHiiPopupStyleWarning,
      EfiHiiPopupTypeOk,
      L"%u files in EFI\\UpdateCapsule, on the USB drives and the EFI system partitions: the next boot would apply all of them. Leave only the capsule to install.",
      (UINT32)Scan.Files
      );
    return;
  }

  if (Scan.Capsules == 0) {
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"%s is not an update for this firmware: a capsule of the other variant, of another computer, or not a capsule.",
      Scan.Name
      );
    return;
  }

  FormatVersion (Scan.Version, New, sizeof (New));
  FormatVersion (Info.Version, Old, sizeof (Old));
  if (Scan.Version < Info.Lowest) {
    FormatVersion (Info.Lowest, Old, sizeof (Old));
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"%s is version %s, older than the oldest accepted update, %s.", Scan.Name, New, Old);
    return;
  }

  if (ShowPopup (
        EfiHiiPopupStyleWarning,
        EfiHiiPopupTypeYesNo,
        L"Install firmware %s (now %s) from %s?\nThe computer restarts, checks the signature and writes the update, in about a minute: do not turn it off. Unsaved changes in the setup are lost.",
        New,
        Old,
        Scan.Name
        ) != EfiHiiPopupSelectionYes)
  {
    return;
  }

  Size = sizeof (Value);
  if (EFI_ERROR (gRT->GetVariable (EFI_OS_INDICATIONS_VARIABLE_NAME, &gEfiGlobalVariableGuid, NULL, &Size, &Value)) ||
      (Size != sizeof (Value)))
  {
    Value = 0;
  }

  Value |= EFI_OS_INDICATIONS_FILE_CAPSULE_DELIVERY_SUPPORTED;
  Status = gRT->SetVariable (
                  EFI_OS_INDICATIONS_VARIABLE_NAME,
                  &gEfiGlobalVariableGuid,
                  EFI_VARIABLE_NON_VOLATILE | EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS,
                  sizeof (Value),
                  &Value
                  );
  if (EFI_ERROR (Status)) {
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"The update could not be requested (%r).", Status);
    return;
  }

  DEBUG ((DEBUG_INFO, "FirmwareUpdate: capsule on disk requested, restarting\n"));
  gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
  CpuDeadLoop ();
}

/**
  Start the release of the other vboot slot from the next boot, then restart.
  The checks of a capsule that apply here first: a release, not the one that
  runs, of the same variant, not older than the lowest supported version.
  The signature of the slot is vboot's to check, at the next boot.
**/
STATIC
VOID
GoToOtherSlot (
  VOID
  )
{
  EFI_STATUS            Status;
  SLOT_INFO             Slots;
  SYSTEM_FIRMWARE_INFO  Info;
  UINT32                Version;
  CONST CHAR16          *Variant;
  CONST CHAR16          *OtherVariant;
  CHAR16                Lowest[VERSION_LENGTH];

  GetSlotInfo (&Slots);
  if (!Slots.Found) {
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"This firmware does not run from one of two slots: there is no other one to start.");
    return;
  }

  if (Slots.OtherName[0] == L'\0') {
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"Slot %c holds no firmware that can start: it is empty or damaged.", Slots.Other);
    return;
  }

  if (Slots.RunningName[0] == L'\0') {
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"The release in slot %c, which runs, is not known: the one in slot %c cannot be checked against it.",
      Slots.Running,
      Slots.Other
      );
    return;
  }

  if (StrCmp (Slots.OtherName, Slots.RunningName) == 0) {
    ShowPopup (
      EfiHiiPopupStyleInfo,
      EfiHiiPopupTypeOk,
      L"Slot %c holds the same firmware as slot %c, %s: there is nothing to go back to.",
      Slots.Other,
      Slots.Running,
      Slots.OtherName
      );
    return;
  }

  Variant      = ReleaseVariant (Slots.RunningName);
  OtherVariant = ReleaseVariant (Slots.OtherName);
  if ((Variant == NULL) || (OtherVariant == NULL)) {
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"The variant of %s (mrc, nri or fsp) is not known: it may not start after the read-only part of this firmware.",
      (OtherVariant == NULL) ? Slots.OtherName : Slots.RunningName
      );
    return;
  }

  if (StrCmp (Variant, OtherVariant) != 0) {
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"%s, in slot %c, is the %s variant: it does not start after the read-only part of this firmware, %s. Write the whole image of a release with flashrom instead.",
      Slots.OtherName,
      Slots.Other,
      OtherVariant,
      Variant
      );
    return;
  }

  GetSystemFirmwareInfo (&Info);
  if (!Info.Found) {
    ShowPopup (EfiHiiPopupStyleError, EfiHiiPopupTypeOk, L"The system firmware is not in the EFI System Resource Table: the oldest accepted update is not known.");
    return;
  }

  if (!ParseReleaseVersion (Slots.OtherName, &Version)) {
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"%s, in slot %c, has no version in its name: it cannot be checked against the oldest accepted update.",
      Slots.OtherName,
      Slots.Other
      );
    return;
  }

  if (Version < Info.Lowest) {
    FormatVersion (Info.Lowest, Lowest, sizeof (Lowest));
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"%s, in slot %c, is older than the oldest accepted update, %s.",
      Slots.OtherName,
      Slots.Other,
      Lowest
      );
    return;
  }

  if (ShowPopup (
        EfiHiiPopupStyleWarning,
        EfiHiiPopupTypeYesNo,
        L"Start %s, in slot %c, from now on?\nThe computer restarts into it. If it does not start twice in a row, the firmware comes back to this one, %s. The first start may train the memory again: up to a minute with a dark screen. Do not turn the computer off meanwhile. Settings, boot entries and Secure Boot keys are kept. Unsaved changes in the setup are lost.",
        Slots.OtherName,
        Slots.Other,
        Slots.RunningName
        ) != EfiHiiPopupSelectionYes)
  {
    return;
  }

  Status = SmmStoreLibInitialize ();
  if (!EFI_ERROR (Status)) {
    Status = SmmStoreLibVbootTryOtherSlot ();
    SmmStoreLibDeinitialize ();
  }

  if (EFI_ERROR (Status)) {
    ShowPopup (
      EfiHiiPopupStyleError,
      EfiHiiPopupTypeOk,
      L"The firmware did not switch to slot %c (%r). Once a boot option has started, the switch waits for a restart: restart, press Esc and try again.",
      Slots.Other,
      Status
      );
    return;
  }

  DEBUG ((DEBUG_INFO, "FirmwareUpdate: slot %c next, %s, restarting\n", Slots.Other, Slots.OtherName));
  gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
  CpuDeadLoop ();
}

/**
  No varstore: nothing to extract.
**/
STATIC
EFI_STATUS
EFIAPI
FirmwareUpdateExtractConfig (
  IN  CONST EFI_HII_CONFIG_ACCESS_PROTOCOL  *This,
  IN  CONST EFI_STRING                      Request,
  OUT EFI_STRING                            *Progress,
  OUT EFI_STRING                            *Results
  )
{
  if ((Progress == NULL) || (Results == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  *Progress = Request;
  return EFI_NOT_FOUND;
}

/**
  No varstore: nothing to route.
**/
STATIC
EFI_STATUS
EFIAPI
FirmwareUpdateRouteConfig (
  IN  CONST EFI_HII_CONFIG_ACCESS_PROTOCOL  *This,
  IN  CONST EFI_STRING                      Configuration,
  OUT EFI_STRING                            *Progress
  )
{
  if ((Configuration == NULL) || (Progress == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  *Progress = Configuration;
  return EFI_NOT_FOUND;
}

/**
  Refresh the page when it opens; update, or go to the other slot, when the
  entry is selected (the browser calls a goto question only with
  EFI_BROWSER_ACTION_CHANGING).
**/
STATIC
EFI_STATUS
EFIAPI
FirmwareUpdateCallback (
  IN  CONST EFI_HII_CONFIG_ACCESS_PROTOCOL  *This,
  IN  EFI_BROWSER_ACTION                    Action,
  IN  EFI_QUESTION_ID                       QuestionId,
  IN  UINT8                                 Type,
  IN  EFI_IFR_TYPE_VALUE                    *Value,
  OUT EFI_BROWSER_ACTION_REQUEST            *ActionRequest
  )
{
  if ((This == NULL) || (ActionRequest == NULL)) {
    return EFI_INVALID_PARAMETER;
  }

  *ActionRequest = EFI_BROWSER_ACTION_REQUEST_NONE;
  if (Action == EFI_BROWSER_ACTION_FORM_OPEN) {
    RefreshInfo ();
    return EFI_SUCCESS;
  }

  if (Action != EFI_BROWSER_ACTION_CHANGING) {
    return EFI_UNSUPPORTED;
  }

  if (QuestionId == FIRMWARE_UPDATE_INSTALL_QUESTION_ID) {
    UpdateFromDrive ();
  } else if (QuestionId == FIRMWARE_UPDATE_SLOT_QUESTION_ID) {
    GoToOtherSlot ();
  }

  return EFI_SUCCESS;
}

/**
  Driver entry point: publish the page.
**/
EFI_STATUS
EFIAPI
FirmwareUpdateDxeEntryPoint (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS  Status;

  mConfigAccess.ExtractConfig = FirmwareUpdateExtractConfig;
  mConfigAccess.RouteConfig   = FirmwareUpdateRouteConfig;
  mConfigAccess.Callback      = FirmwareUpdateCallback;
  mDriverHandle               = NULL;

  Status = gBS->InstallMultipleProtocolInterfaces (
                  &mDriverHandle,
                  &gEfiDevicePathProtocolGuid,
                  &mVendorDevicePath,
                  &gEfiHiiConfigAccessProtocolGuid,
                  &mConfigAccess,
                  NULL
                  );
  if (EFI_ERROR (Status)) {
    return Status;
  }

  mHiiHandle = HiiAddPackages (&gFirmwareUpdateFormSetGuid, mDriverHandle, FirmwareUpdateDxeStrings, FirmwareUpdateVfrBin, NULL);
  if (mHiiHandle == NULL) {
    gBS->UninstallMultipleProtocolInterfaces (
           mDriverHandle,
           &gEfiDevicePathProtocolGuid,
           &mVendorDevicePath,
           &gEfiHiiConfigAccessProtocolGuid,
           &mConfigAccess,
           NULL
           );
    return EFI_OUT_OF_RESOURCES;
  }

  return EFI_SUCCESS;
}
