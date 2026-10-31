# Release testing

The CI checks everything that runs without the hardware: the ROMs and
their flash map (`tools/verify-rom.sh`), the setup menu, the payload in
QEMU (`tools/build.sh smoke`) and capsule updates with vboot A/B in QEMU
(`tools/build.sh update-test`, [docs/vboot.md](vboot.md#how-it-is-tested)).
None of that runs the coreboot of the M920x or of the W541 on the machine.
This page is the rest: the tests a release candidate passes on the
**ThinkCentre M920x Tiny** and the **ThinkPad W541** before it becomes a
release, and `tools/hw-report.py`, which runs the ones that need no hands
in one command.

The layout follows Dasharo's [test
documentation](https://docs.dasharo.com/unified-test-documentation/overview/):
suites of test cases, each with an ID, the steps and the expected result.
Each suite below names the Dasharo suites it matches (*Dasharo:* CBMEM,
HWP, VBO...), so their test cases can be borrowed when ours fall short.

- [tools/hw-report.py](#toolshw-reportpy)
- [How to test a release candidate](#how-to-test-a-release-candidate)
- [Test matrix](#test-matrix): [Boot](#boot-and-boot-time-boot),
  [Memory](#memory-and-training-cache-mem), [CPU](#cpu-and-power-limits-cpu),
  [Idle](#idle-and-package-c-states-idle), [Suspend](#suspend-s3),
  [USB](#usb-usb), [PCIe and storage](#pcie-nvme-and-sata-pci),
  [Display](#display-disp), [Audio](#audio-aud),
  [Network](#network-and-wake-on-lan-net), [Fan and EC](#fan-and-ec-fan),
  [TPM](#tpm-and-measured-boot-tpm), [ME](#intel-me-me),
  [vboot](#vboot-slots-and-fallback-vb), [Updates](#updates-upd),
  [Flash protection](#flash-protection-flash),
  [Setup options](#setup-options-opt), [Event log](#event-log-elog),
  [Identity](#vpd-smbios-and-msdm-id)
- [Coverage of hw-report.py](#coverage-of-hw-reportpy)

## tools/hw-report.py

```sh
sudo python3 -I tools/hw-report.py                      # package C-states sampled for 20 s
sudo python3 -I tools/hw-report.py --seconds 60 --markdown hw-report.md
sudo python3 -I tools/hw-report.py --json > hw-report.json
# with a copy of the flash: event log, vboot's RW_NVRAM, saved setup options
sudo modprobe -r spi_intel_pci                          # W541: spi_intel_platform spi_intel
sudo flashrom -p internal -r flash.bin
sudo python3 -I tools/hw-report.py --dump flash.bin
```

One line per check, `PASS`, `WARN` or `FAIL`, or `INFO` and `SKIP` where
there is nothing to judge, with the numbers behind it; the messages are in
Italian, like those of the other tools. `--markdown FILE` also writes the
report as a Markdown table with the details, to attach to a pull request or
an issue (the *Bug report* and *Hardware report* issue forms ask for it);
`--json` prints it for scripts. The exit status is the worst
result: 0 all `PASS` (or `INFO`, `SKIP`), 1 a `WARN`, 2 a `FAIL`, 3 when
it could not run (not root, a wrong option).

It only reads. It never touches the flash (the event log, `RW_NVRAM` and
the options come only from a copy given with `--dump`), never writes MSRs,
`/sys` or `/dev`, and loads no module: the C-state sample needs the `msr`
module (`sudo modprobe msr`, by hand, or the check is skipped), the SPI
controller registers need `iomem=relaxed` on the kernel command line, as
flashrom and `tools/idle-report.py` do. It needs root and coreboot's
`cbmem` ([docs/flashing.md](flashing.md#first-boot-and-settings)),
`dmidecode`, `journalctl` (or `dmesg`). Serial numbers and UUIDs appear
with their last 4 characters only; the Windows key of the MSDM table is
checked for its format and never printed.

What it reads, and the thresholds:

| ID | From | `PASS` | `WARN` | `FAIL` |
|---|---|---|---|---|
| BOOT-01 | SMBIOS, the stage banners in `cbmem -1` | a release or CI version, the same in every RW stage | another version string, stages that disagree | |
| BOOT-02 | `cbmem -T`: reset to the payload, valid training cache | M920x ≤ 12 s, W541 ≤ 6 s | M920x ≤ 20 s, W541 ≤ 12 s | above |
| BOOT-03 | `[ERROR]` and `[WARN ]` lines of `cbmem -1`, deduplicated | none, or known ones only | an unknown `[WARN ]` | an unknown `[ERROR]`, `[CRIT ]`, `[ALERT]`, `[EMERG]` |
| BOOT-04 | `journalctl -k -b -p warning`, the lines about ACPI, firmware, BIOS, i915, PCI, DMAR, `_DSM`, TPM, microcode... | none, or known ones only | an unknown warning | an unknown error |
| MEM-01 | `FspMemoryInit` (M920x) or the RAM init (W541; on `nri` from v1.4.0, patch 0189, before it the whole romstage) in `cbmem -T`, the cache state in `cbmem -1` | ≤ 2 s with a valid cache or on S3 resume | ≤ 5 s | above |
| MEM-02 | `dmidecode -t 17`, `/proc/meminfo`, *N DIMMs found* | Linux sees ≥ 90% of the modules | less, or a DIMM count that differs from the log | |
| CPU-01 | `/proc/cpuinfo`, MSRs 0x606, 0x610, 0xCE, 0x1A2, 0x1AD, the EC line of the log; the microcode of the firmware from the log, plus one after *Skip microcode update* (Cannon Lake with PRMRR, [docs/m920x.md](m920x.md#status)); as a detail, whether the TCC offset can be set (bit 30 of 0xCE) and its value in 0x1A2 | one microcode on every core, PL1 on | cores with different microcode, PL1 off | |
| IDLE-01 | MSRs 0x60D, 0x3F8-0x3FA, 0x630-0x632 and RAPL over `--seconds`, as `tools/idle-report.py` | PC6 and deeper ≥ 50% | ≥ 10% | below |
| S3-01 | `/sys/power/mem_sleep`, `/sys/power/suspend_stats` | `deep` offered, no failed suspend | no `deep`, a failed suspend | |
| PCI-01 | PCIe capability of every function, not waking sleeping ones | ASPM L1 and LTR on wherever both ends support them | one off | |
| PCI-02 | M920x: `PEG:` lines of `cbmem -1`, `00:01.0` | port off without a card, or a card behind it | the port on with nothing behind it | |
| FAN-01 | hwmon (`coretemp`, `nct6683`, `thinkpad`), `EC: CPU fan at N rpm` in the log | CPU < 80 °C, the fan turns | < 95 °C | ≥ 95 °C, or 0 rpm on the M920x |
| EC-01 | W541: `H8: EC Firmware ID` in the log, the EC string of SMBIOS type 11 | EC 1.15 (`GMHT30WW`) or later | older, without the fix of CVE-2019-6171 ([docs/flashing.md](flashing.md#before-you-start)) | |
| TPM-01 | `/sys/class/tpm`, the ACPI table, the event log, PCR0 | TPM 2.0 and `TPM2` (M920x), TPM 1.2 and `TCPA` (W541; enabled, active and owned in the details), a measurement log | missing or empty | |
| ME-01 | M920x: `ME:` and `CMOS: me_state` lines of the log; W541: the SMBIOS strings of patch 0181 or the `ME: HFSTS1-6` line, and `me_disable` from `SMMSTORE`; `00:16.0` | the state the option asks for, HECI hidden when disabled (W541: *Disabled (AltMeDisable, BUP)*) | another state, HECI visible when disabled | |
| VB-01 | vboot's work buffer in CBMEM (`cbmem -r 78007343`) | slot chosen, the previous boot not failed | the previous slot failed (fallback) | recovery mode |
| UPD-01 | ESRT, `OsIndications` | the last capsule written and running | a refused capsule, or a written one that is not running | |
| FLASH-01 | `BM-LOCKDOWN` lines, BIOS_CNTL, FLOCKDN and the Protected Ranges of the SPI controller as `update.py protection` reads them (both boards), the FMAP in CBMEM; when the kernel refuses the registers, the PR that coreboot logged against `WP_RO` (`INFO`, never `PASS`) | `WP_RO` in a write-protected range, registers locked | *Firmware protection* off, FLOCKDN off (also with `WP_RO` in a PR) | the protection failed |
| ELOG-01 | `--dump`: `RW_ELOG` (as `tools/elog.py`) | | a POST code left by a hang, a thermal trip, a failed cache update or a bad checksum in the last 5 boots | |
| VB-02 | `--dump`: `RW_NVRAM` and the releases in RO and the slots (as `update.py vboot`) | a valid record, the running release in a slot | no valid record, the previous slot failed | |
| OPT-01 | `--dump`: the coreboot options in `SMMSTORE` (4-byte values of GUID `ceae4c1d-...`) | the store healthy | not healthy, almost full | |
| ID-01 | `dmidecode -s` | serial number and UUID from the VPD | empty (VPD not written) | |
| ID-02 | `/sys/firmware/acpi/tables` | `DMAR`, `HPET` and the TPM table; MSDM checked if present | one missing, an MSDM key in the wrong format | |

Where the numbers come from: the M920x reached the payload in 9.4 s with
ci-149 at log level DEBUG and *Clear memory at power-on* on, its FSP-M took
0.2-0.45 s with the cache ([docs/m920x.md](m920x.md#boot-time)); the W541
reaches EDK2 in about 3.4 s, `mrc.bin` takes 0.85 s with its saved
training ([docs/flashing.md](flashing.md#first-boot-and-settings)); at idle
the M920x sits in PC9 83-87% and the W541 in PC6 90% with the screen off.

- **Training boots.** After a W541 update (its capsule clears
  `RW_MRC_CACHE`; from v1.4.0 an M920x one keeps it), or with a cache
  that does not match (*MRC: version mismatch*, *no data in*, *needs
  update* in the log), MEM-01 is `INFO` with the time it took, and BOOT-02
  judges the boot without it. The boot after must pass: the
  regression this tool was written for, ci-150, spent 15.2 s in
  `FspMemoryInit` at every boot with a valid cache instead of 0.2-0.4 s.
- **A busy machine.** With the cores more than 10% busy on average the
  C-state sample is `INFO`: run it again at idle (on a laptop with the
  screen on, nothing running).
- **Events.** Some lines tell of something that was done on purpose:
  *Setup options: N reset to defaults (RTC power lost)*, after a CMOS
  clear on the M920x ([docs/m920x.md](m920x.md#resetting-the-settings)),
  makes BOOT-03 `INFO`, with what it means (`EVENT_FW_LOG` in the
  script).
- **Known messages.** Some lines appear at every boot and are understood:
  `KNOWN_FW_LOG` and `KNOWN_KERNEL` in the script list them, per board,
  with the reason (the W541 ones are those of
  [docs/flashing.md](flashing.md#first-boot-and-settings)); they are
  printed with *noto* and do not count. A message added there needs its
  reason.
- **What it cannot see.** The fan speed now needs `sudo modprobe nct6683`
  on the M920x (otherwise the speed the firmware read at boot); the options
  and the event log need a copy of the flash; an S3 resume only shows if
  the machine has suspended in this boot.

A run on the M920x with ci-151 (a bisect build of v1.4.0 with the 15 s
`FspMemoryInit`), `--seconds 10`, details trimmed:

```text
ouroBIOS hw-report - ThinkCentre M920x (board m920x), 2026-10-30 19:17
firmware ouroBIOS-ci-151-d0aaa35-m920x-fsp, kernel 7.0.14-15-pve, acceso da 189 min

[PASS] BOOT-01  Firmware: ouroBIOS-ci-151-d0aaa35-m920x-fsp (build della CI)
[FAIL] BOOT-02  Tempo di avvio: 24.44 s dal reset al payload (soglie 12/20 s per ThinkCentre M920x)
         fino a romstage (bootblock, verstage)    0.65 s
         romstage                                15.49 s
           di cui FspMemoryInit                  15.24 s
         postcar e caricamento di ramstage        0.07 s
         ramstage                                 7.67 s
           di cui FspSiliconInit                  0.06 s
         caricamento del payload                  0.56 s
         Clear memory at power-on acceso (~0.5 s ogni 10 GB)
[PASS] BOOT-03  Log di coreboot: 2 messaggi diversi (0 errori), 0 non noti
[PASS] BOOT-04  Log del kernel: 4 messaggi del firmware su 13 avvisi (journalctl), 0 non noti
[FAIL] MEM-01   RAM init: FspMemoryInit 15.24 s con la cache valida (soglie 2/5 s)
         cache del training: 'RW_MRC_CACHE' valida, usata
[PASS] MEM-02   Memoria: 2 moduli, 40 GB; Linux vede 39.0 GB
[PASS] CPU-01   CPU: Intel(R) Core(TM) i3-8100 CPU @ 3.60GHz, PL1 65 W, PL2 65 W
[PASS] IDLE-01  Stati C del package: PC6 e oltre 84.1% (soglie 50/10%), il piu' frequente PC9 80.5%, package 0.94 W
[INFO] S3-01    Sospensione: S3 offerto (default); nessuna sospensione in questo avvio (prova: systemctl suspend)
[PASS] PCI-01   PCIe ASPM e LTR: ASPM L1 e LTR accesi su ogni link che li supporta (criterio del kernel: default)
[PASS] PCI-02   Porta PEG del riser: porta PEG spenta (nessuna scheda sul riser)
[PASS] FAN-01   Ventola e temperature: CPU 43 C (soglie 80/95 C), ventola 824 rpm all'avvio (log del firmware)
[PASS] TPM-01   TPM: TPM 2.x, tabella TPM2, PCR0 senza misure di coreboot
[PASS] ME-01    Intel ME: spento (soft temporary disable) come chiesto, HECI nascosto
[PASS] VB-01    vboot: slot A, avvio prima slot B confermato
[PASS] UPD-01   Aggiornamenti: v0.0.0, variante m920x-fsp
[WARN] FLASH-01 Protezione del flash: Firmware protection spenta (Security > Flash protection): riaccenderla dopo flashrom; WP_RO scrivibile
[SKIP] ELOG-01  Registro degli eventi: nessuna copia del flash (--dump, da sudo flashrom -p internal -r flash.bin)
[PASS] ID-01    SMBIOS e VPD: LENOVO 10S2S00V00, S/N ****ZK26
[PASS] ID-02    Tabelle ACPI: DMAR, HPET, TPM2 presenti; MSDM presente

Esito: FAIL - 2 FAIL, 1 WARN, 15 PASS, 1 INFO, 1 SKIP (uscita 2)
```

## How to test a release candidate

1. **Install it as a user would**: the capsule of the candidate on the
   previous release (UPD-02), or `update.py other-slot` for a CI build
   ([docs/update.md](update.md#a-release-from-its-image-in-the-other-slot)).
   Keep a copy of the flash from before and, for the tests that spoil a
   slot, the external programmer at hand
   ([docs/flashing.md](flashing.md#external-programmer)).
2. **First boot**: on the W541 it trains the memory, on the M920x only if
   the cache does not fit the new slot (the first v1.4.0 slot after rc3 or
   older, usually). `hw-report.py`: MEM-01 is `INFO` on a training boot,
   everything else as below.
3. **Second boot**, a reboot from Linux, then a **cold boot** (shut down,
   power on): `hw-report.py --markdown` after each. Every check must be
   `PASS` except those that follow a choice of the tester, each one
   explained in the notes (FLASH-01 is `WARN` while *Firmware protection*
   is off for flashrom). A `FAIL` stops the release.
4. **The manual tests** of the matrix for the board, in the order of the
   suites; the ones marked *not yet* on a board have never been run there
   and are worth a first try with care.
5. **The record**: the two `--markdown` reports and a table of the manual
   test IDs with their result go in the pull request of the release (or
   the issue of the candidate); a failed test with `sudo cbmem -1 > cbmem.txt`,
   the report and the commands that showed it.

A CI build tried on hardware (`ci-test/**` branches) needs the smoke
subset: steps 2 and 3 (BOOT, MEM-01, IDLE-01, PCI-02, VB-01 are in
`hw-report.py`) and the suites the change touches.

## Test matrix

*Board*: M920x, W541 or both. *Auto*: the `hw-report.py` check that runs
it (*partial* when the script gives the facts and a person the verdict),
or *manual*.

### Boot and boot time (BOOT)

*Dasharo:* CBP (coreboot base port), CBMEM (serial boot measure), BPM
(Proxmox booting performance).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| BOOT-01 | both | `cat /sys/class/dmi/id/bios_version`; `sudo cbmem -1 \| grep 'starting (log level'` | the candidate's version; romstage and ramstage print the same | BOOT-01 |
| BOOT-02 | both | `sudo cbmem -t` | to the payload: M920x ≤ 12 s, W541 ≤ 6 s with a valid cache | BOOT-02 |
| BOOT-03 | both | `sudo cbmem -1 \| grep -E '^\[(ERROR\|WARN )\]'` | only the known lines | BOOT-03 |
| BOOT-04 | both | `journalctl -k -b -p warning` | no unknown firmware-related warning | BOOT-04 |
| BOOT-05 | both | power on: logo, Esc opens the setup menu, the boot menu lists the disks | the logo of the board, the setup opens, every entry boots | manual |
| BOOT-06 | both | boot from NVMe, SATA and a USB drive (UEFI) | each boots its OS | manual |
| BOOT-07 | both | reboot from Linux, cold boot, power button held (forced off) then on | BOOT-02 and MEM-01 pass after each kind of reset | partial |
| BOOT-08 | both | *General* → *Boot* → *Boot menu prompt* off, reboot, then on ([docs/m920x.md](m920x.md#boot-options); W541 from v1.4.0, patch 0182, [docs/flashing.md](flashing.md#first-boot-and-settings)) | off: no "Press ESC for Boot Options/Settings" on the logo, and Esc during the timeout still opens the boot menu (W541: from the keyboard of the laptop too); on: the line again; not yet tried | manual |

### Memory and training cache (MEM)

*Dasharo:* HCL (memory HCL), MEM (memtest payload).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| MEM-01 | both | `sudo cbmem -t`, `sudo cbmem -1 \| grep 'MRC:'` | RAM init ≤ 2 s with the cache valid (*does not need update*) or on S3 resume; W541 `nri` from v1.4.0 (patch 0189): *before* and *after RAM initialization* in `cbmem -t` on a training boot, a fast boot and an S3 resume, and MEM-01 no longer `SKIP`, not yet tried | MEM-01 |
| MEM-02 | both | `sudo dmidecode -t memory` | every module with its size and speed; Linux sees at least 90%; W541 from v1.4.0 (patch 0187, both variants): the same records as before with the four 8 GiB DIMMs, and with DIMMs of two sizes in a channel, if at hand, each slot with its own module; not yet tried | MEM-02 |
| MEM-03 | both | the first boot after an update, then the next | W541: the first trains (*no data*, then *updated*), the next takes the fast path. M920x from v1.4.0: no training (*does not need update*) unless the version changed (*version mismatch*, then *updated*, once) | partial (MEM-01 on both boots) |
| MEM-04 | both | `stress-ng --vm 4 --vm-bytes 75% --verify -t 30m` ([docs/raminit.md](raminit.md)) | no errors, no MCE in the kernel log | manual |
| MEM-05 | M920x | another processor or *Hyper-Threading* toggled ([docs/m920x.md](m920x.md#other-processors-and-cards)) | one training boot (the cache version changes), then fast boots | partial |
| MEM-06 | W541 | `nri` of v1.4.0 (patches 0185, 0186) with `RW_MRC_CACHE` empty, as after its capsule: a cold boot, `sudo python3 tools/ddr-report.py --save nri-v1.4.0.txt` and `--compare` with a dump of `mrc` ([docs/raminit.md](raminit.md#measuring)); a reboot, an S3 resume, `stress-ng --vm 4 --vm-bytes 75% --verify -t 30m`; then the cache of an older `nri` slot left for a v1.4.0 slot (only the RW slot written), and the other way round | the first boot trains and logs *Memory test passed*; ranks 1-3 with centering values of their own, the round trips at 44/45 with IO latency 4 + 21 as before; the fast boot, the resume and stress-ng without errors; a v1.4.0 slot on an older cache logs *MRC: version mismatch: 2 vs 3* and trains, an older slot on a v1.4.0 cache *3 vs 2*, then *Using cached memory parameters* at the next boot; not yet tried | partial (MEM-01) |
| MEM-07 | W541 | `nri`, only if a 16 GiB DDR3L SO-DIMM is at hand: in one slot, the 8 GiB ones in the others; `sudo cbmem -1 \| grep 'DIMM ignored'` on the first, training boot; `sudo dmidecode -t 17`; with the module in place, `stress-ng --vm 4 --verify -t 30m` (or a memtest86+ pass) and `ddr-report.py` (patch 0188) | the laptop boots on the others, *CHxSy: DIMM ignored, 11 column address bits, Haswell has 10* after the start of the CBMEM console; type 17 lists the other DIMMs in their own slots, not the 16 GiB one; no errors, margins close to those without the module; with the four 8 GiB DIMMs no *DIMM ignored* line and 32 GiB as before; not yet tried | manual |
| MEM-08 | both | *Security* → *Memory protection* → *Clear memory at power-on* on each setting, two boots each; after each boot `sudo cbmem -1 \| grep -E 'MOR:\|DRAM clear:'` and `od -An -tx1 /sys/firmware/efi/efivars/MemoryOverwriteRequestControl-*`. With *When the OS asks*: Linux with `CONFIG_RESET_ATTACK_MITIGATION`; Windows with BitLocker, a clean restart then a reset ([docs/flashing.md](flashing.md#clearing-the-memory-at-power-on)) | *Always*: *option always: clearing* at every boot, no variable; *Never*: *option never: not clearing*, no variable; *When the OS asks*: the first boot *no MemoryOverwriteRequestControl variable* and *clearing*, then the variable under the OS; Linux: `07 00 00 00 01` while it runs and *request of the OS yes: clearing* at every boot; Windows: *request of the OS no: not clearing* after the clean restart (the boot that much shorter), *yes: clearing* after the reset. The hardware test of v1.4.1 forced the setting in a test build (patch 0195, `edk2/0042`) and cleared the bit from Linux by hand for the Windows case | partial (BOOT-02) |

### CPU and power limits (CPU)

*Dasharo:* CPU (CPU status), CPF (CPU frequency), CPT (CPU temperature).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| CPU-01 | both | `grep microcode /proc/cpuinfo`; `sudo rdmsr 0x610` | one microcode on every core; PL1 and PL2 as set in *Energy Saver* | CPU-01 |
| CPU-02 | both | `stress-ng --cpu 0 -t 5m` with `sudo turbostat --interval 5` | package power up to PL1 (PL2 at first), frequency at base or turbo, no throttling below TjMax | manual |
| CPU-03 | both | another PL1/PL2 in the setup, reboot | MSR 0x610 follows (CPU-01 details) | partial |
| CPU-04 | both | SpeedStep: `cpupower frequency-set -g powersave` at idle | the frequency drops (HWP) | manual |
| CPU-05 | both | M920x: *Hardware* → *Cooling* → *TCC activation offset* 10, reboot: `sudo rdmsr -f 29:24 0x1a2`, the `TCC Offset` device in `/sys/class/thermal/cooling_device*/`, `stress-ng --cpu 0 -t 5m` with `turbostat`; again after S3; then 0 ([docs/m920x.md](m920x.md#fan)). W541, no option: `sudo rdmsr -f 30:30 0xce` and the TCC line of CPU-01 | M920x: 10 in bits 29:24, also after S3, and the cooling device at 10; under load the package levels near 90 °C instead of 94-95; at 0 the field reads 0. W541: bit 30 and the offset (bits 27:24 of 0x1a2) recorded, most likely 0 ([docs/roadmap.md](roadmap.md#tcc-offset-on-the-w541)); not yet tried | manual (W541: CPU-01 details) |

### Idle and package C-states (IDLE)

*Dasharo:* SPM (power management).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| IDLE-01 | both | `hw-report.py --seconds 60` at idle | PC6 and deeper ≥ 50%: M920x PC9 about 85% and package about 0.5 W, W541 PC6 about 90% with the screen off | IDLE-01 |
| IDLE-02 | both | `sudo python3 tools/idle-report.py --seconds 60` ([docs/flashing.md](flashing.md#power-at-idle)) | no device keeping the package awake: ASPM, LTR, runtime PM, SATA LPM as that section describes | partial (PCI-01) |

### Suspend (S3)

*Dasharo:* SUSP and SLM (sleep mode).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| S3-01 | both | `cat /sys/power/mem_sleep` | `deep` offered | S3-01 |
| S3-02 | both | `systemctl suspend`, wake with the power button; W541 also the lid and Fn; `sudo rtcwake -m mem -s 30` | back to the desktop five times; `sudo cbmem -1` shows *S3 Resume*; `suspend_stats/fail` stays 0 | partial (S3-01 after) |
| S3-03 | both | after S3-02: network, USB, display, audio, Wi-Fi | all work as before the suspend | manual |

On the M920x S3 has not been tried yet ([docs/m920x.md](m920x.md#status));
the W541 resumes since v1.0.9.

### USB (USB)

*Dasharo:* USB (HID and mass storage), UDT (USB detection), UBT (USB boot).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| USB-01 | both | a keyboard on each port in the setup menu and in Linux | it types in both | manual |
| USB-02 | both | a USB 3 drive on each port: `lsusb -t` | it enumerates at 5000M or more on the USB 3 ports | manual |
| USB-03 | both | boot from a USB drive | it boots (BOOT-06) | manual |
| USB-04 | M920x | *Hardware* → *Devices*: front or rear USB off, reboot, on again | the ports go dead and come back | manual |
| USB-05 | both | a bootable USB drive plugged in: `efibootmgr`; *General* → *Boot* → *Boot from USB drives* off, reboot twice; on again ([docs/m920x.md](m920x.md#boot-options)). W541 (v1.4.0, patch 0182): also the first boot of v1.4.0, with no variable stored, and the stick in a port of the laptop and in one of the dock | on (on the W541 also with no variable stored): its entry in `efibootmgr` and in the Esc menu; off: that entry gone, those of the disks, the Shell, iPXE and CSMWrap unchanged, and no new `Boot####` record at the second boot (`update.py vars --all` on a copy of the flash); on again: the entry back; not yet tried | manual |

### PCIe, NVMe and SATA (PCI)

*Dasharo:* PEX (PCI Express ports), NVM (NVMe), SHT (SATA hot plug), MSS (M.2 slot).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| PCI-01 | both | `sudo lspci -vv \| grep -E 'LnkCtl:\|LTR'` | ASPM L1 and LTR on wherever both ends support them | PCI-01 |
| PCI-02 | M920x | `sudo cbmem -1 \| grep PEG:`; `lspci -s 00:01.0` | no card: *port off* and no `00:01.0` | PCI-02 |
| PCI-03 | M920x | a card on the riser, *PCIe riser slot* on Auto, then Enabled and Disabled | Auto and Enabled: the card in `lspci` with its link width; an F processor shows the firmware on it ([docs/m920x.md](m920x.md#other-processors-and-cards)); not yet tried | manual |
| PCI-04 | both | NVMe and SATA disks: `lsblk`, boot from each, `sudo smartctl -a` | found, boot, link at their speed | manual |
| PCI-05 | W541 | `sudo python3 tools/peg-report.py` with the NVIDIA GPU on and under load | the link trains to 8 GT/s, no AER errors; D3cold at idle | manual |
| PCI-06 | both | Wi-Fi card: `journalctl -k -b \| grep -i dsm` | M920x: no `_DSM` warning (the ACPI node of patch 0168) | BOOT-04 |
| PCI-07 | M920x | a graphics card, then a network or storage card, on the riser; *General* → *Boot* → *Option ROMs of the cards* on *All*, then *Graphics cards only* | the graphics card shows the logo and the setup with both; the ROM of the other card runs only with *All* (its boot entry); an NVMe drive on the riser boots with both; without a card both boot the same; not yet tried | manual |
| PCI-08 | W541 | *Security* → *Virtualization* → *Untrusted ExpressCard and Thunderbolt* on, *Intel VT-d* on, `intel_iommu=on` (patch 0184): `sudo acpidump -b`, `iasl -d ssdt*.dat`, the `_DSD` of RP03 and RP05; an ExpressCard (USB 3.0 or eSATA): `cat /sys/bus/pci/devices/<card>/removable`, `cat /sys/kernel/iommu_groups/*/type`; `sudo cbmem -1 \| grep 'coreboot table'`; then with VT-d off, and with the ExpressCard port off | `ExternalFacingPort` in the `_DSD` of RP03 and RP05 only, and none with VT-d or the port off; the card `removable`, its IOMMU group of type `DMA`, and it works; *coreboot table: N bytes.* and no *didn't fit*; not yet tried | manual |

### Display (DISP)

*Dasharo:* DSP (display ports and LCD).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| DISP-01 | M920x | a monitor on HDMI: logo, setup menu, Linux desktop | the image at each step, the native resolution in Linux | manual |
| DISP-02 | M920x | a monitor on each DisplayPort | the same; from v1.4.0 the VBT of coreboot bug #670 (patch 0174), not yet tried | manual |
| DISP-03 | W541 | the panel and each external output, with and without the NVIDIA GPU | the image at each step | manual |
| DISP-04 | both | `journalctl -k -b \| grep i915` | no `WARN` or error of i915 | BOOT-04 |

### Audio (AUD)

*Dasharo:* AUD (audio subsystem).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| AUD-01 | M920x | `speaker-test -c 2 -t wav` on the internal speaker and the front headphone jack; `arecord -d 5` from the front microphone jack | sound on each output; the recording plays back; plugging switches the output (jack detection); not yet tried with a plug | manual |
| AUD-02 | W541 | the same on the speakers, the headphone jack and the internal microphone; HDMI or DP audio | the same | manual |
| AUD-03 | W541 | software mute (patch 0190): `journalctl -k -b \| grep -i 'console audio'`; `cat /proc/asound/cards`; the mute key, then muted through an S3 suspend and a reload of `thinkpad_acpi` | no *Console audio control enabled* and no ThinkPad EC card; the mute key mutes and its LED follows, and stays lit after S3 and after the reload; not yet tried | manual |

### Network and Wake-on-LAN (NET)

*Dasharo:* NET (network controller), PXE (network boot), WLE (M.2 Wi-Fi).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| NET-01 | both | `ip link`, `ethtool <if>` | the I219 up (`e1000e`) at 1000 Mb/s with the machine's own MAC address | manual |
| NET-02 | M920x | *Energy Saver* → *Wake on LAN from off* on; `sudo poweroff`; a magic packet from another machine | the machine starts (patches 0154-0155); not yet tried | manual |
| NET-03 | both | the same from S3 | it resumes | manual |
| NET-04 | both | Wi-Fi: scan and connect | connected; M920x: *Hardware* → *Devices* → *Wireless* off hides the card | manual |
| NET-05 | both | network boot (iPXE) from the boot menu | iPXE starts and gets an address | manual |

### Fan and EC (FAN)

*Dasharo:* FAN (fan speed), CFN (coreboot fan control), FNM (fan control
measure), ECR (EC and Super I/O initialization), PSF (power state after
power fail).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| FAN-01 | both | `sudo cbmem -1 \| grep EC:`; `sensors` | the fan turns, the CPU below 80 °C at idle | FAN-01 |
| FAN-02 | M920x | `sudo modprobe nct6683`; `stress-ng --cpu 0 -t 2m` with `watch sensors` | *Better acoustics*: about 850 rpm at idle, about 3000 rpm with the CPU at 94 °C, below 100 °C ([docs/m920x.md](m920x.md#fan)) | partial (FAN-01 reads the fan once loaded) |
| FAN-03 | M920x | *Hardware* → *Cooling* → *Fan mode (ICE)*: *Better cooling*, *Full speed* | about 1400 and 7500 rpm at idle | manual |
| FAN-04 | M920x | *Energy Saver* → *After a power loss*: each value, then the power cord out and in | off, on or the state before, as chosen; not yet tried | manual |
| FAN-05 | W541 | `cat /proc/acpi/ibm/fan` under load | the fan follows the temperature | partial (FAN-01) |
| FAN-06 | W541 | `sudo dmidecode -t 11 \| grep 'Embedded Controller'`; `sudo cbmem -1 \| grep 'EC Firmware ID'` | EC 1.15 (`GMHT30WW`) or later: it fixes CVE-2019-6171, and only the Lenovo firmware updates it ([docs/flashing.md](flashing.md#before-you-start)) | EC-01 |
| FAN-07 | W541 | first EC 0x00-0x0f with each value of *USB always on* (`sudo modprobe ec_sys`, `sudo xxd -l 16 /sys/kernel/debug/ec/ec0/io`: read only); then *Energy Saver* → *Power* → *Power on with AC attached* on (patch 0183): shut down, unplug the AC adapter, plug it in; the same from hibernation; with the adapter out, suspend to S3 and plug it in; then off | on: the laptop starts, and resumes from hibernation; off: nothing; the S3 result recorded, not judged; not yet tried | manual |
| FAN-08 | W541 | *General* → *Sound* → *Keyboard beep* off and on (patch 0183), each with a Fn combination that the EC does not handle; on a test build, also with `beepmask1` 0x87, which the Lenovo firmware writes | on: a beep; off: none. If it beeps only with 0x87, the option needs that bit of the mask too; not yet tried | manual |
| FAN-09 | W541 | *Energy Saver* → *Power* → *USB always on*: *AC and battery*, then *AC only* (patch 0183); on battery, a load (a phone) on the yellow port with the laptop off, in hibernation and in S3; the help of each value | *AC and battery*: the load gets power in power-off and hibernation on battery; *AC only*: none there; S3 recorded, not judged; not yet tried | manual |
| FAN-10 | W541 | EC events (patch 0190): dock and undock; `_Q4E`, `_Q4F` and `_Q40` called through `acpi_call`; EC 0x88-0x8b (`ec_sys`, read only) at idle and through 10 minutes of `stress-ng --cpu 0`, on AC and on battery, with `/sys/firmware/acpi/interrupts/gpe11` before and after; `journalctl -k -b`; a boot of macOS with OpenCore and of Windows with the Lenovo drivers | *docked into hotplug port replicator* and *undocked*; the alarms logged, without an ACPI error; EC 0x8a 0 at normal temperatures (otherwise the 0x6022 report goes, the Notify stays) and no THERMAL line; the EC GPE count also tells whether the EC repeats its CPU limit events without the acknowledgement that the Lenovo firmware writes; macOS (no `AE_ALREADY_EXISTS` from the SSDTs of the configuration) and Windows without ACPI errors or thermal warnings; not yet tried | manual |

### TPM and measured boot (TPM)

*Dasharo:* TPM and TPD (TPM support), TPMCMD (TPM2 commands), MBO
(measured boot).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| TPM-01 | both | `ls /dev/tpm0 /dev/tpmrm0`; `/sys/firmware/acpi/tables` | M920x: TPM 2.0 and `TPM2`; W541: TPM 1.2 and `TCPA`; the firmware's event log | TPM-01 |
| TPM-02 | M920x | `sudo tpm2_getcap properties-fixed`; `sudo tpm2_pcrread sha256` | answers; PCR 1, 4, 5 and 7 extended by the payload | manual |
| TPM-03 | both | PCR0 against the value of a lone separator | **a known gap**: `CONFIG_TPM_MEASURED_BOOT` is off, coreboot measures nothing and PCR0 holds only the payload's separator; a release that turns it on must show other values | TPM-01 (reported as a note) |

### Intel ME (ME)

*Dasharo:* MNE (ME neuter and disable).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| ME-01 | both | `sudo cbmem -1 \| grep -E 'me_state\|Operation Mode\|HFSTS1-6'`; `lspci -s 00:16` | M920x *Disabled*: operation mode 3, no `00:16.0`; *Enabled*: mode 0, working state 5, `mei_me` on `00:16.0`. W541 from v1.4.0 (patch 0181): *Disabled (AltMeDisable, BUP)*, `00:16.0` hidden with *Intel ME interface (HECI)* off, shown with it on | ME-01 (W541 before v1.4.0: values only) |
| ME-02 | M920x | *Security* → *Management Engine*: *Disabled*, reboot, *Enabled*, reboot | ME-01 passes after each; *Enabled* again not yet tried ([docs/m920x.md](m920x.md#intel-me)) | partial |
| ME-03 | W541 | *Intel ME interface (HECI)* off and on | `00:16.0` hidden and shown; no `mei` errors | manual |
| ME-04 | both | *General* → *About this ThinkCentre* (W541: *About this ThinkPad*) → *Management Engine* and its help; `sudo dmidecode -t 11`; `sudo python3 tools/update.py status` ([docs/m920x.md](m920x.md#intel-me), [docs/flashing.md](flashing.md#first-boot-and-settings)). W541 (patch 0181) also: a warm reboot with HECI hidden; with HECI on, `sudo setpci -s 00:16.0 40.l 48.l 60.l 64.l 68.l 6c.l`; on `nri`, a cold boot and a warm reboot | the state of ME-01 (M920x: *Disabled (soft temporary disable)* with the option on *Disabled*, *Enabled* with it on; W541: *Disabled (AltMeDisable, BUP)*); the six registers of the help and of `ME HFSTS:` those of `sudo cbmem -1 \| grep HFSTS`; the `ME:` line of `update.py status`. W541: the two ME strings before the EC one, and no more SMBIOS structures than before; the registers still read after the warm reboot; `setpci` gives the same six words; on `nri`, what *ME: Checking whether CPU was replaced...* prints, and no *CPU was replaced, forcing a cold boot*, which would train the memory at every boot; whether ME 9 reports mode 2. Not yet tried | manual |

### vboot slots and fallback (VB)

*Dasharo:* VBO (verified boot).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| VB-01 | both | `sudo cbmem -r 78007343 > vbwork.bin && python3 tools/update.py vboot-work vbwork.bin` | the slot chosen from `RW_NVRAM`, no recovery, the previous boot not failed | VB-01 |
| VB-02 | both | `python3 tools/update.py vboot flash.bin` on a copy taken in this boot | a valid record; the running release in its slot | VB-02 (`--dump`) |
| VB-03 | both | the A/B switch with the same capsule ([docs/vboot.md](vboot.md#testing-on-the-laptop), step 4) | the other slot boots and stays after three more reboots | manual |
| VB-04 | both | a whole slot rewritten by a capsule (step 5) | `update.py vboot --image`: every block of the slot equal to the release | manual |
| VB-05 | both | fallback: spoil the running slot (step 6), programmer at hand | the other slot boots, *precedente: slot X, fallito*; the capsule repairs it | partial (VB-01 shows the fallback) |

### Updates (UPD)

*Dasharo:* CUP (capsule update), FFW (firmware update with fwupd).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| UPD-01 | both | `sudo python3 tools/update.py status` | the candidate's version, the last capsule *riuscito* and running | UPD-01 |
| UPD-02 | both | from the previous release: `sudo python3 tools/update.py stage FILE.cap`, reboot | the new slot runs; MEM-03; settings, VPD and event log kept (OPT-02, ID-01, ELOG-01) | partial |
| UPD-03 | both | the setup: *Firmware Update* → *Update from a USB drive* ([docs/update.md](update.md#from-the-setup-with-a-usb-drive)) | the same | manual |
| UPD-04 | both | fwupd: `sudo fwupdmgr install FILE.cab` ([docs/update.md](update.md#fwupd)) | `fwupdmgr get-history` shows success; UPD-01 | partial |
| UPD-05 | both | `sudo python3 tools/update.py rollback flash.bin`, reboot | the release before runs, from the other slot, nothing written to the slots; `RW_MRC_CACHE` emptied by the capsules that name it (W541, M920x before v1.4.0) | manual |
| UPD-06 | both | capsules that must be refused: the other board, the other W541 variant, an older version without `--allow-older` | `update.py` refuses before the reboot; staged by hand, the firmware refuses and UPD-01 shows why | partial |
| UPD-07 | M920x | between two builds with patch 0173: a capsule (`update.py info` lists `RW_SECTION_A RW_SECTION_B`), then `update.py other-slot` and `other-slot --retrain`, then *Go back to* in the setup ([docs/m920x.md](m920x.md#updates)) | no *Clearing the memory training data* on the update screen; after the capsule, `other-slot` and *Go back to*: *does not need update* and no training; after `--retrain`: one training, then the fast path; not yet tried | partial (MEM-01) |

### Flash protection (FLASH)

*Dasharo:* HWP (flash write protection), BLS (BIOS lock), SMM (SMM BIOS
write protection).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| FLASH-01 | both | `sudo cbmem -1 \| grep BM-LOCKDOWN`; `sudo python3 tools/update.py protection` | with the default *Firmware protection* on: *Enabled bootmedia protection*, `WP_RO` read-only in a PR, the SPI configuration locked (FLOCKDN 1) | FLASH-01 |
| FLASH-02 | both | *BIOS Lock* on, then `flashrom -p internal -r` and a capsule | the flash reads, writes from the OS are refused, the capsule installs, settings still save | manual |
| FLASH-03 | both | *Firmware protection* off and on again (as for a flashrom update of the read-only part) | FLASH-01 `WARN` while off, `PASS` once on again | partial |
| FLASH-04 | both | `sudo python3 tools/update.py protection --expect-ro on`, with *Firmware protection* on, then off; with *BIOS Lock* on; after an S3 resume ([docs/update.md](update.md#flash-protection)) | on: exit 0, `WP_RO` in a locked PR (M920x `0x1700000-0x17fffff`; W541 PR0 `0x8bff0b60`, `0xb60000-0xbfffff`, GCS BILD 1), FLOCKDN 1; off: exit 1; registers that cannot be read: exit 2 with the reason (W541: a refused page of `/dev/mem`; then once with `iomem=relaxed`); *BIOS Lock* on: `BIOS Lock: acceso`, flashrom refused, the capsule still installs (W541: BIOS_CNTL 0x2a on, 0x09 off, as predicted from the code); the same after S3; not yet tried with the options on (M920x), not yet tried at all (W541) | partial (FLASH-01) |

### Setup options (OPT)

*Dasharo:* CBO (custom boot order), PSW (setup password).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| OPT-01 | both | `hw-report.py --dump flash.bin`; `python3 tools/update.py vars flash.bin` | the store healthy, the coreboot options listed | OPT-01 (`--dump`) |
| OPT-02 | both | change options with a visible effect (*Console Log Level*, *Management Engine*, *PCIe riser slot*, a device off), save, reboot twice | the effect at each boot (BOOT-01 log level, ME-01, PCI-02) and the value in OPT-01 | partial |
| OPT-03 | both | OPT-01 before and after a capsule update | the same options with the same values | partial (two `--dump` runs) |
| OPT-04 | both | the boot order, the supervisor password | kept across reboots and updates; the password asked before the setup opens | manual |
| OPT-05 | both | M920x, before: `sudo cbmem -1 \| grep GEN_PMCON` with bit 2 of the second word clear, `efibootmgr -v`, the Secure Boot state; then a CMOS clear ([docs/m920x.md](m920x.md#resetting-the-settings)) and two boots. W541, only on a test build with `CONFIG_DRIVERS_EFI_RESET_OPTIONS_ON_RTC_FAILURE=y` (patch 0180; off in the release builds): first whether software can set the RTC power loss bit (`00:1f.0` 0xa4 bit 2: write it, read it back, reboot); then the same with the AC adapter, the batteries and the coin cell out. The way out of a boot that hangs at POST 0x37 (the deletion), to know before: hold the power button 4 s with the AC adapter or a battery still attached | M920x, first boot: *Setup options: N reset to defaults (RTC power lost)*, *RTC: power failure cleared* with bit 2 clear, no *CMOS: me_state* line, an *RTC Reset* in the event log, the setup at its defaults (*Firmware protection* on), the Secure Boot keys and the other boot entries kept (iPXE, CSMWrap and USB entries back if they were off); extra restarts from FSP or the ME allowed. Second boot: no reset line, *CMOS: me_state* again. Then *Firmware protection* off before any flashrom write. W541: if software can set the bit, the option stays off (a reboot would turn *BIOS Lock* off); first boot: *Setup options: N reset to defaults (RTC power lost)* (N may be 0 after an extra reset by `mrc.bin` or the NRI) or *RTC power lost: setup options reset to defaults*, *RTC: failed = 0x1*, an *RTC Reset* in the event log, the setup at its defaults; the laptop may power on by itself when the power comes back; the second boot and an S3 resume reset nothing; after a hang, *Setup options: not reset, last boot hung there* (removing every supply would repeat the deletion). Not yet tried on either | partial (BOOT-03) |

### Event log (ELOG)

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| ELOG-01 | both | `python3 tools/elog.py flash.bin` | no POST code left by a hang, no thermal trip, no failed cache update in the last boots | ELOG-01 (`--dump`) |
| ELOG-02 | both | a cycle of reboot, cold boot, suspend and shutdown, then a copy of the flash | a *System boot* for each boot, *ACPI enter* S3 and S5 with their wakes | partial |

### VPD, SMBIOS and MSDM (ID)

*Dasharo:* DMI (SMBIOS verification).

| ID | Board | How to run | Pass criteria | Auto |
|---|---|---|---|---|
| ID-01 | both | `sudo dmidecode -t 0,1,2,3` | vendor coreboot, the version of BOOT-01; product, serial number and UUID from the VPD ([docs/flashing.md](flashing.md#serial-number-and-machine-type-vpd)) | ID-01 |
| ID-02 | both | `ls /sys/firmware/acpi/tables` | `DMAR`, `HPET`, the TPM table; `MSDM` when the VPD has a key | ID-02 |
| ID-03 | both | the label of the machine against ID-01 | MTM (product name) and serial number match | manual |
| ID-04 | M920x | Windows in a VM given the MSDM table ([docs/m920x.md](m920x.md#serial-number-and-machine-type-vpd)) | it activates by itself | manual |

## Coverage of hw-report.py

| Suite | Automated | Partial | Manual |
|---|---|---|---|
| BOOT | 01-04 | 07 | 05, 06, 08 |
| MEM | 01, 02 | 03, 05, 06 | 04, 07 |
| CPU | 01 | 03 | 02, 04, 05 |
| IDLE | 01 | 02 | |
| S3 | 01 | 02 | 03 |
| USB | | | 01-05 |
| PCI | 01, 02, 06 | | 03-05, 07, 08 |
| DISP | 04 | | 01-03 |
| AUD | | | 01-03 |
| NET | | | 01-05 |
| FAN | 01, 06 | 02, 05 | 03, 04, 07-10 |
| TPM | 01, 03 | | 02 |
| ME | 01 | 02 | 03, 04 |
| VB | 01, 02 | 05 | 03, 04 |
| UPD | 01 | 02, 04, 06, 07 | 03, 05 |
| FLASH | 01 | 03, 04 | 02 |
| OPT | 01 | 02, 03, 05 | 04 |
| ELOG | 01 | 02 | |
| ID | 01, 02 | | 03, 04 |

`hw-report.py` has run on the M920x only. On the W541 the parts written
for it from the code and these docs are not yet tried there: the SPI
registers of Lynx Point through the probe of `update.py` (one page at
RCBA + 0x3000, which a kernel with `IO_STRICT_DEVMEM` refuses while
`intel-spi` and `iTCO_wdt` hold it), the ME state from the SMBIOS strings
of patch 0181 (or the ME lines with names of `lynxpoint/me_status.c` on
older slots), the EC version (EC-01), the RAM init timestamps of patch
0189, the `TCPA` table and TPM 1.2 PCRs, the fan of `thinkpad_acpi`, and
the boot time thresholds; MEM-01 has thresholds measured on FSP only. The
W541 cases of `tools/ci-check.sh` use logs built from the strings of the
sources, to be replaced by real ones.
