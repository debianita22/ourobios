# Hardware tests after v1.6.2, on the W541

What is still to run on the ThinkPad W541 of the port after v1.6.2, and
the tests of the candidate of v1.6.3 (patches 0266-0269). The M920x has
its own file, [test-v1.6.3-m920x.md](test-v1.6.3-m920x.md). The IDs are
those of [docs/testing.md](testing.md); the ones that are new here
(TBL-01, WDT-02, WDT-03, VAR-01, CMOS-01) are defined in this file.

Written for an agent that works on the machine by itself, under Linux
(CachyOS), with `sudo`. It runs every row marked **agent** without
asking, in the order of the file, and leaves the rows marked **owner**
(the setup menu, the lid, the battery, macOS) in the record as *not run,
needs the owner*. A row it cannot run is recorded with the reason, not
skipped in silence, and never turned into a PASS by changing the test.

## Rules

These hold whatever else the agent decides.

1. **A copy of the flash first**, and after every write:
   `sudo modprobe -r spi_intel_platform spi_intel; sudo flashrom -p internal -r FILE`,
   12582912 bytes (8388608 means flashrom went through `/dev/mtd0`: the
   `modprobe -r` did not take). Keep `flash-before.bin` off the machine
   too, if a place is reachable.
2. **The only writes of the flash**: a capsule (`update.py stage`,
   `update.py rollback`: the firmware writes the slot that is not
   running) and the flashrom command that `update.py other-slot` prints,
   as it is. Never `WP_RO`, `--ifd`, the descriptor, the ME, the GbE or
   the whole image; never flashrom with a layout or a region of your
   own. Those are a brick risk and no part of these tests; the external
   programmer is not available to an agent.
3. **No setup option is changed from the OS.** The options are
   boot-service variables; the only way to change one is the setup menu,
   by the owner. No tool that issues SMMSTORE SMIs against the variable
   store, no change of Secure Boot keys, no change of the ME state.
4. flashrom must end with `VERIFIED`; if not, the same command once
   more; if it fails again, stop, do not reboot, and report.
5. Reboot right after a write, without suspending.
6. **A boot that does not come back**: nothing to do from the agent's
   side. After two failed boots vboot returns to the slot of before by
   itself; otherwise the owner powers the machine off (4 s) and on. Say
   in the journal, before every reboot, power-off and reset, what was
   about to happen, so that whoever finds the machine knows.
7. **Stop the whole run** and report when: a `FAIL` of FLASH-01 with the
   protections on, a slot that vboot marks failed, a machine check or a
   memory error, a flashrom write that does not verify, or the date of
   the RTC wrong after a CMOS step.
8. **The repository**: the record only (below). No tag, no release, no
   push to `main` or to a `ci-test/**` or `ci-edk2/**` branch (a push
   there starts a build), no force push, no change outside
   `docs/tests/v1.6.3/w541-nri/`.

## The machine and the builds

- **Running**: v1.6.2 `nri` in slot A (a capsule from rc1, 2026-11-09),
  v1.6.2-rc1 in slot B; the read-only part is the one of v1.5.0 and
  starts only `nri` slots, so nothing here runs on `mrc`. Check before
  anything else: `sudo python3 CLONE/tools/update.py status` and
  `python3 CLONE/tools/update.py vboot flash-before.bin`. **Both slots
  must hold v1.6.1 or later** for WDT-02 (an older slot has no code that
  stops the watchdog).
- **Candidate**: the CI build of `ci-test/v1.6.3-consolidation`
  (`24a28d6`, run 42692289173, build `ci-314-24a28d6`): v1.6.2 plus
  patches 0266-0269. Install it only if the run ended green:
  `gh run view 42692289173 -R debianita22/ourobios --json conclusion -q .conclusion`
  must say `success`. A CI build has no capsule. If a pre-release
  `v1.6.3-rc*` exists (`gh release list -R debianita22/ourobios`), use
  its capsule instead: it installs with *BIOS Lock* on and needs nobody.
- **Tools**: a clone at `next`; `python3`, flashrom 1.2 or later,
  `cbmem`, `gcc`, `ethtool`, `acpica`, `fwts`, chipsec, `stress-ng`,
  `gh`. What is missing and cannot be installed makes its rows *not
  run*.

