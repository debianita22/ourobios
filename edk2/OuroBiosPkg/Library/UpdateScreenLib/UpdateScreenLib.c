/** @file
  The firmware update screen of ouroBIOS, as the DisplayUpdateProgressLib of
  the payload.

  FmpDxe reports the progress of a capsule (DisplayUpdateProgress(), 0 to
  100), FmpDeviceSmmLib publishes what it writes (the region, each flash
  block, the vboot slots, the versions: Protocol/FirmwareUpdateStatus.h),
  and the boot manager sets the status line before and around the capsule
  and counts down to the reset (UpdateScreenStatus(), UpdateScreenRestart()).
  This file turns that into the model of the screen; UpdateScreenDraw.c
  draws it on the GOP.  Without a GOP, or on a screen too small, nothing is
  drawn: the progress is in the debug log (DxeCapsuleLibFmp) and the lines
  go to the text console.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <PiDxe.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DisplayUpdateProgressLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PrintLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UpdateScreenLib.h>
#include <Protocol/FirmwareUpdateStatus.h>
#include <Protocol/GraphicsOutput.h>
#include "UpdateScreenDraw.h"
#include "UpdateScreenFont.h"

//
// The last ESRT number of the release format before X.Y.Z.R: v1.3.6-rc1
//
#define LAST_OLD_LAYOUT_VERSION  0x01030006

//
// The estimate of the time left: the RTC read every ETA_EVERY redraws,
// shown after ETA_MIN_SECONDS and 1/ETA_MIN_SHARE of the blocks
//
#define ETA_EVERY        16
#define ETA_MIN_SECONDS  3
#define ETA_MIN_SHARE    20
#define SECONDS_PER_DAY  86400

//
// The wink, in microseconds
//
#define WINK_CLOSED  140000
#define WINK_OPEN    360000

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL  *mGop;
STATIC BOOLEAN                       mGopTried;
STATIC UPDATE_SCREEN_CANVAS          mCanvas;
STATIC UPDATE_SCREEN_DRAW            *mDraw;
STATIC UPDATE_SCREEN_MODEL           mModel;
STATIC FIRMWARE_UPDATE_STATUS        *mStatus;

STATIC UINTN               mCompletion;
STATIC BOOLEAN             mProgress;               ///< a capsule has reported progress
STATIC CHAR16              mMessage[UPDATE_SCREEN_TEXT];
STATIC UPDATE_SCREEN_TONE  mMessageTone;
STATIC BOOLEAN             mMessageFresh;           ///< newer than the progress
STATIC UINTN               mCountdown;              ///< seconds to the reset, 0: none

STATIC UINT32   mEtaCalls;
STATIC BOOLEAN  mEtaStarted;
STATIC UINT32   mEtaSecond;
STATIC UINT32   mEtaBlocks;

STATIC
VOID
EFIAPI
GopFill (
  IN UPDATE_SCREEN_CANVAS  *Canvas,
  IN UINTN                 X,
  IN UINTN                 Y,
  IN UINTN                 Width,
  IN UINTN                 Height,
  IN UINT32                Color
  )
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  Pixel;

  Pixel.Blue     = (UINT8)Color;
  Pixel.Green    = (UINT8)(Color >> 8);
  Pixel.Red      = (UINT8)(Color >> 16);
  Pixel.Reserved = 0;
  mGop->Blt (mGop, &Pixel, EfiBltVideoFill, 0, 0, X, Y, Width, Height, 0);
}

STATIC
VOID
EFIAPI
GopBlit (
  IN UPDATE_SCREEN_CANVAS           *Canvas,
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Pixels,
  IN UINTN                          X,
  IN UINTN                          Y,
  IN UINTN                          Width,
  IN UINTN                          Height
  )
{
  mGop->Blt (mGop, Pixels, EfiBltBufferToVideo, 0, 0, X, Y, Width, Height, Width * sizeof (EFI_GRAPHICS_OUTPUT_BLT_PIXEL));
}

/**
  The GOP of the console and the layout for it, once.

  @retval TRUE   The screen can be drawn.
**/
STATIC
BOOLEAN
ScreenReady (
  VOID
  )
{
  EFI_STATUS  Status;

  if (mDraw != NULL) {
    return TRUE;
  }

  if (mGopTried) {
    return FALSE;
  }

  mGopTried = TRUE;
  Status    = EFI_NOT_FOUND;
  if (gST->ConsoleOutHandle != NULL) {
    Status = gBS->HandleProtocol (gST->ConsoleOutHandle, &gEfiGraphicsOutputProtocolGuid, (VOID **)&mGop);
  }

  if (EFI_ERROR (Status)) {
    Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mGop);
  }

  if (EFI_ERROR (Status) || (mGop == NULL) || (mGop->Mode == NULL) || (mGop->Mode->Info == NULL)) {
    DEBUG ((DEBUG_INFO, "UpdateScreen: no graphics console (%r)\n", Status));
    mGop = NULL;
    return FALSE;
  }

  mCanvas.Width   = mGop->Mode->Info->HorizontalResolution;
  mCanvas.Height  = mGop->Mode->Info->VerticalResolution;
  mCanvas.Fill    = GopFill;
  mCanvas.Blit    = GopBlit;
  mCanvas.Context = NULL;
  mDraw           = UpdateScreenDrawCreate (&mCanvas);
  if (mDraw == NULL) {
    DEBUG ((DEBUG_INFO, "UpdateScreen: no layout for %ux%u\n", (UINT32)mCanvas.Width, (UINT32)mCanvas.Height));
    return FALSE;
  }

  return TRUE;
}

