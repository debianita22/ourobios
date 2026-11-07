/** @file
  A Setup Menu for configuring boot options defined by bootloader CFR.
  This file parses CFR to produce HII IFR.

  Copyright (c) 2023, 9elements GmbH.<BR>
  SPDX-License-Identifier: BSD-2-Clause-Patent

**/

#include "SetupMenu.h"
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/CfrHelpersLib.h>
#include <Library/DebugLib.h>
#include <Library/HiiLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PcdLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/VariablePolicyHelperLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Guid/CfrSetupMenuGuid.h>
#include <Guid/VariableFormat.h>

//
// CFR_OPTFLAG_LOCK_AT_BOOT: the setup may still write the option in this
// boot, nothing after ReadyToBoot may. A Variable Policy rule cannot be added
// at ReadyToBoot: the variable driver closes Variable Policy to new rules at
// EndOfDxe (LockVariablePolicy()), which BDS signals first, and a rule
// registered later is refused with EFI_WRITE_PROTECTED. So each option gets a
// LOCK_ON_VAR_STATE rule while the driver starts, before EndOfDxe, that locks
// it once the volatile trigger CfrLockAtBoot holds 1, and the trigger is
// written at ReadyToBoot. The trigger itself is lock-on-create, so it cannot
// be cleared or pre-created by anything that runs after it.
//
#define CFR_LOCK_AT_BOOT_TRIGGER  L"CfrLockAtBoot"

STATIC EFI_EVENT  mLockAtBootEvent      = NULL;
STATIC BOOLEAN    mLockAtBootRegistered = FALSE;
STATIC BOOLEAN    mLockAtBootApplied    = FALSE;

/**
  Register, before EndOfDxe, the rule that write-locks a CFR option variable
  once the trigger is set at ReadyToBoot.

**/
STATIC
VOID
EFIAPI
CfrQueueLockAtBoot (
  IN CONST CHAR16  *VariableName
  )
{
  EFI_STATUS  Status;

  if ((VariableName == NULL) || (VariableName[0] == L'\0')) {
    return;
  }

  if (mVariablePolicy == NULL) {
    DEBUG ((DEBUG_WARN, "CFR: No Variable Policy; no lock-at-boot for \"%s\"!\n", VariableName));
    return;
  }

  if (!mLockAtBootRegistered) {
    Status = RegisterBasicVariablePolicy (
               mVariablePolicy,
               &gEficorebootNvDataGuid,
               CFR_LOCK_AT_BOOT_TRIGGER,
               sizeof (UINT8),
               sizeof (UINT8),
               VARIABLE_POLICY_NO_MUST_ATTR,
               EFI_VARIABLE_NON_VOLATILE | EFI_VARIABLE_RUNTIME_ACCESS,
               VARIABLE_POLICY_TYPE_LOCK_ON_CREATE
               );
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_WARN, "CFR: No rule for the lock-at-boot trigger: %r\n", Status));
      return;
    }

    mLockAtBootRegistered = TRUE;
  }

  Status = RegisterVarStateVariablePolicy (
             mVariablePolicy,
             &gEficorebootNvDataGuid,
             VariableName,
             VARIABLE_POLICY_NO_MIN_SIZE,
             VARIABLE_POLICY_NO_MAX_SIZE,
             VARIABLE_POLICY_NO_MUST_ATTR,
             VARIABLE_POLICY_NO_CANT_ATTR,
             &gEficorebootNvDataGuid,
             CFR_LOCK_AT_BOOT_TRIGGER,
             1
             );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "CFR: Failed to lock-at-boot variable \"%s\": %r\n", VariableName, Status));
  }
}

/**
  At ReadyToBoot, set the trigger that the lock-at-boot rules wait for.

**/
STATIC
VOID
EFIAPI
CfrApplyLockAtBoot (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  EFI_STATUS  Status;
  UINT8       On;

  if (mLockAtBootApplied) {
    return;
  }

  mLockAtBootApplied = TRUE;
  On                 = 1;
  Status             = gRT->SetVariable (
                              CFR_LOCK_AT_BOOT_TRIGGER,
                              &gEficorebootNvDataGuid,
                              EFI_VARIABLE_BOOTSERVICE_ACCESS,
                              sizeof (On),
                              &On
                              );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "CFR: Failed to set the lock-at-boot trigger: %r\n", Status));
  }
}

/**
  Register a ReadyToBoot callback that write-locks CFR variables marked
  CFR_OPTFLAG_LOCK_AT_BOOT.

**/
EFI_STATUS
EFIAPI
CfrRegisterLockAtBootEvent (
  VOID
  )
{
  EFI_STATUS  Status;

  if (!mLockAtBootRegistered || (mLockAtBootEvent != NULL)) {
    return EFI_SUCCESS;
  }

  Status = EfiCreateEventReadyToBootEx (
             TPL_CALLBACK,
             CfrApplyLockAtBoot,
             NULL,
             &mLockAtBootEvent
             );
  if (EFI_ERROR (Status)) {
    mLockAtBootEvent = NULL;
  }

  return Status;
}

/**
  Free deferred lock state. Safe to call if nothing was registered.

**/
VOID
EFIAPI
CfrCleanupLockAtBoot (
  VOID
  )
{
  //
  // The rules stay registered: Variable Policy has no way to remove one, and
  // without the event the trigger is never set, so they never lock.
  //
  if (mLockAtBootEvent != NULL) {
    gBS->CloseEvent (mLockAtBootEvent);
    mLockAtBootEvent = NULL;
  }

  mLockAtBootApplied = FALSE;
}

//
// HII question IDs are 16-bit while CFR object IDs are 64-bit (derived from
// pointers in coreboot), so the options get consecutive question IDs from
// CFR_COMPONENT_START, which are also the IDs of their VARSTOREs.
//
typedef struct {
  UINT64             ObjectId;
  EFI_QUESTION_ID    QuestionId;
} CFR_QUESTION_ID_MAP;

STATIC CFR_QUESTION_ID_MAP  *mQuestionIdMap     = NULL;
STATIC UINTN                mQuestionIdMapCount = 0;
STATIC UINTN                mQuestionIdMapSize  = 0;

//
// The pages of other drivers that some categories link to, after their
// options, in cards of their own: the time and date, the firmware update,
// the boot splash and the graphical UI in the category named by
// PcdCfrSetupMenuGeneralCategory, Secure Boot and the password asked for
// before the setup menu opens in the one named by
// PcdCfrSetupMenuPasswordCategory. A link is only there with its page: the
// links go in at EndOfDxe, once the drivers have installed their formsets.
//
typedef enum {
  CfrLinksGeneral,
  CfrLinksSecurity,
  CfrLinksMax
} CFR_LINKS_SET;

typedef struct {
  CFR_LINKS_SET      Set;
  EFI_STRING_ID      Card;
  EFI_GUID           FormSetGuid;
  EFI_FORM_ID        FormId;
  EFI_QUESTION_ID    QuestionId;
  EFI_STRING_ID      Prompt;
  EFI_STRING_ID      Help;
} CFR_PAGE_LINK;

