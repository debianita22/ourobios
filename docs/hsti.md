# HSTI: the security tests the firmware reports

From v1.7.0 (`edk2/0063`, `PlatformHstiDxe`) the payload publishes the
Hardware Security Testability Interface of Microsoft's specification:
when a boot is started, after it has armed its locks, it reads the
protections from the hardware and publishes the result, as the HSTI
table of the Adapter Information protocol (role IBV, *independent BIOS
vendor*), which Windows reads for its device security report, and as
the volatile UEFI variable `HstiTable` of the same GUID
(`6be272c7-1320-4ccd-9017-d4612c012b25`), which the OS can read but not
write. `tools/hw-report.py` reads it (CONF-08 of
[docs/testing.md](testing.md)).

The table reports what the machines do not have as well as what they
have: a test that fails is a line of the error string, with its code.
The features are two bytes; bit *n* is the test below with code
`0x0001000n`.

| Code | Test | Passes when | On these boards |
|---|---|---|---|
| `0x00010000` | Flash configuration locked | `FLOCKDN` set in `HSFS` | yes, set by coreboot's finalize |
| `0x00010001` | BIOS region write-protected | `BIOS_CNTL`: `BLE` and `SMM_BWP` (`EISS`) set, `WPD` (`BIOSWE`) clear | yes with *BIOS Lock* on (the default) |
| `0x00010002` | Flash range protected | a Protected Range with write protection, and `FLOCKDN` | yes with *Firmware protection* on (`WP_RO`) |
| `0x00010003` | Descriptor not writable by the host | `FRAP`: the BIOS master has no write access to region 0 | **no**: the regions are unlocked with ifdtool, so that flashrom can write the whole flash |
| `0x00010004` | ME region not writable by the host | `FRAP`: no write access to region 2 | **no**, for the same reason |
| `0x00010005` | SMRAM locked | the lock bit of `TSEGMB` in the host bridge | yes |
| `0x00010006` | Debug interface locked | `IA32_DEBUG_INTERFACE`: enable clear, lock set (only with `CPUID.1:ECX.SDBG`; without it the test does not apply) | yes on the M920x (`0x40000000`: locked, off); on the W541 as its processor reports it |
| `0x00010007` | Microcode loaded | `IA32_BIOS_SIGN_ID` not zero | yes |
| `0x00010008` | Secure Boot | `SecureBoot` 1 and `SetupMode` 0 | the owner's choice in the setup |
| `0x00010009` | TPM | the TCG2 or TCG protocol present (measured boot) | yes |
| `0x0001000a` | Setup option lock | `OptionLockStatus` is `EFI_SUCCESS` | yes |
| `0x0001000b` | MOR lock | `MemoryOverwriteRequestControlLock` exists | yes |
| `0x0001000c` | Pre-boot DMA protection | never | **no**: the FSP-M of the M920x has no PMR data, and the W541's firmware sets none ([docs/roadmap.md](roadmap.md#dma-protection)) |

The tests only read registers, but the microcode signature MSR, which
the SDM asks to clear before reading it. They run when a boot starts:
a protection turned off later, by the OS, is not seen, and that is what
`tools/hw-report.py` checks from the OS.
