/** @file
  Drawing of the firmware update screen.

  On black, the ouroboros of the ouroBIOS logo (assets/ourobios.svg, 16 x 16
  cells) is the progress: its body lights up from the head, clockwise, until
  it reaches the tail at 100%.  Below it the title, the versions, the status
  line with the percentage, and the bar, which is a map of the flash region
  being written: one column per 4 KiB block, rewritten, already up to date
  or still to do, the block being written in white.  At the bottom, what not
  to do while it runs.

  The first call draws everything, the next ones only what changed: a few
  cells of the ring, the columns of the blocks just written, the lines whose
  text changed.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include "UpdateScreenDraw.h"
#include "UpdateScreenFont.h"
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Protocol/FirmwareUpdateStatus.h>

//
// Colors, 0xRRGGBB: those of the setup UI (LvglTheme.h) and of the logo
//
#define COLOR_BACKGROUND    0x000000
#define COLOR_TEXT          0xF5F5F7
#define COLOR_SECONDARY     0xA1A1A6
#define COLOR_TERTIARY      0x8E8E93
#define COLOR_RING          0x007AFF
#define COLOR_RING_EDGE     0x64D2FF
#define COLOR_RING_DIM      0x16202C
#define COLOR_EYE           0xF5F5F7
#define COLOR_INFINITY      0xA1A1A6
#define COLOR_INFINITY_LOW  0x3A3A3C
#define COLOR_TRACK         0x2C2C2E
#define COLOR_CURRENT       0xFFFFFF
#define COLOR_WRITTEN       0x0A84FF
#define COLOR_SAME          0x2E7D5B
#define COLOR_SUCCESS       0x30D158
#define COLOR_WARNING       0xFF9F0A
#define COLOR_ERROR         0xFF453A

#define RING_CELLS   16
#define RING_LENGTH  94
#define RING_EDGE    4
#define BAR_WIDTH    720
#define LINE_MAX     40

//
// The logo: R the body, E the eye, I the infinity inside
//
STATIC CONST CHAR8  mOuroboros[RING_CELLS][RING_CELLS + 1] = {
  "................",
  "....RRRR........",
  "...RR.RRREERR...",
  "..RRRRR...RRRR..",
  ".RRRR......RRRR.",
  ".RRR........RRR.",
  ".RR..II..II..RR.",
  "RRR.I..II..I.RRR",
  "RRR.I..II..I.RRR",
  ".RR..II..II..RR.",
  ".RRR........RRR.",
  ".RRRR......RRRR.",
  "..RRRR....RRRR..",
  "...RRRRRRRRRR...",
  "....RRRRRRRR....",
  "................"
};

//
// The body cells (y * 16 + x) clockwise from the head, by the angle of
// their center around the center of the ring
//
STATIC CONST UINT8  mRingOrder[RING_LENGTH] = {
  58,  43,  59,  44,  75,  60,  61,  76,  77,  92,  78,  93,  94,  109, 110, 125,
  126, 127, 143, 142, 141, 158, 157, 174, 173, 190, 172, 189, 188, 205, 187, 204,
  220, 203, 219, 202, 235, 218, 234, 217, 233, 216, 232, 231, 215, 230, 214, 229,
  213, 228, 197, 212, 196, 211, 180, 195, 194, 179, 178, 163, 177, 162, 161, 146,
  145, 130, 129, 128, 112, 113, 114, 97,  98,  81,  82,  65,  83,  66,  67,  50,
  68,  51,  35,  52,  36,  53,  20,  21,  54,  38,  22,  39,  23,  40
};

//
// What a column of the bar shows
//
#define COLUMN_NONE       0xFF
#define COLUMN_SEPARATOR  0xFE

struct _UPDATE_SCREEN_DRAW {
  BOOLEAN                          Drawn;
  UINTN                            Cell;
  UINTN                            RingX;
  UINTN                            RingY;
  UINTN                            TitleY;
  UINTN                            VersionsY;
  UINTN                            StatusY;
  UINTN                            BarX;
  UINTN                            BarY;
  UINTN                            BarW;
  UINTN                            BarH;
  UINTN                            LegendY;
  UINTN                            FooterY;
  UINTN                            Lit;                  ///< body cells lit
  UINTN                            Breath;               ///< shade of the infinity, 0-7
  UINT8                            *Columns;             ///< BarW: what each column shows
  UINT8                            *Insets;              ///< BarW: the rounded ends
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL    *Line;                ///< a line of text, canvas width x LINE_MAX
  UPDATE_SCREEN_MODEL              Last;
};

/**
  Integer square root.
**/
STATIC
UINTN
ISqrt (
  IN UINTN  Value
  )
{
  UINTN  Root;
  UINTN  Bit;

  Root = 0;
  Bit  = (UINTN)1 << (sizeof (UINTN) * 8 - 2);
  while (Bit > Value) {
    Bit >>= 2;
  }

  while (Bit != 0) {
    if (Value >= Root + Bit) {
      Value -= Root + Bit;
      Root   = (Root >> 1) + Bit;
    } else {
      Root >>= 1;
    }

    Bit >>= 2;
  }

  return Root;
}