STATIC CONST CFR_PAGE_LINK  mPageLinks[] = {
  //
  // TIME_DATE_SETTINGS_FORMSET_GUID (TimeDateSettingsDxe)
  //
  {
    CfrLinksGeneral,
    STRING_TOKEN (STR_LINKS_TITLE),
    { 0x7a8b9c0d, 0x1e2f, 0x3a4b, { 0x5c, 0x6d, 0x7e, 0x8f, 0x9a, 0x0b, 0x1c, 0x2d }
    },
    0x1000,
    SETUP_MENU_LINK_QUESTION_ID,
    STRING_TOKEN (STR_LINK_TIME_DATE),
    STRING_TOKEN (STR_LINK_TIME_DATE_HELP)
  },
  //
  // FIRMWARE_UPDATE_FORMSET_GUID (FirmwareUpdateDxe)
  //
  {
    CfrLinksGeneral,
    STRING_TOKEN (STR_LINKS_TITLE),
    { 0x04e8b12f, 0xc919, 0x4cd9, { 0x89, 0x3d, 0x64, 0x23, 0x40, 0x4d, 0xc0, 0x2d }
    },
    0x1000,
    SETUP_MENU_LINK_QUESTION_ID + 1,
    STRING_TOKEN (STR_LINK_FIRMWARE_UPDATE),
    STRING_TOKEN (STR_LINK_FIRMWARE_UPDATE_HELP)
  },
  //
  // BOOT_SPLASH_CONFIG_FORMSET_GUID (BootSplashConfigDxe)
  //
  {
    CfrLinksGeneral,
    STRING_TOKEN (STR_LINKS_TITLE),
    { 0xb2d4e6f8, 0x1a3c, 0x4e5f, { 0x8b, 0x9d, 0x0c, 0x2e, 0x4a, 0x6f, 0x8d, 0xb1 }
    },
    0x1000,
    SETUP_MENU_LINK_QUESTION_ID + 2,
    STRING_TOKEN (STR_LINK_BOOT_SPLASH),
    STRING_TOKEN (STR_LINK_BOOT_SPLASH_HELP)
  },
  //
  // LVGL_UI_CONFIG_FORMSET_GUID (LvglPkg, LvglSetupDxe)
  //
  {
    CfrLinksGeneral,
    STRING_TOKEN (STR_LINKS_TITLE),
    { 0xddb969f2, 0xe99b, 0x4dd5, { 0x8e, 0x36, 0xb8, 0x0b, 0x52, 0x6d, 0x3b, 0x73 }
    },
    0x0001,
    SETUP_MENU_LINK_QUESTION_ID + 3,
    STRING_TOKEN (STR_LINK_GRAPHICAL_UI),
    STRING_TOKEN (STR_LINK_GRAPHICAL_UI_HELP)
  },
  //
  // SECUREBOOT_CONFIG_FORM_SET_GUID (SecureBootConfigDxe)
  //
  {
    CfrLinksSecurity,
    STRING_TOKEN (STR_SECURE_BOOT_TITLE),
    { 0x5daf50a5, 0xea81, 0x4de2, { 0x8f, 0x9b, 0xca, 0xbd, 0xa9, 0xcf, 0x5c, 0x14 }
    },
    0x0001,
    SETUP_MENU_LINK_QUESTION_ID + 4,
    STRING_TOKEN (STR_LINK_SECURE_BOOT),
    STRING_TOKEN (STR_LINK_SECURE_BOOT_HELP)
  },
  //
  // USER_AUTHENTICATION_FORMSET_GUID (UserAuthenticationDxe): its form asks
  // for the current and the new password
  //
  {
    CfrLinksSecurity,
    STRING_TOKEN (STR_PASSWORD_TITLE),
    { 0x760e3022, 0xf149, 0x4560, { 0x9c, 0x6f, 0x33, 0xaa, 0x7d, 0x48, 0x75, 0xfa }
    },
    0x0001,
    SETUP_MENU_PASSWORD_QUESTION_ID,
    STRING_TOKEN (STR_PASSWORD_PROMPT),
    STRING_TOKEN (STR_PASSWORD_HELP)
  },
};

//
// The category form of each set of links, 0 for none, and the EndOfDxe
// event that fills them
//
STATIC EFI_FORM_ID  mPageLinksForm[CfrLinksMax];
STATIC EFI_EVENT    mPageLinksEvent = NULL;

//
// Titles of the category forms, set from the top-level CFR forms
//
STATIC CONST EFI_STRING_ID  mCategoryTitle[SETUP_MENU_CATEGORY_MAX] = {
  STRING_TOKEN (STR_CFR_CATEGORY_0),
  STRING_TOKEN (STR_CFR_CATEGORY_1),
  STRING_TOKEN (STR_CFR_CATEGORY_2),
  STRING_TOKEN (STR_CFR_CATEGORY_3),
  STRING_TOKEN (STR_CFR_CATEGORY_4),
  STRING_TOKEN (STR_CFR_CATEGORY_5),
  STRING_TOKEN (STR_CFR_CATEGORY_6),
  STRING_TOKEN (STR_CFR_CATEGORY_7),
};

/**
  Return the question ID of a CFR option.

  @param[in]  ObjectId  CFR object ID of the option.

  @return The question ID, or 0 when ObjectId is not an option.

**/
STATIC
EFI_QUESTION_ID
CfrQuestionId (
  IN UINT64  ObjectId
  )
{
  UINTN  Index;

  if (ObjectId == 0) {
    return 0;
  }

  for (Index = 0; Index < mQuestionIdMapCount; Index++) {
    if (mQuestionIdMap[Index].ObjectId == ObjectId) {
      return mQuestionIdMap[Index].QuestionId;
    }
  }

  return 0;
}

/**
  Give a CFR option the next free question ID, unless it has one.

**/
STATIC
VOID
CfrAssignQuestionId (
  IN UINT64  ObjectId
  )
{
  CFR_QUESTION_ID_MAP  *NewMap;

  if ((ObjectId == 0) || (CfrQuestionId (ObjectId) != 0)) {
    return;
  }

  if (CFR_COMPONENT_START + mQuestionIdMapCount >= LABEL_RT_COMP_END) {
    DEBUG ((DEBUG_ERROR, "CFR: Too many options, 0x%lx left out!\n", ObjectId));
    return;
  }

  if (mQuestionIdMapCount == mQuestionIdMapSize) {
    NewMap = ReallocatePool (
               mQuestionIdMapSize * sizeof (CFR_QUESTION_ID_MAP),
               (mQuestionIdMapSize + 64) * sizeof (CFR_QUESTION_ID_MAP),
               mQuestionIdMap
               );
    if (NewMap == NULL) {
      return;
    }

    mQuestionIdMap      = NewMap;
    mQuestionIdMapSize += 64;
  }

  mQuestionIdMap[mQuestionIdMapCount].ObjectId   = ObjectId;
  mQuestionIdMap[mQuestionIdMapCount].QuestionId = (EFI_QUESTION_ID)(CFR_COMPONENT_START + mQuestionIdMapCount);
  mQuestionIdMapCount++;
}

/**
  Offset of the first child record of a CFR form: past its header, its UI
  name and its optional dependency values.

**/
STATIC
UINTN
CfrFormChildrenOffset (
  IN CFR_OPTION_FORM  *Form
  )
{
  UINTN  Offset;

  Offset = sizeof (CFR_OPTION_FORM);
  CfrExtractVarBinary ((UINT8 *)Form, &Offset, CB_TAG_CFR_VARCHAR_UI_NAME);
  CfrExtractVarBinary ((UINT8 *)Form, &Offset, CB_TAG_CFR_DEP_VALUES);

  return Offset;
}

/**
  Assign question IDs to the options of a CFR form and its nested forms.

**/
STATIC
VOID
CfrAssignFormQuestionIds (
  IN CFR_OPTION_FORM  *Form
  )
{
  UINTN            Offset;
  CFR_OPTION_FORM  *Record;

  Offset = CfrFormChildrenOffset (Form);
  while (Offset < Form->size) {
    Record = (CFR_OPTION_FORM *)((UINT8 *)Form + Offset);
    if (Record->size == 0) {
      break;
    }

    switch (Record->tag) {
      case CB_TAG_CFR_OPTION_FORM:
        CfrAssignFormQuestionIds (Record);
        break;
      case CB_TAG_CFR_OPTION_ENUM:
      case CB_TAG_CFR_OPTION_NUMBER:
      case CB_TAG_CFR_OPTION_BOOL:
      case CB_TAG_CFR_OPTION_VARCHAR:
        CfrAssignQuestionId (Record->object_id);
        break;
      default:
        break;
    }

    Offset += Record->size;
  }
}

/**
  CFR_VARBINARY records are used as option name and UI name and help text.
  Convert one to formats used for EDK2 HII.

  Caller is responsible for freeing the UnicodeString pool.

**/
STATIC
VOID
EFIAPI
CfrConvertVarBinaryToStrings (
  IN     CFR_VARBINARY  *CfrString,
  IN OUT CHAR16         **UnicodeString,
  IN OUT EFI_STRING_ID  *HiiStringId      OPTIONAL
  )
{
  EFI_STATUS  Status;

  ASSERT ((CfrString != NULL) && (UnicodeString != NULL));

  *UnicodeString = AllocatePool (CfrString->data_length * sizeof (CHAR16));
  ASSERT (*UnicodeString != NULL);
  Status = AsciiStrToUnicodeStrS (
             (CHAR8 *)CfrString->data,
             *UnicodeString,
             CfrString->data_length
             );
  ASSERT_EFI_ERROR (Status);

  if (HiiStringId != NULL) {
    *HiiStringId = HiiSetString (
                     mSetupMenuPrivate.HiiHandle,
                     0,
                     *UnicodeString,
                     NULL
                     );
    ASSERT (*HiiStringId != 0);
  }
}

