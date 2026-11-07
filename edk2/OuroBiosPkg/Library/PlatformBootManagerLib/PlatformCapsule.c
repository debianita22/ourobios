/** @file
  Update capsules of a boot: in memory, from coreboot, or on disk.

  coreboot lets the SMMSTORE handler write the whole flash for the rest of a
  boot that starts with update capsules: capsules the OS left in memory,
  which the payload gets as HOBs, or capsules on disk (UEFI 2.10, 8.5.5),
  announced by EFI_OS_INDICATIONS_FILE_CAPSULE_DELIVERY_SUPPORTED in
  OsIndications.  The payload has no PEI phase that could load the files of
  a capsule on disk into memory on a later boot, so they are read from
  \EFI\UpdateCapsule of the EFI system partitions and of USB drives, and
  applied in the same boot, before EndOfDxe locks the FMP instances.

  After a capsule is applied the system resets.  Otherwise, before EndOfDxe
  and before any Driver#### option, option ROM or OS can reach the whole
  flash, the access is given up, or the system resets if that fails.  Whether
  the flash is writable is asked to the SMI handler itself rather than
  inferred from the variables: coreboot and the variable driver could read
  OsIndications differently from a store with crafted contents.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include "PlatformBootManager.h"
#include "PlatformConsole.h"
#include <Library/UpdateScreenLib.h>
#include <Guid/CapsuleReport.h>
#include <Guid/FileInfo.h>
#include <Guid/Gpt.h>
#include <Library/SmmStoreLib.h>
#include <Library/VariablePolicyHelperLib.h>
#include <Protocol/VariablePolicy.h>
#include <Protocol/BatteryStatus.h>
#include <Protocol/SimpleFileSystem.h>

#define CAPSULE_ON_DISK_DIR       L"\\EFI\\UpdateCapsule"
#define CAPSULE_ON_DISK_MAX       8           // capsules applied in a boot
#define CAPSULE_ON_DISK_MAX_SIZE  SIZE_64MB   // size of a capsule file
#define CAPSULE_FILE_INFO_SIZE    (SIZE_OF_EFI_FILE_INFO + 256 * sizeof (CHAR16))
#define CAPSULE_MIN_BATTERY       25          // percent, when not charging
#define CAPSULE_POWER_WAIT        60          // seconds to plug the AC adapter
#define CAPSULE_MESSAGE_DELAY     3000000     // microseconds a message stays
#define CAPSULE_RESTART_SECONDS   3           // countdown to the reset after a capsule

/**
  Show a line about the update on the update screen (UpdateScreenLib), and
  in the debug log.

  @param[in] Tone    Its color.
  @param[in] Format  Format string, then its arguments.
**/
STATIC
VOID
EFIAPI
CapsuleMessage (
  IN UPDATE_SCREEN_TONE  Tone,
  IN CONST CHAR16        *Format,
  ...
  )
{
  VA_LIST  Marker;
  CHAR16   Message[128];

  VA_START (Marker, Format);
  UnicodeVSPrint (Message, sizeof (Message), Format, Marker);
  VA_END (Marker);

  DEBUG ((DEBUG_INFO, "Capsules: %s\n", Message));
  UpdateScreenStatus (Tone, L"%s", Message);
}

/**
  Ask the SMMSTORE handler of coreboot whether it serves the whole flash in
  this boot, which it does only in a boot that started with update capsules.
  SmmStoreLib must be initialized.

  @retval TRUE   A read outside of the variable store succeeded.
  @retval FALSE  The handler refused it.
**/
STATIC
BOOLEAN
CapsuleFlashIsWritable (
  VOID
  )
{
  UINT8  Byte;
  UINTN  Size;

  Size = sizeof (Byte);
  return !EFI_ERROR (SmmStoreLibReadAnyBlock (0, 0, &Size, &Byte));
}