```sh
git -C CLONE fetch origin && git -C CLONE checkout next && git -C CLONE pull --ff-only
mkdir -p ~/ourobios-test-v1.6.3/w541-nri && cd ~/ourobios-test-v1.6.3/w541-nri
```

## Across reboots, and the record

The run has reboots, power-offs and one reset that the agent does not
survive. Keep a journal, `STATE.md` in the work folder: before each of
them the step in progress, what the next boot must show and the time;
after the boot, read it and go on. Whatever is set up to start again
after a boot (the run of v1.6.1 used a systemd one-shot) is removed at
the end.

The record is `docs/tests/v1.6.3/w541-nri/README.md` in the clone, as
the ones of v1.6.1 and v1.6.2: a table *ID, Result (PASS, FAIL, INFO,
not run), Notes* with the numbers read, then a paragraph for anything
that needs one, and the files next to it (the `hw-report` Markdown
reports, `cbmem -1` of the boots that matter, the fwts and chipsec logs;
no copy of the flash). Commit it on `next` with the git identity of the
repository (`git config user.name` and `user.email` must be the
owner's, not a placeholder; no `Co-authored-by` or other trailer of an
AI), `git pull --rebase` before the push, that folder only.

## The port helper

The watchdog register and the CMOS byte are read and written with real
port accesses. `pio.c`, built in the work folder (`gcc -O2 -o pio pio.c`):

```c
/* pio r PORT | pio w PORT VALUE (32 bit) | pio cr INDEX | pio cw INDEX VALUE (CMOS) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/io.h>

int main(int argc, char **argv)
{
	if (argc < 3 || iopl(3)) {
		perror("pio");
		return 1;
	}
	unsigned long a = strtoul(argv[2], NULL, 0);
	unsigned long v = argc > 3 ? strtoul(argv[3], NULL, 0) : 0;

	if (!strcmp(argv[1], "w") && argc > 3)
		outl(v, a);
	if (argv[1][0] == 'r' || argv[1][0] == 'w') {
		printf("0x%08x\n", inl(a));
		return 0;
	}
	if (!strcmp(argv[1], "cw") && argc > 3) {
		outb(a, 0x70);
		outb(v, 0x71);
	}
	outb(a, 0x70);
	printf("0x%02x\n", inb(0x71));
	return 0;
}
```

The CMOS index port is shared with the kernel's RTC driver: no CMOS step
while `hwclock`, `rtcwake` or a time sync runs, every read three times
with the same answer, and `timedatectl` compared with the network time
after a write (rule 7).

## Part 1: v1.6.2 as it runs

Nothing is installed for this part.

| ID | Who | Test | Expected |
|---|---|---|---|
| — | agent | the baseline: the copy of the flash; `sudo python3 -I CLONE/tools/hw-report.py --markdown hw-1.md --dump flash-before.bin`; `sudo cbmem -1 > cbmem-1.txt`; `sudo cbmem -t`; `sudo cbmem -l`; `update.py status`, `protection`, `vboot`; `sudo acpidump -b` kept for part 2 | every check PASS but the known ones (EC-01 and ME-01 WARN, IDLE-01 INFO with the panel on); FLASH-01 PASS; the `COREBOOT` entry of `cbmem -l` 0x8000 bytes and *coreboot table: N bytes* in the log, N written down |
| CMOS-01 | agent | `sudo ./pio cr 0x7e`, `sudo ./pio cr 0x7f` | whatever they hold, written down: patch 0268 takes byte 0x7e, which v1.6.2 does not use; 0x7f is the Ethernet switch's, 0 |
| FLASH-06 | agent | `od -An -tx1 /sys/firmware/efi/efivars/OptionLockStatus-ceae4c1d-335b-4685-a4a0-fc4a94eea085` | `06 00 00 00` and eight zeros: the option lock armed |
| VAR-01 | agent | the time of a variable write with the option lock armed: the `Timeout` now (`efibootmgr \| grep Timeout`), then twenty writes, `efibootmgr -q -t 4` and `-t 3` in turn, each timed; the first value back at the end | no limit set yet: the median and the worst written down. Above 0.5 s of median, an INFO with the numbers |
| S3-02 | agent | five times `sudo rtcwake -m mem -s 30`, 20 s apart; then `cat /sys/power/suspend_stats/fail`, `sudo cbmem -1 \| grep -c "S3 Resume"`, `hw-report.py` once more | five resumes, `fail` 0, every CPU back, FLASH-01 and TPM-03 still PASS, the Ethernet and the camera there |
| PCI-05 | agent | `sudo python3 CLONE/tools/peg-report.py` at idle, then with a load on the NVIDIA GPU if one can be started without a desktop session | the link at 8 GT/s, no AER error, D3cold at idle |
| CONF-02 | agent | as in docs/testing.md | 0 errors, no warning 3115 |
| CONF-03 | agent | as in docs/testing.md | no CRITICAL or HIGH; the MEDIUM ones are those of the rc7 record of v1.6.0 |
| CONF-04 | agent | as in docs/testing.md | as in the record of v1.6.0: `spi_desc` FAILED by design (the Protected Range over `SI_ALL` is what protects the descriptor), the others PASSED |
| NET-02 | agent, with a second host | below | the machine starts on the packet |
| WDT-02 | agent | below | below |