STATIC
UINT32
ToneColor (
  IN UPDATE_SCREEN_TONE  Tone,
  IN UINT32              Normal
  )
{
  switch (Tone) {
    case UpdateScreenToneSuccess:
      return COLOR_SUCCESS;
    case UpdateScreenToneWarning:
      return COLOR_WARNING;
    case UpdateScreenToneError:
      return COLOR_ERROR;
    default:
      return Normal;
  }
}

/**
  The color between Low and High, Level of 7.
**/
STATIC
UINT32
Mix (
  IN UINT32  Low,
  IN UINT32  High,
  IN UINTN   Level
  )
{
  UINT32  Result;
  UINTN   Shift;
  INT32   L;
  INT32   H;

  Result = 0;
  for (Shift = 0; Shift < 24; Shift += 8) {
    L       = (INT32)((Low >> Shift) & 0xFF);
    H       = (INT32)((High >> Shift) & 0xFF);
    Result |= (UINT32)(L + ((H - L) * (INT32)Level) / 7) << Shift;
  }

  return Result;
}

//
// Text
//

STATIC
CONST UPDATE_SCREEN_GLYPH *
FindGlyph (
  IN CONST UPDATE_SCREEN_FONT  *Font,
  IN CHAR16                    CodePoint
  )
{
  UINTN  Low;
  UINTN  High;
  UINTN  Middle;

  Low  = 0;
  High = Font->GlyphCount;
  while (Low < High) {
    Middle = (Low + High) / 2;
    if (Font->Glyphs[Middle].CodePoint == CodePoint) {
      return &Font->Glyphs[Middle];
    }

    if (Font->Glyphs[Middle].CodePoint < CodePoint) {
      Low = Middle + 1;
    } else {
      High = Middle;
    }
  }

  return (CodePoint == L'?') ? NULL : FindGlyph (Font, L'?');
}

/**
  The advance of Glyph after Previous, in whole pixels as LVGL counts it.
**/
STATIC
UINTN
GlyphAdvance (
  IN CONST UPDATE_SCREEN_FONT   *Font,
  IN CONST UPDATE_SCREEN_GLYPH  *Glyph,
  IN CONST UPDATE_SCREEN_GLYPH  *Next      OPTIONAL
  )
{
  INTN  Advance;

  Advance = Glyph->Advance;
  if ((Next != NULL) && (Glyph->LeftClass != 0) && (Next->RightClass != 0) &&
      (Glyph->LeftClass <= Font->LeftClasses) && (Next->RightClass <= Font->RightClasses))
  {
    Advance += Font->Kern[(Glyph->LeftClass - 1) * Font->RightClasses + (Next->RightClass - 1)];
  }

  if (Advance < 0) {
    return 0;
  }

  return (UINTN)((Advance + 8) >> 4);
}