/**
  Whether the battery can last through a flash update: absent (the adapter
  powers the computer), charging, or charged enough.  Without battery
  information, assume it can.

  @param[out] Percentage  Charge of the battery, or 0xFF if unknown.
**/
STATIC
BOOLEAN
CapsulePowerIsEnough (
  OUT UINT8  *Percentage
  )
{
  EFI_STATUS                   Status;
  EFI_BATTERY_STATUS_PROTOCOL  *Battery;
  BOOLEAN                      Present;
  BOOLEAN                      Charging;

  *Percentage = 0xFF;
  Status      = gBS->LocateProtocol (&gEfiBatteryStatusProtocolGuid, NULL, (VOID **)&Battery);
  if (EFI_ERROR (Status)) {
    return TRUE;
  }

  Status = Battery->GetBatteryInfo (Battery, Percentage, &Present, &Charging);
  if (EFI_ERROR (Status) || !Present || Charging || (*Percentage > 100)) {
    return TRUE;
  }

  return *Percentage >= CAPSULE_MIN_BATTERY;
}

/**
  Wait up to CAPSULE_POWER_WAIT seconds for enough power to update.

  @retval TRUE   There is enough power.
  @retval FALSE  There is not, the update has to wait for another boot.
**/
STATIC
BOOLEAN
CapsuleWaitForPower (
  VOID
  )
{
  UINT8  Percentage;
  UINTN  Second;

  for (Second = 0; Second < CAPSULE_POWER_WAIT; Second++) {
    if (CapsulePowerIsEnough (&Percentage)) {
      return TRUE;
    }

    CapsuleMessage (
      UpdateScreenToneWarning,
      L"Battery at %d%%: connect the AC adapter to update the firmware (%d)",
      Percentage,
      (UINT32)(CAPSULE_POWER_WAIT - Second)
      );
    gBS->Stall (1000000);
  }

  return CapsulePowerIsEnough (&Percentage);
}

/**
  Read a capsule file into memory and delete it.

  @param[in]  Dir   The directory of the file.
  @param[in]  Name  The name of the file.

  @return The capsule, or NULL if the file is not one.
**/
STATIC
EFI_CAPSULE_HEADER *
CapsuleLoadFile (
  IN EFI_FILE_PROTOCOL  *Dir,
  IN CHAR16             *Name
  )
{
  EFI_STATUS          Status;
  EFI_FILE_PROTOCOL   *File;
  EFI_FILE_INFO       *Info;
  EFI_CAPSULE_HEADER  *Capsule;
  UINTN               Size;
  UINTN               ReadSize;
  BOOLEAN             ReadOnly;

  ReadOnly = FALSE;
  Status   = Dir->Open (Dir, &File, Name, EFI_FILE_MODE_READ | EFI_FILE_MODE_WRITE, 0);
  if (EFI_ERROR (Status)) {
    ReadOnly = TRUE;
    Status   = Dir->Open (Dir, &File, Name, EFI_FILE_MODE_READ, 0);
  }

  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "Capsules: can't open %s: %r\n", Name, Status));
    return NULL;
  }

  Capsule = NULL;
  Info    = AllocatePool (CAPSULE_FILE_INFO_SIZE);
  Size    = CAPSULE_FILE_INFO_SIZE;
  if ((Info != NULL) && !EFI_ERROR (File->GetInfo (File, &gEfiFileInfoGuid, &Size, Info)) &&
      (Info->FileSize >= sizeof (EFI_CAPSULE_HEADER)) && (Info->FileSize <= CAPSULE_ON_DISK_MAX_SIZE))
  {
    Size    = (UINTN)Info->FileSize;
    Capsule = AllocatePool (Size);
    if (Capsule != NULL) {
      ReadSize = Size;
      Status   = File->Read (File, &ReadSize, Capsule);
      if (EFI_ERROR (Status) || (ReadSize != Size) ||
          (Capsule->HeaderSize < sizeof (EFI_CAPSULE_HEADER)) ||
          (Capsule->HeaderSize > Capsule->CapsuleImageSize) ||
          (Capsule->CapsuleImageSize > Size))
      {
        FreePool (Capsule);
        Capsule = NULL;
      }
    }
  }

  if (Info != NULL) {
    FreePool (Info);
  }

  DEBUG ((DEBUG_INFO, "Capsules: %s %a\n", Name, (Capsule != NULL) ? "loaded" : "is not a capsule"));

  //
  // Delete the file either way: a capsule is applied once, the others would
  // only come back in the next update.
  //
  if (ReadOnly) {
    File->Close (File);
    DEBUG ((DEBUG_ERROR, "Capsules: can't delete %s: read-only\n", Name));
  } else {
    Status = File->Delete (File);
    if (Status != EFI_SUCCESS) {
      DEBUG ((DEBUG_ERROR, "Capsules: can't delete %s: %r\n", Name, Status));
    }
  }

  return Capsule;
}

