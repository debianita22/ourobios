/** @file
  The firmware update screen of ouroBIOS.  The library is also the
  DisplayUpdateProgressLib of the payload: FmpDxe reports the progress of a
  capsule through DisplayUpdateProgress(), FmpDeviceSmmLib publishes what it
  writes (Protocol/FirmwareUpdateStatus.h), and the boot manager, before and
  after the capsule, sets the status line and the countdown below.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef UPDATE_SCREEN_LIB_H_
#define UPDATE_SCREEN_LIB_H_

typedef enum {
  UpdateScreenToneNormal,
  UpdateScreenToneSuccess,
  UpdateScreenToneWarning,
  UpdateScreenToneError
} UPDATE_SCREEN_TONE;

/**
  Show what the update is doing in the status line, drawing the screen if it
  is not there yet.  Without a graphics console the line goes to the text
  console.  The line stays until the next one, or until the progress of a
  capsule replaces it.

  @param[in] Tone    Its color.
  @param[in] Format  A format string, then its arguments.
**/
VOID
EFIAPI
UpdateScreenStatus (
  IN UPDATE_SCREEN_TONE  Tone,
  IN CONST CHAR16        *Format,
  ...
  );

/**
  Count down to the reset after the capsules, Seconds seconds, on the
  screen if there is one; after an update that succeeded the snake winks
  first.  Returns when the time is up.

  @param[in] Tone     Success or error, for the countdown.
  @param[in] Seconds  How long.
**/
VOID
EFIAPI
UpdateScreenRestart (
  IN UPDATE_SCREEN_TONE  Tone,
  IN UINTN               Seconds
  );

#endif