/**
  An ESRT version as the tag of its release, as the setup and
  tools/update.py print it: X.Y.Z.R, a release X.Y.Z.0, its candidate N the
  release before with R = N; up to v1.3.6-rc1 X.Y.Z, Z in 16 bits.
**/
STATIC
VOID
FormatTag (
  OUT CHAR16  *Buffer,
  IN  UINTN   BufferSize,
  IN  UINT32  Version
  )
{
  UINT32  Release;

  if ((Version <= LAST_OLD_LAYOUT_VERSION) && ((Version & 0xFF00) == 0)) {
    if (Version == LAST_OLD_LAYOUT_VERSION) {
      UnicodeSPrint (Buffer, BufferSize, L"v1.3.6-rc1");
    } else {
      UnicodeSPrint (Buffer, BufferSize, L"v%u.%u.%u", Version >> 24, (Version >> 16) & 0xFF, Version & 0xFFFF);
    }

    return;
  }

  if ((Version & 0xFF) == 0) {
    UnicodeSPrint (Buffer, BufferSize, L"v%u.%u.%u", Version >> 24, (Version >> 16) & 0xFF, (Version >> 8) & 0xFF);
    return;
  }

  Release = (Version & ~0xFFu) + 0x100;
  UnicodeSPrint (
    Buffer,
    BufferSize,
    L"v%u.%u.%u-rc%u",
    Release >> 24,
    (Release >> 16) & 0xFF,
    (Release >> 8) & 0xFF,
    Version & 0xFF
    );
}

/**
  Label and Blocks of BlockSize bytes, in KiB or in MiB with one decimal.
**/
STATIC
VOID
FormatSize (
  OUT CHAR16        *Buffer,
  IN  UINTN         BufferSize,
  IN  CONST CHAR16  *Label,
  IN  UINT32        Blocks,
  IN  UINT32        BlockSize
  )
{
  UINT64  KiB;
  UINT64  Tenths;

  KiB = MultU64x32 (Blocks, BlockSize) / 1024;
  if (KiB < 1024) {
    UnicodeSPrint (Buffer, BufferSize, L"%s %Lu KiB", Label, KiB);
  } else {
    Tenths = (KiB * 10 + 512) / 1024;
    UnicodeSPrint (Buffer, BufferSize, L"%s %Lu.%Lu MiB", Label, Tenths / 10, Tenths % 10);
  }
}