/**
  Load the capsules in \EFI\UpdateCapsule of a file system.

  @param[in]     Root      The root directory of the file system.
  @param[in,out] Capsules  The capsules, Count of them so far.
  @param[in]     Count     The number of capsules in Capsules.
  @param[in]     Max       The capacity of Capsules.

  @return The number of capsules in Capsules.
**/
STATIC
UINTN
CapsuleLoadDirectory (
  IN     EFI_FILE_PROTOCOL   *Root,
  IN OUT EFI_CAPSULE_HEADER  **Capsules,
  IN     UINTN               Count,
  IN     UINTN               Max
  )
{
  EFI_STATUS          Status;
  EFI_FILE_PROTOCOL   *Dir;
  EFI_FILE_INFO       *Info;
  CHAR16              *Names[CAPSULE_ON_DISK_MAX];
  UINTN               NameCount;
  UINTN               Index;
  UINTN               Size;
  EFI_CAPSULE_HEADER  *Capsule;

  Status = Root->Open (Root, &Dir, CAPSULE_ON_DISK_DIR, EFI_FILE_MODE_READ, 0);
  if (EFI_ERROR (Status)) {
    return Count;
  }

  //
  // The names first: the directory is not read while its files are deleted.
  //
  NameCount = 0;
  Info      = AllocatePool (CAPSULE_FILE_INFO_SIZE);
  while ((Info != NULL) && (NameCount < ARRAY_SIZE (Names)) && (NameCount < Max - Count)) {
    Size   = CAPSULE_FILE_INFO_SIZE;
    Status = Dir->Read (Dir, &Size, Info);
    if (EFI_ERROR (Status) || (Size == 0)) {
      break;
    }

    if ((Info->Attribute & EFI_FILE_DIRECTORY) == 0) {
      Names[NameCount] = AllocateCopyPool (StrSize (Info->FileName), Info->FileName);
      if (Names[NameCount] != NULL) {
        NameCount++;
      }
    }
  }

  if (Info != NULL) {
    FreePool (Info);
  }

  for (Index = 0; Index < NameCount; Index++) {
    Capsule = CapsuleLoadFile (Dir, Names[Index]);
    if (Capsule != NULL) {
      Capsules[Count++] = Capsule;
    }

    FreePool (Names[Index]);
  }

  Dir->Close (Dir);
  return Count;
}

/**
  Whether capsules on disk are read from a file system: an EFI system
  partition, or a USB drive, which lets the firmware be updated without an
  OS.  Each capsule is authenticated anyway; this only limits the files
  that are read and deleted.  FirmwareUpdateDxe uses the same rule.

  @param[in] Handle  The handle of the file system.
**/
STATIC
BOOLEAN
CapsuleIsSource (
  IN EFI_HANDLE  Handle
  )
{
  VOID                      *Interface;
  EFI_DEVICE_PATH_PROTOCOL  *Node;

  if (!EFI_ERROR (gBS->HandleProtocol (Handle, &gEfiPartTypeSystemPartGuid, &Interface))) {
    return TRUE;
  }

  for (Node = DevicePathFromHandle (Handle); (Node != NULL) && !IsDevicePathEnd (Node); Node = NextDevicePathNode (Node)) {
    if ((DevicePathType (Node) == MESSAGING_DEVICE_PATH) &&
        ((DevicePathSubType (Node) == MSG_USB_DP) || (DevicePathSubType (Node) == MSG_USB_CLASS_DP) ||
         (DevicePathSubType (Node) == MSG_USB_WWID_DP)))
    {
      return TRUE;
    }
  }

  return FALSE;
}

