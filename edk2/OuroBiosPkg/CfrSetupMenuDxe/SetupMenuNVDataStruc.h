/** @file
  A Setup Menu for configuring boot options defined by bootloader CFR.

  Copyright (c) 2023, 9elements GmbH.<BR>
  SPDX-License-Identifier: BSD-2-Clause-Patent

**/

#ifndef _SETUPMENUNVDATASTRUC_H_
#define _SETUPMENUNVDATASTRUC_H_

#define SETUP_MENU_FORMSET_GUID \
  { \
    0x93E6FCD9, 0x8E17, 0x43DF, { 0xB7, 0xF0, 0x91, 0x3E, 0x58, 0xB1, 0xA7, 0x89 } \
  }

#define SETUP_MENU_FORM_ID   0x0001
#define LABEL_RT_COMP_START  0x0001
#define CFR_COMPONENT_START  0x1000
#define LABEL_RT_COMP_END    0xefff

//
// The first top-level CFR forms get forms of their own (categories), with
// these IDs (also in SetupMenuVfr.Vfr), which the main form links to.
//
#define SETUP_MENU_CATEGORY_FORM_ID  0x0100
#define SETUP_MENU_CATEGORY_MAX      8

//
// Question IDs of the links to the pages of other drivers at the end of some
// categories (SetupMenuCfr.c), the password of the setup menu among them.
//
#define SETUP_MENU_PASSWORD_QUESTION_ID  0x00F0
#define SETUP_MENU_LINK_QUESTION_ID      0x00F1

//
// The labels between which those links go, a start and an end label for
// each set of them (LABEL_LINKS_START + 2 * set, + 1).
//
#define LABEL_LINKS_START  0x2000

//
// EDKII_IFR_FRONT_PAGE_FORMS_GUID: the front page lists the categories
//
#include <Guid/HiiFrontPageForms.h>

#endif