/**
  The seconds of the day by the RTC, or MAX_UINT32.
**/
STATIC
UINT32
SecondOfDay (
  VOID
  )
{
  EFI_TIME  Time;

  if (EFI_ERROR (gRT->GetTime (&Time, NULL))) {
    return MAX_UINT32;
  }

  return (UINT32)Time.Hour * 3600 + (UINT32)Time.Minute * 60 + Time.Second;
}

/**
  The time left, from the blocks done since the first estimate.
**/
STATIC
VOID
UpdateEta (
  IN FIRMWARE_UPDATE_STATUS  *Status
  )
{
  UINT32  Now;
  UINT32  Elapsed;
  UINT32  Done;
  UINT32  Left;

  if ((Status == NULL) || (Status->Phase != FIRMWARE_UPDATE_PHASE_WRITING) ||
      (Status->TotalBlocks == 0) || (Status->DoneBlocks >= Status->TotalBlocks))
  {
    mModel.Eta[0] = L'\0';
    return;
  }

  if ((mEtaCalls++ % ETA_EVERY) != 0) {
    return;
  }

  Now = SecondOfDay ();
  if (Now == MAX_UINT32) {
    return;
  }

  if (!mEtaStarted) {
    mEtaStarted = TRUE;
    mEtaSecond  = Now;
    mEtaBlocks  = Status->DoneBlocks;
    return;
  }

  Elapsed = (Now + SECONDS_PER_DAY - mEtaSecond) % SECONDS_PER_DAY;
  Done    = Status->DoneBlocks - mEtaBlocks;
  if ((Elapsed < ETA_MIN_SECONDS) || (Done == 0) || ((UINT64)Status->DoneBlocks * ETA_MIN_SHARE < Status->TotalBlocks)) {
    return;
  }

  Left = (UINT32)DivU64x32 (MultU64x32 (Elapsed, Status->TotalBlocks - Status->DoneBlocks) + Done - 1, Done);
  if (Left < 10) {
    UnicodeSPrint (mModel.Eta, sizeof (mModel.Eta), L"Almost done");
  } else if (Left < 60) {
    UnicodeSPrint (mModel.Eta, sizeof (mModel.Eta), L"About %u s left", ((Left + 4) / 5) * 5);
  } else {
    UnicodeSPrint (mModel.Eta, sizeof (mModel.Eta), L"About %u min left", (Left + 30) / 60);
  }
}

/**
  The block of the region that failed, from 1, or 0.
**/
STATIC
UINT32
FailedBlock (
  IN FIRMWARE_UPDATE_STATUS  *Status
  )
{
  UINT32  Index;
  UINT32  Entries;

  Entries = MIN (Status->RegionBlocks, FIRMWARE_UPDATE_STATUS_MAP_SIZE);
  for (Index = 0; Index < Entries; Index++) {
    if (Status->Map[Index] == FIRMWARE_UPDATE_BLOCK_FAILED) {
      if (Status->RegionBlocks > FIRMWARE_UPDATE_STATUS_MAP_SIZE) {
        return (UINT32)DivU64x32 (MultU64x32 (Status->RegionBlocks, Index), FIRMWARE_UPDATE_STATUS_MAP_SIZE) + 1;
      }

      return Index + 1;
    }
  }

  return 0;
}

/**
  Verb and the region being written, for the status line.
**/
STATIC
VOID
RegionText (
  OUT CHAR16                  *Buffer,
  IN  UINTN                   BufferSize,
  IN  FIRMWARE_UPDATE_STATUS  *Status,
  IN  CONST CHAR16            *Verb
  )
{
  if (AsciiStrCmp (Status->Region, "RW_MRC_CACHE") == 0) {
    UnicodeSPrint (Buffer, BufferSize, L"%s the memory training data", Verb);
  } else if ((AsciiStrCmp (Status->Region, "RW_SECTION_A") == 0) || (AsciiStrCmp (Status->Region, "RW_SECTION_B") == 0)) {
    UnicodeSPrint (Buffer, BufferSize, L"%s slot %c", Verb, (CHAR16)Status->Region[11]);
  } else {
    UnicodeSPrint (Buffer, BufferSize, L"%s %a", Verb, Status->Region);
  }
}