/**
  Load the capsules on disk, from the EFI system partitions and USB drives.

  @param[out] Capsules  The capsules.
  @param[in]  Max       The capacity of Capsules.

  @return The number of capsules in Capsules.
**/
STATIC
UINTN
CapsuleLoadFromDisk (
  OUT EFI_CAPSULE_HEADER  **Capsules,
  IN  UINTN               Max
  )
{
  EFI_STATUS                       Status;
  EFI_HANDLE                       *Handles;
  UINTN                            HandleCount;
  UINTN                            Index;
  UINTN                            Count;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL  *FileSystem;
  EFI_FILE_PROTOCOL                *Root;

  Count  = 0;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &HandleCount, &Handles);
  if (EFI_ERROR (Status)) {
    return 0;
  }

  for (Index = 0; (Index < HandleCount) && (Count < Max); Index++) {
    if (!CapsuleIsSource (Handles[Index])) {
      continue;
    }

    Status = gBS->HandleProtocol (Handles[Index], &gEfiSimpleFileSystemProtocolGuid, (VOID **)&FileSystem);
    if (EFI_ERROR (Status)) {
      continue;
    }

    Status = FileSystem->OpenVolume (FileSystem, &Root);
    if (EFI_ERROR (Status)) {
      continue;
    }

    Count = CapsuleLoadDirectory (Root, Capsules, Count, Max);
    Root->Close (Root);
  }

  FreePool (Handles);
  return Count;
}

/**
  The result recorded for the last capsule processed (UEFI 2.10, 8.5.6).

  @param[in] Before      The CapsuleLast variable before the capsule, or NULL.
  @param[in] BeforeSize  Its size.

  @return The status of the capsule, EFI_NOT_FOUND without a new record.
**/
STATIC
EFI_STATUS
CapsuleLastStatus (
  IN CONST VOID  *Before OPTIONAL,
  IN UINTN       BeforeSize
  )
{
  CHAR16                              *Last;
  CHAR16                              Name[sizeof ("Capsule####")];
  UINTN                               Size;
  EFI_CAPSULE_RESULT_VARIABLE_HEADER  *Result;
  EFI_STATUS                          Status;

  if (EFI_ERROR (GetVariable2 (L"CapsuleLast", &gEfiCapsuleReportGuid, (VOID **)&Last, &Size))) {
    return EFI_NOT_FOUND;
  }

  Status = EFI_NOT_FOUND;
  if ((Before == NULL) || (Size != BeforeSize) || (CompareMem (Last, Before, Size) != 0)) {
    ZeroMem (Name, sizeof (Name));
    CopyMem (Name, Last, MIN (Size, sizeof (Name) - sizeof (CHAR16)));
    if (!EFI_ERROR (GetVariable2 (Name, &gEfiCapsuleReportGuid, (VOID **)&Result, &Size))) {
      if (Size >= sizeof (EFI_CAPSULE_RESULT_VARIABLE_HEADER)) {
        Status = Result->CapsuleStatus;
      }

      FreePool (Result);
    }
  }

  FreePool (Last);
  return Status;
}