/**
  CFR_VARBINARY records are used to store a list of dependency values.
  Get a pointer to an array of enum values and its length.
**/
STATIC
VOID
EFIAPI
CfrConvertVarBinaryToUint32Array (
  IN     CFR_VARBINARY  *CfrList,
  IN OUT UINT32         **Array,
     OUT UINT32         *ArrayLength
  )
{
  ASSERT ((CfrList != NULL) && (Array != NULL) && (ArrayLength != NULL));

  *Array = (UINT32 *)CfrList->data;
  *ArrayLength = CfrList->data_length / sizeof (UINT32);
}

/**
  Produce unconditional HII `*_IF` for CFR flags.

  Caller to close each `*_IF` with `HiiCreateEndOpCode()`.

**/
STATIC
VOID
EFIAPI
CfrProduceHiiForFlags (
  IN VOID   *StartOpCodeHandle,
  IN UINT8  OpCode
  )
{
  EFI_IFR_OP_HEADER  IfOpHeader;
  UINT8              *TempHiiBuffer;
  EFI_IFR_OP_HEADER  ConditionTrue;

  if ((OpCode != EFI_IFR_SUPPRESS_IF_OP) && (OpCode != EFI_IFR_GRAY_OUT_IF_OP)) {
    return;
  }

  IfOpHeader.OpCode = OpCode;
  IfOpHeader.Length = sizeof (EFI_IFR_OP_HEADER);
  // `if` statements are new scopes
  IfOpHeader.Scope = 1;

  TempHiiBuffer = HiiCreateRawOpCodes (
                    StartOpCodeHandle,
                    (UINT8 *)&IfOpHeader,
                    sizeof (EFI_IFR_OP_HEADER)
                    );
  ASSERT (TempHiiBuffer != NULL);

  ConditionTrue.OpCode = EFI_IFR_TRUE_OP;
  ConditionTrue.Length = sizeof (EFI_IFR_OP_HEADER);
  // Same scope as above statement
  ConditionTrue.Scope = 0;

  TempHiiBuffer = HiiCreateRawOpCodes (
                    StartOpCodeHandle,
                    (UINT8 *)&ConditionTrue,
                    sizeof (EFI_IFR_OP_HEADER)
                    );
  ASSERT (TempHiiBuffer != NULL);
}

/**
  Produce conditional HII `SUPPRESS_IF` based on a dependency:

  Caller to close each `SUPPRESS_IF` with `HiiCreateEndOpCode()`.

**/
STATIC
VOID
EFIAPI
CfrProduceHiiForDependency (
  IN VOID    *StartOpCodeHandle,
  IN UINTN   DependencyId,
  IN UINT32  *DepValues,
  IN UINT32  NumDepValues
  )
{
  EFI_IFR_OP_HEADER       OpHeader;
  UINT8                   *TempHiiBuffer;
  UINTN                   EqIdValListSize;
  EFI_IFR_EQ_ID_VAL_LIST  *EqIdValList;
  EFI_IFR_EQ_ID_VAL       EqIdVal;
  UINTN                   Index;

  OpHeader.OpCode = EFI_IFR_SUPPRESS_IF_OP;
  OpHeader.Length = sizeof (EFI_IFR_OP_HEADER);
  OpHeader.Scope = 1;

  TempHiiBuffer = HiiCreateRawOpCodes (
                    StartOpCodeHandle,
                    (UINT8 *)&OpHeader,
                    sizeof (EFI_IFR_OP_HEADER)
                    );
  ASSERT (TempHiiBuffer != NULL);

  if (NumDepValues != 0) {
    EqIdValListSize = sizeof (EFI_IFR_EQ_ID_VAL_LIST) + ((NumDepValues - 1) * sizeof (UINT16));
    EqIdValList = AllocatePool (EqIdValListSize);
    ASSERT (EqIdValList != NULL);

    EqIdValList->Header.OpCode = EFI_IFR_EQ_ID_VAL_LIST_OP;
    EqIdValList->Header.Length = EqIdValListSize;
    EqIdValList->Header.Scope = 1;

    EqIdValList->QuestionId = DependencyId;
    EqIdValList->ListLength = NumDepValues;
    for (Index = 0; Index < NumDepValues; Index++) {
      EqIdValList->ValueList[Index] = (UINT16)*DepValues++;
    }

    TempHiiBuffer = HiiCreateRawOpCodes (
                      StartOpCodeHandle,
                      (UINT8 *)EqIdValList,
                      EqIdValListSize
                      );
    ASSERT (TempHiiBuffer != NULL);

    FreePool (EqIdValList);

    OpHeader.OpCode = EFI_IFR_NOT_OP;
    OpHeader.Length = sizeof (EFI_IFR_OP_HEADER);
    OpHeader.Scope = 0;

    TempHiiBuffer = HiiCreateRawOpCodes (
                      StartOpCodeHandle,
                      (UINT8 *)&OpHeader,
                      sizeof (EFI_IFR_OP_HEADER)
                      );
    ASSERT (TempHiiBuffer != NULL);
  } else {
    EqIdVal.Header.OpCode = EFI_IFR_EQ_ID_VAL_OP;
    EqIdVal.Header.Length = sizeof (EFI_IFR_EQ_ID_VAL);
    EqIdVal.Header.Scope = 1;
    EqIdVal.QuestionId = DependencyId;
    EqIdVal.Value = 0;

    TempHiiBuffer = HiiCreateRawOpCodes (
                      StartOpCodeHandle,
                      (UINT8 *)&EqIdVal,
                      sizeof (EFI_IFR_EQ_ID_VAL)
                      );
    ASSERT (TempHiiBuffer != NULL);
  }

  OpHeader.OpCode = EFI_IFR_END_OP;
  OpHeader.Length = sizeof (EFI_IFR_OP_HEADER);
  OpHeader.Scope = 0;

  TempHiiBuffer = HiiCreateRawOpCodes (
                    StartOpCodeHandle,
                    (UINT8 *)&OpHeader,
                    sizeof (EFI_IFR_OP_HEADER)
                    );
  ASSERT (TempHiiBuffer != NULL);
}

