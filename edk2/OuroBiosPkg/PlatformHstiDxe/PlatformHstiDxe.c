/** @file
  The Hardware Security Testability Interface (HSTI) of the platform.

  When a boot is started, after the platform has armed its locks, read the
  protections from the hardware and publish the result: as the HSTI table of
  the Adapter Information protocol, which Windows reads for its device
  security report, and as the volatile variable HstiTable of the same GUID,
  which the OS can read from efivarfs but not write (Variable Policy, lock on
  create). Only reads: no register is written but the microcode signature
  MSR, as the SDM asks before reading it.

  Every test the firmware cannot pass is reported as such, with its line in
  the error string: what these machines do not have (a descriptor that the
  host cannot write, pre-boot DMA protection) next to what they do.

  Copyright (c) 2026, Domenico D'Arrigo. All rights reserved.<BR>
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <PiDxe.h>
#include <IndustryStandard/Hsti.h>
#include <IndustryStandard/Pci.h>
#include <IndustryStandard/MemoryOverwriteRequestControlLock.h>
#include <Guid/GlobalVariable.h>
#include <Protocol/Tcg2Protocol.h>
#include <Protocol/TcgService.h>
#include <Protocol/VariablePolicy.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/HstiLib.h>
#include <Library/IoLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PciLib.h>
#include <Library/PrintLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/VariablePolicyHelperLib.h>

#define HSTI_VARIABLE_NAME  L"HstiTable"
#define HSTI_FEATURES_SIZE  2
#define HSTI_ERROR_CHARS    4096
#define HSTI_DOC            L"https://github.com/debianita22/ourobios/blob/main/docs/hsti.md"

//
// The SPI controller: Cannon Point's fast SPI at 00:1f.5 (BAR0), or Lynx
// Point's in the RCBA of the LPC at 00:1f.0 (soc/intel/common/block/fast_spi
// and southbridge/intel/common/spi.c of coreboot, tools/update.py).
//
#define SPI_BIOS_CONTROL  0xDC
#define BC_WPD            BIT0              // BIOSWE on Lynx Point
#define BC_BLE            BIT1
#define BC_EISS           BIT5              // SMM_BWP on Lynx Point
#define SPI_HSFS          0x04
#define HSFS_FLOCKDN      BIT15
#define SPI_FRAP          0x50
#define FRAP_BRWA_DESC    BIT8              // BIOS master write access, region 0
#define FRAP_BRWA_ME      BIT10             // region 2
#define SPI_FREG0         0x54              // the regions: base and limit in 4 KiB
#define REGION_DESCRIPTOR 0
#define REGION_ME         2
#define FAST_SPI_PR0      0x84
#define LPT_SPI_PR0       0x74
#define SPI_PR_COUNT      5
#define PR_WPE            BIT31
#define LPC_RCBA          0xF0
#define RCBA_EN           BIT0
#define RCBA_MASK         0xFFFFC000
#define LPT_SPIBAR        0x3800

//
// The host bridge's TSEG base, with its lock in bit 0 (Haswell and Coffee Lake).
//
#define HOST_TSEGMB       0xB8
#define TSEGMB_LOCK       BIT0

#define MSR_BIOS_SIGN_ID          0x8B
#define MSR_DEBUG_INTERFACE       0xC80
#define DEBUG_INTERFACE_ENABLE    BIT0
#define DEBUG_INTERFACE_LOCK      BIT30
#define CPUID1_ECX_SDBG           BIT11

typedef enum {
  HstiFlashConfigLocked,
  HstiBiosWriteProtected,
  HstiFlashRangeProtected,
  HstiDescriptorProtected,
  HstiMeRegionProtected,
  HstiSmramLocked,
  HstiDebugLocked,
  HstiMicrocodeLoaded,
  HstiSecureBoot,
  HstiTpm,
  HstiOptionLock,
  HstiMorLock,
  HstiPreBootDma,
  HstiFeatureCount
} HSTI_FEATURE;

typedef struct {
  CONST CHAR16    *Category;
  CONST CHAR16    *Failure;
} HSTI_TEST;

STATIC CONST HSTI_TEST  mTests[HstiFeatureCount] = {
  { L"Flash",          L"the flash configuration is not locked (FLOCKDN)"                                         },
  { L"Flash",          L"the BIOS region can be written outside SMM (BIOS_CNTL: BLE, SMM_BWP or WPD)"             },
  { L"Flash",          L"no locked Protected Range write-protects the flash"                                      },
  { L"Flash",          L"the host can write the flash descriptor (FRAP, and no locked Protected Range over it)"     },
  { L"Flash",          L"the host can write the ME region (FRAP, and no locked Protected Range over it)"            },
  { L"SMM",            L"the TSEG base is not locked"                                                             },
  { L"Debug",          L"the debug interface is enabled or not locked (IA32_DEBUG_INTERFACE)"                     },
  { L"CPU",            L"no microcode update is loaded"                                                           },
  { L"Secure Boot",    L"Secure Boot is off"                                                                      },
  { L"TPM",            L"no TPM, no measured boot"                                                                },
  { L"Setup options",  L"the write-lock of the setup options is not armed"                                        },
  { L"MOR",            L"the OS cannot lock the memory overwrite request (MemoryOverwriteRequestControlLock)"     },
  { L"DMA",            L"no pre-boot DMA protection"                                                              },
};

STATIC UINT8      mRequired[HSTI_FEATURES_SIZE];
STATIC UINT8      mImplemented[HSTI_FEATURES_SIZE];
STATIC UINT8      mVerified[HSTI_FEATURES_SIZE];
STATIC CHAR16     *mErrors;
STATIC UINTN      mErrorsLength;
STATIC EFI_EVENT  mPublishEvent;
STATIC BOOLEAN    mPublished;

/**
  Record the result of one test. A test that does not apply to the platform
  (Implemented FALSE and not required) gives no error line.
**/
STATIC
VOID
HstiReport (
  IN HSTI_FEATURE  Feature,
  IN BOOLEAN       Required,
  IN BOOLEAN       Implemented,
  IN BOOLEAN       Verified
  )
{
  UINTN  Byte;
  UINT8  Bit;

  Byte = (UINTN)Feature / 8;
  Bit  = (UINT8)(1 << ((UINTN)Feature % 8));
  if (Required) {
    mRequired[Byte] |= Bit;
  }

  if (Implemented) {
    mImplemented[Byte] |= Bit;
  }

  if (Implemented && Verified) {
    mVerified[Byte] |= Bit;
    return;
  }

  if (!Required) {
    return;
  }

  mErrorsLength += UnicodeSPrint (
                     mErrors + mErrorsLength,
                     (HSTI_ERROR_CHARS - mErrorsLength) * sizeof (CHAR16),
                     L"0x%08x %s: %s %s\r\n",
                     0x00010000 | (UINT32)Feature,
                     mTests[Feature].Category,
                     mTests[Feature].Failure,
                     HSTI_DOC
                     );
}

