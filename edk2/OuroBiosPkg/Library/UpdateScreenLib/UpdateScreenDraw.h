/** @file
  Drawing of the firmware update screen, on any surface that can fill a
  rectangle and copy a block of pixels (UpdateScreenDraw.c): the GOP in the
  firmware, a file in the host tool that renders it.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef UPDATE_SCREEN_DRAW_H_
#define UPDATE_SCREEN_DRAW_H_

#include <Uefi.h>
#include <Protocol/GraphicsOutput.h>
#include <Library/UpdateScreenLib.h>

#define UPDATE_SCREEN_TEXT  128

typedef struct _UPDATE_SCREEN_CANVAS UPDATE_SCREEN_CANVAS;

/**
  Fill a rectangle of the surface; the caller keeps it inside.

  @param[in] Color  0xRRGGBB.
**/
typedef
VOID
(EFIAPI *UPDATE_SCREEN_FILL)(
  IN UPDATE_SCREEN_CANVAS  *Canvas,
  IN UINTN                 X,
  IN UINTN                 Y,
  IN UINTN                 Width,
  IN UINTN                 Height,
  IN UINT32                Color
  );

/**
  Copy Width x Height pixels to the surface; the caller keeps them inside.
**/
typedef
VOID
(EFIAPI *UPDATE_SCREEN_BLIT)(
  IN UPDATE_SCREEN_CANVAS           *Canvas,
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Pixels,
  IN UINTN                          X,
  IN UINTN                          Y,
  IN UINTN                          Width,
  IN UINTN                          Height
  );

struct _UPDATE_SCREEN_CANVAS {
  UINTN                 Width;
  UINTN                 Height;
  UPDATE_SCREEN_FILL    Fill;
  UPDATE_SCREEN_BLIT    Blit;
  VOID                  *Context;
};

//
// What the screen shows.  Ring and Map are the progress: Ring, from 0 to
// 1000, lights the ouroboros from its head around to its tail; Map, when
// there is one, is the bar, one entry (FIRMWARE_UPDATE_BLOCK_*) per flash
// block of the region being written, else the bar follows Ring.
//
typedef struct {
  UPDATE_SCREEN_TONE    TitleTone;
  CHAR16                Title[UPDATE_SCREEN_TEXT];
  CHAR16                Versions[UPDATE_SCREEN_TEXT];
  UPDATE_SCREEN_TONE    StatusTone;
  CHAR16                Status[UPDATE_SCREEN_TEXT];
  CHAR16                Percent[16];
  BOOLEAN               Legend;               ///< the three counters under the bar
  CHAR16                Written[32];
  CHAR16                Same[32];
  CHAR16                ToDo[32];
  CHAR16                Eta[48];
  UPDATE_SCREEN_TONE    FooterTone;
  CHAR16                Footer[UPDATE_SCREEN_TEXT];
  UINT32                Ring;
  BOOLEAN               EyeClosed;            ///< the wink at the end
  BOOLEAN               Breathing;            ///< the infinity breathes while blocks are written
  UINT32                Tick;
  UINT32                MapBlocks;
  CONST UINT8           *Map;
} UPDATE_SCREEN_MODEL;

typedef struct _UPDATE_SCREEN_DRAW UPDATE_SCREEN_DRAW;

/**
  The layout of the screen for the size of the canvas.

  @return The drawing state, or NULL without memory or room.
**/
UPDATE_SCREEN_DRAW *
UpdateScreenDrawCreate (
  IN UPDATE_SCREEN_CANVAS  *Canvas
  );

/**
  Draw the model: everything the first time, then what changed.
**/
VOID
UpdateScreenDrawRender (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model
  );

#endif
