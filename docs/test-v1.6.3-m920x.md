# Hardware tests after v1.6.2, on the M920x

What is still to run on the ThinkCentre M920x of the port after v1.6.2,
and the tests of the candidate of v1.6.3 (patches 0266-0269). The W541
has its own file, [test-v1.6.3-w541.md](test-v1.6.3-w541.md), with the
same rules and the same new IDs (TBL-01, WDT-02, WDT-03, VAR-01,
CMOS-01); OPT-06 is only here.

Written for an agent that works on the machine by itself, under Linux
(Proxmox), as root. It runs every row marked **agent** without asking,
in the order of the file, and leaves the rows marked **owner** (the
setup menu needs a monitor and a keyboard) in the record as *not run,
needs the owner*. A row it cannot run is recorded with the reason, not
skipped in silence, and never turned into a PASS by changing the test.

## Rules

These hold whatever else the agent decides.

1. **A copy of the flash first**, and after every write:
   `modprobe -r spi_intel_pci spi_intel; flashrom -p internal -r FILE`,
   25165824 bytes (less means flashrom went through `/dev/mtd0`: the
   `modprobe -r` did not take). Keep `flash-before.bin` off the machine
   too, if a place is reachable.
2. **The only writes of the flash are capsules** (`update.py stage`,
   `update.py rollback`: the firmware writes the slot that is not
   running, with its own checks). flashrom only reads here (`-r`): no
   `-w` of anything, no `update.py other-slot`, no `--ifd`, nothing on
   `WP_RO`, the descriptor, the ME, the GbE or the whole image. Those
   are a brick risk and no part of these tests; the external programmer
   is not available to an agent.
3. **No setup option is changed from the OS.** The options are
   boot-service variables; the only way to change one is the setup menu,
   by the owner. No tool that issues SMMSTORE SMIs against the variable
   store, no change of Secure Boot keys, no change of the ME state or of
   the HAP bit.
4. A capsule that the firmware refuses is a result (UPD-01 says why),
   not something to get around: no `--allow-older`, no other way in.
5. Reboot right after a capsule is staged, without suspending.
6. **The guests**: this is a Proxmox host. Before every reboot, suspend
   and reset, the list of what runs (`qm list`, `pct list`) in the
   journal and a clean shutdown of each guest; at the end, what was
   running runs again. WDT-02 is a reset with the OS running: no guest
   up, `sync` first.
7. **A boot that does not come back**: nothing to do from the agent's
   side. After two failed boots vboot returns to the slot of before by
   itself; otherwise the owner powers the machine off (4 s) and on. Say
   in the journal, before every reboot, power-off and reset, what was
   about to happen.
8. **Stop the whole run** and report when: a `FAIL` of FLASH-01 with the
   protections on, a slot that vboot marks failed, a machine check or a
   memory error, a capsule that leaves the machine on neither slot's
   release, the date of the RTC wrong after a CMOS step, or the RTC
   power bit of OPT-06 left set.
9. **The repository**: the record only (below). No tag, no release, no
   push to `main` or to a `ci-test/**` or `ci-edk2/**` branch (a push
   there starts a build), no force push, no change outside
   `docs/tests/v1.6.3/m920x-fsp/`.

## The machine and the builds

- **Running**: v1.6.2 `fsp` in slot B (a capsule from v1.6.1,
  2026-11-09), v1.6.1 in slot A; the read-only part is the one of
  v1.5.0. Check before anything else: `python3 CLONE/tools/update.py status`
  and `python3 CLONE/tools/update.py vboot flash-before.bin`. **Both
  slots must hold v1.6.1 or later** for WDT-02 (an older slot has no
  code that stops the watchdog).
- **The kernel must let root at the hardware**:
  `cat /sys/kernel/security/lockdown` says `[none]`. With a lockdown
  (Secure Boot on), flashrom, the port helper and `/dev/mem` are
  refused: the rows that need them are *not run, Secure Boot on*, and
  turning it off is the owner's.