### NET-02, the case an agent can run

*Wake on LAN* at its default, *AC only*, the adapter plugged in. It needs
another machine on the same network to send the packet: the M920x, if
its agent or `ssh` can be reached; otherwise the row is the owner's.

```sh
ip link show eno0 | grep ether                  # the MAC for the sender
sudo ethtool -s eno0 wol g
sudo setpci -s 1f.0 a4.w                        # bit 13 (WOL_EN_OVRD) set
# the sender, 3 minutes from now:  wakeonlan MAC   (or etherwake)
sudo rtcwake -m off -s 900                      # power off; the RTC alarm 15 minutes later, as a net
```

Expected: the machine starts about 3 minutes after the power-off, on the
packet; the event log of that boot (`python3 CLONE/tools/elog.py` on a
new copy of the flash) may name the wake source. Started at 15 minutes
instead: the RTC alarm, the packet did not wake it, FAIL with the two
times. Not started at all: neither works from off (an RTC alarm from off
was never tried on this board), the owner powers it on, and the row says
so. The other settings (*Off*, *AC and battery*), the battery alone and
the wake from sleep are the owner's.

### WDT-02, a reset by the watchdog, armed from Linux

The question the roadmap leaves open
([Firmware watchdog](roadmap.md#firmware-watchdog)): what a reset by the
overclocking watchdog does on this board, whether its status bits are
set after it and whether its enable bit survives it. No firmware hang is
needed: the register is not locked, so Linux can arm the timer and let it
expire. **It is a reset of the machine with the OS running, as a power
loss is for the disks**: every file of the run saved and `sync` first,
nothing else running that matters.

Before: *Firmware watchdog* Off (`sudo cbmem -1 | grep "Firmware watchdog"`
says `off`), both slots v1.6.1 or later (above), `sudo ./pio r 0x554`
reads `0x00002000` (another value: write it down and stop if bit 12, the
lock, or bit 14, the enable, is set).

```sh
date -u +%s > wdt02-armed-at; sync
sudo ./pio w 0x554 0x8000e077     # reload, enable, all modes, ICC survivability, 120 s
# must print 0x0000e077. Anything else:  sudo ./pio w 0x554 0x00002077  (stop), and report
```

To give up before it fires: `sudo ./pio w 0x554 0x00002077`.

| What | Expected, or what to write down |
|---|---|
| the reset | about 120 s after the arm; no reset within 300 s: stop the timer, FAIL, the register as it reads |
| the boot after | `sudo cbmem -1 \| grep "Firmware watchdog"`: *the last reset came from the watchdog (OC_WDT_CTL 0x...)*, then *off*. The value answers two questions: bits 25 and 24 are the status (which one is set), bit 14 is the enable as the reset left it |
| if that line is not in the log | the boot trained the memory and the romstage lines were lost (`sudo cbmem -1 \| grep -c "Firmware watchdog"`, `sudo cbmem -t`): say so; the test may be run once more |
| the kind of reset | what tells a reset of the host from a power cycle: the time from the arm to the new boot, the RAM init (from the cache, 0.11 s, or a training), the event log of that boot (`elog.py`), `journalctl -b -1 \| tail` for the end of the boot before, `hw-report.py` (ME-01, TPM-03, WDT-01) |
| at the OS | `sudo ./pio r 0x554`: the enable clear (romstage stopped it), the status clear |
| a reboot | no *last reset came from the watchdog* line: reported once |
| the slot | `update.py status`: the same slot, still confirmed; vboot did not count the reset against it |

## Part 2: the candidate

### Install

- **With a `v1.6.3-rc*` capsule**: `sudo python3 CLONE/tools/update.py stage FILE.cap`
  and a reboot, with *BIOS Lock* on (UPD-02). Nobody needed.
- **With the CI build**: `update.py other-slot` and flashrom
  ([docs/update.md](update.md#a-release-from-its-image-in-the-other-slot)),
  which needs *BIOS Lock* off for that boot: **the owner** turns it off
  in the setup (*Security* → *Flash protection*) and on again after the
  first boot of the candidate. Until then part 2 waits and the record
  says so. In the boot with *BIOS Lock* off the option lock is not armed
  (`OptionLockStatus` holds `EFI_UNSUPPORTED`, not zeros): run VAR-01
  once more there, for the comparison.

```sh
gh run download 42692289173 -R debianita22/ourobios -n ourobios-ci-314-24a28d6 -D ci-314
ls ci-314            # the nri ROM of the W541, SHA256SUMS
sudo flashrom -p internal -r flash-now.bin
python3 CLONE/tools/update.py other-slot flash-now.bin ci-314/W541-NRI.rom
# the flashrom command it prints, as it is (rule 2), then a reboot
```

The candidate goes to slot B, over rc1; v1.6.2 stays in slot A.

### Tests

| ID | Who | Test | Expected |
|---|---|---|---|
| — | agent | the reports: `hw-report.py --markdown` at the first boot, after a reboot and after a cold boot (`sudo rtcwake -m off -s 120`; if it does not start by itself, the owner) | PASS but the known ones; BOOT-01 with `ci-314-24a28d6` (or the rc) |
| MEM-03 | agent | `sudo cbmem -1 \| grep -i "MRC:\|cached memory"` at the first boot | no training: the code of the native RAM init is that of v1.6.2 (*does not need update*, RAM init 0.11 s). A training is an INFO with the lines: the key of patch 0250 changed |
| TBL-01 | agent | patch 0269: `sudo cbmem -l \| grep -i coreboot`; `sudo cbmem -1 \| grep -E "coreboot table:\|didn't fit\|CFR: Written"`; `sudo cbmem -t`; OPT-01 of `hw-report.py --dump` | the `COREBOOT` entry 0x10000 bytes; *coreboot table: N bytes* with about the N of part 1 (the tables do not change, but for the version strings), no *didn't fit*; `cbmem` and the kernel read the table as before; the same options in OPT-01 |
| CONF-02 | agent | `sudo acpidump -b`, each table against the one of part 1 (`cmp`); the DSDT and the SSDT disassembled and compiled | the DSDT the same, byte for byte (no patch of the candidate touches the ACPI code); in the SSDT and the tables that carry addresses, only addresses differ (CBMEM moves by 32 KiB). Anything else that differs is an INFO with the list |
| FLASH-01, FLASH-06 | agent | as in part 1 | PASS; `06 00 00 00` and eight zeros (with *BIOS Lock* on) |
| S3-02 | agent | three times `sudo rtcwake -m mem -s 30` | three resumes, `fail` 0, FLASH-01 and TPM-03 PASS after |
| WDT-03 | agent | below | below |
| WDT-02 | agent | as in part 1, on the candidate | the line ends with *, 1 in a row* (patch 0268); at the OS `sudo ./pio cr 0x7e` reads `0xa0`: SMM cleared the count when the payload confirmed the boot |
| WDT-01 | owner, then agent | *General* → *Boot* → *Firmware watchdog* at 5 minutes: `sudo cbmem -1 \| grep "Firmware watchdog"`, `sudo ./pio r 0x554` after 7 minutes of uptime; with it on, WDT-03 again; then Off | *armed, 300 s*, *at the payload*, the enable clear at the OS, the machine up past 420 s |
| VB-01, VB-02 | agent | as in docs/testing.md | the candidate in slot B, confirmed; v1.6.2 in slot A |

### WDT-03, the count of patch 0268 without a hang

Three resets by the watchdog in a row cannot be had without a firmware
that hangs: every boot that reaches the payload clears the count. The
byte is written by hand instead.

| Step | Expected |
|---|---|
| after any boot of the candidate: `sudo ./pio cr 0x7e` | `0xa0`: the mark, no reset counted (SMM writes it at the first confirmed boot, whatever the byte held: compare with CMOS-01) |
| the same after each of the next five boots and after a resume from S3 | `0xa0` every time. Another value means that something else writes the byte: it is not free on this board, FAIL, and the watchdog stays off |
| `sudo ./pio cw 0x7e 0x55`, a reboot, `sudo ./pio cr 0x7e` | `0xa0`: a byte without the mark reads as no reset |
| `sudo ./pio cw 0x7e 0xa3`, a reboot, with *Firmware watchdog* Off | no *resets in a row* line (the watchdog is off anyway), `0xa0` at the OS: the confirmation clears the count |
| the same with *Firmware watchdog* at 5 minutes (after the owner's visit of WDT-01) | romstage: *Firmware watchdog: 3 resets in a row and no boot confirmed, not armed*, then *off*; `sudo ./pio r 0x554` with the enable clear; `0xa0` at the OS; after one more reboot *armed, 300 s* again |

Rule 7 after each write of the byte: `timedatectl` against the network
time.

## Part 3: the owner's

Not for the agent; they stay in the record as *not run, needs the
owner* until someone sits at the machine. The first three are asked by
the project for every change of ACPI, SMM or power management, and none
ran on v1.6.1 or v1.6.2.

| ID | Test | Expected |
|---|---|---|
| macOS | a boot of macOS (OpenCore), sleep and wake, a dark wake (`pmset -g log \| grep -i "darkwake\|wake reason"`), the same with the dGPU off in the setup | boots; sleeps and wakes; the panel stays off on a dark wake; no HKEY or EC error in the log |
| S3-02 | sleep and wake with the lid and with Fn | as with `rtcwake` |
| DISP-03 | *NVIDIA GPU* off in the setup, then on | the panel at each step; with it off no `01:00.0` |
| NET-02 | *Wake on LAN* Off, *AC only*, *AC and battery*; on AC and on battery; from off and from sleep | as in docs/testing.md |
| WDT-01 | *Firmware watchdog* at 5 minutes, for the agent's rows above | above |
| — | Secure Boot with shim, CSMWrap (a legacy boot), NET-05 (iPXE), BOOT-05/06, OPT-02, MEM-09, USB-06, DISP-05 | as in docs/testing.md; not run since v1.6.0 |
| DEV-W01 | the fingerprint switch, on a W541 that has the reader | the reader gone from `lsusb` with the switch off |
| OPT-05 | a real loss of the RTC power (the coin cell out) | the options reset once |

Not possible on this machine, and said so in the record: the `mrc`
variant (the read-only part starts only `nri` slots) and Windows (none
installed).

## The end

1. The machine back on v1.6.2: `sudo python3 CLONE/tools/update.py rollback flash-now.bin`
   on a copy of that boot, a reboot, `update.py status`. If it refuses
   (a CI build in the slot), leave the candidate running and say so.
2. `hw-report.py` once more: FLASH-01 PASS (*BIOS Lock* and *Firmware
   protection* on), *Firmware watchdog* off, `sudo ./pio r 0x554` with
   the enable clear, the `Timeout` of the boot manager as it was.
3. Whatever was set up to survive the reboots removed.
4. The record committed and pushed (above), and a short report: what
   passed, what failed with the evidence, what was not run and why, and
   the answers of WDT-02 (the status bits, the enable bit, the kind of
   reset), which decide the next step of the roadmap.