/**
  The SPI controller's registers: its BIOS_CNTL and the base of the others.

  @retval FALSE  neither Cannon Point's fast SPI nor Lynx Point's RCBA.
**/
STATIC
BOOLEAN
HstiSpiController (
  OUT UINT8   *BiosControl,
  OUT UINTN   *SpiBar,
  OUT UINTN   *Pr0
  )
{
  UINTN   FastSpi;
  UINTN   Lpc;
  UINT32  Bar;

  FastSpi = PCI_LIB_ADDRESS (0, 0x1f, 5, 0);
  if ((PciRead16 (FastSpi + PCI_VENDOR_ID_OFFSET) == 0x8086) &&
      (PciRead8 (FastSpi + PCI_CLASSCODE_OFFSET + 2) == PCI_CLASS_SERIAL) &&
      (PciRead8 (FastSpi + PCI_CLASSCODE_OFFSET + 1) == 0x80) &&
      ((PciRead16 (FastSpi + PCI_COMMAND_OFFSET) & EFI_PCI_COMMAND_MEMORY_SPACE) != 0))
  {
    Bar = PciRead32 (FastSpi + PCI_BASE_ADDRESSREG_OFFSET) & ~(UINT32)0xF;
    if (Bar != 0) {
      *BiosControl = PciRead8 (FastSpi + SPI_BIOS_CONTROL);
      *SpiBar      = Bar;
      *Pr0         = FAST_SPI_PR0;
      return TRUE;
    }
  }

  Lpc = PCI_LIB_ADDRESS (0, 0x1f, 0, 0);
  if ((PciRead16 (Lpc + PCI_VENDOR_ID_OFFSET) == 0x8086) &&
      (PciRead8 (Lpc + PCI_CLASSCODE_OFFSET + 2) == PCI_CLASS_BRIDGE) &&
      (PciRead8 (Lpc + PCI_CLASSCODE_OFFSET + 1) == PCI_CLASS_BRIDGE_ISA))
  {
    Bar = PciRead32 (Lpc + LPC_RCBA);
    if ((Bar & RCBA_EN) != 0) {
      *BiosControl = PciRead8 (Lpc + SPI_BIOS_CONTROL);
      *SpiBar      = (Bar & RCBA_MASK) + LPT_SPIBAR;
      *Pr0         = LPT_SPI_PR0;
      return TRUE;
    }
  }

  return FALSE;
}