/**
  The status line from the published state.
**/
STATIC
VOID
StatusText (
  IN FIRMWARE_UPDATE_STATUS  *Status
  )
{
  UINT32  Failed;
  UINTN   Length;

  switch (Status->Phase) {
    case FIRMWARE_UPDATE_PHASE_PREPARING:
      UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"Preparing the flash");
      break;
    case FIRMWARE_UPDATE_PHASE_WRITING:
      RegionText (
        mModel.Status,
        sizeof (mModel.Status),
        Status,
        (AsciiStrCmp (Status->Region, "RW_MRC_CACHE") == 0) ? L"Clearing" : L"Writing"
        );
      break;
    case FIRMWARE_UPDATE_PHASE_FINISHING:
      UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"Asking vboot to try slot %c", (CHAR16)Status->TargetSlot);
      break;
    case FIRMWARE_UPDATE_PHASE_DONE:
      if (Status->TargetSlot != 0) {
        UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"Slot %c is ready: the laptop starts from it next", (CHAR16)Status->TargetSlot);
      } else {
        UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"The new firmware is written");
      }

      mModel.StatusTone = UpdateScreenToneSuccess;
      break;
    case FIRMWARE_UPDATE_PHASE_FAILED:
      Failed = FailedBlock (Status);
      if (Failed != 0) {
        RegionText (mModel.Status, sizeof (mModel.Status), Status, L"Writing failed in");
        Length = StrLen (mModel.Status);
        UnicodeSPrint (
          mModel.Status + Length,
          sizeof (mModel.Status) - Length * sizeof (CHAR16),
          L", block %u of %u",
          Failed,
          Status->RegionBlocks
          );
      } else if (Status->Reason == FIRMWARE_UPDATE_REASON_INVALID) {
        UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"The capsule is not for this flash: nothing was written");
      } else if (Status->Reason == FIRMWARE_UPDATE_REASON_LAYOUT) {
        UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"The capsule has another flash map: update with flashrom");
      } else if (Status->Reason == FIRMWARE_UPDATE_REASON_FLASH) {
        UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"Reading the flash failed: nothing was written");
      } else {
        UnicodeSPrint (mModel.Status, sizeof (mModel.Status), L"The capsule was not written");
      }

      mModel.StatusTone = UpdateScreenToneError;
      break;
    default:
      mModel.Status[0] = L'\0';
      break;
  }
}