/**
  Produce variable and VARSTORE for CFR option name.

**/
STATIC
VOID
EFIAPI
CfrProduceStorageForOption (
  IN CFR_VARBINARY  *CfrOptionName,
  IN VOID           *CfrOptionDefaultValue,
  IN UINTN          CfrOptionLength,
  IN UINT32         OptionFlags,
  IN VOID           *StartOpCodeHandle,
  IN UINTN          QuestionIdVarStoreId
  )
{
  CHAR16            *VariableCfrName;
  UINT32            VariableAttributes;
  UINTN             DataSize;
  EFI_STATUS        Status;
  UINTN             OptionNameLength;
  UINTN             VarStoreStructSize;
  EFI_IFR_VARSTORE  *VarStore;
  UINT8             *TempHiiBuffer;

  //
  // Initialise defaults for VARSTORE variable
  //
  CfrConvertVarBinaryToStrings (CfrOptionName, &VariableCfrName, NULL);

  //
  // BS always; NV unless VOLATILE; RT only if CFR_OPTFLAG_RUNTIME (OS-visible).
  //
  VariableAttributes = EFI_VARIABLE_BOOTSERVICE_ACCESS;
  if (!(OptionFlags & CFR_OPTFLAG_VOLATILE)) {
    VariableAttributes |= EFI_VARIABLE_NON_VOLATILE;
  }
  if (OptionFlags & CFR_OPTFLAG_RUNTIME) {
    VariableAttributes |= EFI_VARIABLE_RUNTIME_ACCESS;
  }

  DataSize = 0;
  Status = gRT->GetVariable (
                  VariableCfrName,
                  &gEficorebootNvDataGuid,
                  NULL,
                  &DataSize,
                  NULL
                  );
  if (Status == EFI_NOT_FOUND) {
    DataSize = CfrOptionLength;
    Status = gRT->SetVariable (
                    VariableCfrName,
                    &gEficorebootNvDataGuid,
                    VariableAttributes,
                    DataSize,
                    CfrOptionDefaultValue
                    );
    ASSERT_EFI_ERROR (Status);
  }

  //
  // READONLY: lock immediately (setup UI and OS). Takes precedence over
  // LOCK_AT_BOOT.
  // LOCK_AT_BOOT alone: allow setup writes this boot, lock at ReadyToBoot.
  //
  if ((OptionFlags & CFR_OPTFLAG_READONLY) && (mVariablePolicy != NULL)) {
    Status = RegisterBasicVariablePolicy (
               mVariablePolicy,
               &gEficorebootNvDataGuid,
               VariableCfrName,
               VARIABLE_POLICY_NO_MIN_SIZE,
               VARIABLE_POLICY_NO_MAX_SIZE,
               VARIABLE_POLICY_NO_MUST_ATTR,
               VARIABLE_POLICY_NO_CANT_ATTR,
               VARIABLE_POLICY_TYPE_LOCK_NOW
               );
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_WARN, "CFR: Failed to lock variable \"%s\"!\n", VariableCfrName));
    }
  } else if (OptionFlags & CFR_OPTFLAG_LOCK_AT_BOOT) {
    CfrQueueLockAtBoot (VariableCfrName);
  }

  FreePool (VariableCfrName);

  //
  // Build a `varstore` and copy it as raw HII opcodes. Then free this
  //
  /* Struct contains space for terminator only, allocate with name too */
  OptionNameLength = AsciiStrLen ((CHAR8 *)CfrOptionName->data);
  VarStoreStructSize = sizeof (EFI_IFR_VARSTORE) + OptionNameLength;
  ASSERT (VarStoreStructSize <= 0x7F);
  if (VarStoreStructSize > 0x7F) {
    DEBUG ((DEBUG_ERROR, "CFR: Option name length 0x%x is too long!\n", OptionNameLength));
    return;
  }

  VarStore = AllocateZeroPool (VarStoreStructSize);
  ASSERT (VarStore != NULL);
  if (VarStore == NULL) {
    DEBUG ((DEBUG_ERROR, "CFR: Failed to allocate memory for varstore!\n"));
    return;
  }

  VarStore->Header.OpCode = EFI_IFR_VARSTORE_OP;
  VarStore->Header.Length = VarStoreStructSize;

  /* Direct mapping */
  VarStore->VarStoreId = QuestionIdVarStoreId;
  VarStore->Size = CfrOptionLength;

  CopyMem (&VarStore->Guid, &gEficorebootNvDataGuid, sizeof (EFI_GUID));
  CopyMem (VarStore->Name, CfrOptionName->data, CfrOptionName->data_length);

  TempHiiBuffer = HiiCreateRawOpCodes (
                    StartOpCodeHandle,
                    (UINT8 *)VarStore,
                    VarStoreStructSize
                    );
  ASSERT (TempHiiBuffer != NULL);
  FreePool (VarStore);
}

STATIC
VOID
EFIAPI
CfrProcessNumericOption (
  IN     CFR_OPTION_NUMERIC  *Option,
  IN     VOID                *StartOpCodeHandle,
  IN OUT UINTN               *ProcessedLength
  );

STATIC
VOID
EFIAPI
CfrProcessCharacterOption (
  IN     CFR_OPTION_VARCHAR  *Option,
  IN     VOID                *StartOpCodeHandle,
  IN OUT UINTN               *ProcessedLength
  );

STATIC
VOID
EFIAPI
CfrProcessFormOption (
  IN     CFR_OPTION_FORM  *Option,
  IN     VOID             *StartOpCodeHandle,
  IN OUT UINTN            *ProcessedLength
  );

/**
  Create the HII components of the options of a CFR form, from Offset to
  the end of the form. Nested forms are processed with their options.

**/
STATIC
VOID
EFIAPI
CfrProcessFormChildren (
  IN CFR_OPTION_FORM  *Form,
  IN UINTN            Offset,
  IN VOID             *StartOpCodeHandle
  )
{
  CFR_OPTION_FORM  *Record;

  while (Offset < Form->size) {
    Record = (CFR_OPTION_FORM *)((UINT8 *)Form + Offset);
    if (Record->size == 0) {
      DEBUG ((DEBUG_ERROR, "CFR: Offset 0x%x - Empty entry!\n", Offset));
      break;
    }

    switch (Record->tag) {
      case CB_TAG_CFR_OPTION_FORM:
        CfrProcessFormOption (Record, StartOpCodeHandle, &Offset);
        break;
      case CB_TAG_CFR_OPTION_ENUM:
      case CB_TAG_CFR_OPTION_NUMBER:
      case CB_TAG_CFR_OPTION_BOOL:
        CfrProcessNumericOption ((CFR_OPTION_NUMERIC *)Record, StartOpCodeHandle, &Offset);
        break;
      case CB_TAG_CFR_OPTION_VARCHAR:
      case CB_TAG_CFR_OPTION_COMMENT:
        CfrProcessCharacterOption ((CFR_OPTION_VARCHAR *)Record, StartOpCodeHandle, &Offset);
        break;
      default:
        DEBUG ((
          DEBUG_ERROR,
          "CFR: Offset 0x%x - Unexpected entry 0x%x (size 0x%x)!\n",
          Offset,
          Record->tag,
          Record->size
          ));
        Offset += Record->size;
        break;
    }
  }
}

/**
  Open the HII scopes for the dependency and the flags of a CFR form:
  suppressif and grayoutif. Close them with CfrCloseFormScopes().

  @return The number of scopes opened.

**/
STATIC
UINTN
CfrOpenFormScopes (
  IN CFR_OPTION_FORM  *Form,
  IN VOID             *StartOpCodeHandle
  )
{
  UINTN            Offset;
  CFR_VARBINARY    *CfrDepValues;
  UINT32           *DepValues;
  UINT32           NumDepValues;
  EFI_QUESTION_ID  DependencyId;
  UINTN            Scopes;

  Scopes = 0;

  DepValues    = NULL;
  NumDepValues = 0;
  Offset       = sizeof (CFR_OPTION_FORM);
  CfrExtractVarBinary ((UINT8 *)Form, &Offset, CB_TAG_CFR_VARCHAR_UI_NAME);
  CfrDepValues = CfrExtractVarBinary ((UINT8 *)Form, &Offset, CB_TAG_CFR_DEP_VALUES);
  if (CfrDepValues != NULL) {
    CfrConvertVarBinaryToUint32Array (CfrDepValues, &DepValues, &NumDepValues);
  }

  DependencyId = CfrQuestionId (Form->dependency_id);
  if (DependencyId != 0) {
    CfrProduceHiiForDependency (StartOpCodeHandle, DependencyId, DepValues, NumDepValues);
    Scopes++;
  }

  if (Form->flags & CFR_OPTFLAG_SUPPRESS) {
    CfrProduceHiiForFlags (StartOpCodeHandle, EFI_IFR_SUPPRESS_IF_OP);
    Scopes++;
  }

  if (Form->flags & CFR_OPTFLAG_INACTIVE) {
    CfrProduceHiiForFlags (StartOpCodeHandle, EFI_IFR_GRAY_OUT_IF_OP);
    Scopes++;
  }

  return Scopes;
}

/**
  Close the scopes opened by CfrOpenFormScopes().

**/
STATIC
VOID
CfrCloseFormScopes (
  IN VOID   *StartOpCodeHandle,
  IN UINTN  Scopes
  )
{
  UINT8  *TempHiiBuffer;

  while (Scopes-- > 0) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }
}

