/** @file
  vboot A/B updates for SMMSTORE-backed firmware updates.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>

#include "FmpDeviceSmmVboot.h"

/**
  Whether a manifest entry names Name.
**/
STATIC
BOOLEAN
EntryIs (
  IN CONST REGION_MANIFEST_ENTRY  *Entry,
  IN CONST CHAR8                  *Name
  )
{
  CHAR8  Padded[REGION_MANIFEST_NAME_LEN];

  ZeroMem (Padded, sizeof (Padded));
  CopyMem (Padded, Name, AsciiStrLen (Name));
  return CompareMem (Entry->RegionName, Padded, sizeof (Padded)) == 0;
}

BOOLEAN
FmpVbootFindSlots (
  IN  CONST REGION_MANIFEST_ENTRY  *Entries,
  IN  UINTN                        Count,
  OUT UINTN                        *IndexA,
  OUT UINTN                        *IndexB
  )
{
  UINTN  Index;
  UINTN  FoundA;
  UINTN  FoundB;

  if (Entries == NULL) {
    return FALSE;
  }

  FoundA = 0;
  FoundB = 0;
  for (Index = 0; Index < Count; Index++) {
    if (EntryIs (&Entries[Index], "RW_SECTION_A")) {
      *IndexA = Index;
      FoundA++;
    } else if (EntryIs (&Entries[Index], "RW_SECTION_B")) {
      *IndexB = Index;
      FoundB++;
    }
  }

  return (FoundA == 1) && (FoundB == 1);
}

BOOLEAN
FmpVbootManifestFitsFlash (
  IN CONST REGION_MANIFEST_ENTRY  *Entries,
  IN UINTN                        Count,
  IN BOOLEAN                      FlashHasSlots
  )
{
  UINTN  IndexA;
  UINTN  IndexB;

  return !FlashHasSlots || FmpVbootFindSlots (Entries, Count, &IndexA, &IndexB);
}

UINT8
FmpVbootNvCrc8 (
  IN CONST UINT8  *Data,
  IN UINTN        Size
  )
{
  UINT32  Crc;
  UINTN   Index;
  UINTN   Bit;

  Crc = 0;
  for (Index = 0; Index < Size; Index++) {
    Crc ^= ((UINT32)Data[Index] << 8);
    for (Bit = 0; Bit < 8; Bit++) {
      if ((Crc & 0x8000) != 0) {
        Crc ^= (0x1070 << 3);
      }

      Crc <<= 1;
    }
  }

  return (UINT8)(Crc >> 8);
}

/**
  Whether a record is erased flash.
**/
STATIC
BOOLEAN
RecordIsErased (
  IN CONST UINT8  *Record
  )
{
  UINTN  Index;

  for (Index = 0; Index < VBOOT_NV_RECORD_SIZE; Index++) {
    if (Record[Index] != 0xFF) {
      return FALSE;
    }
  }

  return TRUE;
}

BOOLEAN
FmpVbootNvFindCurrent (
  IN  CONST UINT8  *Region,
  IN  UINTN        Size,
  OUT UINT8        Record[VBOOT_NV_RECORD_SIZE],
  OUT UINTN        *NextOffset
  )
{
  UINTN  Offset;

  //
  // Records are appended from the start of the region, and the region is
  // erased when it is full: the current one is the last before the first
  // erased one.
  //
  for (Offset = 0; Offset + VBOOT_NV_RECORD_SIZE <= Size; Offset += VBOOT_NV_RECORD_SIZE) {
    if (RecordIsErased (Region + Offset)) {
      break;
    }
  }

  *NextOffset = (Offset + VBOOT_NV_RECORD_SIZE <= Size) ? Offset : Size;
  if ((Offset > 0) &&
      ((Region[Offset - VBOOT_NV_RECORD_SIZE + VBOOT_NV_OFFS_HEADER] & VBOOT_NV_HEADER_MASK) == VBOOT_NV_HEADER_SIGNATURE) &&
      (FmpVbootNvCrc8 (Region + Offset - VBOOT_NV_RECORD_SIZE, VBOOT_NV_OFFS_CRC) ==
       Region[Offset - VBOOT_NV_RECORD_SIZE + VBOOT_NV_OFFS_CRC]))
  {
    CopyMem (Record, Region + Offset - VBOOT_NV_RECORD_SIZE, VBOOT_NV_RECORD_SIZE);
    return TRUE;
  }

  //
  // What vboot starts from without valid nvdata: slot A, nothing to try.
  //
  ZeroMem (Record, VBOOT_NV_RECORD_SIZE);
  Record[VBOOT_NV_OFFS_HEADER] = VBOOT_NV_HEADER_SIGNATURE;
  Record[VBOOT_NV_OFFS_CRC]    = FmpVbootNvCrc8 (Record, VBOOT_NV_OFFS_CRC);
  return FALSE;
}

UINTN
FmpVbootNvTriedSlot (
  IN CONST UINT8  Record[VBOOT_NV_RECORD_SIZE]
  )
{
  return ((Record[VBOOT_NV_OFFS_BOOT2] & VBOOT_NV_BOOT2_TRIED) != 0) ? 1 : 0;
}

VOID
FmpVbootNvSetTryNext (
  IN OUT UINT8  Record[VBOOT_NV_RECORD_SIZE],
  IN     UINTN  Slot,
  IN     UINT8  Tries
  )
{
  if (Slot != 0) {
    Record[VBOOT_NV_OFFS_BOOT2] |= VBOOT_NV_BOOT2_TRY_NEXT;
  } else {
    Record[VBOOT_NV_OFFS_BOOT2] &= (UINT8) ~VBOOT_NV_BOOT2_TRY_NEXT;
  }

  Record[VBOOT_NV_OFFS_BOOT] &= (UINT8) ~VBOOT_NV_BOOT_TRY_COUNT;
  Record[VBOOT_NV_OFFS_BOOT] |= (Tries & VBOOT_NV_BOOT_TRY_COUNT);
  Record[VBOOT_NV_OFFS_CRC]   = FmpVbootNvCrc8 (Record, VBOOT_NV_OFFS_CRC);
}