/**
  The model of the screen from the progress, the published state and the
  lines of the boot manager.
**/
STATIC
VOID
UpdateModel (
  VOID
  )
{
  FIRMWARE_UPDATE_STATUS  *Status;
  CHAR16                  From[24];
  CHAR16                  To[24];
  UINT32                  Phase;
  BOOLEAN                 Final;

  if (mStatus == NULL) {
    if (EFI_ERROR (gBS->LocateProtocol (&gFirmwareUpdateStatusProtocolGuid, NULL, (VOID **)&mStatus)) ||
        (mStatus->Revision != FIRMWARE_UPDATE_STATUS_REVISION))
    {
      mStatus = NULL;
    }
  }

  //
  // The state of the writer counts once a capsule reports progress
  //
  Status = (mProgress && (mStatus != NULL) && (mStatus->Phase != FIRMWARE_UPDATE_PHASE_IDLE)) ? mStatus : NULL;
  Phase  = (Status != NULL) ? Status->Phase : FIRMWARE_UPDATE_PHASE_IDLE;
  Final  = (Phase == FIRMWARE_UPDATE_PHASE_DONE) || (Phase == FIRMWARE_UPDATE_PHASE_FAILED);

  //
  // Title and versions
  //
  mModel.TitleTone = UpdateScreenToneNormal;
  if (Phase == FIRMWARE_UPDATE_PHASE_DONE) {
    UnicodeSPrint (mModel.Title, sizeof (mModel.Title), L"ouroBIOS updated");
  } else if (Phase == FIRMWARE_UPDATE_PHASE_FAILED) {
    UnicodeSPrint (mModel.Title, sizeof (mModel.Title), L"The update did not complete");
    mModel.TitleTone = UpdateScreenToneError;
  } else if (mProgress) {
    UnicodeSPrint (mModel.Title, sizeof (mModel.Title), L"Updating ouroBIOS");
  } else {
    UnicodeSPrint (mModel.Title, sizeof (mModel.Title), L"Firmware update");
  }

  if ((Status != NULL) && (Status->ToVersion != 0)) {
    FormatTag (From, sizeof (From), Status->FromVersion);
    FormatTag (To, sizeof (To), Status->ToVersion);
    if (Status->TargetSlot != 0) {
      UnicodeSPrint (
        mModel.Versions,
        sizeof (mModel.Versions),
        L"%s %c slot %c   %c   %s %c slot %c",
        From,
        UPDATE_SCREEN_BULLET,
        (CHAR16)Status->RunningSlot,
        UPDATE_SCREEN_ICON_NEXT,
        To,
        UPDATE_SCREEN_BULLET,
        (CHAR16)Status->TargetSlot
        );
    } else {
      UnicodeSPrint (mModel.Versions, sizeof (mModel.Versions), L"%s   %c   %s", From, UPDATE_SCREEN_ICON_NEXT, To);
    }
  }

  //
  // The status line: the result of the writer, else the newest of the
  // boot manager's line and what is being written
  //
  mModel.StatusTone = UpdateScreenToneNormal;
  if ((Status != NULL) && (Final || !mMessageFresh)) {
    StatusText (Status);
  } else {
    StrCpyS (mModel.Status, ARRAY_SIZE (mModel.Status), mMessage);
    mModel.StatusTone = mMessageTone;
  }

  if (mProgress) {
    UnicodeSPrint (mModel.Percent, sizeof (mModel.Percent), L"%u%%", (UINT32)mCompletion);
  } else {
    mModel.Percent[0] = L'\0';
  }

  //
  // The ring and the bar
  //
  mModel.Ring      = mProgress ? (UINT32)mCompletion * 10 : 0;
  mModel.Breathing = (Phase == FIRMWARE_UPDATE_PHASE_WRITING);
  mModel.Tick++;
  if ((Status != NULL) && (Phase >= FIRMWARE_UPDATE_PHASE_WRITING) && (Status->RegionBlocks != 0)) {
    mModel.Map       = Status->Map;
    mModel.MapBlocks = Status->RegionBlocks;
  } else {
    mModel.Map       = NULL;
    mModel.MapBlocks = 0;
  }

  mModel.Legend = (Status != NULL) && (Status->TotalBlocks != 0) && (Phase >= FIRMWARE_UPDATE_PHASE_WRITING) &&
                  (Status->DoneBlocks != 0);
  if (mModel.Legend) {
    FormatSize (mModel.Written, sizeof (mModel.Written), L"Rewritten", Status->WrittenBlocks, Status->BlockSize);
    FormatSize (mModel.Same, sizeof (mModel.Same), L"Unchanged", Status->SameBlocks, Status->BlockSize);
    if (Status->DoneBlocks < Status->TotalBlocks) {
      FormatSize (mModel.ToDo, sizeof (mModel.ToDo), L"To do", Status->TotalBlocks - Status->DoneBlocks, Status->BlockSize);
    } else {
      mModel.ToDo[0] = L'\0';
    }
  }

  //
  // Right of the legend: the time left, or the countdown to the reset
  //
  if (mCountdown != 0) {
    UnicodeSPrint (mModel.Eta, sizeof (mModel.Eta), L"Restarting in %u s", (UINT32)mCountdown);
  } else {
    UpdateEta (Status);
  }

  //
  // The footer: what to do, or what the result means
  //
  if (Phase == FIRMWARE_UPDATE_PHASE_DONE) {
    mModel.FooterTone = UpdateScreenToneSuccess;
    if (Status->RunningSlot != 0) {
      FormatTag (From, sizeof (From), Status->FromVersion);
      UnicodeSPrint (
        mModel.Footer,
        sizeof (mModel.Footer),
        L"If slot %c does not start, the laptop goes back to %s by itself",
        (CHAR16)Status->TargetSlot,
        From
        );
    } else {
      UnicodeSPrint (mModel.Footer, sizeof (mModel.Footer), L"The laptop restarts to start it");
    }
  } else if (Phase == FIRMWARE_UPDATE_PHASE_FAILED) {
    mModel.FooterTone = UpdateScreenToneError;
    if (Status->RunningSlot != 0) {
      UnicodeSPrint (mModel.Footer, sizeof (mModel.Footer), L"Slot %c, the one in use, was not touched", (CHAR16)Status->RunningSlot);
    } else {
      UnicodeSPrint (mModel.Footer, sizeof (mModel.Footer), L"Keep the laptop on and try the update again");
    }
  } else if (!mProgress && ((mMessageTone == UpdateScreenToneWarning) || (mMessageTone == UpdateScreenToneError))) {
    mModel.FooterTone = UpdateScreenToneNormal;
    UnicodeSPrint (mModel.Footer, sizeof (mModel.Footer), L"The firmware in use was not changed");
  } else {
    mModel.FooterTone = UpdateScreenToneWarning;
    UnicodeSPrint (mModel.Footer, sizeof (mModel.Footer), L"Do not turn off the laptop or unplug the AC adapter");
  }

}

