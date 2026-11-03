/** @file
  The state of the update being written, published for the update screen
  (Protocol/FirmwareUpdateStatus.h).

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef FMP_DEVICE_SMM_STATUS_H_
#define FMP_DEVICE_SMM_STATUS_H_

#include <Protocol/FirmwareUpdateStatus.h>

/**
  Publish the state, idle, for the screen to find.  From the constructor.
**/
VOID
FmpStatusInstall (
  VOID
  );

/**
  A capsule starts: from FromVersion, running, to ToVersion.
**/
VOID
FmpStatusBegin (
  IN UINT32  FromVersion,
  IN UINT32  ToVersion
  );

/**
  The vboot slot written, 0 for A or 1 for B; the other one runs.
**/
VOID
FmpStatusSlots (
  IN UINTN  TargetSlot
  );

/**
  How many flash blocks of BlockSize bytes the regions written have.
**/
VOID
FmpStatusTotal (
  IN UINTN  Blocks,
  IN UINTN  BlockSize
  );

/**
  The region Name (a manifest name, up to Length characters) starts: the
  Index-th of Count, Blocks blocks.  Its first block is current.
**/
VOID
FmpStatusRegion (
  IN CONST CHAR8  *Name,
  IN UINTN        Length,
  IN UINTN        Index,
  IN UINTN        Count,
  IN UINTN        Blocks
  );

/**
  Block of the region is done (FIRMWARE_UPDATE_BLOCK_WRITTEN or _SAME), and
  the next one becomes current, or it failed (FIRMWARE_UPDATE_BLOCK_FAILED).
**/
VOID
FmpStatusBlock (
  IN UINTN  Block,
  IN UINT8  State
  );

/**
  The update moves to Phase (FIRMWARE_UPDATE_PHASE_*).
**/
VOID
FmpStatusPhase (
  IN UINT32  Phase
  );

/**
  The update failed, for Reason (FIRMWARE_UPDATE_REASON_*).
**/
VOID
FmpStatusFailed (
  IN UINT32  Reason
  );

#endif