/**
  Process one nested CFR form: a subtitle with its UI name, then its
  options. The dependency and the flags of the form apply to all of them.

**/
STATIC
VOID
EFIAPI
CfrProcessFormOption (
  IN     CFR_OPTION_FORM  *Option,
  IN     VOID             *StartOpCodeHandle,
  IN OUT UINTN            *ProcessedLength
  )
{
  UINTN           Offset;
  CFR_VARBINARY   *CfrFormName;
  CHAR16          *HiiFormNameString;
  EFI_STRING_ID   HiiFormNameStringId;
  UINT8           *TempHiiBuffer;
  UINTN           Scopes;

  Offset      = sizeof (CFR_OPTION_FORM);
  CfrFormName = CfrExtractVarBinary ((UINT8 *)Option, &Offset, CB_TAG_CFR_VARCHAR_UI_NAME);
  ASSERT (CfrFormName != NULL);
  if (CfrFormName == NULL) {
    *ProcessedLength += Option->size;
    return;
  }

  DEBUG ((
    DEBUG_INFO,
    "CFR: Processing form \"%a\", size 0x%x\n",
    CfrFormName->data,
    Option->size
    ));

  CfrConvertVarBinaryToStrings (CfrFormName, &HiiFormNameString, &HiiFormNameStringId);
  FreePool (HiiFormNameString);

  Scopes = CfrOpenFormScopes (Option, StartOpCodeHandle);

  TempHiiBuffer = HiiCreateSubTitleOpCode (
                    StartOpCodeHandle,
                    HiiFormNameStringId,
                    STRING_TOKEN (STR_EMPTY_STRING),
                    0,
                    0
                    );
  ASSERT (TempHiiBuffer != NULL);

  CfrProcessFormChildren (Option, CfrFormChildrenOffset (Option), StartOpCodeHandle);

  CfrCloseFormScopes (StartOpCodeHandle, Scopes);

  *ProcessedLength += Option->size;
}

/**
  Process one CFR numeric option and create HII component.

**/
STATIC
VOID
EFIAPI
CfrProcessNumericOption (
  IN     CFR_OPTION_NUMERIC  *Option,
  IN     VOID                *StartOpCodeHandle,
  IN OUT UINTN               *ProcessedLength
  )
{
  UINTN           OptionProcessedLength;
  CFR_VARBINARY   *CfrOptionName;
  CFR_VARBINARY   *CfrDisplayName;
  CFR_VARBINARY   *CfrHelpText;
  UINT32          *DepValues;
  UINT32          NumDepValues;
  CFR_VARBINARY   *CfrDepValues;
  UINTN           QuestionIdVarStoreId;
  EFI_QUESTION_ID DependencyId;
  VOID            *BoolDefaultOpCodeHandle;
  UINT8           QuestionFlags;
  VOID            *DefaultOpCodeHandle;
  UINT8           *TempHiiBuffer;
  CHAR16          *HiiDisplayString;
  EFI_STRING_ID   HiiDisplayStringId;
  CHAR16          *HiiHelpText;
  EFI_STRING_ID   HiiHelpTextId;
  VOID            *OptionOpCodeHandle;
  CFR_ENUM_VALUE  *CfrEnumValues;
  CFR_VARBINARY   *CfrEnumUiString;
  CHAR16          *HiiEnumStrings;
  EFI_STRING_ID   HiiEnumStringsId;

  //
  // Extract variable-length fields that follow the header
  //
  OptionProcessedLength = sizeof (CFR_OPTION_NUMERIC);

  CfrOptionName = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_OPT_NAME);
  ASSERT (CfrOptionName != NULL);
  CfrDisplayName = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_UI_NAME);
  ASSERT (CfrDisplayName != NULL);

  // Help text is optional
  CfrHelpText = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_UI_HELPTEXT);
  if (CfrHelpText != NULL) {
    ASSERT (CfrHelpText->tag == CB_TAG_CFR_VARCHAR_UI_HELPTEXT);
  }

  // Dependency values are optional
  DepValues = NULL;
  NumDepValues = 0;
  CfrDepValues = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_DEP_VALUES);
  if (CfrDepValues != NULL) {
    ASSERT (CfrDepValues->tag == CB_TAG_CFR_DEP_VALUES);
    CfrConvertVarBinaryToUint32Array (CfrDepValues, &DepValues, &NumDepValues);
  }

  DEBUG ((
    DEBUG_INFO,
    "CFR: Processing option \"%a\", size 0x%x\n",
    CfrOptionName->data,
    Option->size
    ));

  //
  // Processing start
  //
  QuestionIdVarStoreId = CfrQuestionId (Option->object_id);
  if (QuestionIdVarStoreId == 0) {
    *ProcessedLength += Option->size;
    return;
  }

  CfrProduceStorageForOption (
    CfrOptionName,
    &Option->default_value,
    sizeof (Option->default_value),
    Option->flags,
    StartOpCodeHandle,
    QuestionIdVarStoreId
    );

  QuestionFlags = EFI_IFR_FLAG_RESET_REQUIRED;
  if (Option->flags & CFR_OPTFLAG_READONLY) {
    QuestionFlags |= EFI_IFR_FLAG_READ_ONLY;
  }

  DependencyId = CfrQuestionId (Option->dependency_id);
  if (DependencyId != 0) {
    CfrProduceHiiForDependency (
      StartOpCodeHandle,
      DependencyId,
      DepValues,
      NumDepValues
      );
  }

  if (Option->flags & CFR_OPTFLAG_SUPPRESS) {
    CfrProduceHiiForFlags (StartOpCodeHandle, EFI_IFR_SUPPRESS_IF_OP);
  }
  if (Option->flags & (CFR_OPTFLAG_INACTIVE | CFR_OPTFLAG_READONLY)) {
    CfrProduceHiiForFlags (StartOpCodeHandle, EFI_IFR_GRAY_OUT_IF_OP);
  }

  DefaultOpCodeHandle = HiiAllocateOpCodeHandle ();
  ASSERT (DefaultOpCodeHandle != NULL);

  TempHiiBuffer = HiiCreateDefaultOpCode (
                    DefaultOpCodeHandle,
                    EFI_HII_DEFAULT_CLASS_STANDARD,
                    EFI_IFR_TYPE_NUM_SIZE_32,
                    Option->default_value
                    );
  ASSERT (TempHiiBuffer != NULL);

  CfrConvertVarBinaryToStrings (CfrDisplayName, &HiiDisplayString, &HiiDisplayStringId);
  FreePool (HiiDisplayString);

  if (CfrHelpText != NULL) {
    CfrConvertVarBinaryToStrings (CfrHelpText, &HiiHelpText, &HiiHelpTextId);
    FreePool (HiiHelpText);
  } else {
    HiiHelpTextId = STRING_TOKEN (STR_EMPTY_STRING);
  }

  //
  // Create HII opcodes, processing complete.
  //
  OptionOpCodeHandle = NULL;
  if (Option->tag == CB_TAG_CFR_OPTION_ENUM) {
    OptionOpCodeHandle = HiiAllocateOpCodeHandle ();
    ASSERT (OptionOpCodeHandle != NULL);


    while (OptionProcessedLength < Option->size) {
      CfrEnumValues = (CFR_ENUM_VALUE *)((UINT8 *)Option + OptionProcessedLength);
      ASSERT (CfrEnumValues->tag == CB_TAG_CFR_ENUM_VALUE);

      CfrEnumUiString = (CFR_VARBINARY *)((UINT8 *)CfrEnumValues + sizeof (CFR_ENUM_VALUE));
      ASSERT (CfrEnumUiString->tag == CB_TAG_CFR_VARCHAR_UI_NAME);
      CfrConvertVarBinaryToStrings (CfrEnumUiString, &HiiEnumStrings, &HiiEnumStringsId);
      FreePool (HiiEnumStrings);

      TempHiiBuffer = HiiCreateOneOfOptionOpCode (
                        OptionOpCodeHandle,
                        HiiEnumStringsId,
                        0,
                        EFI_IFR_TYPE_NUM_SIZE_32,
                        CfrEnumValues->value
                        );
      ASSERT (TempHiiBuffer != NULL);

      OptionProcessedLength += CfrEnumValues->size;
    }

    TempHiiBuffer = HiiCreateOneOfOpCode (
                      StartOpCodeHandle,
                      QuestionIdVarStoreId,
                      QuestionIdVarStoreId,
                      0x0,
                      HiiDisplayStringId,
                      HiiHelpTextId,
                      QuestionFlags,
                      EFI_IFR_NUMERIC_SIZE_4,
                      OptionOpCodeHandle,
                      DefaultOpCodeHandle
                      );
    ASSERT (TempHiiBuffer != NULL);
  } else if (Option->tag == CB_TAG_CFR_OPTION_NUMBER) {
    TempHiiBuffer = HiiCreateNumericOpCode (
                      StartOpCodeHandle,
                      QuestionIdVarStoreId,
                      QuestionIdVarStoreId,
                      0x0,
                      HiiDisplayStringId,
                      HiiHelpTextId,
                      QuestionFlags,
                      EFI_IFR_NUMERIC_SIZE_4 |
                        ((Option->display_flags & CFR_NUM_OPT_DISPFLAG_HEX) ?
                        EFI_IFR_DISPLAY_UINT_HEX : EFI_IFR_DISPLAY_UINT_DEC),
                      Option->min,
                      Option->max,
                      Option->step,
                      DefaultOpCodeHandle
                      );
    ASSERT (TempHiiBuffer != NULL);
  } else if (Option->tag == CB_TAG_CFR_OPTION_BOOL) {
    //
    // A checkbox: displays show it as a switch. It uses the first byte of
    // the 32-bit variable, which holds 0 or 1, and keeps the variable size.
    //
    BoolDefaultOpCodeHandle = HiiAllocateOpCodeHandle ();
    ASSERT (BoolDefaultOpCodeHandle != NULL);

    TempHiiBuffer = HiiCreateDefaultOpCode (
                      BoolDefaultOpCodeHandle,
                      EFI_HII_DEFAULT_CLASS_STANDARD,
                      EFI_IFR_TYPE_BOOLEAN,
                      Option->default_value != 0
                      );
    ASSERT (TempHiiBuffer != NULL);

    TempHiiBuffer = HiiCreateCheckBoxOpCode (
                      StartOpCodeHandle,
                      QuestionIdVarStoreId,
                      QuestionIdVarStoreId,
                      0x0,
                      HiiDisplayStringId,
                      HiiHelpTextId,
                      QuestionFlags,
                      (Option->default_value != 0) ? EFI_IFR_CHECKBOX_DEFAULT : 0,
                      BoolDefaultOpCodeHandle
                      );
    ASSERT (TempHiiBuffer != NULL);

    HiiFreeOpCodeHandle (BoolDefaultOpCodeHandle);
  }

  if (Option->flags & (CFR_OPTFLAG_INACTIVE | CFR_OPTFLAG_READONLY)) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }
  if (Option->flags & CFR_OPTFLAG_SUPPRESS) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }

  if (DependencyId != 0) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }

  if (OptionOpCodeHandle != NULL) {
    HiiFreeOpCodeHandle (OptionOpCodeHandle);
  }
  HiiFreeOpCodeHandle (DefaultOpCodeHandle);

  ASSERT (OptionProcessedLength == Option->size);
  *ProcessedLength += Option->size;
}

