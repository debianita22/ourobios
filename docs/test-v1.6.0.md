# Hardware tests of the v1.6.0 candidate

The tests before the tag of v1.6.0, on the W541 (`mrc` and `nri`) and the
M920x (`fsp`), with the candidate v1.6.0-rc6. The IDs are those of
[docs/testing.md](testing.md). Whoever runs them, a person or an agent
such as Claude Code on the machine, follows the rules below; the results
stay on the machine, in `~/ourobios-test-v1.6.0/`, one folder per board
and variant, for the record of the candidate (docs/testing.md, *How to
test a release candidate*, step 5).

## The build

- **Candidate**: the pre-releases
  [v1.6.0-rc6-mrc](https://github.com/debianita22/ourobios/releases/tag/v1.6.0-rc6-mrc),
  [v1.6.0-rc6-nri](https://github.com/debianita22/ourobios/releases/tag/v1.6.0-rc6-nri) and
  [v1.6.0-rc6-m920x-fsp](https://github.com/debianita22/ourobios/releases/tag/v1.6.0-rc6-m920x-fsp),
  built by the Release workflow from `next` at `65e0068` or later: for each
  variant the ROM, the capsule (`.cap`, version v1.6.0-rc6, so it installs
  and goes back as a release does) and `SHA256SUMS`.
- **After rc5** (tested on the M920x from rc1 to rc5; the W541 may still
  be on v1.5.0): patch 0225 (the measurement log of coreboot at DEBUG,
  off the serial port of the M920x at INFO), the serial port counted by
  `hw-report.py` (BOOT-01), the serial console of the M920x off by
  default, *Disabled (HAP bit)* for its ME (patch 0226), the payload
  without the UEFI Shell (`edk2/0053`, patch 0227) and without the two
  SDHCI drivers for controllers these boards do not have (`edk2/0054`,
  `edk2/0055`): the rows at the end of section 3. The CI of each change
  passed (the smoke test in QEMU, the A/B update, the reproducible build,
  `edk2-parity`); none of it has run on a machine yet.
- **Tools**: from a clone at `next`, `65e0068` or later. On the machine:
  `python3`, flashrom 1.2 or later, `cbmem` (coreboot's `util/cbmem`),
  `dmidecode`, `fwts` (CONF-03), `mokutil`, `efibootmgr`, and `gh` to
  download the candidate.

```sh
git -C CLONE fetch origin && git -C CLONE checkout next && git -C CLONE pull --ff-only
mkdir -p ~/ourobios-test-v1.6.0 && cd ~/ourobios-test-v1.6.0
for v in mrc nri m920x-fsp; do
  gh release download v1.6.0-rc6-$v -R debianita22/ourobios -D rom/$v -p '*.rom' -p '*.cap' -p SHA256SUMS
  ( cd rom/$v && sha256sum -c SHA256SUMS --ignore-missing )
done
```

## Rules

1. A copy of the flash first: `flashrom -p internal -r flash-before.bin`,
   12582912 bytes on the W541, 25165824 on the M920x, kept off the
   machine.
2. Write only through the capsules (`update.py stage`, `update.py
   rollback`: the firmware writes the slot that is not running) or what
   `update.py other-slot` prints: the flashrom command as it is (the slot
   that is not running and `RW_NVRAM`, on the W541 with `RW_MRC_CACHE`).
   Never `WP_RO`, `--ifd`, the descriptor, ME, GbE or the whole image:
   writing those is a brick risk and no part of these tests.
3. An agent shows each flashrom write and runs it only after an explicit
   yes from the owner of the machine.
4. flashrom must end with `VERIFIED`; if not, the same command once
   more, and if it fails again, stop and ask.
5. Reboot right after the write, without suspending.
6. A boot that hangs: power off with the button (4 s) and on again; after
   two failed boots vboot goes back to the slot of before by itself. The
   external programmer is the last resort.
7. Nothing is changed in the repository: no commits, no pushes.

## 1. Install

As a user updates (UPD-02): the capsule of rc6 of the variant that runs,
on v1.5.0 or on rc5, with *BIOS Lock* on (the payload writes the slot
through SMM). The read-only part stays the one of v1.5.0. From rc5 the
capsule is written by the payload of v1.6.0 itself (`edk2/0045`,
`edk2/0046`), which no machine has done yet; from v1.5.0 by the payload
of v1.5.0, as rc5 was installed on the M920x.

```sh
# as a user with sudo; the copy of the flash first (rule 1)
sudo modprobe -r spi_intel_platform spi_intel || true    # M920x: spi_intel_pci spi_intel
sudo flashrom -p internal -r flash-before.bin && stat -c %s flash-before.bin
sudo python3 CLONE/tools/update.py stage rom/mrc/w541-coreboot-v1.6.0-rc6-mrc.cap   # or nri, m920x-fsp
sudo systemctl reboot
```

The update screen, then rc6 from the other slot: `update.py status` says
it. The W541 trains the memory at that boot (a few seconds of black
screen); the M920x does not, the version of its cache is the same (patch
0222 at 0). At that first boot the boot manager deletes the *UEFI Shell*
entry that the older firmware left (BOOT-10). The other variant on the W541 goes in with `other-slot`, as
in the rules, and only behind the read-only part of `mrc`; behind the one
of `nri`, `nri` only (`other-slot` refuses a slot that cannot start):
*BIOS Lock* off for that write (*Security* → *Flash protection*; on the
M920x also Secure Boot, or the kernel's lockdown keeps flashrom away),
on again after the first boot.

```sh
sudo flashrom -p internal -r flash-now.bin       # the copy of this boot
python3 CLONE/tools/update.py other-slot flash-now.bin rom/nri/w541-coreboot-v1.6.0-rc6-nri.rom
# the flashrom command that other-slot prints, after the yes, then:
sudo systemctl reboot
```

## 2. The reports

`sudo python3 -I CLONE/tools/hw-report.py --markdown hw-BOARD-VARIANT-N.md`
at the second boot (a reboot from Linux) and after a cold boot (powered off
and on).

| Check | Expected |
|---|---|
| all | PASS, but those known below |
| BOOT-01 | the stages with `26.09-517` and the version `v1.6.0-rc6-VARIANT`; on the M920x the serial port line (the level of the boot, and at Info, Notice, Error) and *Serial Console* off |
| CONF-01 | the WSMT, revision 1, flags 7 |
| CONF-07 | the ECAM window reserved in the memory map and among the `pnp` resources |
| PCI-09 | PASS, or INFO for a BAR of a device no driver of the payload uses (on the M920x the SPI controller, `00:1f.5`): every other BAR of bus 0 inside the aperture of the payload |
| MEM-01 | the cache valid and used (W541: training at the first boot, the cache from the second); on the M920x with the ME disabled, INFO at 5.2 s on some boots and resumes (the DRAM Init Done wait, patch 0191) |

Known, not a stop for the tag: on the W541 EC-01 WARN (an EC before
1.15), ME-01 as in the reports of v1.5.0, IDLE-01 INFO with the 3K panel
on (it stays in PC2 then); FLASH-01 WARN only while a protection is off.

## 3. What is new in v1.6.0

| ID | Test | Expected |
|---|---|---|
| CONF-03 | `sudo fwts --acpitests --uefitests wsmt mcfg -r fwts.log; cat fwts.log \| grep -E "FAILED\|CRITICAL\|HIGH"` | no CRITICAL or HIGH; no *MCFGMMIONotReserved* |
| OPT-02 | an option with a visible effect changed in the setup, *Save*, two reboots (SMMSTORE with the fixed com buffer: 0211-0215, `edk2/0044`) | the effect at every boot, OPT-01 with the value |
| — | `sudo efibootmgr -t 3`, a reboot, `efibootmgr \| head -3` (variables written by the OS) | `Timeout: 3 seconds` |
| MEM-09 | as in docs/testing.md, with *BIOS Lock* on | the lock reads `07 00 00 00 01`; writing `00` is refused; *request of the OS yes: clearing* after the reboot |
| UPD-02 | the install of step 1: from rc5 (the M920x) the payload of v1.6.0 writes the rc6 capsule (`edk2/0045`, `edk2/0046`, the arguments in the com buffer), the first time on a machine; from v1.5.0 the payload of v1.5.0 writes it | the update screen; the other slot holds the new version and boots; settings, VPD and event log stay |
| UPD-06 | `update.py stage` with the v1.5.0 capsule of the other board and of the other W541 variant | refused before the reboot |
| UPD-05 | from rc6, `update.py rollback` (or the setup's *Go back to*): the payload of rc6 takes the capsule of the other slot (v1.5.0 or rc5), finds the slot written and switches; then `update.py stage` of the rc6 capsule again | the other release boots (the W541 trains again: `RW_MRC_CACHE` is cleared), then rc6; settings stay |
| USB-06 | a USB 3 drive behind a USB 2 hub and a keyboard behind a USB 3 hub, plugged in before power-on | the Esc menu, the setup and the boot from the drive work |
| DISP-05 | the setup at every *UI Scale* (W541 at 2880x1620, M920x on a monitor), a reboot for each; the list below | every screen drawn whole |
| CPU-05 | the TCC offset of the W541 | passed on 2026-11-03 |

New in rc6, not in rc5:

| ID | Test | Expected |
|---|---|---|
| BOOT-09 | M920x: the serial console with no setting saved, then *Console* → *Serial Console* on | off by default (BOOT-01, no SPCR table); on, the SPCR table and the log on COM1 |
| BOOT-10 | the first boot after the capsule: `efibootmgr`, the boot menu | no *UEFI Shell* entry; the disks, iPXE and CSMWrap as before |
| ME-05 | M920x, optional, **RISCHIO BRICK**: the firmware writes the descriptor itself (about 50 ms), which rule 2 keeps out of the other tests; only after an explicit yes of the owner, with the copy of rule 1 off the machine, recovery with the external programmer ([docs/m920x.md](m920x.md#intel-me)). *Disabled (HAP bit)*, a power cycle, then *Disabled* again | as in docs/testing.md: `HAP: written`, then *ME: Disabled (HAP bit)*, no `00:16.0`, no 5 s wait at DRAM Init Done |
| BOOT-05, BOOT-06 | the boot menu and a boot from each disk, on the W541 also from an SD card in the reader (`SdMmcPciHcDxe`, unchanged: the two drivers left out bound nothing here) | as before |

The list of `lvglpkg/0021`, within DISP-05:
- the cursor shows with the TrackPoint or the touchpad and hides when only
  the keyboard is used;
- a long page scrolls with the touchpad and stops at its end;
- the icons of the front page light up under the pointer and on a click,
  which opens the category;
- in a category, Up and Down to the last row keep the selected row in
  view;
- a text field or the password dialog brings up the on-screen keyboard
  with the field active, and Esc or leaving the field hides it;
- the top bar and the wallpaper: the battery (W541), the model name, the
  circles.

## 4. Regressions

| ID | Test | Expected |
|---|---|---|
| S3-02, S3-03 | `systemctl suspend` five times; on the W541 also the lid and Fn | back each time; `sudo cbmem -1` with *S3 Resume* and *TPM: resuming from S3, nothing is measured*; network, USB, video, audio and Wi-Fi work |
| TPM-03 (after S3) | hw-report after the five suspends, without a reboot | PASS: the PCRs still replay from the log (patch 0223; up to v1.5.0 PCR 2 was extended again on every resume). The bootblock of the read-only part of v1.5.0 still logs three entries per resume in cbmem's log, none extended |
| — | W541: *NVIDIA discrete GPU* on and then off, a boot and a suspend with each | `lspci -nn \| grep -i nvidia` as the option says; S3 as above |
| — | W541: macOS from OpenCore | boot, sleep and wake, dark wake (the panel stays off on a dark wake), also with the dGPU off |
| — | Secure Boot on, with a system signed for Microsoft's keys (shim: a live USB of Fedora or Ubuntu, if the installed one is not); `mokutil --sb-state`, `sudo mokutil --pk \| grep Subject` | `SecureBoot enabled`; `CN=Windows OEM Devices PK`; it boots |
| NET-05 | iPXE from the Esc menu | it starts and gets an address |
| — | Secure Boot off, *CSMWrap Legacy Boot* from the Esc menu with a BIOS-only medium | SeaBIOS starts and boots it; with Secure Boot on the entry is not there |
| BOOT-06 | boot from SATA, USB and (M920x) NVMe | each disk boots its system |
| TPM-01, TPM-03 | hw-report | TPM 1.2 and TCPA on the W541, TPM 2.0 on the M920x |

## 5. M920x only

Done on rc1-rc6 (2026-11-03 to 11-05, the record in
[docs/tests/v1.6.0/m920x-fsp/](tests/v1.6.0/m920x-fsp/README.md)): the
findings became patches 0223 (TPM-03 after S3) and 0224 (the processor
graphics always on); the report of rc5 passes, with PCI-09 INFO for the
SPI controller; the boot time of rc5 step by step is in
[docs/m920x.md](m920x.md#boot-time). With rc6:
the two reports again (BOOT-01 with the serial port off, BOOT-02 without
the Shell to load: the boot time against the table of rc5), the rows new
in rc6, the rows of section 4 not run there yet, and the items below.

- PCI-02 (hw-report): the PEG port off without a card on the riser.
- PCI-09 PASS or INFO (the SPI controller's BAR, no driver of the payload).
- Optional, with Windows 11 on a disk of its own ([docs/hlk.md](hlk.md)):
  WIN-01, WIN-02; WIN-09,
  `(Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard).AvailableSecurityProperties`,
  expected 1, 2, 4, 5, 6 and 7, no 3; WIN-10, a capsule from Windows with
  `tools/win-firmware-inf.py`; CONF-06, HLK.

## 6. What to bring back

The M920x's are in [docs/tests/v1.6.0/m920x-fsp/](tests/v1.6.0/m920x-fsp/README.md):
the record of ci-244 to rc6, the reports and logs of rc6 and the i915
DPLL measurements. For each board and variant, in its folder:
- the two reports;
- a table of the IDs of the manual tests with their results;
- `sudo cbmem -1 > cbmem-BOARD-VARIANT.txt` of the second boot, whole;
- for a test that did not pass, `sudo cbmem -1 > cbmem.txt`, the report
  and the commands that showed it;
- for the roadmap item *Memory training across updates on the W541*,
  `sudo cbmem -t` at the first boot after `other-slot` (with the training)
  and at the second (from the cache), for `mrc` and `nri`.

At the end, *BIOS Lock* and *Firmware protection* on, and `hw-report.py`
with FLASH-01 PASS. A FAIL stops the tag; the tag and the releases are
made by the owner of the repository.