STATIC
UINTN
TextWidth (
  IN CONST UPDATE_SCREEN_FONT  *Font,
  IN CONST CHAR16              *Text
  )
{
  UINTN                      Width;
  CONST UPDATE_SCREEN_GLYPH  *Glyph;

  Width = 0;
  for ( ; *Text != L'\0'; Text++) {
    Glyph = FindGlyph (Font, *Text);
    if (Glyph != NULL) {
      Width += GlyphAdvance (Font, Glyph, (Text[1] != L'\0') ? FindGlyph (Font, Text[1]) : NULL);
    }
  }

  return Width;
}

/**
  Start a line of text: Width x the height of Font in Draw->Line, background.
**/
STATIC
VOID
LineClear (
  IN UPDATE_SCREEN_DRAW        *Draw,
  IN UINTN                     Width,
  IN CONST UPDATE_SCREEN_FONT  *Font
  )
{
  ZeroMem (Draw->Line, Width * Font->LineHeight * sizeof (EFI_GRAPHICS_OUTPUT_BLT_PIXEL));
}

/**
  Draw Text at X of the line, in Color, blended on what is there.

  @return The X after the text.
**/
STATIC
UINTN
LineText (
  IN UPDATE_SCREEN_DRAW        *Draw,
  IN UINTN                     Width,
  IN CONST UPDATE_SCREEN_FONT  *Font,
  IN UINTN                     X,
  IN CONST CHAR16              *Text,
  IN UINT32                    Color
  )
{
  CONST UPDATE_SCREEN_GLYPH      *Glyph;
  CONST UINT8                    *Bits;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Pixel;
  UINTN                          Row;
  UINTN                          Column;
  UINTN                          Index;
  INTN                           Left;
  INTN                           Top;
  INTN                           PixelX;
  INTN                           PixelY;
  UINT32                         Alpha;
  UINT8                          Red;
  UINT8                          Green;
  UINT8                          Blue;

  Red   = (UINT8)(Color >> 16);
  Green = (UINT8)(Color >> 8);
  Blue  = (UINT8)Color;
  for ( ; *Text != L'\0'; Text++) {
    Glyph = FindGlyph (Font, *Text);
    if (Glyph == NULL) {
      continue;
    }

    Bits  = Font->Bitmap + Glyph->Offset;
    Left  = (INTN)X + Glyph->OffsetX;
    Top   = (INTN)(Font->LineHeight - Font->BaseLine) - Glyph->OffsetY - Glyph->Height;
    Index = 0;
    for (Row = 0; Row < Glyph->Height; Row++) {
      for (Column = 0; Column < Glyph->Width; Column++, Index++) {
        Alpha = (Bits[Index / 2] >> ((Index % 2 == 0) ? 4 : 0)) & 0x0F;
        if (Alpha == 0) {
          continue;
        }

        PixelX = Left + (INTN)Column;
        PixelY = Top + (INTN)Row;
        if ((PixelX < 0) || (PixelY < 0) || ((UINTN)PixelX >= Width) || ((UINTN)PixelY >= Font->LineHeight)) {
          continue;
        }

        Alpha        *= 17;
        Pixel         = &Draw->Line[(UINTN)PixelY * Width + (UINTN)PixelX];
        Pixel->Red    = (UINT8)(Pixel->Red + (((INT32)Red - Pixel->Red) * (INT32)Alpha) / 255);
        Pixel->Green  = (UINT8)(Pixel->Green + (((INT32)Green - Pixel->Green) * (INT32)Alpha) / 255);
        Pixel->Blue   = (UINT8)(Pixel->Blue + (((INT32)Blue - Pixel->Blue) * (INT32)Alpha) / 255);
      }
    }

    X += GlyphAdvance (Font, Glyph, (Text[1] != L'\0') ? FindGlyph (Font, Text[1]) : NULL);
  }

  return X;
}