/**
  Whether the host cannot write a region of the flash: FRAP gives the BIOS
  master no write access to it, or a Protected Range with write protection,
  locked by FLOCKDN until the next reset, covers all of it (the payload's
  Firmware protection over the descriptor and the ME with the regions
  unlocked). A region that is not used has nothing to protect.
**/
STATIC
BOOLEAN
HstiRegionProtected (
  IN UINTN   SpiBar,
  IN UINTN   Pr0,
  IN UINT32  Hsfs,
  IN UINT32  Frap,
  IN UINTN   Region,
  IN UINT32  FrapWrite
  )
{
  UINT32  Freg;
  UINT32  Pr;
  UINT32  Base;
  UINT32  Limit;
  UINTN   Index;

  if ((Frap & FrapWrite) == 0) {
    return TRUE;
  }

  Freg  = MmioRead32 (SpiBar + SPI_FREG0 + Region * 4);
  Base  = (Freg & 0x7FFF) << 12;
  Limit = (((Freg >> 16) & 0x7FFF) << 12) | 0xFFF;
  if (Base > Limit) {
    return TRUE;
  }

  if ((Hsfs & HSFS_FLOCKDN) == 0) {
    return FALSE;
  }

  for (Index = 0; Index < SPI_PR_COUNT; Index++) {
    Pr = MmioRead32 (SpiBar + Pr0 + Index * 4);
    if (((Pr & PR_WPE) != 0) && (((Pr & 0x7FFF) << 12) <= Base) &&
        (((((Pr >> 16) & 0x7FFF) << 12) | 0xFFF) >= Limit))
    {
      return TRUE;
    }
  }

  return FALSE;
}

STATIC
VOID
HstiTestFlash (
  VOID
  )
{
  UINT8    BiosControl;
  UINTN    SpiBar;
  UINTN    Pr0;
  UINT32   Hsfs;
  UINT32   Frap;
  UINTN    Index;
  BOOLEAN  Found;
  BOOLEAN  Range;

  Found = HstiSpiController (&BiosControl, &SpiBar, &Pr0);
  if (!Found) {
    DEBUG ((DEBUG_WARN, "HSTI: no known SPI controller, the flash is not tested\n"));
    HstiReport (HstiFlashConfigLocked, TRUE, FALSE, FALSE);
    HstiReport (HstiBiosWriteProtected, TRUE, FALSE, FALSE);
    HstiReport (HstiFlashRangeProtected, TRUE, FALSE, FALSE);
    HstiReport (HstiDescriptorProtected, TRUE, FALSE, FALSE);
    HstiReport (HstiMeRegionProtected, TRUE, FALSE, FALSE);
    return;
  }

  Hsfs  = MmioRead32 (SpiBar + SPI_HSFS);
  Frap  = MmioRead32 (SpiBar + SPI_FRAP);
  Range = FALSE;
  for (Index = 0; Index < SPI_PR_COUNT; Index++) {
    if ((MmioRead32 (SpiBar + Pr0 + Index * 4) & PR_WPE) != 0) {
      Range = TRUE;
    }
  }

  DEBUG ((DEBUG_INFO, "HSTI: BIOS_CNTL 0x%02x, HSFS 0x%08x, FRAP 0x%08x\n", BiosControl, Hsfs, Frap));
  HstiReport (HstiFlashConfigLocked, TRUE, TRUE, (Hsfs & HSFS_FLOCKDN) != 0);
  HstiReport (
    HstiBiosWriteProtected,
    TRUE,
    TRUE,
    ((BiosControl & (BC_BLE | BC_EISS)) == (BC_BLE | BC_EISS)) && ((BiosControl & BC_WPD) == 0)
    );
  HstiReport (HstiFlashRangeProtected, TRUE, TRUE, Range && ((Hsfs & HSFS_FLOCKDN) != 0));
  HstiReport (
    HstiDescriptorProtected,
    TRUE,
    TRUE,
    HstiRegionProtected (SpiBar, Pr0, Hsfs, Frap, REGION_DESCRIPTOR, FRAP_BRWA_DESC)
    );
  HstiReport (
    HstiMeRegionProtected,
    TRUE,
    TRUE,
    HstiRegionProtected (SpiBar, Pr0, Hsfs, Frap, REGION_ME, FRAP_BRWA_ME)
    );
}

