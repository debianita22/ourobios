/** @file
  Bitmap fonts of the firmware update screen (UpdateScreenFont.c, made by
  tools/ui-font.py of ouroBIOS from the Montserrat fonts of LvglPkg).

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef UPDATE_SCREEN_FONT_H_
#define UPDATE_SCREEN_FONT_H_

#include <Uefi.h>

//
// A glyph: its bitmap is Width x Height pixels of 4 bits (alpha 0-15), high
// nibble first, rows one after the other.  Its box sits OffsetX pixels right
// of the pen and OffsetY above the baseline; Advance and the kerning are in
// 1/16 px.
//
typedef struct {
  UINT16    CodePoint;
  UINT16    Advance;
  UINT32    Offset;
  UINT8     Width;
  UINT8     Height;
  INT8      OffsetX;
  INT8      OffsetY;
  UINT8     LeftClass;                  ///< kerning, 0: none
  UINT8     RightClass;
} UPDATE_SCREEN_GLYPH;

typedef struct {
  UINT8                        LineHeight;
  UINT8                        BaseLine;    ///< from the bottom of the line
  UINT16                       GlyphCount;
  CONST UPDATE_SCREEN_GLYPH    *Glyphs;     ///< by CodePoint
  CONST UINT8                  *Bitmap;
  UINT8                        LeftClasses;
  UINT8                        RightClasses;
  CONST INT8                   *Kern;       ///< [LeftClass - 1][RightClass - 1]
} UPDATE_SCREEN_FONT;

//
// Each font has the glyphs the screen draws with it, and '?', drawn for any
// other (tools/ui-font.py checks the strings of UpdateScreenLib.c):
//   gUpdateScreenFont16  printable ASCII and the icons of the footer: status
//                        line, legend, time left, footer, and the lines of
//                        the boot manager;
//   gUpdateScreenFont20  the versions line, as "v1.3.6-rc3 * slot B > v1.3.6
//                        * slot A": digits, '.', '-', the letters of "v",
//                        "rc" and "slot", A and B, the bullet and the arrow;
//   gUpdateScreenFont32  the letters of the titles.
//
extern CONST UPDATE_SCREEN_FONT  gUpdateScreenFont16;
extern CONST UPDATE_SCREEN_FONT  gUpdateScreenFont20;
extern CONST UPDATE_SCREEN_FONT  gUpdateScreenFont32;

//
// Icons of Font Awesome 5 Free: those of the footer in gUpdateScreenFont16,
// the arrow and the bullet in gUpdateScreenFont20
//
#define UPDATE_SCREEN_ICON_WARNING  0xF071
#define UPDATE_SCREEN_ICON_CHECK    0xF00C
#define UPDATE_SCREEN_ICON_CLOSE    0xF00D
#define UPDATE_SCREEN_ICON_NEXT     0xF054
#define UPDATE_SCREEN_BULLET        0x2022

#endif