/**
  A square of Size pixels at X, centered on the lower-case letters of Font.
**/
STATIC
VOID
LineSquare (
  IN UPDATE_SCREEN_DRAW        *Draw,
  IN UINTN                     Width,
  IN CONST UPDATE_SCREEN_FONT  *Font,
  IN UINTN                     X,
  IN UINTN                     Size,
  IN UINT32                    Color
  )
{
  UINTN                          Row;
  UINTN                          Column;
  UINTN                          Top;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Pixel;

  Top = Font->LineHeight - Font->BaseLine;
  Top = (Top > Size + Size / 3) ? Top - Size - Size / 3 : 0;
  for (Row = Top; (Row < Top + Size) && (Row < Font->LineHeight); Row++) {
    for (Column = X; (Column < X + Size) && (Column < Width); Column++) {
      Pixel           = &Draw->Line[Row * Width + Column];
      Pixel->Red      = (UINT8)(Color >> 16);
      Pixel->Green    = (UINT8)(Color >> 8);
      Pixel->Blue     = (UINT8)Color;
      Pixel->Reserved = 0;
    }
  }
}

STATIC
VOID
LineShow (
  IN UPDATE_SCREEN_DRAW        *Draw,
  IN UPDATE_SCREEN_CANVAS      *Canvas,
  IN UINTN                     X,
  IN UINTN                     Y,
  IN UINTN                     Width,
  IN CONST UPDATE_SCREEN_FONT  *Font
  )
{
  if ((X + Width > Canvas->Width) || (Y + Font->LineHeight > Canvas->Height)) {
    return;
  }

  Canvas->Blit (Canvas, Draw->Line, X, Y, Width, Font->LineHeight);
}

/**
  A line of text centered on the screen, the whole width cleared.  Icon, if
  not 0, goes before the text in IconColor.
**/
STATIC
VOID
DrawCentered (
  IN UPDATE_SCREEN_DRAW        *Draw,
  IN UPDATE_SCREEN_CANVAS      *Canvas,
  IN UINTN                     Y,
  IN CONST UPDATE_SCREEN_FONT  *Font,
  IN CONST CHAR16              *Text,
  IN UINT32                    Color,
  IN CHAR16                    Icon,
  IN UINT32                    IconColor
  )
{
  CHAR16  IconText[2];
  UINTN   Width;
  UINTN   IconWidth;
  UINTN   X;

  IconText[0] = Icon;
  IconText[1] = L'\0';
  IconWidth   = (Icon != 0) ? TextWidth (Font, IconText) + Font->LineHeight / 2 : 0;
  Width       = IconWidth + TextWidth (Font, Text);
  X           = (Width < Canvas->Width) ? (Canvas->Width - Width) / 2 : 0;

  LineClear (Draw, Canvas->Width, Font);
  if (Icon != 0) {
    LineText (Draw, Canvas->Width, Font, X, IconText, IconColor);
  }

  LineText (Draw, Canvas->Width, Font, X + IconWidth, Text, Color);
  LineShow (Draw, Canvas, 0, Y, Canvas->Width, Font);
}

//
// The ring
//

STATIC
VOID
FillCell (
  IN UPDATE_SCREEN_DRAW    *Draw,
  IN UPDATE_SCREEN_CANVAS  *Canvas,
  IN UINTN                 Index,
  IN UINT32                Color
  )
{
  Canvas->Fill (
            Canvas,
            Draw->RingX + (Index % RING_CELLS) * Draw->Cell,
            Draw->RingY + (Index / RING_CELLS) * Draw->Cell,
            Draw->Cell,
            Draw->Cell,
            Color
            );
}

STATIC
UINT32
RingColor (
  IN UINTN  Rank,
  IN UINTN  Lit
  )
{
  if (Rank >= Lit) {
    return COLOR_RING_DIM;
  }

  if ((Lit < RING_LENGTH) && (Rank + RING_EDGE >= Lit)) {
    return COLOR_RING_EDGE;
  }

  return COLOR_RING;
}