STATIC
VOID
HstiTestCpu (
  VOID
  )
{
  UINTN   HostBridge;
  UINT32  Ecx;
  UINT64  Debug;
  UINT64  Microcode;

  HostBridge = PCI_LIB_ADDRESS (0, 0, 0, 0);
  if (PciRead16 (HostBridge + PCI_VENDOR_ID_OFFSET) == 0x8086) {
    HstiReport (HstiSmramLocked, TRUE, TRUE, (PciRead32 (HostBridge + HOST_TSEGMB) & TSEGMB_LOCK) != 0);
  } else {
    HstiReport (HstiSmramLocked, TRUE, FALSE, FALSE);
  }

  //
  // IA32_DEBUG_INTERFACE only with CPUID.1:ECX.SDBG; without it there is no
  // debug interface for the firmware to lock.
  //
  AsmCpuid (1, NULL, NULL, &Ecx, NULL);
  if ((Ecx & CPUID1_ECX_SDBG) != 0) {
    Debug = AsmReadMsr64 (MSR_DEBUG_INTERFACE);
    HstiReport (
      HstiDebugLocked,
      TRUE,
      TRUE,
      ((Debug & DEBUG_INTERFACE_ENABLE) == 0) && ((Debug & DEBUG_INTERFACE_LOCK) != 0)
      );
  } else {
    HstiReport (HstiDebugLocked, FALSE, FALSE, FALSE);
  }

  AsmWriteMsr64 (MSR_BIOS_SIGN_ID, 0);
  AsmCpuid (1, NULL, NULL, NULL, NULL);
  Microcode = RShiftU64 (AsmReadMsr64 (MSR_BIOS_SIGN_ID), 32);
  HstiReport (HstiMicrocodeLoaded, TRUE, TRUE, Microcode != 0);
}

STATIC
VOID
HstiTestBoot (
  VOID
  )
{
  UINT8       SecureBoot;
  UINT8       SetupMode;
  UINT8       MorLock;
  UINT64      OptionLock;
  UINTN       Size;
  VOID        *Tpm;
  BOOLEAN     Have;
  EFI_STATUS  Status;

  Size   = sizeof (SecureBoot);
  Status = gRT->GetVariable (EFI_SECURE_BOOT_MODE_NAME, &gEfiGlobalVariableGuid, NULL, &Size, &SecureBoot);
  Have   = !EFI_ERROR (Status) && (SecureBoot == 1);
  Size   = sizeof (SetupMode);
  Status = gRT->GetVariable (EFI_SETUP_MODE_NAME, &gEfiGlobalVariableGuid, NULL, &Size, &SetupMode);
  Have   = Have && !EFI_ERROR (Status) && (SetupMode == 0);
  HstiReport (HstiSecureBoot, TRUE, TRUE, Have);

  Have = !EFI_ERROR (gBS->LocateProtocol (&gEfiTcg2ProtocolGuid, NULL, &Tpm)) ||
         !EFI_ERROR (gBS->LocateProtocol (&gEfiTcgProtocolGuid, NULL, &Tpm));
  HstiReport (HstiTpm, TRUE, Have, Have);

  //
  // What coreboot answered to the arm, as PlatformBootManagerLib reports it
  // (EFI_SUCCESS armed); without the variable the platform has no such lock.
  //
  Size   = sizeof (OptionLock);
  Status = gRT->GetVariable (L"OptionLockStatus", &gEficorebootNvDataGuid, NULL, &Size, &OptionLock);
  Have   = !EFI_ERROR (Status) && (Size == sizeof (OptionLock));
  HstiReport (HstiOptionLock, Have, Have, Have && ((EFI_STATUS)OptionLock == EFI_SUCCESS));

  Size   = sizeof (MorLock);
  Status = gRT->GetVariable (
                  MEMORY_OVERWRITE_REQUEST_CONTROL_LOCK_NAME,
                  &gEfiMemoryOverwriteRequestControlLockGuid,
                  NULL,
                  &Size,
                  &MorLock
                  );
  HstiReport (HstiMorLock, TRUE, TRUE, !EFI_ERROR (Status));

  HstiReport (HstiPreBootDma, TRUE, FALSE, FALSE);
}