/**
  Process one CFR character option and create HII component.

**/
STATIC
VOID
EFIAPI
CfrProcessCharacterOption (
  IN     CFR_OPTION_VARCHAR  *Option,
  IN     VOID                *StartOpCodeHandle,
  IN OUT UINTN               *ProcessedLength
  )
{
  UINTN           OptionProcessedLength;
  CFR_VARBINARY   *CfrOptionName;
  CFR_VARBINARY   *CfrDisplayName;
  CFR_VARBINARY   *CfrHelpText;
  CFR_VARBINARY   *CfrDefaultValue;
  UINT32          *DepValues;
  UINT32          NumDepValues;
  CFR_VARBINARY   *CfrDepValues;
  UINTN           QuestionIdVarStoreId;
  EFI_QUESTION_ID DependencyId;
  CHAR16          *HiiDefaultValue;
  EFI_STRING_ID   HiiDefaultValueId;
  UINTN           HiiDefaultValueLengthChars;
  CHAR16          *HiiDisplayString;
  EFI_STRING_ID   HiiDisplayStringId;
  CHAR16          *HiiHelpText;
  EFI_STRING_ID   HiiHelpTextId;
  UINT8           QuestionFlags;
  VOID            *DefaultOpCodeHandle;
  UINT8           *TempHiiBuffer;

  //
  // Extract variable-length fields that follow the header
  //
  ASSERT (sizeof (CFR_OPTION_VARCHAR) == sizeof (CFR_OPTION_COMMENT));
  OptionProcessedLength = sizeof (CFR_OPTION_VARCHAR);

  // Only true string options have variables
  CfrOptionName = NULL;
  if (Option->tag == CB_TAG_CFR_OPTION_VARCHAR) {
    CfrDefaultValue = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_DEF_VALUE);
    ASSERT (CfrDefaultValue != NULL);

    if (CfrDefaultValue->data_length > 0xFF) {
      DEBUG ((DEBUG_ERROR, "CFR: Default value length 0x%x is too long!\n", CfrDefaultValue->data_length));
      *ProcessedLength += Option->size;
      return;
    }

    CfrOptionName = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_OPT_NAME);
    ASSERT (CfrOptionName != NULL);
  }

  CfrDisplayName = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_UI_NAME);
  ASSERT (CfrDisplayName != NULL);

  // Help text is optional
  CfrHelpText = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_VARCHAR_UI_HELPTEXT);
  if (CfrHelpText != NULL) {
    ASSERT (CfrHelpText->tag == CB_TAG_CFR_VARCHAR_UI_HELPTEXT);
  }

  // Dependency values are optional
  DepValues = NULL;
  NumDepValues = 0;
  CfrDepValues = CfrExtractVarBinary ((UINT8 *)Option, &OptionProcessedLength, CB_TAG_CFR_DEP_VALUES);
  if (CfrDepValues != NULL) {
    ASSERT (CfrDepValues->tag == CB_TAG_CFR_DEP_VALUES);
    CfrConvertVarBinaryToUint32Array (CfrDepValues, &DepValues, &NumDepValues);
  }

  DEBUG ((
    DEBUG_INFO,
    "CFR: Processing option \"%a\", size 0x%x\n",
    (CfrOptionName != NULL) ? CfrOptionName->data : CfrDisplayName->data,
    Option->size
    ));

  //
  // Processing start
  //
  if (Option->tag == CB_TAG_CFR_OPTION_VARCHAR) {
    QuestionIdVarStoreId = CfrQuestionId (Option->object_id);
    if (QuestionIdVarStoreId == 0) {
      *ProcessedLength += Option->size;
      return;
    }

    if (CfrDefaultValue->data_length > 1) {
      CfrConvertVarBinaryToStrings (CfrDefaultValue, &HiiDefaultValue, &HiiDefaultValueId);
      HiiDefaultValueLengthChars = CfrDefaultValue->data_length;
    } else {
      HiiDefaultValue = HiiGetString (mSetupMenuPrivate.HiiHandle, STRING_TOKEN (STR_INVALID_STRING), NULL);
      HiiDefaultValueId = STRING_TOKEN (STR_INVALID_STRING);
      HiiDefaultValueLengthChars = StrLen (HiiDefaultValue) + 1;
    }

    CfrProduceStorageForOption (
      CfrOptionName,
      HiiDefaultValue,
      HiiDefaultValueLengthChars * sizeof (CHAR16),
      Option->flags,
      StartOpCodeHandle,
      QuestionIdVarStoreId
      );

    if (HiiDefaultValue != NULL) {
      FreePool (HiiDefaultValue);
    }
  }

  DependencyId = CfrQuestionId (Option->dependency_id);
  if (DependencyId != 0) {
    CfrProduceHiiForDependency (
      StartOpCodeHandle,
      DependencyId,
      DepValues,
      NumDepValues
      );
  }

  if (Option->flags & CFR_OPTFLAG_SUPPRESS) {
    CfrProduceHiiForFlags (StartOpCodeHandle, EFI_IFR_SUPPRESS_IF_OP);
  }
  if (Option->flags & (CFR_OPTFLAG_INACTIVE | CFR_OPTFLAG_READONLY)) {
    CfrProduceHiiForFlags (StartOpCodeHandle, EFI_IFR_GRAY_OUT_IF_OP);
  }

  CfrConvertVarBinaryToStrings (CfrDisplayName, &HiiDisplayString, &HiiDisplayStringId);
  FreePool (HiiDisplayString);

  if (CfrHelpText != NULL) {
    CfrConvertVarBinaryToStrings (CfrHelpText, &HiiHelpText, &HiiHelpTextId);
    FreePool (HiiHelpText);
  } else {
    HiiHelpTextId = STRING_TOKEN (STR_EMPTY_STRING);
  }

  //
  // Create HII opcodes, processing complete.
  //
  if (Option->tag == CB_TAG_CFR_OPTION_VARCHAR) {
    QuestionFlags = EFI_IFR_FLAG_RESET_REQUIRED;
    if (Option->flags & CFR_OPTFLAG_READONLY) {
      QuestionFlags |= EFI_IFR_FLAG_READ_ONLY;
    }

    DefaultOpCodeHandle = HiiAllocateOpCodeHandle ();
    ASSERT (DefaultOpCodeHandle != NULL);

    TempHiiBuffer = HiiCreateDefaultOpCode (
                      DefaultOpCodeHandle,
                      EFI_HII_DEFAULT_CLASS_STANDARD,
                      EFI_IFR_TYPE_NUM_SIZE_16,
                      HiiDefaultValueId
                      );
    ASSERT (TempHiiBuffer != NULL);

    // TODO: User can adjust length of string?
    TempHiiBuffer = HiiCreateStringOpCode (
                      StartOpCodeHandle,
                      QuestionIdVarStoreId,
                      QuestionIdVarStoreId,
                      0x0,
                      HiiDisplayStringId,
                      HiiHelpTextId,
                      QuestionFlags,
                      0,
                      HiiDefaultValueLengthChars - 1,
                      HiiDefaultValueLengthChars - 1,
                      DefaultOpCodeHandle
                      );
    ASSERT (TempHiiBuffer != NULL);

    HiiFreeOpCodeHandle (DefaultOpCodeHandle);
  } else if (Option->tag == CB_TAG_CFR_OPTION_COMMENT) {
    TempHiiBuffer = HiiCreateTextOpCode (
                      StartOpCodeHandle,
                      HiiDisplayStringId,
                      HiiHelpTextId,
                      STRING_TOKEN (STR_EMPTY_STRING)
                      );
    ASSERT (TempHiiBuffer != NULL);
  }

  if (Option->flags & (CFR_OPTFLAG_INACTIVE | CFR_OPTFLAG_READONLY)) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }
  if (Option->flags & CFR_OPTFLAG_SUPPRESS) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }

  if (DependencyId != 0) {
    TempHiiBuffer = HiiCreateEndOpCode (StartOpCodeHandle);
    ASSERT (TempHiiBuffer != NULL);
  }

  ASSERT (OptionProcessedLength == Option->size);
  *ProcessedLength += Option->size;
}