STATIC
VOID
DrawInfinity (
  IN UPDATE_SCREEN_DRAW    *Draw,
  IN UPDATE_SCREEN_CANVAS  *Canvas,
  IN UINTN                 Breath
  )
{
  UINTN   Index;
  UINT32  Color;

  Color = Mix (COLOR_INFINITY_LOW, COLOR_INFINITY, Breath);
  for (Index = 0; Index < RING_CELLS * RING_CELLS; Index++) {
    if (mOuroboros[Index / RING_CELLS][Index % RING_CELLS] == 'I') {
      FillCell (Draw, Canvas, Index, Color);
    }
  }
}

STATIC
VOID
DrawRing (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model,
  IN BOOLEAN                    All
  )
{
  UINTN  Lit;
  UINTN  From;
  UINTN  To;
  UINTN  Rank;
  UINTN  Index;
  UINTN  Breath;
  UINTN  Phase;

  Lit = (MIN (Model->Ring, 1000) * RING_LENGTH) / 1000;
  if (All || (Model->EyeClosed != Draw->Last.EyeClosed)) {
    for (Index = 0; Index < RING_CELLS * RING_CELLS; Index++) {
      if (mOuroboros[Index / RING_CELLS][Index % RING_CELLS] == 'E') {
        FillCell (Draw, Canvas, Index, Model->EyeClosed ? COLOR_RING : COLOR_EYE);
      }
    }
  }

  if (All) {
    From = 0;
    To   = RING_LENGTH;
  } else {
    From = MIN (Lit, Draw->Lit);
    From = (From > RING_EDGE) ? From - RING_EDGE : 0;
    To   = MAX (Lit, Draw->Lit);
  }

  for (Rank = From; Rank < To; Rank++) {
    if (All || (RingColor (Rank, Lit) != RingColor (Rank, Draw->Lit))) {
      FillCell (Draw, Canvas, mRingOrder[Rank], RingColor (Rank, Lit));
    }
  }

  Draw->Lit = Lit;

  //
  // The infinity breathes, 0 to 6 and back, while blocks are written
  //
  if (Model->Breathing) {
    Phase  = (Model->Tick / 2) % 14;
    Breath = (Phase < 7) ? Phase : 13 - Phase;
  } else {
    Breath = 7;
  }

  if (All || (Breath != Draw->Breath)) {
    DrawInfinity (Draw, Canvas, Breath);
    Draw->Breath = Breath;
  }
}

//
// The bar
//

/**
  What column Column shows: the block under it, or with more blocks than
  columns the least advanced of them.
**/
STATIC
UINT8
ColumnState (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN CONST UPDATE_SCREEN_MODEL  *Model,
  IN UINTN                      Column
  )
{
  UINTN  Blocks;
  UINTN  First;
  UINTN  Last;
  UINTN  Block;
  UINT8  State;
  UINT8  Result;

  Blocks = MIN (Model->MapBlocks, FIRMWARE_UPDATE_STATUS_MAP_SIZE);
  if ((Model->Map == NULL) || (Blocks == 0)) {
    return (Column < (MIN (Model->Ring, 1000) * Draw->BarW) / 1000) ? FIRMWARE_UPDATE_BLOCK_WRITTEN : FIRMWARE_UPDATE_BLOCK_TO_DO;
  }

  //
  // A failed block narrower than a column shows over three
  //
  if ((Blocks * 3 > Draw->BarW) &&
      (((Column > 0) && (Model->Map[((Column - 1) * Blocks) / Draw->BarW] == FIRMWARE_UPDATE_BLOCK_FAILED)) ||
       ((Column + 1 < Draw->BarW) && (Model->Map[((Column + 1) * Blocks) / Draw->BarW] == FIRMWARE_UPDATE_BLOCK_FAILED))))
  {
    return FIRMWARE_UPDATE_BLOCK_FAILED;
  }

  First = (Column * Blocks) / Draw->BarW;
  Last  = ((Column + 1) * Blocks) / Draw->BarW;
  if (Last <= First) {
    //
    // A block over several columns: a gap of one column between blocks of
    // 4 columns or more
    //
    if ((Blocks * 4 <= Draw->BarW) && (Column > 0) && ((((Column - 1) * Blocks) / Draw->BarW) != First)) {
      return COLUMN_SEPARATOR;
    }

    return Model->Map[First];
  }

  Result = FIRMWARE_UPDATE_BLOCK_SAME;
  for (Block = First; Block < Last; Block++) {
    State = Model->Map[Block];
    if ((State == FIRMWARE_UPDATE_BLOCK_FAILED) || (State == FIRMWARE_UPDATE_BLOCK_CURRENT)) {
      return State;
    }

    if ((State == FIRMWARE_UPDATE_BLOCK_TO_DO) ||
        ((State == FIRMWARE_UPDATE_BLOCK_WRITTEN) && (Result == FIRMWARE_UPDATE_BLOCK_SAME)))
    {
      Result = State;
    }
  }

  return Result;
}

