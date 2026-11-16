/** @file
  The event group that says that an image that is not part of the firmware is
  about to be loaded before a boot was started.

  Until a boot option is started (ReadyToBoot) the setup may change the
  settings of the firmware, and the locks that keep an OS from changing them
  are not armed yet. An option ROM, a Driver#### option and a SysPrep####
  option run in that window. ThirdPartyImageLockLib arms the locks before the
  first such image is loaded and then signals this group once, for the
  modules that keep their own state of the locks.

  Copyright (c) 2026, ouroBIOS contributors
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef THIRD_PARTY_IMAGE_H_
#define THIRD_PARTY_IMAGE_H_

#define THIRD_PARTY_IMAGE_EVENT_GROUP_GUID \
  { \
    0xa44c4d4f, 0x13c8, 0x4857, { 0xbf, 0x6d, 0xb0, 0x0d, 0x51, 0xbc, 0x12, 0x36 } \
  }

extern EFI_GUID  gUefiPayloadThirdPartyImageEventGroupGuid;

#endif