/**
  Allocate an opcode handle that starts with a label.

**/
STATIC
VOID *
CfrAllocateLabeledOpCodeHandle (
  IN UINT16  LabelNumber
  )
{
  VOID                *OpCodeHandle;
  EFI_IFR_GUID_LABEL  *Label;

  OpCodeHandle = HiiAllocateOpCodeHandle ();
  ASSERT (OpCodeHandle != NULL);

  Label = (EFI_IFR_GUID_LABEL *)HiiCreateGuidOpCode (
                                  OpCodeHandle,
                                  &gEfiIfrTianoGuid,
                                  NULL,
                                  sizeof (EFI_IFR_GUID_LABEL)
                                  );
  ASSERT (Label != NULL);

  Label->ExtendOpCode = EFI_IFR_EXTEND_OP_LABEL;
  Label->Number       = LabelNumber;

  return OpCodeHandle;
}

/**
  Return the title of the category that gets a set of links, from its PCD.

  @param[in]  Set  The set of links.

  @return The title; NULL or an empty string for no category.

**/
STATIC
CONST CHAR16 *
CfrPageLinksCategory (
  IN CFR_LINKS_SET  Set
  )
{
  switch (Set) {
    case CfrLinksGeneral:
      return (CONST CHAR16 *)PcdGetPtr (PcdCfrSetupMenuGeneralCategory);
    case CfrLinksSecurity:
      return (CONST CHAR16 *)PcdGetPtr (PcdCfrSetupMenuPasswordCategory);
    default:
      return NULL;
  }
}

/**
  End a category form with the labels of the sets of links it gets, empty
  until EndOfDxe: those whose PCD names it.

  @param[in]  Title         Title of the category.
  @param[in]  OpCodeHandle  Handle of the category form.
  @param[in]  FormId        ID of the category form.

**/
STATIC
VOID
CfrReservePageLinks (
  IN CONST CHAR16  *Title,
  IN VOID          *OpCodeHandle,
  IN EFI_FORM_ID   FormId
  )
{
  CONST CHAR16        *Category;
  EFI_IFR_GUID_LABEL  *Label;
  UINTN               Set;
  UINTN               Index;

  for (Set = 0; Set < CfrLinksMax; Set++) {
    Category = CfrPageLinksCategory ((CFR_LINKS_SET)Set);
    if ((Title == NULL) || (Category == NULL) || (Category[0] == L'\0') ||
        (StrCmp (Title, Category) != 0) || (mPageLinksForm[Set] != 0))
    {
      continue;
    }

    for (Index = 0; Index < 2; Index++) {
      Label = (EFI_IFR_GUID_LABEL *)HiiCreateGuidOpCode (
                                      OpCodeHandle,
                                      &gEfiIfrTianoGuid,
                                      NULL,
                                      sizeof (EFI_IFR_GUID_LABEL)
                                      );
      if (Label == NULL) {
        return;
      }

      Label->ExtendOpCode = EFI_IFR_EXTEND_OP_LABEL;
      Label->Number       = (UINT16)(LABEL_LINKS_START + 2 * Set + Index);
    }

    mPageLinksForm[Set] = FormId;
  }
}

/**
  Mark the links whose page is there: a formset with its GUID is in the HII
  database.

  @param[out]  Installed  For each link of mPageLinks, whether it is there.

**/
STATIC
VOID
CfrFindLinkedPages (
  OUT BOOLEAN  *Installed
  )
{
  EFI_HII_HANDLE     *Handles;
  EFI_IFR_FORM_SET   *FormSets;
  EFI_IFR_OP_HEADER  *OpHeader;
  UINTN              FormSetsSize;
  UINTN              Offset;
  UINTN              Index;
  UINTN              Link;

  ZeroMem (Installed, sizeof (BOOLEAN) * ARRAY_SIZE (mPageLinks));

  Handles = HiiGetHiiHandles (NULL);
  if (Handles == NULL) {
    return;
  }

  for (Index = 0; Handles[Index] != NULL; Index++) {
    if (EFI_ERROR (HiiGetFormSetFromHiiHandle (Handles[Index], &FormSets, &FormSetsSize))) {
      continue;
    }

    //
    // The formset opcodes of the package list, one after the other
    //
    Offset = 0;
    while (Offset + sizeof (EFI_IFR_FORM_SET) <= FormSetsSize) {
      OpHeader = (EFI_IFR_OP_HEADER *)((UINT8 *)FormSets + Offset);
      if (OpHeader->Length < sizeof (EFI_IFR_FORM_SET)) {
        break;
      }

      for (Link = 0; Link < ARRAY_SIZE (mPageLinks); Link++) {
        if (CompareGuid (&((EFI_IFR_FORM_SET *)OpHeader)->Guid, &mPageLinks[Link].FormSetGuid)) {
          Installed[Link] = TRUE;
        }
      }

      Offset += OpHeader->Length;
    }

    FreePool (FormSets);
  }

  FreePool (Handles);
}

/**
  Put in the labels of each set of links the links to the pages that are
  there, in their cards. When the driver of a page is missing, its link is
  left out, and so is a card without links.

  @param[in]  Event    The EndOfDxe event.
  @param[in]  Context  Not used.

**/
STATIC
VOID
EFIAPI
CfrAddPageLinks (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  BOOLEAN        Installed[ARRAY_SIZE (mPageLinks)];
  VOID           *StartOpCodeHandle;
  VOID           *EndOpCodeHandle;
  EFI_STRING_ID  Card;
  UINTN          Set;
  UINTN          Link;
  UINT8          *TempHiiBuffer;
  EFI_STATUS     Status;

  gBS->CloseEvent (Event);
  mPageLinksEvent = NULL;

  CfrFindLinkedPages (Installed);

  for (Set = 0; Set < CfrLinksMax; Set++) {
    if (mPageLinksForm[Set] == 0) {
      continue;
    }

    StartOpCodeHandle = CfrAllocateLabeledOpCodeHandle ((UINT16)(LABEL_LINKS_START + 2 * Set));
    EndOpCodeHandle   = CfrAllocateLabeledOpCodeHandle ((UINT16)(LABEL_LINKS_START + 2 * Set + 1));

    Card = 0;
    for (Link = 0; Link < ARRAY_SIZE (mPageLinks); Link++) {
      if (((UINTN)mPageLinks[Link].Set != Set) || !Installed[Link]) {
        continue;
      }

      if (mPageLinks[Link].Card != Card) {
        Card          = mPageLinks[Link].Card;
        TempHiiBuffer = HiiCreateSubTitleOpCode (StartOpCodeHandle, Card, 0, 0, 0);
        ASSERT (TempHiiBuffer != NULL);
      }

      TempHiiBuffer = HiiCreateGotoExOpCode (
                        StartOpCodeHandle,
                        mPageLinks[Link].FormId,
                        mPageLinks[Link].Prompt,
                        mPageLinks[Link].Help,
                        0,
                        mPageLinks[Link].QuestionId,
                        0,
                        (EFI_GUID *)&mPageLinks[Link].FormSetGuid,
                        0
                        );
      ASSERT (TempHiiBuffer != NULL);
    }

    Status = HiiUpdateForm (
               mSetupMenuPrivate.HiiHandle,
               &mSetupMenuFormsetGuid,
               mPageLinksForm[Set],
               StartOpCodeHandle,
               EndOpCodeHandle
               );
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_WARN, "CFR: No page links in form 0x%x: %r\n", mPageLinksForm[Set], Status));
    }

    HiiFreeOpCodeHandle (StartOpCodeHandle);
    HiiFreeOpCodeHandle (EndOpCodeHandle);
  }
}