/**
  Apply capsules loaded from disk.

  @param[in] Capsules  The capsules.
  @param[in] Count     How many.

  @return EFI_SUCCESS, or the error of the last capsule that failed.
**/
STATIC
EFI_STATUS
CapsuleApply (
  IN EFI_CAPSULE_HEADER  **Capsules,
  IN UINTN               Count
  )
{
  UINTN       Index;
  VOID        *Before;
  UINTN       BeforeSize;
  EFI_STATUS  Status;
  EFI_STATUS  Failure;

  Failure = EFI_SUCCESS;
  for (Index = 0; Index < Count; Index++) {
    CapsuleMessage (UpdateScreenToneNormal, L"Checking the signature of the update");
    if (EFI_ERROR (GetVariable2 (L"CapsuleLast", &gEfiCapsuleReportGuid, &Before, &BeforeSize))) {
      Before     = NULL;
      BeforeSize = 0;
    }

    Status = ProcessCapsuleImage (Capsules[Index]);
    if (!EFI_ERROR (Status)) {
      Status = CapsuleLastStatus (Before, BeforeSize);
    }

    DEBUG ((DEBUG_INFO, "Capsules: capsule %u of %u: %r\n", (UINT32)(Index + 1), (UINT32)Count, Status));
    if (EFI_ERROR (Status)) {
      Failure = Status;
    }

    if (Before != NULL) {
      FreePool (Before);
    }

    FreePool (Capsules[Index]);
  }

  if (EFI_ERROR (Failure)) {
    CapsuleMessage (UpdateScreenToneError, L"The update failed (%r)", Failure);
  } else {
    CapsuleMessage (UpdateScreenToneSuccess, L"Firmware updated");
  }

  return Failure;
}

STATIC BOOLEAN  mFirmwareSlotsLocked;
STATIC BOOLEAN  mOptionLockReported;

/**
  Before EndOfDxe, which closes Variable Policy to new rules: OptionLockStatus
  becomes read-only as soon as it exists (lock on create), so only the first
  write, PlatformReportOptionLock() at ReadyToBoot, goes in.
**/
VOID
PlatformRegisterOptionLockPolicy (
  VOID
  )
{
  EFI_STATUS                      Status;
  EDKII_VARIABLE_POLICY_PROTOCOL  *VariablePolicy;

  Status = gBS->LocateProtocol (&gEdkiiVariablePolicyProtocolGuid, NULL, (VOID **)&VariablePolicy);
  if (!EFI_ERROR (Status)) {
    Status = RegisterBasicVariablePolicy (
               VariablePolicy,
               &gEficorebootNvDataGuid,
               L"OptionLockStatus",
               VARIABLE_POLICY_NO_MIN_SIZE,
               VARIABLE_POLICY_NO_MAX_SIZE,
               VARIABLE_POLICY_NO_MUST_ATTR,
               EFI_VARIABLE_NON_VOLATILE,
               VARIABLE_POLICY_TYPE_LOCK_ON_CREATE
               );
  }

  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "Capsules: no Variable Policy for OptionLockStatus: %r\n", Status));
  }
}

/**
  Tell the OS what coreboot answered to the arm of the option lock: the
  EFI_STATUS of SmmStoreLibOptionLock() (EFI_SUCCESS armed, EFI_UNSUPPORTED
  with no option lock or BIOS Lock off) as a UINT64 in the volatile variable
  OptionLockStatus of the coreboot options GUID, readable from efivarfs
  (tools/hw-report.py, FLASH-06). PlatformRegisterOptionLockPolicy() made it
  lock-on-create before EndOfDxe, so once written here the OS can read it but
  not change it, nor create it first. It is the
  payload's report of the answer of SMM, not a reading of the state there:
  coreboot's SMM console is compiled out in the release builds (DEBUG_SMI).
**/
STATIC
VOID
PlatformReportOptionLock (
  IN EFI_STATUS  LockStatus
  )
{
  EFI_STATUS  Status;
  UINT64      Value;

  if (mOptionLockReported) {
    return;
  }

  mOptionLockReported = TRUE;
  Value               = (UINT64)LockStatus;
  Status              = gRT->SetVariable (
                               L"OptionLockStatus",
                               &gEficorebootNvDataGuid,
                               EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS,
                               sizeof (Value),
                               &Value
                               );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "Capsules: OptionLockStatus not written: %r\n", Status));
    return;
  }
}

