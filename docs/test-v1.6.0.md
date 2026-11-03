# Hardware tests of the v1.6.0 candidate

The tests before the tag of v1.6.0, on the W541 (`mrc` and `nri`) and the
M920x (`fsp`), with the CI build `ci-244-98e7f1c`. The IDs are those of
[docs/testing.md](testing.md). Whoever runs them, a person or an agent
such as Claude Code on the machine, follows the rules below; the results
stay on the machine, in `~/ourobios-test-v1.6.0/`, one folder per board
and variant, for the record of the candidate (docs/testing.md, *How to
test a release candidate*, step 5).

## The build

- **Run**: [Build #244](https://github.com/debianita22/ourobios/actions/runs/41675819773)
  of `ci-test/v1.6.0-final`, which is `next` at `98e7f1c`: every ROM, the
  smoke test of the setup at 1920x1080 and 2880x1620, the A/B update in
  QEMU, the ROMs again on another runner, a reproducible build.
- **Artifact**: `ourobios-ci-244-98e7f1c`, kept until 2026-11-17:
  `w541-coreboot-ci-244-98e7f1c-mrc.rom`,
  `w541-coreboot-ci-244-98e7f1c-nri.rom`,
  `m920x-coreboot-ci-244-98e7f1c-fsp.rom`, with `SHA256SUMS`. A CI build
  has no capsule (its version is 0): it goes in with `update.py
  other-slot`.
- **Tools**: from a clone at `next`, `98e7f1c` or later. On the machine:
  `python3`, flashrom 1.2 or later, `cbmem` (coreboot's `util/cbmem`),
  `dmidecode`, `fwts` (CONF-03), `mokutil`, `efibootmgr`, and `gh` to
  download the artifact.

```sh
git -C CLONE fetch origin && git -C CLONE checkout next && git -C CLONE pull --ff-only
mkdir -p ~/ourobios-test-v1.6.0 && cd ~/ourobios-test-v1.6.0
gh run download 41675819773 -R debianita22/ourobios -n ourobios-ci-244-98e7f1c -D rom
( cd rom && sha256sum -c SHA256SUMS --ignore-missing )
```

## Rules

1. A copy of the flash first: `flashrom -p internal -r flash-before.bin`,
   12582912 bytes on the W541, 25165824 on the M920x, kept off the
   machine.
2. Write only what `update.py other-slot` prints: the flashrom command as
   it is (the slot that is not running and `RW_NVRAM`, on the W541 with
   `RW_MRC_CACHE`). Never `WP_RO`, `--ifd`, the descriptor, ME, GbE or
   the whole image: writing those is a brick risk and no part of these
   tests.
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

*BIOS Lock* off in the setup (*Security* → *Flash protection*), save and
reboot: `update.py protection` must say *BIOS Lock: spento*. *Firmware
protection* can stay on, it covers the read-only part only. On the M920x
Secure Boot off too, or the kernel's lockdown keeps flashrom away from the
flash. On the W541, behind the read-only part of `mrc` both variants can
be tried; behind the one of `nri`, `nri` only (`other-slot` refuses a slot
that cannot start).

```sh
# W541, as a user with sudo; on the M920x the same, unloading spi_intel_pci spi_intel
sudo modprobe -r spi_intel_platform spi_intel || true
sudo flashrom -p internal -r flash-before.bin && stat -c %s flash-before.bin
python3 CLONE/tools/update.py other-slot flash-before.bin rom/w541-coreboot-ci-244-98e7f1c-nri.rom
# the flashrom command that other-slot prints, after the yes, then:
sudo systemctl reboot
```

After the first boot, *BIOS Lock* on again (and Secure Boot on the M920x as
it was): the tests run with it on. The W541 trains the memory at that boot
(a few seconds of black screen). The M920x does not train coming from
v1.5.x: the version of its cache is the same (patch 0222 at 0).

## 2. The reports

`sudo python3 -I CLONE/tools/hw-report.py --markdown hw-BOARD-VARIANT-N.md`
at the second boot (a reboot from Linux) and after a cold boot (powered off
and on).

| Check | Expected |
|---|---|
| all | PASS, but those known below |
| BOOT-01 | the stages with `26.09-517` and the version `ci-244-98e7f1c` |
| CONF-01 | the WSMT, revision 1, flags 7 |
| CONF-07 | the ECAM window reserved in the memory map and among the `pnp` resources |
| PCI-09 | PASS: every BAR of bus 0 inside the aperture of the payload |
| MEM-01 | the cache valid and used (W541: training at the first boot, the cache from the second) |

Known, not a stop for the tag: on the W541 EC-01 WARN (an EC before
1.15), ME-01 as in the reports of v1.5.0, IDLE-01 INFO with the 3K panel
on (it stays in PC2 then); FLASH-01 WARN only while a protection is off.

## 3. What is new in v1.6.0

| ID | Test | Expected |
|---|---|---|
| CONF-03 | `sudo fwts acpi uefi wsmt mcfg -r fwts.log; cat fwts.log \| grep -E "FAILED\|CRITICAL\|HIGH"` | no CRITICAL or HIGH; no *MCFGMMIONotReserved* |
| OPT-02 | an option with a visible effect changed in the setup, *Save*, two reboots (SMMSTORE with the fixed com buffer: 0211-0215, `edk2/0044`) | the effect at every boot, OPT-01 with the value |
| — | `sudo efibootmgr -t 3`, a reboot, `efibootmgr \| head -3` (variables written by the OS) | `Timeout: 3 seconds` |
| MEM-09 | as in docs/testing.md, with *BIOS Lock* on | the lock reads `07 00 00 00 01`; writing `00` is refused; *request of the OS yes: clearing* after the reboot |
| UPD-02 | from `ci-244`, the capsule of v1.5.0 of the same variant (`gh release download v1.5.0-mrc -R debianita22/ourobios -p '*.cap'`, or `v1.5.0-nri`, `v1.5.0-m920x-fsp`), `sudo python3 CLONE/tools/update.py stage FILE.cap`, a reboot, *BIOS Lock* on: the payload of `ci-244` writes it (`edk2/0045`, `edk2/0046`, the arguments in the com buffer) | the update screen; the other slot holds v1.5.0 and boots; settings, VPD and event log stay. Back to `ci-244`: `other-slot` again, as in step 1 (the setup's *Go back to* takes releases only, and a CI build has no version in its name) |
| UPD-06 | `update.py stage` with the v1.5.0 capsule of the other board and of the other W541 variant | refused before the reboot |
| UPD-05 | rollback | with a tag only: `update.py rollback` does not go back to a CI build |
| USB-06 | a USB 3 drive behind a USB 2 hub and a keyboard behind a USB 3 hub, plugged in before power-on | the Esc menu, the setup and the boot from the drive work |
| DISP-05 | the setup at every *UI Scale* (W541 at 2880x1620, M920x on a monitor), a reboot for each; the list below | every screen drawn whole |
| CPU-05 | the TCC offset of the W541 | passed on 2026-11-03 |

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
| S3-02, S3-03 | `systemctl suspend` five times; on the W541 also the lid and Fn | back each time; `sudo cbmem -1` with *S3 Resume*; network, USB, video, audio and Wi-Fi work |
| — | W541: *NVIDIA discrete GPU* on and then off, a boot and a suspend with each | `lspci -nn \| grep -i nvidia` as the option says; S3 as above |
| — | W541: macOS from OpenCore | boot, sleep and wake, dark wake (the panel stays off on a dark wake), also with the dGPU off |
| — | Secure Boot on, with a system signed for Microsoft's keys (shim: a live USB of Fedora or Ubuntu, if the installed one is not); `mokutil --sb-state`, `sudo mokutil --pk \| grep Subject` | `SecureBoot enabled`; `CN=Windows OEM Devices PK`; it boots |
| NET-05 | iPXE from the Esc menu | it starts and gets an address |
| — | Secure Boot off, *CSMWrap Legacy Boot* from the Esc menu with a BIOS-only medium | SeaBIOS starts and boots it; with Secure Boot on the entry is not there |
| BOOT-06 | boot from SATA, USB and (M920x) NVMe | each disk boots its system |
| TPM-01, TPM-03 | hw-report | TPM 1.2 and TCPA on the W541, TPM 2.0 on the M920x |

## 5. M920x only

- PCI-02 (hw-report): the PEG port off without a card on the riser.
- PCI-09 PASS.
- Optional, with Windows 11 on a disk of its own ([docs/hlk.md](hlk.md)):
  WIN-01, WIN-02; WIN-09,
  `(Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard).AvailableSecurityProperties`,
  expected 1, 2, 4, 5, 6 and 7, no 3; WIN-10, a capsule from Windows with
  `tools/win-firmware-inf.py`; CONF-06, HLK.

## 6. What to bring back

For each board and variant, in its folder:
- the two reports;
- a table of the IDs of the manual tests with their results;
- for a test that did not pass, `sudo cbmem -1 > cbmem.txt`, the report
  and the commands that showed it;
- for the roadmap item *Memory training across updates on the W541*,
  `sudo cbmem -t` at the first boot after `other-slot` (with the training)
  and at the second (from the cache), for `mrc` and `nri`.

At the end, *BIOS Lock* and *Firmware protection* on, and `hw-report.py`
with FLASH-01 PASS. A FAIL stops the tag; the tag and the releases are
made by the owner of the repository.