STATIC
UINT32
ColumnColor (
  IN UINT8  State
  )
{
  switch (State) {
    case FIRMWARE_UPDATE_BLOCK_CURRENT:
      return COLOR_CURRENT;
    case FIRMWARE_UPDATE_BLOCK_WRITTEN:
      return COLOR_WRITTEN;
    case FIRMWARE_UPDATE_BLOCK_SAME:
      return COLOR_SAME;
    case FIRMWARE_UPDATE_BLOCK_FAILED:
      return COLOR_ERROR;
    case COLUMN_SEPARATOR:
      return COLOR_BACKGROUND;
    default:
      return COLOR_TRACK;
  }
}

STATIC
VOID
DrawBar (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model
  )
{
  UINTN  Column;
  UINT8  State;

  for (Column = 0; Column < Draw->BarW; Column++) {
    State = ColumnState (Draw, Model, Column);
    if (State == Draw->Columns[Column]) {
      continue;
    }

    Canvas->Fill (
              Canvas,
              Draw->BarX + Column,
              Draw->BarY + Draw->Insets[Column],
              1,
              Draw->BarH - 2 * Draw->Insets[Column],
              ColumnColor (State)
              );
    Draw->Columns[Column] = State;
  }
}

//
// The lines
//

STATIC
VOID
DrawStatus (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model
  )
{
  CONST UPDATE_SCREEN_FONT  *Font;
  UINTN                     Width;

  Font = &gUpdateScreenFont16;
  LineClear (Draw, Draw->BarW, Font);
  LineText (Draw, Draw->BarW, Font, 0, Model->Status, ToneColor (Model->StatusTone, COLOR_TEXT));
  Width = TextWidth (Font, Model->Percent);
  if (Width < Draw->BarW) {
    LineText (Draw, Draw->BarW, Font, Draw->BarW - Width, Model->Percent, COLOR_TEXT);
  }

  LineShow (Draw, Canvas, Draw->BarX, Draw->StatusY, Draw->BarW, Font);
}

STATIC
VOID
DrawLegend (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model
  )
{
  CONST UPDATE_SCREEN_FONT  *Font;
  UINTN                     X;
  UINTN                     Size;
  UINTN                     Gap;
  UINTN                     Width;

  Font = &gUpdateScreenFont16;
  Size = Font->LineHeight / 2;
  Gap  = Font->LineHeight;
  LineClear (Draw, Draw->BarW, Font);
  if (Model->Legend) {
    X = 0;
    if (Model->Written[0] != L'\0') {
      LineSquare (Draw, Draw->BarW, Font, X, Size, COLOR_WRITTEN);
      X = LineText (Draw, Draw->BarW, Font, X + Size + Size / 2, Model->Written, COLOR_TERTIARY) + Gap;
    }

    if (Model->Same[0] != L'\0') {
      LineSquare (Draw, Draw->BarW, Font, X, Size, COLOR_SAME);
      X = LineText (Draw, Draw->BarW, Font, X + Size + Size / 2, Model->Same, COLOR_TERTIARY) + Gap;
    }

    if (Model->ToDo[0] != L'\0') {
      LineSquare (Draw, Draw->BarW, Font, X, Size, COLOR_TRACK);
      LineText (Draw, Draw->BarW, Font, X + Size + Size / 2, Model->ToDo, COLOR_TERTIARY);
    }
  }

  Width = TextWidth (Font, Model->Eta);
  if (Width < Draw->BarW) {
    LineText (Draw, Draw->BarW, Font, Draw->BarW - Width, Model->Eta, COLOR_TERTIARY);
  }

  LineShow (Draw, Canvas, Draw->BarX, Draw->LegendY, Draw->BarW, Font);
}