/**
  A boot option or an OS is about to start: from now on, only an update
  capsule, with its checks, may change the RW slot that vboot boots.
  Allocates nothing.
**/
STATIC
VOID
EFIAPI
PlatformLockFirmwareSlots (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  EFI_STATUS  Status;

  if (mFirmwareSlotsLocked) {
    return;
  }

  Status               = SmmStoreLibVbootLockSlots ();
  mFirmwareSlotsLocked = !EFI_ERROR (Status);
  DEBUG ((DEBUG_INFO, "Capsules: switch to the other firmware slot locked: %r\n", Status));

  //
  // The setup could have changed the security options (bios_lock,
  // bootmedia_lock) in this boot; from here, before a boot option or an OS
  // runs, coreboot keeps the OS from turning them off.
  //
  Status = SmmStoreLibOptionLock ();
  DEBUG ((DEBUG_INFO, "Capsules: security options write-locked: %r\n", Status));
  PlatformReportOptionLock (Status);
}

/**
  Tell coreboot that the firmware booted: with vboot, a new RW slot that it is
  trying (after an update) is then kept, instead of being given up for the
  other one when its tries run out.  Called once the console is up.

  With two RW slots, the setup can also switch to the other slot (the
  Firmware Update page); coreboot refuses that once a boot option starts
  (ReadyToBoot, which booting the setup does not signal) or anything calls
  ExitBootServices().
**/
VOID
PlatformMarkFirmwareGood (
  VOID
  )
{
  EFI_STATUS  Status;
  EFI_EVENT   Event;

  if (EFI_ERROR (SmmStoreLibInitialize ())) {
    return;
  }

  Status = SmmStoreLibVbootSlotGood ();
  if (Status != EFI_UNSUPPORTED) {
    DEBUG ((DEBUG_INFO, "Capsules: firmware slot marked good: %r\n", Status));
  }

  if (Status == EFI_UNSUPPORTED) {
    SmmStoreLibDeinitialize ();
    return;
  }

  //
  // The library stays initialized for the lock: at ExitBootServices() it
  // cannot allocate.  Without both events, lock now: the setup then cannot
  // switch slots in this boot.
  //
  if (EFI_ERROR (EfiCreateEventReadyToBootEx (TPL_CALLBACK, PlatformLockFirmwareSlots, NULL, &Event)) ||
      EFI_ERROR (
        gBS->CreateEventEx (
               EVT_NOTIFY_SIGNAL,
               TPL_CALLBACK,
               PlatformLockFirmwareSlots,
               NULL,
               &gEfiEventExitBootServicesGuid,
               &Event
               )
        ))
  {
    DEBUG ((DEBUG_ERROR, "Capsules: no event for the lock of the firmware slots\n"));
    PlatformLockFirmwareSlots (NULL, NULL);
  }
}

