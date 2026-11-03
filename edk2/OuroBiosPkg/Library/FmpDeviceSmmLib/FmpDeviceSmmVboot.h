/** @file
  vboot A/B updates for SMMSTORE-backed firmware updates.

  A firmware verified by vboot with two RW slots (RW_SECTION_A and
  RW_SECTION_B in the FMAP) and its nvdata in flash (RW_NVRAM, the format of
  coreboot's vbnv_flash.c: 16-byte V1 records appended until the region is
  full) is updated one slot at a time: the slot that is not running is
  written, then vboot is asked to try it on the next boots.  If the write is
  cut short, or the new slot does not verify, vboot boots the old one.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#pragma once

#include <Base.h>
#include "FmpDeviceSmmManifest.h"

#define VBOOT_NV_RECORD_SIZE  16

//
// Fields of a V1 record (vboot_reference, 2nvstorage_fields.h).
//
#define VBOOT_NV_OFFS_HEADER         0
#define VBOOT_NV_OFFS_BOOT           1
#define VBOOT_NV_OFFS_BOOT2          7
#define VBOOT_NV_OFFS_CRC            15
#define VBOOT_NV_HEADER_SIGNATURE    0x40
#define VBOOT_NV_HEADER_MASK         0xC0
#define VBOOT_NV_BOOT_TRY_COUNT      0x0F
#define VBOOT_NV_BOOT2_RESULT        0x03
#define VBOOT_NV_BOOT2_TRIED         0x04
#define VBOOT_NV_BOOT2_TRY_NEXT      0x08

//
// Boots vboot gives a new slot before it falls back to the other one, if
// the payload of the new slot never reports that it booted.
//
#define VBOOT_AB_TRY_COUNT  2

/**
  Whether a manifest names the two RW slots of vboot, each once; it may name
  other regions too.

  @param[in]  Entries  Manifest entries.
  @param[in]  Count    Number of entries.
  @param[out] IndexA   Entry of RW_SECTION_A.
  @param[out] IndexB   Entry of RW_SECTION_B.

  @retval TRUE   The manifest has RW_SECTION_A and RW_SECTION_B.
  @retval FALSE  It does not.
**/
BOOLEAN
FmpVbootFindSlots (
  IN  CONST REGION_MANIFEST_ENTRY  *Entries,
  IN  UINTN                        Count,
  OUT UINTN                        *IndexA,
  OUT UINTN                        *IndexB
  );

/**
  Whether a manifest may update a flash: one whose FMAP has the two RW
  slots of vboot is updated a slot at a time, by a manifest with both
  slots, of which only the one that is not running is written.  Any other
  manifest could write the slot that runs, and leave vboot nothing to fall
  back to.

  @param[in] Entries        Manifest entries.
  @param[in] Count          Number of entries.
  @param[in] FlashHasSlots  The FMAP of the flash has RW_SECTION_A and
                            RW_SECTION_B.

  @retval TRUE   The manifest may update the flash.
  @retval FALSE  It may not.
**/
BOOLEAN
FmpVbootManifestFitsFlash (
  IN CONST REGION_MANIFEST_ENTRY  *Entries,
  IN UINTN                        Count,
  IN BOOLEAN                      FlashHasSlots
  );

/**
  CRC-8 of a V1 record, as vboot computes it (x^8 + x^2 + x + 1).
**/
UINT8
FmpVbootNvCrc8 (
  IN CONST UINT8  *Data,
  IN UINTN        Size
  );

/**
  Find the current record in the contents of RW_NVRAM.

  @param[in]  Region      The region.
  @param[in]  Size        Its size, a multiple of VBOOT_NV_RECORD_SIZE.
  @param[out] Record      The current record if it is valid, otherwise an
                          empty valid one, as vboot would start from.
  @param[out] NextOffset  Offset of the first erased record, where the next
                          one goes; Size if the region is full.

  @retval TRUE   The current record is valid.
  @retval FALSE  There is none, or it is corrupted.
**/
BOOLEAN
FmpVbootNvFindCurrent (
  IN  CONST UINT8  *Region,
  IN  UINTN        Size,
  OUT UINT8        Record[VBOOT_NV_RECORD_SIZE],
  OUT UINTN        *NextOffset
  );

/**
  The slot that vboot booted, 0 for A and 1 for B.
**/
UINTN
FmpVbootNvTriedSlot (
  IN CONST UINT8  Record[VBOOT_NV_RECORD_SIZE]
  );

/**
  Ask vboot to try Slot on the next boots: try_next, and the try count.
**/
VOID
FmpVbootNvSetTryNext (
  IN OUT UINT8  Record[VBOOT_NV_RECORD_SIZE],
  IN     UINTN  Slot,
  IN     UINT8  Tries
  );