- **Candidate**: the pre-release
  [v1.6.3-rc1-m920x-fsp](https://github.com/debianita22/ourobios/releases/tag/v1.6.3-rc1-m920x-fsp),
  built by the Release workflow from `next`: v1.6.2 plus patches
  0266-0269, with its capsule, which installs with *BIOS Lock* and
  Secure Boot as they are and needs nobody. If the release is not there
  (`gh release view v1.6.3-rc1-m920x-fsp -R debianita22/ourobios`), its
  build failed: part 1 only, and the record says so.
- **Tools**: a clone at `next`; `python3`, flashrom 1.2 or later,
  `cbmem`, `gcc`, `acpica-tools`, `fwts`, chipsec, `wakeonlan` or
  `etherwake`, `gh`. Install what is missing; what cannot be installed
  makes its rows *not run*.

```sh
git -C CLONE fetch origin && git -C CLONE checkout next && git -C CLONE pull --ff-only
mkdir -p ~/ourobios-test-v1.6.3/m920x-fsp && cd ~/ourobios-test-v1.6.3/m920x-fsp
```

## Across reboots, and the record

The run has reboots, suspends and one reset that the agent does not
survive. Keep a journal, `STATE.md` in the work folder: before each of
them the step in progress, what the next boot must show and the time;
after the boot, read it and go on. Whatever is set up to start again
after a boot is removed at the end.

The record is `docs/tests/v1.6.3/m920x-fsp/README.md` in the clone, as
the one of v1.6.2: a table *ID, Result (PASS, FAIL, INFO, not run),
Notes* with the numbers read, then a paragraph for anything that needs
one, and the files next to it (the `hw-report` Markdown reports,
`cbmem -1` of the boots that matter, the fwts and chipsec logs; no copy
of the flash). Commit it on `next` with the git identity of the
repository (`git config user.name` and `user.email` must be the
owner's, not a placeholder; no `Co-authored-by` or other trailer of an
AI), `git pull --rebase` before the push, that folder only.

## The order of the run

Nobody is at the machine: the step that may leave it down comes after
what does not depend on it is in the record.

1. Part 1, but WDT-02 and OPT-06.
2. Part 2: the install and every row but WDT-02.
3. The record, committed and pushed a first time.
4. WDT-02 on rc1, which prints the register in its line and clears the
   status by itself. What a reset by the watchdog does on this board is
   not known: if the machine does not come back, the run ends here.
5. The end, step 1: back on v1.6.2; then WDT-02 once more there, for
   the defect that patch 0267 corrects (its table below is written for
   v1.6.2).
6. The record again.
7. OPT-06, last of all: if its bit cannot be cleared the agent must not
   reboot, and nothing else may still depend on a reboot. Then the
   record a last time, the guests up, the rest of the end.

The packet for the W541 (NET-02) is sent when asked, whatever the step.

## The helpers

`pio.c` of [the W541 file](test-v1.6.3-w541.md#the-port-helper), built
here the same way, for the watchdog register (port 0x1854 on this
board) and the CMOS byte; its cautions about the CMOS hold here too.
For OPT-06, one register of the chipset through `/dev/mem`, `mm.c`
(`gcc -O2 -o mm mm.c`):

```c
/* mm r ADDRESS | mm w ADDRESS VALUE: one 32-bit register, through /dev/mem */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	if (argc < 3)
		return 1;
	off_t a = strtoull(argv[2], NULL, 0);
	long pg = sysconf(_SC_PAGESIZE);
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	void *m = fd < 0 ? MAP_FAILED :
		mmap(NULL, pg, PROT_READ | PROT_WRITE, MAP_SHARED, fd, a & ~(off_t)(pg - 1));

	if (m == MAP_FAILED) {
		perror("mm");
		return 1;
	}
	volatile uint32_t *p = (volatile uint32_t *)((char *)m + (a & (pg - 1)));
	if (argv[1][0] == 'w' && argc > 3)
		*p = strtoul(argv[3], NULL, 0);
	printf("0x%08x\n", *p);
	return 0;
}
```

If the kernel refuses the mapping (strict `/dev/mem`), the same read and
write with `chipsec_util mem` (its own help has the syntax), or the row
is *not run*.

## Part 1: v1.6.2 as it runs

Nothing is installed for this part.

| ID | Who | Test | Expected |
|---|---|---|---|
| — | agent | the baseline: the copy of the flash; `python3 -I CLONE/tools/hw-report.py --markdown hw-1.md --dump flash-before.bin`; `cbmem -1 > cbmem-1.txt`; `cbmem -t`; `cbmem -l`; `update.py status`, `protection`, `vboot`; `acpidump -b` kept for part 2 | as the record of v1.6.2: 25 PASS with the copy of the flash; the `COREBOOT` entry of `cbmem -l` 0x8000 bytes and *coreboot table: N bytes* in the log, N written down; the options of OPT-01 kept in the record (OPT-06 may cost them) |
| CMOS-01 | agent | `./pio cr 0x7e` | whatever it holds, written down: patch 0268 takes byte 0x7e, which v1.6.2 does not use |
| FLASH-06 | agent | `od -An -tx1 /sys/firmware/efi/efivars/OptionLockStatus-ceae4c1d-335b-4685-a4a0-fc4a94eea085` | `06 00 00 00` and eight zeros: the option lock armed |
| VAR-01 | agent | the time of a variable write with the option lock armed: the `Timeout` now (`efibootmgr \| grep Timeout`), then twenty writes, `efibootmgr -q -t 4` and `-t 3` in turn, each timed; the first value back at the end | no limit set yet: the median and the worst written down. Above 0.5 s of median, an INFO with the numbers |
| OPT-06 | agent | below, last of all (the order of the run) | below |
| WDT-02 | agent | below, after part 2 (the order of the run) | below |
| NET-02 | agent, for the W541 | when the agent of the W541 or the owner asks: `wakeonlan MAC` (or `etherwake -i IFACE MAC`) at the time they give | sent; the time in the record. The result is in the record of the W541 |

### OPT-06, the RTC power bit

From v1.4.0 an RTC power loss resets the setup options of this board,
and the code looks at one bit alone, `RTC_PWR_STS`, bit 2 of
`GEN_PMCON_B`. On the W541 the same bit can be set by the OS (measured),
so that code there also asks for a lost CMOS (patch 0256). Whether the
OS can set it on Cannon Point was never measured. **No reboot is part of
this test**: a boot with the bit set resets every setup option.

`GEN_PMCON_B` is at 0xfe001024 (`PCH_PWRM_BASE_ADDRESS` 0xfe000000 plus
0x1024, from coreboot's `soc/intel/cannonlake`); confirm it before any
write: `cbmem -1 | grep GEN_PMCON` prints two words, and the second must
be what `./mm r 0xfe001024` reads, but for the lock bits the firmware
sets later (4, 17, 18). Something else there: stop, *not run, address
not confirmed*.

| Step | Expected, or what to write down |
|---|---|
| `./mm r 0xfe001024` → R0 | bit 2 clear. Set already: stop, and tell the owner (the next boot resets the options) |
| `./mm w 0xfe001024 $((R0 \| 4))` → R1 | bit 2 of R1: **set** means the OS can ask for a reset of the options, as on the W541; **clear** means the bit is not writable here |
| if set: `./mm w 0xfe001024 R0` → R2 | R2 equal to R0: the bit cleared by writing 0 |
| if still set: `./mm w 0xfe001024 $((R0 \| 4))` once more | cleared by writing 1 (a write-1-to-clear bit): say which of the two it is |
| if still set after both | rule 8: no reboot by the agent, the owner told at once; the options of the baseline are what a reset would lose |

The result is the answer, either way; with the bit writable, the next
step is the check of patch 0256 on this board (the roadmap).

### WDT-02, a reset by the watchdog, armed from Linux

The question the roadmap leaves open
([Firmware watchdog](roadmap.md#firmware-watchdog)): what a reset by the
overclocking watchdog does on Cannon Point (the host or the whole
platform), whether its status bits are set after it and whether its
enable bit survives it. The armed path never ran on this machine. No
firmware hang is needed: the register is not locked, so Linux can arm
the timer and let it expire. **It is a reset of the machine with the OS
running, as a power loss is for the disks** (rule 6).

Before: *Firmware watchdog* Off (`cbmem -1 | grep "Firmware watchdog"`
says `off`), both slots v1.6.1 or later (above), `./pio r 0x1854` reads
`0x00002000` (another value: write it down and stop if bit 12, the lock,
or bit 14, the enable, is set).

```sh
date -u +%s > wdt02-armed-at; sync
./pio w 0x1854 0x8000e077     # reload, enable, all modes, ICC survivability, 120 s
# must print 0x0000e077. Anything else:  ./pio w 0x1854 0x00002077  (stop), and report
```

To give up before it fires: `./pio w 0x1854 0x00002077`.

| What | Expected, or what to write down |
|---|---|
| the reset | about 120 s after the arm; no reset within 300 s: stop the timer, FAIL, the register as it reads |
| the boot after | `cbmem -1 \| grep -E "Firmware watchdog\|OC Watchdog"`: *the last reset came from the watchdog*, then *off*. v1.6.2 does not print the register in that line: the enable bit survived the reset if *OC Watchdog: disabling watchdog timer* is there (romstage found it on and stopped it), and did not if it is not |
| at the OS | `./pio r 0x1854`: the enable clear; bits 25 and 24, the status, **still set**: v1.6.2 logs them and never clears them (what patch 0267 corrects). Which of the two is set |
| the kind of reset | what tells a reset of the host from a power cycle: the time from the arm to the new boot, `cbmem -1 \| grep GEN_PMCON` and `prev_sleep_state` of that boot against the baseline, FspMemoryInit (0.25 s from the cache, or a training), the ME (ME-01), the event log of that boot (`python3 CLONE/tools/elog.py` on a new copy of the flash), `journalctl -b -1 \| tail` |
| a reboot | on v1.6.2 the same *last reset came from the watchdog* line again, for a reset that is one boot old: the defect of 0267, seen. If the line is gone, the chipset cleared the status by itself: say so |
| after that | the status cleared by hand, so that it does not follow the machine: the value as `./pio r 0x1854` reads it, written back (`./pio w 0x1854 VALUE`: the status bits clear when written as 1); `./pio r 0x1854` reads `0x00002000` again |
| the slot | `update.py status`: the same slot, still confirmed; vboot did not count the reset against it |

## Part 2: the candidate

### Install

As a user updates (UPD-02): the capsule of rc1 on v1.6.2, with *BIOS
Lock* and *Firmware protection* on. The payload of v1.6.2 writes the
slot that is not running, slot A, over v1.6.1; v1.6.2 stays in slot B.

```sh
gh release download v1.6.3-rc1-m920x-fsp -R debianita22/ourobios -D rc1 -p '*.cap' -p SHA256SUMS
( cd rc1 && sha256sum -c SHA256SUMS --ignore-missing )
python3 CLONE/tools/update.py stage rc1/*.cap
systemctl reboot
```

rc1 from slot A after the reboot: `update.py status` says *v1.6.3-rc1*,
the last capsule *riuscito* (UPD-01). A capsule that is refused, or a
boot that returns to v1.6.2: FAIL with `update.py status` and
`cbmem -1`, and part 2 stops there.

### Tests

| ID | Who | Test | Expected |
|---|---|---|---|
| — | agent | the reports: `hw-report.py --markdown` at the first boot and after a reboot, with `--dump` of a new copy of the flash | as the baseline; BOOT-01 with `v1.6.3-rc1-m920x-fsp`; UPD-01 PASS |
| MEM-03, BOOT-02 | agent | `cbmem -1 \| grep "MRC:"`, `cbmem -t` | no training (*does not need update*), FspMemoryInit about 0.25 s; to the payload within 12 s |
| TBL-01 | agent | patch 0269: `cbmem -l \| grep -i coreboot`; `cbmem -1 \| grep -E "coreboot table:\|didn't fit\|CFR: Written"`; `cbmem -t`; OPT-01 of `hw-report.py --dump` | the `COREBOOT` entry 0x10000 bytes; *coreboot table: N bytes* with about the N of part 1 (the tables do not change, but for the version strings), no *didn't fit*; `cbmem` and the kernel read the table as before; the same options in OPT-01 |
| CONF-02 | agent | `acpidump -b`, each table against the one of part 1 (`cmp`); the DSDT and the SSDT disassembled and compiled | the DSDT the same, byte for byte (no patch of the candidate touches the ACPI code); in the SSDT and the tables that carry addresses, only addresses differ (CBMEM moves by 32 KiB). Anything else that differs is an INFO with the list |
| CONF-03, CONF-04 | agent | as in docs/testing.md | fwts as in the record of v1.6.2 (no CRITICAL or HIGH); chipsec as in the record of v1.6.1 rc2: `spi_desc` FAILED by design, the others PASSED |
| FLASH-01, FLASH-06 | agent | as in part 1 | PASS; `06 00 00 00` and eight zeros |
| VAR-01 | agent | as in part 1 | the numbers of part 1, within their spread (the comparison with the lock not armed needs *BIOS Lock* off: the owner's) |
| S3-01 | agent | three times `rtcwake -m mem -s 30`, the guests down | three resumes, `suspend_stats/fail` 0, FLASH-01 and TPM-03 PASS after |
| WDT-03 | agent | below | below |
| WDT-02 | agent | as described in part 1, on the candidate, after the first push of the record (the order of the run) | the line has the register now and ends with *, 1 in a row* (patches 0267, 0268): bit 14 of that value is the enable as the reset left it, the direct answer; at the OS the status **clear** and `./pio cr 0x7e` `0xa0`; after a reboot no *last reset came from the watchdog* line: reported once, nothing to clear by hand |
| WDT-01 | owner, then agent | *General* → *Boot* → *Firmware watchdog* at 5 minutes: `cbmem -1 \| grep "Firmware watchdog"`, `./pio r 0x1854` after 7 minutes of uptime; with it on, WDT-03 again; then Off | *armed, 300 s*, *at the payload* with what FSP-S left of the register, the enable clear at the OS, the machine up past 420 s. Never run on this board |
| VB-01, VB-02 | agent | as in docs/testing.md | the candidate in slot A, confirmed; v1.6.2 in slot B |

### WDT-03, the count of patch 0268 without a hang

Three resets by the watchdog in a row cannot be had without a firmware
that hangs: every boot that reaches the payload clears the count. The
byte is written by hand instead.

| Step | Expected |
|---|---|
| after any boot of the candidate: `./pio cr 0x7e` | `0xa0`: the mark, no reset counted (SMM writes it at the first confirmed boot, whatever the byte held: compare with CMOS-01) |
| the same after each of the next five boots and after a resume from S3 | `0xa0` every time. Another value means that something else writes the byte (the FSP, the ME): it is not free on this board, FAIL, and the watchdog stays off |
| `./pio cw 0x7e 0x55`, a reboot, `./pio cr 0x7e` | `0xa0`: a byte without the mark reads as no reset |
| `./pio cw 0x7e 0xa3`, a reboot, with *Firmware watchdog* Off | no *resets in a row* line (the watchdog is off anyway), `0xa0` at the OS: the confirmation clears the count |
| the same with *Firmware watchdog* at 5 minutes (after the owner's visit of WDT-01) | romstage: *Firmware watchdog: 3 resets in a row and no boot confirmed, not armed*, then *off*; `./pio r 0x1854` with the enable clear; `0xa0` at the OS; after one more reboot *armed, 300 s* again |

Rule 8 after each write of the byte: `timedatectl` against the network
time.

## Part 3: the owner's

Not for the agent; they stay in the record as *not run, needs the
owner* until someone sits at the machine with a monitor.

| ID | Test | Expected |
|---|---|---|
| VAR-01 | *BIOS Lock* off for one boot: the time of a variable write with the option lock not armed | the numbers to compare with the armed ones |
| WDT-01 | *Firmware watchdog* at 5 minutes, for the agent's rows above | above |
| BOOT-09 | *Serial Console* off in the setup, if the saved value is still on | the seconds of the serial port gone from `cbmem -t` |
| ME-05 | as in docs/testing.md | not run since v1.6.0 |
| OPT-05 | a CMOS clear, only if OPT-06 says the bit cannot be set by the OS and the owner wants the real case once more | the options reset once |
| DMA | a Thunderbolt card in the slot, for its `ExternalFacingPort` | none at hand (the roadmap) |

## The end

1. The machine back on v1.6.2 (UPD-05): a copy of the flash of that
   boot, `python3 CLONE/tools/update.py rollback flash-now.bin`, a
   reboot, `update.py status`: v1.6.2 from slot B, rc1 kept in slot A.
   If it refuses, leave rc1 running and say so.
2. `hw-report.py` once more: FLASH-01 PASS (*BIOS Lock* and *Firmware
   protection* on), *Firmware watchdog* off, `./pio r 0x1854` reads
   `0x00002000`, `./mm r 0xfe001024` with bit 2 clear, the `Timeout` of
   the boot manager as it was.
3. The guests that ran before run again; whatever was set up to survive
   the reboots removed.
4. The record committed and pushed (above), and a short report: what
   passed, what failed with the evidence, what was not run and why, and
   the answers of OPT-06 (can the OS set the bit) and of WDT-02 (the
   status bits, the enable bit, the kind of reset), which decide the next
   steps of the roadmap.
