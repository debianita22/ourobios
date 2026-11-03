/** @file
  The state of the update being written, published for the update screen:
  FmpDxe calls the progress callback of the capsule library after each
  block, and the screen reads this state from there.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include "FmpDeviceSmmStatus.h"

STATIC FIRMWARE_UPDATE_STATUS  mFmpStatus;

/**
  The entry of Map for Block: a region of more blocks than entries shares
  them out.
**/
STATIC
UINTN
MapIndex (
  IN UINTN  Block
  )
{
  if (mFmpStatus.RegionBlocks <= FIRMWARE_UPDATE_STATUS_MAP_SIZE) {
    return Block;
  }

  return (Block * FIRMWARE_UPDATE_STATUS_MAP_SIZE) / mFmpStatus.RegionBlocks;
}

VOID
FmpStatusInstall (
  VOID
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  Handle;

  mFmpStatus.Revision = FIRMWARE_UPDATE_STATUS_REVISION;
  mFmpStatus.Phase    = FIRMWARE_UPDATE_PHASE_IDLE;
  Handle              = NULL;
  Status              = gBS->InstallMultipleProtocolInterfaces (
                               &Handle,
                               &gFirmwareUpdateStatusProtocolGuid,
                               &mFmpStatus,
                               NULL
                               );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "%a(): the update screen will not see the blocks: %r\n", __func__, Status));
  }
}

VOID
FmpStatusBegin (
  IN UINT32  FromVersion,
  IN UINT32  ToVersion
  )
{
  ZeroMem (&mFmpStatus, sizeof (mFmpStatus));
  mFmpStatus.Revision    = FIRMWARE_UPDATE_STATUS_REVISION;
  mFmpStatus.Phase       = FIRMWARE_UPDATE_PHASE_PREPARING;
  mFmpStatus.FromVersion = FromVersion;
  mFmpStatus.ToVersion   = ToVersion;
}

VOID
FmpStatusSlots (
  IN UINTN  TargetSlot
  )
{
  mFmpStatus.TargetSlot  = (TargetSlot == 0) ? 'A' : 'B';
  mFmpStatus.RunningSlot = (TargetSlot == 0) ? 'B' : 'A';
}

VOID
FmpStatusTotal (
  IN UINTN  Blocks,
  IN UINTN  BlockSize
  )
{
  mFmpStatus.TotalBlocks   = (UINT32)MIN (Blocks, MAX_UINT32);
  mFmpStatus.BlockSize     = (UINT32)MIN (BlockSize, MAX_UINT32);
  mFmpStatus.DoneBlocks    = 0;
  mFmpStatus.WrittenBlocks = 0;
  mFmpStatus.SameBlocks    = 0;
}

VOID
FmpStatusRegion (
  IN CONST CHAR8  *Name,
  IN UINTN        Length,
  IN UINTN        Index,
  IN UINTN        Count,
  IN UINTN        Blocks
  )
{
  UINTN  Char;

  ZeroMem (mFmpStatus.Region, sizeof (mFmpStatus.Region));
  for (Char = 0; (Char < Length) && (Char < sizeof (mFmpStatus.Region) - 1) && (Name[Char] != '\0'); Char++) {
    mFmpStatus.Region[Char] = Name[Char];
  }

  mFmpStatus.Phase        = FIRMWARE_UPDATE_PHASE_WRITING;
  mFmpStatus.RegionIndex  = (UINT32)Index;
  mFmpStatus.RegionCount  = (UINT32)Count;
  mFmpStatus.RegionBlocks = (UINT32)MIN (Blocks, MAX_UINT32);
  SetMem (mFmpStatus.Map, sizeof (mFmpStatus.Map), FIRMWARE_UPDATE_BLOCK_TO_DO);
  if (Blocks != 0) {
    mFmpStatus.Map[0] = FIRMWARE_UPDATE_BLOCK_CURRENT;
  }
}

VOID
FmpStatusBlock (
  IN UINTN  Block,
  IN UINT8  State
  )
{
  if (Block >= mFmpStatus.RegionBlocks) {
    return;
  }

  mFmpStatus.Map[MapIndex (Block)] = State;
  if (State == FIRMWARE_UPDATE_BLOCK_FAILED) {
    return;
  }

  mFmpStatus.DoneBlocks++;
  if (State == FIRMWARE_UPDATE_BLOCK_SAME) {
    mFmpStatus.SameBlocks++;
  } else {
    mFmpStatus.WrittenBlocks++;
  }

  if ((Block + 1 < mFmpStatus.RegionBlocks) && (MapIndex (Block + 1) != MapIndex (Block))) {
    mFmpStatus.Map[MapIndex (Block + 1)] = FIRMWARE_UPDATE_BLOCK_CURRENT;
  }
}

VOID
FmpStatusPhase (
  IN UINT32  Phase
  )
{
  mFmpStatus.Phase = Phase;
}

VOID
FmpStatusFailed (
  IN UINT32  Reason
  )
{
  mFmpStatus.Phase  = FIRMWARE_UPDATE_PHASE_FAILED;
  mFmpStatus.Reason = Reason;
}