/**
  Run the tests and publish the table, once. Signalled from the ReadyToBoot
  handler, so that it runs after every other handler of ReadyToBoot at
  TPL_CALLBACK, the arm of the option lock among them.
**/
STATIC
VOID
EFIAPI
HstiPublish (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  ADAPTER_INFO_PLATFORM_SECURITY  *Hsti;
  UINTN                           ErrorSize;
  UINTN                           Size;
  UINT8                           *Features;
  EFI_STATUS                      Status;

  if (mPublished) {
    return;
  }

  mPublished = TRUE;
  mErrors    = AllocateZeroPool (HSTI_ERROR_CHARS * sizeof (CHAR16));
  if (mErrors == NULL) {
    return;
  }

  HstiTestFlash ();
  HstiTestCpu ();
  HstiTestBoot ();

  ErrorSize = (mErrorsLength + 1) * sizeof (CHAR16);
  Size      = sizeof (*Hsti) + 3 * HSTI_FEATURES_SIZE + ErrorSize;
  Hsti      = AllocateZeroPool (Size);
  if (Hsti == NULL) {
    FreePool (mErrors);
    return;
  }

  Hsti->Version = PLATFORM_SECURITY_VERSION_VNEXTCS;
  Hsti->Role    = PLATFORM_SECURITY_ROLE_PLATFORM_IBV;
  UnicodeSPrint (
    Hsti->ImplementationID,
    sizeof (Hsti->ImplementationID),
    L"%s, firmware revision 0x%08x",
    gST->FirmwareVendor,
    gST->FirmwareRevision
    );
  Hsti->SecurityFeaturesSize = HSTI_FEATURES_SIZE;
  Features                   = (UINT8 *)(Hsti + 1);
  CopyMem (Features, mRequired, HSTI_FEATURES_SIZE);
  CopyMem (Features + HSTI_FEATURES_SIZE, mImplemented, HSTI_FEATURES_SIZE);
  CopyMem (Features + 2 * HSTI_FEATURES_SIZE, mVerified, HSTI_FEATURES_SIZE);
  CopyMem (Features + 3 * HSTI_FEATURES_SIZE, mErrors, ErrorSize);

  DEBUG ((
    DEBUG_INFO,
    "HSTI: required %02x%02x, implemented %02x%02x, verified %02x%02x\n",
    mRequired[1],
    mRequired[0],
    mImplemented[1],
    mImplemented[0],
    mVerified[1],
    mVerified[0]
    ));

  Status = HstiLibSetTable (Hsti, Size);
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "HSTI: table not published: %r\n", Status));
  }

  Status = gRT->SetVariable (
                  HSTI_VARIABLE_NAME,
                  &gAdapterInfoPlatformSecurityGuid,
                  EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS,
                  Size,
                  Hsti
                  );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "HSTI: %s not written: %r\n", HSTI_VARIABLE_NAME, Status));
  }

  FreePool (Hsti);
  FreePool (mErrors);
}

STATIC
VOID
EFIAPI
HstiReadyToBoot (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  gBS->CloseEvent (Event);
  gBS->SignalEvent (mPublishEvent);
}

/**
  Make HstiTable read-only once it exists, before EndOfDxe closes Variable
  Policy to new rules, and wait for the start of a boot.
**/
EFI_STATUS
EFIAPI
PlatformHstiDxeEntryPoint (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EDKII_VARIABLE_POLICY_PROTOCOL  *VariablePolicy;
  EFI_EVENT                       ReadyToBoot;
  EFI_STATUS                      Status;

  Status = gBS->LocateProtocol (&gEdkiiVariablePolicyProtocolGuid, NULL, (VOID **)&VariablePolicy);
  if (!EFI_ERROR (Status)) {
    Status = RegisterBasicVariablePolicy (
               VariablePolicy,
               &gAdapterInfoPlatformSecurityGuid,
               HSTI_VARIABLE_NAME,
               VARIABLE_POLICY_NO_MIN_SIZE,
               VARIABLE_POLICY_NO_MAX_SIZE,
               VARIABLE_POLICY_NO_MUST_ATTR,
               EFI_VARIABLE_NON_VOLATILE,
               VARIABLE_POLICY_TYPE_LOCK_ON_CREATE
               );
  }

  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_WARN, "HSTI: no Variable Policy for %s: %r\n", HSTI_VARIABLE_NAME, Status));
  }

  Status = gBS->CreateEvent (EVT_NOTIFY_SIGNAL, TPL_CALLBACK, HstiPublish, NULL, &mPublishEvent);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  return EfiCreateEventReadyToBootEx (TPL_CALLBACK, HstiReadyToBoot, NULL, &ReadyToBoot);
}