STATIC
VOID
DrawFooter (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model
  )
{
  CHAR16  Icon;
  UINT32  Color;

  switch (Model->FooterTone) {
    case UpdateScreenToneWarning:
      Icon = UPDATE_SCREEN_ICON_WARNING;
      break;
    case UpdateScreenToneSuccess:
      Icon = UPDATE_SCREEN_ICON_CHECK;
      break;
    case UpdateScreenToneError:
      Icon = UPDATE_SCREEN_ICON_CLOSE;
      break;
    default:
      Icon = 0;
      break;
  }

  Color = ToneColor (Model->FooterTone, COLOR_TERTIARY);
  DrawCentered (Draw, Canvas, Draw->FooterY, &gUpdateScreenFont16, Model->Footer, Color, Icon, Color);
}

UPDATE_SCREEN_DRAW *
UpdateScreenDrawCreate (
  IN UPDATE_SCREEN_CANVAS  *Canvas
  )
{
  UPDATE_SCREEN_DRAW  *Draw;
  UINTN               Scale;
  UINTN               Block;
  UINTN               Top;
  UINTN               Radius;
  UINTN               Column;
  UINTN               Distance;
  UINTN               Half;
  UINTN               Gap;

  if ((Canvas->Width < 640) || (Canvas->Height < 480)) {
    return NULL;
  }

  Draw = AllocateZeroPool (sizeof (*Draw));
  if (Draw == NULL) {
    return NULL;
  }

  //
  // Sizes for 1920 x 1080, scaled (in 1/1000) to the screen
  //
  Scale = MIN ((Canvas->Width * 1000) / 1920, (Canvas->Height * 1000) / 1080);
  if (Scale > 1000) {
    Scale = 1000 + (Scale - 1000) / 2;
  }

  Draw->Cell = MAX (8, (18 * Scale + 500) / 1000);
  Draw->BarW = MIN (BAR_WIDTH, Canvas->Width - 96);
  Draw->BarH = MAX (8, ((12 * Scale + 500) / 1000) & ~(UINTN)1);
  Gap        = MAX (24, (48 * Scale) / 1000);

  //
  // The block from the ring to the legend, 42% down the free height
  //
  Block = Draw->Cell * RING_CELLS + Gap + gUpdateScreenFont32.LineHeight + 10 + gUpdateScreenFont20.LineHeight +
          Gap + gUpdateScreenFont16.LineHeight + 12 + Draw->BarH + 12 + gUpdateScreenFont16.LineHeight;
  if (Block + 2 * gUpdateScreenFont16.LineHeight + 48 > Canvas->Height) {
    FreePool (Draw);
    return NULL;
  }

  Top             = ((Canvas->Height - Block) * 42) / 100;
  Draw->RingX     = (Canvas->Width - Draw->Cell * RING_CELLS) / 2;
  Draw->RingY     = Top;
  Draw->TitleY    = Draw->RingY + Draw->Cell * RING_CELLS + Gap;
  Draw->VersionsY = Draw->TitleY + gUpdateScreenFont32.LineHeight + 10;
  Draw->StatusY   = Draw->VersionsY + gUpdateScreenFont20.LineHeight + Gap;
  Draw->BarX      = (Canvas->Width - Draw->BarW) / 2;
  Draw->BarY      = Draw->StatusY + gUpdateScreenFont16.LineHeight + 12;
  Draw->LegendY   = Draw->BarY + Draw->BarH + 12;
  Draw->FooterY   = Canvas->Height - MAX (48, (96 * Scale) / 1000) - gUpdateScreenFont16.LineHeight;
  if (Draw->FooterY < Draw->LegendY + gUpdateScreenFont16.LineHeight + 16) {
    Draw->FooterY = Draw->LegendY + gUpdateScreenFont16.LineHeight + 16;
  }

  Draw->Columns = AllocatePool (Draw->BarW);
  Draw->Insets  = AllocateZeroPool (Draw->BarW);
  Draw->Line    = AllocatePool (Canvas->Width * LINE_MAX * sizeof (EFI_GRAPHICS_OUTPUT_BLT_PIXEL));
  if ((Draw->Columns == NULL) || (Draw->Insets == NULL) || (Draw->Line == NULL)) {
    if (Draw->Columns != NULL) {
      FreePool (Draw->Columns);
    }

    if (Draw->Insets != NULL) {
      FreePool (Draw->Insets);
    }

    if (Draw->Line != NULL) {
      FreePool (Draw->Line);
    }

    FreePool (Draw);
    return NULL;
  }

  //
  // Rounded ends: the half height of a circle of the bar's height at the
  // center of each end column, rounded
  //
  Radius = Draw->BarH / 2;
  for (Column = 0; Column < Radius; Column++) {
    Distance = 2 * Radius - 2 * Column - 1;
    Half     = ISqrt (4 * Radius * Radius - Distance * Distance);
    Draw->Insets[Column]                  = (UINT8)(Radius - MIN (Radius, (Half + 1) / 2));
    Draw->Insets[Draw->BarW - 1 - Column] = Draw->Insets[Column];
  }

  SetMem (Draw->Columns, Draw->BarW, COLUMN_NONE);
  return Draw;
}

