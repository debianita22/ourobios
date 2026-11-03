# Windows HLK

The Windows Hardware Lab Kit runs Microsoft's own tests of a system on
real Windows: here it is the check of the firmware against Windows'
requirements for UEFI, Secure Boot, ACPI, SMBIOS and the TPM (CONF-06 of
[docs/testing.md](testing.md#uefi-and-acpi-conformance-conf)). It is not a
certification: the project submits nothing to Microsoft. The run below is
for the M920x with Windows 11; the W541 is outside Windows 11's processor
list and has a TPM 1.2, so on it HLK can only be a partial run with a
Windows 10 HLK, with the TPM 2.0 tests out.

Nothing here can be done without the machine, a second machine for the
test server and a Windows licence: this page is the checklist for that
run.

## What is known not to pass

These come from what the firmware does not have, each written down where
it was decided. They are not bugs to find in the logs.

| What | Board | In HLK and Windows | Why |
|---|---|---|---|
| HSTI | both | *Hardware Security Testability Interface Test* fails | the firmware publishes no HSTI ([docs/roadmap.md](roadmap.md#hsti)) |
| DMA protection | both | `Win32_DeviceGuard` without 3; Kernel DMA Protection off | no IOMMU before the OS and no DMAR opt-in flag ([docs/roadmap.md](roadmap.md#dma-protection)) |
| System Guard Secure Launch | both | *SystemGuard Test* | no DRTM: run it with Secure Launch off, as its test page says (the `Enabled` value removed from `HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\SystemGuard`) |
| Modern Standby | both | its tests are not scheduled | the boards sleep in S3 |
| MBEC | W541 | `Win32_DeviceGuard` without 7 | Haswell: Microsoft lists Kaby Lake and later; memory integrity uses its emulation |
| TPM 2.0 | W541 | the TPM 2.0 tests do not apply | TPM 1.2 (TCPA), no fTPM |

## The lab

1. **Test server**: a machine of its own, with Windows Server 2022 or 2025,
   and the HLK Controller and Studio of the HLK release made for the
   Windows 11 version that the M920x will run (Microsoft's
   [HLK page](https://learn.microsoft.com/windows-hardware/test/hlk/) lists
   the releases). The M920x and the server on the same network.
2. **The M920x**, on the release under test, with *BIOS Lock* and
   *Firmware protection* on, as shipped:
   - in the setup, *TPM 2.0 Configuration* → *TPM2 Operation* →
     *TPM2 ClearControl(NO) + Clear*, save and confirm at the next boot:
     the *Secure Boot Logo Test* wants a TPM cleared before Windows is
     installed;
   - *Secure Boot*: *Reset Secure Boot Keys* (the default keys of the
     release: Microsoft's KEK and db, the dbx of Microsoft's feed) and
     *Attempt Secure Boot* on;
   - Windows 11 from Microsoft's media, on a disk of its own, with no
     bypass of the requirements (WIN-01), the drivers from Windows Update
     (WIN-03).
3. **HLK Client**: Secure Boot can make its installation fail, so turn
   *Attempt Secure Boot* off first, then run
   `\\<ControllerName>\HLKInstall\Client\Setup.cmd` and allow the port it
   asks for (TCP 1771). Do not rename the M920x after this.
4. **Studio**: a machine pool with the M920x, set to *Ready*; a project
   with the M920x as the system target; the compatibility playlist of the
   HLK release.

## The run

In three passes, as Microsoft's
[System testing with Secure Boot](https://learn.microsoft.com/windows-hardware/test/hlk/testref/system-testing-with-secure-boot)
asks.

| Pass | Setup | Tests | Expected |
|---|---|---|---|
| 1 | *Attempt Secure Boot* off | those that Microsoft's page runs with Secure Boot off, among them *ACPI Logo Test*, *PCI Hardware Compliance Test For Systems*, *TPM 2.0 UEFI Preboot Interface Test*, *TPM 2.0 TCG Physical Presence Interface 1.2 Test*, *UEFI Firmware Certification Test*, *UEFI GOP Mode Test*, *Firmware Update test*, *Crashdump Support test*, *WHEAHCT Logo* and the USB tests | pass |
| 2 | *Reset Secure Boot Keys*, *Attempt Secure Boot* on | the rest of the system tests, among them *Secure Boot Logo Test*, the *Check SMBIOS* tests, the TPM 2.0 tests, *Verify System.Fundamentals.Security.VirtualizationSupport*, *Hardware Security Testability Interface Test* and *SystemGuard Test* | pass, except the two of the table above |
| 3 | *Custom Mode* → *Enter Setup Mode* (clears the PK) | *Secure Boot Manual Logo Test* | pass; then *Reset Secure Boot Keys* again |

Before pass 2, the two `reg add` commands that the
[Secure Boot Logo Test](https://learn.microsoft.com/windows-hardware/test/hlk/testref/45ea8a48-d845-4400-b4a4-a4aeb8af686e)
asks for, in an elevated prompt:

```bat
reg add HKLM\System\CurrentControlSet\Services\iospy\StartOverride /v 0 /t REG_DWORD /d 3 /f
reg add HKLM\System\CurrentControlSet\Services\MSDMFilt\StartOverride /v 0 /t REG_DWORD /d 3 /f
```

Bring back the HLK package of the project (Studio, *Package*), or for each
test that does not pass its log, with the release and `sudo cbmem -1` of
the same boot taken from Linux.

## Windows' own view of the firmware

Without HLK, Windows says what it takes from the firmware for
virtualization-based security (WIN-09 of
[docs/testing.md](testing.md#windows-11-win)), in an elevated PowerShell:

```powershell
(Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard).AvailableSecurityProperties
```

The numbers are Microsoft's
([memory integrity](https://learn.microsoft.com/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity)):

| Value | What | Expected on the M920x | Where it comes from |
|---|---|---|---|
| 1 | hypervisor support | yes | VT-x (`ENABLE_VMX`, on in both builds) |
| 2 | Secure Boot | yes | *Attempt Secure Boot* on |
| 3 | DMA protection | no | known, above |
| 4 | Secure Memory Overwrite | yes, with *BIOS Lock* on | the MOR lock (patch 0207, `edk2/0043`, MEM-09) |
| 5 | NX protections | yes | the memory attributes table that the DXE core of the payload installs |
| 6 | SMM mitigations | yes | the WSMT with its three flags (patches 0211-0215, CONF-01) |
| 7 | MBEC | yes | the processor (Kaby Lake and later) |

On the W541, with Windows 10, the same without 7. `msinfo32` shows them
in words, under *Virtualization-based security Available Security
Properties*. A 4 or a 6 missing is a bug: WSMT and MOR are what the
firmware declares itself, and Windows reads them before it starts the
hypervisor.

## Firmware updates from Windows

Windows updates system firmware with a driver package for the ESRT entry
of the firmware, an INF, the capsule and a catalog, and hands the capsule
to the firmware with `UpdateCapsule()` before a warm reset. ouroBIOS ships
its capsules for Linux (`tools/update.py`, fwupd), which put them on the
ESP; the path in memory goes through the same checks, but whether the
memory survives the warm reset is untested
([docs/update.md](update.md)). To try it (WIN-10):

1. `tools/win-firmware-inf.py w541-coreboot-vX.Y.Z-mrc.cap pkg` (or the
   capsule of the M920x) writes `pkg/firmware.bin` and `pkg/ourobios.inf`,
   the INF of Microsoft's
   [Authoring an update driver package](https://learn.microsoft.com/windows-hardware/drivers/bringup/authoring-an-update-driver-package),
   with the GUID of the ESRT and the version of the capsule.
2. On Windows, the catalog and a test signature as that page says for
   test systems (Secure Boot off, `bcdedit /set testsigning on`).
3. *Device Manager* → *Firmware* → the system firmware → *Update driver* →
   *Have disk*, the INF; then a restart.

What to check, from Microsoft's
[validation of the UEFI firmware update platform](https://learn.microsoft.com/windows-hardware/manufacture/desktop/validating-windows-uefi-firmware-update-platform-functionality)
(its scenarios S1-S3.7), with `sudo python3 tools/update.py status` from
Linux afterwards:

| Scenario | Capsule | Expected |
|---|---|---|
| S1, S2 | the next release of the same variant | written, the new version in the ESRT, last attempt status success |
| S3.4, S3.5 | one signed with another key | refused, *Security Violation* |
| S3.6 | one with a byte of the image changed | refused |
| S3.7 | one below the lowest supported version (v1.3.9) | refused, *Aborted* |
| S3.1 (W541) | the next release, on battery below 25% | postponed: the firmware waits a minute for the AC adapter, then does not write |

If the capsule never arrives (no update screen at the restart, the
version unchanged, `cbmem -1` without the capsule), the memory did not
survive the warm reset: that is the answer to the open question of
`docs/update.md`, and capsules on disk stay the way to update.
