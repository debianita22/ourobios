/** @file
  The state of the firmware update that FmpDeviceSmmLib writes, for the
  update screen (UpdateScreenLib): phase, versions, vboot slots, the region
  being written and what happened to each of its flash blocks.

  FmpDxe, with FmpDeviceSmmLib, owns the structure and changes it between
  its progress callbacks; the screen only reads it, from those callbacks
  (DisplayUpdateProgress()), so nothing runs concurrently.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef FIRMWARE_UPDATE_STATUS_H_
#define FIRMWARE_UPDATE_STATUS_H_

#define FIRMWARE_UPDATE_STATUS_PROTOCOL_GUID \
  { 0xe769a170, 0xb26e, 0x4763, { 0x9b, 0xbd, 0x42, 0xb7, 0xf6, 0x68, 0xdd, 0xa5 } }

#define FIRMWARE_UPDATE_STATUS_REVISION  1

//
// Phase
//
#define FIRMWARE_UPDATE_PHASE_IDLE       0
#define FIRMWARE_UPDATE_PHASE_PREPARING  1    ///< reading the flash map and the vboot nvdata
#define FIRMWARE_UPDATE_PHASE_WRITING    2    ///< the blocks of Region
#define FIRMWARE_UPDATE_PHASE_FINISHING  3    ///< asking vboot to try TargetSlot
#define FIRMWARE_UPDATE_PHASE_DONE       4
#define FIRMWARE_UPDATE_PHASE_FAILED     5

//
// A flash block of the region being written
//
#define FIRMWARE_UPDATE_BLOCK_TO_DO    0
#define FIRMWARE_UPDATE_BLOCK_CURRENT  1      ///< being erased, programmed and verified
#define FIRMWARE_UPDATE_BLOCK_WRITTEN  2      ///< rewritten and verified
#define FIRMWARE_UPDATE_BLOCK_SAME     3      ///< already as in the capsule: not written
#define FIRMWARE_UPDATE_BLOCK_FAILED   4

//
// Why an update failed, in phase FAILED
//
#define FIRMWARE_UPDATE_REASON_NONE     0
#define FIRMWARE_UPDATE_REASON_INVALID  1     ///< not an image for this flash
#define FIRMWARE_UPDATE_REASON_LAYOUT   2     ///< another flash map: flashrom only
#define FIRMWARE_UPDATE_REASON_FLASH    3     ///< reading, erasing or writing the flash failed
#define FIRMWARE_UPDATE_REASON_OTHER    4

//
// Map entries: a region of more blocks shares them out
//
#define FIRMWARE_UPDATE_STATUS_MAP_SIZE  1024

typedef struct {
  UINT32    Revision;
  UINT32    Phase;
  UINT32    FromVersion;                        ///< ESRT version of the firmware running
  UINT32    ToVersion;                          ///< version of the capsule
  CHAR8     RunningSlot;                        ///< 'A' or 'B', 0 without vboot slots
  CHAR8     TargetSlot;                         ///< the slot written, 0 without vboot slots
  CHAR8     Region[34];                         ///< FMAP name of the region being written
  UINT32    RegionIndex;                        ///< among the regions written, from 0
  UINT32    RegionCount;
  UINT32    BlockSize;
  UINT32    RegionBlocks;                       ///< blocks of Region
  UINT32    TotalBlocks;                        ///< blocks of all the regions written
  UINT32    DoneBlocks;
  UINT32    WrittenBlocks;
  UINT32    SameBlocks;
  UINT32    Reason;                             ///< FIRMWARE_UPDATE_REASON_*
  UINT8     Map[FIRMWARE_UPDATE_STATUS_MAP_SIZE];  ///< FIRMWARE_UPDATE_BLOCK_*, per block of Region
} FIRMWARE_UPDATE_STATUS;

extern EFI_GUID  gFirmwareUpdateStatusProtocolGuid;

#endif