/**
  Register the EndOfDxe callback that puts in the links to the pages of
  other drivers, if a category gets some.

**/
EFI_STATUS
EFIAPI
CfrRegisterPageLinksEvent (
  VOID
  )
{
  EFI_STATUS  Status;
  UINTN       Set;

  for (Set = 0; Set < CfrLinksMax; Set++) {
    if (mPageLinksForm[Set] != 0) {
      break;
    }
  }

  if ((Set == CfrLinksMax) || (mPageLinksEvent != NULL)) {
    return EFI_SUCCESS;
  }

  Status = gBS->CreateEventEx (
                  EVT_NOTIFY_SIGNAL,
                  TPL_CALLBACK,
                  CfrAddPageLinks,
                  NULL,
                  &gEfiEndOfDxeEventGroupGuid,
                  &mPageLinksEvent
                  );
  if (EFI_ERROR (Status)) {
    mPageLinksEvent = NULL;
  }

  return Status;
}

/**
  Close the EndOfDxe event of the page links, if it has not run.

**/
VOID
EFIAPI
CfrCleanupPageLinks (
  VOID
  )
{
  if (mPageLinksEvent != NULL) {
    gBS->CloseEvent (mPageLinksEvent);
    mPageLinksEvent = NULL;
  }
}

/**
  Create runtime components by iterating CFR forms.

  Each top-level CFR form, up to SETUP_MENU_CATEGORY_MAX, fills a category
  form of its own, and the main form links to it. A form that is suppressed
  or comes after those stays in the main form, under a subtitle, as before.
  Nested forms become subtitles in the form of their parent. The categories
  named by PcdCfrSetupMenuGeneralCategory and PcdCfrSetupMenuPasswordCategory
  end with the labels of the links to the pages of other drivers, which
  CfrRegisterPageLinksEvent() puts in at EndOfDxe.

**/
VOID
EFIAPI
CfrCreateRuntimeComponents (
  VOID
  )
{
  VOID               *MainOpCodeHandle;
  VOID               *FormOpCodeHandle;
  VOID               *EndOpCodeHandle;
  EFI_HOB_GUID_TYPE  *GuidHob;
  CFR_OPTION_FORM    *CfrFormHob;
  CFR_VARBINARY      *CfrFormName;
  CHAR16             *FormName;
  UINTN              Offset;
  UINTN              Category;
  UINTN              Scopes;
  EFI_STATUS         Status;
  UINT8              *TempHiiBuffer;

  //
  // Question IDs first: dependencies can refer to any option
  //
  GuidHob = GetFirstGuidHob (&gEfiCfrSetupMenuFormGuid);
  while (GuidHob != NULL) {
    CfrAssignFormQuestionIds (GET_GUID_HOB_DATA (GuidHob));
    GuidHob = GetNextGuidHob (&gEfiCfrSetupMenuFormGuid, GET_NEXT_HOB (GuidHob));
  }

  MainOpCodeHandle = CfrAllocateLabeledOpCodeHandle (LABEL_RT_COMP_START);
  EndOpCodeHandle  = CfrAllocateLabeledOpCodeHandle (LABEL_RT_COMP_END);

  Category = 0;
  GuidHob  = GetFirstGuidHob (&gEfiCfrSetupMenuFormGuid);
  while (GuidHob != NULL) {
    CfrFormHob = GET_GUID_HOB_DATA (GuidHob);

    Offset      = sizeof (CFR_OPTION_FORM);
    CfrFormName = CfrExtractVarBinary ((UINT8 *)CfrFormHob, &Offset, CB_TAG_CFR_VARCHAR_UI_NAME);
    ASSERT (CfrFormName != NULL);

    if ((CfrFormName == NULL) || (Category >= SETUP_MENU_CATEGORY_MAX) ||
        (CfrFormHob->flags & CFR_OPTFLAG_SUPPRESS))
    {
      //
      // In the main form, as a subtitle followed by an empty line
      //
      Offset = 0;
      CfrProcessFormOption (CfrFormHob, MainOpCodeHandle, &Offset);

      TempHiiBuffer = HiiCreateSubTitleOpCode (
                        MainOpCodeHandle,
                        STRING_TOKEN (STR_EMPTY_STRING),
                        0,
                        0,
                        0
                        );
      ASSERT (TempHiiBuffer != NULL);
    } else {
      DEBUG ((DEBUG_INFO, "CFR: Category %u: \"%a\"\n", (UINT32)Category, CfrFormName->data));

      //
      // The category form: its title and its options, and the labels of
      // the links to the pages of other drivers if it gets some
      //
      CfrConvertVarBinaryToStrings (CfrFormName, &FormName, NULL);
      HiiSetString (mSetupMenuPrivate.HiiHandle, mCategoryTitle[Category], FormName, NULL);

      FormOpCodeHandle = CfrAllocateLabeledOpCodeHandle (LABEL_RT_COMP_START);
      CfrProcessFormChildren (CfrFormHob, CfrFormChildrenOffset (CfrFormHob), FormOpCodeHandle);
      CfrReservePageLinks (FormName, FormOpCodeHandle, (EFI_FORM_ID)(SETUP_MENU_CATEGORY_FORM_ID + Category));

      FreePool (FormName);
      Status = HiiUpdateForm (
                 mSetupMenuPrivate.HiiHandle,
                 &mSetupMenuFormsetGuid,
                 (EFI_FORM_ID)(SETUP_MENU_CATEGORY_FORM_ID + Category),
                 FormOpCodeHandle,
                 EndOpCodeHandle
                 );
      ASSERT_EFI_ERROR (Status);
      HiiFreeOpCodeHandle (FormOpCodeHandle);

      //
      // The link in the main form, with the dependency and flags of the form
      //
      Scopes        = CfrOpenFormScopes (CfrFormHob, MainOpCodeHandle);
      TempHiiBuffer = HiiCreateGotoOpCode (
                        MainOpCodeHandle,
                        (EFI_FORM_ID)(SETUP_MENU_CATEGORY_FORM_ID + Category),
                        mCategoryTitle[Category],
                        STRING_TOKEN (STR_EMPTY_STRING),
                        0,
                        (EFI_QUESTION_ID)(SETUP_MENU_CATEGORY_FORM_ID + Category)
                        );
      ASSERT (TempHiiBuffer != NULL);
      CfrCloseFormScopes (MainOpCodeHandle, Scopes);

      Category++;
    }

    GuidHob = GetNextGuidHob (&gEfiCfrSetupMenuFormGuid, GET_NEXT_HOB (GuidHob));
  }

  //
  // Submit updates
  //
  Status = HiiUpdateForm (
             mSetupMenuPrivate.HiiHandle,
             &mSetupMenuFormsetGuid,
             SETUP_MENU_FORM_ID,
             MainOpCodeHandle,
             EndOpCodeHandle
             );
  ASSERT_EFI_ERROR (Status);

  HiiFreeOpCodeHandle (MainOpCodeHandle);
  HiiFreeOpCodeHandle (EndOpCodeHandle);
}