/**
  Apply the update capsules of this boot, if it has any, and reset after
  applying one.  Otherwise make sure that the whole flash is no longer
  writable, or reset.  To be called before EndOfDxe.

  @retval TRUE   The console is initialized.
  @retval FALSE  It is not.
**/
BOOLEAN
PlatformProcessCapsules (
  VOID
  )
{
  EFI_STATUS          Status;
  BOOLEAN             InMemory;
  BOOLEAN             OnDisk;
  BOOLEAN             Writable;
  BOOLEAN             Applied;
  BOOLEAN             Console;
  EFI_STATUS          Result;
  EFI_CAPSULE_HEADER  *Capsules[CAPSULE_ON_DISK_MAX];
  UINTN               Count;

  InMemory = (GetBootModeHob () == BOOT_ON_FLASH_UPDATE);
  OnDisk   = PcdGetBool (PcdCapsuleOnDiskSupport) && CoDCheckCapsuleOnDiskFlag ();
  Writable = !EFI_ERROR (SmmStoreLibInitialize ()) && CapsuleFlashIsWritable ();
  Applied  = FALSE;
  Console  = FALSE;
  Result   = EFI_SUCCESS;

  if (OnDisk) {
    //
    // Cleared first: whatever happens next, the next boot is a normal one.
    //
    CoDClearCapsuleOnDiskFlag ();
  }

  if ((InMemory || OnDisk) && !Writable) {
    //
    // coreboot read the request differently, or didn't see it: say so, the
    // user is waiting for an update that doesn't happen.
    //
    PlatformConsoleInit ();
    BootSplashApply ();
    Console = TRUE;
    CapsuleMessage (UpdateScreenToneError, L"Firmware update requested, but the flash is not writable in this boot");
    gBS->Stall (CAPSULE_MESSAGE_DELAY);
  } else if (InMemory || OnDisk) {
    PlatformConsoleInit ();
    BootSplashApply ();
    Console = TRUE;

    if (!CapsuleWaitForPower ()) {
      CapsuleMessage (UpdateScreenToneWarning, L"Battery too low, firmware update postponed");
      gBS->Stall (CAPSULE_MESSAGE_DELAY);
    } else {
      //
      // This slot booted as far as the console: if vboot is trying it,
      // keep it now, before an update asks vboot to try the other slot.
      // The reset after the updates comes before PlatformMarkFirmwareGood ():
      // without this, an update that fails, or that is refused before it
      // writes anything, uses up a try of a slot that works.
      //
      Status = SmmStoreLibVbootSlotGood ();
      if (Status != EFI_UNSUPPORTED) {
        DEBUG ((DEBUG_INFO, "Capsules: firmware slot marked good before the updates: %r\n", Status));
      }

      if (InMemory) {
        Applied = TRUE;
        Status  = ProcessCapsules ();
        if (EFI_ERROR (Status)) {
          DEBUG ((DEBUG_ERROR, "%a(): ProcessCapsules() failed with: %r\n", __func__, Status));
          Result = Status;
        }
      }

      if (OnDisk) {
        CapsuleMessage (UpdateScreenToneNormal, L"Looking for the update on the disks");
        EfiBootManagerConnectAll ();
        Count = CapsuleLoadFromDisk (Capsules, ARRAY_SIZE (Capsules));
        if (Count == 0) {
          CapsuleMessage (UpdateScreenToneWarning, L"No firmware update found in %s of the EFI partitions and USB drives", CAPSULE_ON_DISK_DIR);
          gBS->Stall (CAPSULE_MESSAGE_DELAY);
        } else {
          Applied = TRUE;
          Status  = CapsuleApply (Capsules, Count);
          if (EFI_ERROR (Status)) {
            Result = Status;
          }
        }
      }
    }
  }

  if (Applied) {
    //
    // The flash may have changed: start again from it.
    //
    UpdateScreenRestart (EFI_ERROR (Result) ? UpdateScreenToneError : UpdateScreenToneSuccess, CAPSULE_RESTART_SECONDS);
    gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
    CpuDeadLoop ();
  }

  if (Writable) {
    //
    // Nothing written: give up the whole flash and boot on, or reset if it
    // can't be given up.
    //
    Status = SmmStoreLibEndAnyBlockAccess ();
    if (EFI_ERROR (Status) || CapsuleFlashIsWritable ()) {
      DEBUG ((DEBUG_ERROR, "Capsules: can't end the whole flash access (%r), resetting\n", Status));
      gRT->ResetSystem (EfiResetCold, EFI_SUCCESS, 0, NULL);
      CpuDeadLoop ();
    }

    DEBUG ((DEBUG_INFO, "Capsules: the whole flash is no longer writable\n"));
  }

  SmmStoreLibDeinitialize ();
  return Console;
}