STATIC
VOID
Redraw (
  VOID
  )
{
  if (!ScreenReady ()) {
    return;
  }

  UpdateModel ();
  UpdateScreenDrawRender (mDraw, &mCanvas, &mModel);
}

/**
  Function indicates the current completion progress of a firmware update.

  @param[in] Completion  A value between 0 and 100 indicating the current
                         completion progress of a firmware update.  A value
                         lower than the one before starts a new update.
  @param[in] Color       Not used: the screen has its own colors.

  @retval EFI_SUCCESS            Progress displayed, or logged without a screen.
  @retval EFI_INVALID_PARAMETER  Completion is not in range 0..100.
**/
EFI_STATUS
EFIAPI
DisplayUpdateProgress (
  IN UINTN                                Completion,
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL_UNION  *Color       OPTIONAL
  )
{
  if (Completion > 100) {
    return EFI_INVALID_PARAMETER;
  }

  if (!mProgress || (Completion < mCompletion)) {
    //
    // A capsule starts, with its own estimate of the time
    //
    mEtaStarted = FALSE;
    mEtaCalls   = 0;
    mCountdown  = 0;
  }

  mProgress     = TRUE;
  mCompletion   = Completion;
  mMessageFresh = FALSE;
  Redraw ();
  return EFI_SUCCESS;
}

VOID
EFIAPI
UpdateScreenStatus (
  IN UPDATE_SCREEN_TONE  Tone,
  IN CONST CHAR16        *Format,
  ...
  )
{
  VA_LIST  Marker;

  VA_START (Marker, Format);
  UnicodeVSPrint (mMessage, sizeof (mMessage), Format, Marker);
  VA_END (Marker);

  mMessageTone  = Tone;
  mMessageFresh = TRUE;
  DEBUG ((DEBUG_INFO, "UpdateScreen: %s\n", mMessage));
  if (ScreenReady ()) {
    Redraw ();
  } else if ((gST != NULL) && (gST->ConOut != NULL)) {
    Print (L"%s\n", mMessage);
  }
}

VOID
EFIAPI
UpdateScreenRestart (
  IN UPDATE_SCREEN_TONE  Tone,
  IN UINTN               Seconds
  )
{
  if (!ScreenReady ()) {
    gBS->Stall (Seconds * 1000000);
    return;
  }

  if ((Tone == UpdateScreenToneSuccess) && (Seconds != 0)) {
    //
    // The snake winks: the firmware is reborn
    //
    mCountdown       = Seconds;
    mModel.EyeClosed = TRUE;
    Redraw ();
    gBS->Stall (WINK_CLOSED);
    mModel.EyeClosed = FALSE;
    Redraw ();
    gBS->Stall (WINK_OPEN);
    Seconds--;
    gBS->Stall (1000000 - WINK_CLOSED - WINK_OPEN);
  }

  for ( ; Seconds > 0; Seconds--) {
    mCountdown = Seconds;
    Redraw ();
    gBS->Stall (1000000);
  }

  mCountdown = 0;
}