VOID
UpdateScreenDrawRender (
  IN UPDATE_SCREEN_DRAW         *Draw,
  IN UPDATE_SCREEN_CANVAS       *Canvas,
  IN CONST UPDATE_SCREEN_MODEL  *Model
  )
{
  BOOLEAN  All;

  All = !Draw->Drawn;
  if (All) {
    Canvas->Fill (Canvas, 0, 0, Canvas->Width, Canvas->Height, COLOR_BACKGROUND);
  }

  DrawRing (Draw, Canvas, Model, All);
  DrawBar (Draw, Canvas, Model);

  if (All || (Model->TitleTone != Draw->Last.TitleTone) || (StrCmp (Model->Title, Draw->Last.Title) != 0)) {
    DrawCentered (Draw, Canvas, Draw->TitleY, &gUpdateScreenFont32, Model->Title, ToneColor (Model->TitleTone, COLOR_TEXT), 0, 0);
  }

  if (All || (StrCmp (Model->Versions, Draw->Last.Versions) != 0)) {
    DrawCentered (Draw, Canvas, Draw->VersionsY, &gUpdateScreenFont20, Model->Versions, COLOR_SECONDARY, 0, 0);
  }

  if (All || (Model->StatusTone != Draw->Last.StatusTone) || (StrCmp (Model->Status, Draw->Last.Status) != 0) ||
      (StrCmp (Model->Percent, Draw->Last.Percent) != 0))
  {
    DrawStatus (Draw, Canvas, Model);
  }

  if (All || (Model->Legend != Draw->Last.Legend) || (StrCmp (Model->Written, Draw->Last.Written) != 0) ||
      (StrCmp (Model->Same, Draw->Last.Same) != 0) || (StrCmp (Model->ToDo, Draw->Last.ToDo) != 0) ||
      (StrCmp (Model->Eta, Draw->Last.Eta) != 0))
  {
    DrawLegend (Draw, Canvas, Model);
  }

  if (All || (Model->FooterTone != Draw->Last.FooterTone) || (StrCmp (Model->Footer, Draw->Last.Footer) != 0)) {
    DrawFooter (Draw, Canvas, Model);
  }

  CopyMem (&Draw->Last, Model, sizeof (Draw->Last));
  Draw->Drawn = TRUE;
}
