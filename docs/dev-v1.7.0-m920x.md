# Development on the M920x for v1.7.0: the option lock

Two pieces of work on the lock of the setup options
(`SMMSTORE_OPTION_LOCK`, patches 0236, 0237 and 0273, `edk2/0056` to
`0058`), to develop and to test on the ThinkCentre M920x of the port:

1. **The time of a variable write with the lock armed.** v1.6.3 has it at
   0.29 s on the M920x (VAR-01 with rc4, 44 ms an SMI); the flash write
   itself takes a few milliseconds.
2. **The lock for every setup option.** Today it keeps two options,
   `bios_lock` and `bootmedia_lock`, from being turned off. Every other
   option is a boot-service variable too, which the OS cannot write with
   `SetVariable`, but a program with root can still write the variable
   store through the SMMSTORE commands and, at the next boot, turn on
   again a device that the owner turned off in the setup (camera,
   microphone, Ethernet, Thunderbolt, the USB ports), or change
   `dma_untrusted_ports`, `clear_dram_on_boot`, the boot switches.

Written for an agent that works on the machine by itself, under Linux
(Proxmox), as root, and that also writes the code. What the owner has to
decide is in [Decisions for the owner](#decisions-for-the-owner): the
agent prepares each with the numbers, and does not take it.

The analysis is defensive: what is written and tested here is the
check, in SMM and in the payload, and the proof that it refuses what it
must is a set of unit tests of the decision. No tool that changes the
options of a machine from the OS is written, here or anywhere else.

## Rules

These hold whatever else the agent decides.

1. **A copy of the flash first**, and after every write:
   `modprobe -r spi_intel_pci spi_intel; flashrom -p internal -r FILE`,
   25165824 bytes. Keep the first one off the machine too. A copy holds
   the variable store of the machine: it is never committed.
2. **The only writes of the flash are capsules** (`update.py stage`,
   `update.py rollback`). flashrom only reads (`-r`): no `-w` of
   anything, no `update.py other-slot`, nothing on `WP_RO`, the
   descriptor, the ME, the GbE or the whole image. The external
   programmer is not available to an agent.
3. **No setup option is changed from the OS, and nothing sends SMMSTORE
   commands to the variable store from the OS**: no program, script or
   module that issues the SMI by itself, on any build, the ones without
   the new check included. The variable store is written only through
   the UEFI variable services (`efibootmgr`, efivarfs), on variables of
   the test's own GUID or the boot entries. No change of Secure Boot
   keys, of the ME state or of the HAP bit.
4. **The proof that the lock refuses** is in the unit tests
   ([The proof](#the-proof)), on stores built by the test. On the machine
   the tests show that what must keep working does.
5. A capsule that the firmware refuses is a result, not something to
   get around: no `--allow-older` unless the step says so.
6. **The guests**: this is a Proxmox host. Before every reboot and
   suspend, the list of what runs (`qm list`, `pct list`) in the journal
   and a clean shutdown of each guest; at the end, what was running runs
   again.
7. **A boot that does not come back**: after two failed boots vboot
   returns to the slot of before by itself; otherwise the owner powers
   the machine off and on. Say in the journal, before every reboot, what
   was about to happen. **The slot that is not being written always
   holds a release that booted** (v1.6.3-rc6 or later): never two
   untried builds in the two slots.
8. **Stop and report** when: a slot that vboot marks failed; a machine
   check or a memory error; a `FAIL` of FLASH-01 with the protections
   on; a variable write that still fails after a reboot (the store
   stayed full or damaged); the boot entries or the Secure Boot state
   changed by a test; a setup option of the baseline (LOCK-06) changed by
   anything but the owner.
9. **The repository**: branch `ci-test/v1.7.0-m920x-option-lock`, made
   from `ci-test/v1.7.0-nri-xmp` (the work for v1.7.0 so far: `next`
   plus patches 0275-0280 for the W541, which the M920x build does not
   run but for a hook that does nothing there). New coreboot patches
   from 0281, payload patches from `edk2/0061`, then
   `tools/edk2-import.py`. Commits with the identity of the repository
   (`git config user.name` and `user.email` the owner's, no
   `Co-authored-by` or other trailer of an AI), coreboot style, no
   `Signed-off-by` and no `Change-Id`. No push to `main` or `next`, no
   force push.
10. **One build for each finished stage.** A push to a `ci-test/**`
    branch starts a build and stops the one before it on that branch:
    `tools/ci-check.sh`, `tools/coreboot-lint.sh` and the unit tests
    pass on the machine first, then one push.
11. **A build becomes installable only as a candidate.** A `ci-...`
    build has ROMs and no capsule (`fw_version()` of `tools/build.sh`).
    The capsule comes with a pre-release, `v1.7.0-rcN`, from the
    *Build* workflow run on the branch
    (`gh workflow run build.yml -R debianita22/ourobios --ref BRANCH -f version=v1.7.0-rcN`).
    **Publishing one is the owner's decision**: the agent does it only
    if the owner's instructions to it say so, one candidate for each
    stage that is ready for the machine, never a release. A
    `v1.7.0-rcN` is 1.6.255.N in the ESRT, above every v1.6.3: going
    back to a v1.6.3 afterwards is `update.py rollback` to the other
    slot, or the owner's `--allow-older`.

## Where things are

| What | Where |
|---|---|
| The check of each write and erase, the latch at arm | `src/drivers/smmstore/options_lock.c` (patches 0237, 0273) |
| Where the check is called | `smmstore_rawwrite_region()`, `smmstore_rawclear_region()` in `store.c`; the command in `smi.c` |
| The state kept across S3 | the SMRAM subregion of patch 0236 (`smm_get_option_lock_state_buffer()`, 4 KiB) |
| The reader of the variable store | `src/drivers/efi/efivars.c`: `walk_variables()`, `efi_fv_get_options()` (0273), `ftw_write_pending()`; its unit tests in `tests/drivers/efivars.c` |
| The twin, to keep in step | `mor_lock.c` (the TCG MOR lock) |
| The arm, the report to the OS | `PlatformLockFirmwareSlots()` of `PlatformBootManagerLib`, `SmmStoreLibOptionLock()`, `OptionLockStatus` (`edk2/0056`, `0057`) |
| The lock of the variable driver | `CFR_OPTFLAG_LOCK_AT_BOOT` in `CfrSetupMenuDxe` (`edk2/0058`); no option of the boards has the flag |
| The options | `src/mainboard/lenovo/m720q_m920q/cfr.c`, `src/mainboard/lenovo/haswell/cfr.c`; read by `get_uint_option()` (`src/drivers/efi/option.c`), which matches GUID and name and does not look at the attributes |
| The tests so far | FLASH-06, VAR-01 of [docs/testing.md](testing.md); [docs/tests/v1.6.3/m920x-fsp](tests/v1.6.3/m920x-fsp/README.md), *VAR-01: where the time of a write goes* |
| The design of the lock | the header of `options_lock.c`; [Variable store robustness](roadmap.md#variable-store-robustness) for the reader and the fault tolerant write |

## Stage 0: the facts, before any code

On the firmware that runs (v1.6.3-rc6 or later, *BIOS Lock* on), and
from the sources. Each answer goes in the record with where it comes
from; the design of the next stages depends on them.

| # | Question | How |
|---|---|---|
| F1 | The baseline of VAR-01 | twenty writes of `Timeout` as in VAR-01, `MSR_SMI_COUNT` (0x34) around each: seconds and SMIs a write |
| F2 | The store: its size, what is free, how many records, how many of the options GUID and with which attributes | a copy of the flash, the `SMMSTORE` region read by a script (read only); `update.py` has the parser of the store (`cb_store()`) |
| F3 | Which code writes a variable of the options GUID, and when | `grep` in the coreboot tree (`efi_fv_set_option`, `efi_fv_delete_options`) and in `edk2/OuroBiosPkg` and the patched packages (`gEficorebootNvDataGuid`): the setup, the settings reset, anything after ReadyToBoot |
| F4 | How a variable write reaches the flash: how many SMMSTORE writes, of which ranges, and whether one record can be written in pieces that leave the store unreadable for coreboot's reader between two of them (a header across a block boundary) | the sources of the variable driver and of `SmmStoreFvbRuntimeDxe`; then, on a candidate with `DEBUG_SMI` for the purpose, the lines of the handler in `cbmem -1` around one write |
| F5 | The reclaim: when the payload does it (at its start, at EndOfDxe with `PcdReclaimVariableSpaceAtEndOfDxe`, at runtime when a write does not fit), and what it writes and erases | the sources of the variable driver and of FaultTolerantWriteDxe; the value of the PCD in the build |
| F6 | The fault tolerant write: where its working and spare blocks are in `SMMSTORE`; what an ordinary variable write does to them; what the payload does at its start with a write that the record says is pending | the sources (`FtwMisc.c`, `InitFtwProtocol()`), `ftw_write_pending()` and its comment |
| F7 | Every writer of the `SMMSTORE` region in SMM other than the two raw commands (capsules, vboot, the event log, the MOR lock), and whether any goes around the check | `grep` of `rdev_writeat`, `rdev_eraseat` and of the region in the `smm` sources |
| F8 | Whether SHA-256 links in the SMM stage (vboot's library is there for `vboot_lib.c`) and what the handler has for static data and stack | the build |

F6 has a question of its own, to answer before anything else of stage
2: **the payload redoes a pending fault tolerant write at its start,
before the lock is armed**, from the spare blocks, which are in the
`SMMSTORE` region and outside the variable store that the check reads.
If a record and a spare copy written during one boot can make the
payload rewrite the store at the next, the check of today does not see
it, for the two options it protects either. If the sources say so, it
is the first thing that stage 2 closes, and the owner is told at once:
it concerns the releases from v1.6.1.

## Stage 1: the time of a write

Where the time goes is in the record of VAR-01: with the lock armed
each SMMSTORE write walks the store as it would be after the write,
through an overlay without `mmap`, so every header and name and the
whole erased tail are read from the flash, about 150 KiB a walk. Patch
0273 made it one walk a write instead of two.

In this order, each measured (F1 again) before the next is started:

1. **The erased tail read once.** The bytes after the last record were
   checked when the lock was armed, and since then only this handler
   wrote the region (F7 must say so). The walk of a write needs the tail
   only where the write itself touches it. The decision must not change:
   a write that puts something after the last record is still seen.
2. **The store in memory.** A copy of the variable store in SMRAM, made
   at the arm and kept in step by the handler, which is the only writer:
   the check of a write reads no flash at all. To settle first: the
   size (F2), where it lives (static data of the handler, made again
   after a resume from S3 at the first write, with the latch of stage 2
   in the subregion of patch 0236 as the reference; or a larger
   subregion), and what happens when a flash write fails half way (the
   range read back from the flash). Only if step 1 leaves the SMI well
   above the flash write.
3. **Not walking at all for a write that cannot matter** is not
   proposed: with stage 2 every write can add or hide a variable of the
   options GUID, and a rule that guesses which cannot is where a
   mistake would hide.

Done when: the armed write is within a few milliseconds an SMI of the
flash write, or the record says what is left and why; the unit tests of
`drivers/efi` and of the lock pass; the rows of
[On the machine](#on-the-machine) pass.

## Stage 2: the lock for every option

### The rule

**While the lock is armed, the flash never holds a variable store from
which coreboot would read, at the next boot, another set of options
than the one latched at the arm.**

- *The set*: every variable of the options GUID that coreboot's reader
  returns, name and data, whatever its attributes (the reader does not
  look at them: a second variable of the same name with other attributes
  is a change). The boards have no option with `CFR_OPTFLAG_RUNTIME`; a
  board that had one would need its names left out, by name.
- *Latched at the arm*, in SMRAM, kept across S3: enough to tell
  whether a set is the same one, exactly. No sum and no non-cryptographic
  hash of the set: whoever writes the store chooses names and values. A
  SHA-256 of each name and value, compared entry by entry, fits the 4 KiB
  of today for about a hundred options; so does the list itself.
- *Checked on the store as it would be after each write or erase*, with
  the reader that the boot uses (`walk_variables()`), not a second
  parser: one more function next to `efi_fv_get_options()` that gives
  every variable of a GUID in one walk, with its unit test.
- *Refused*: a write or an erase after which the set differs (a value
  changed, an option gone, one more), or after which the reader cannot
  read the store (it then gives the default of every option), or that
  cannot be checked (the flash not read).
- *When the latch cannot be made* (more options than fit, the store not
  readable at the arm): the lock of today, for the two options, and a
  status that says so. Never no lock, never every write refused.
- A Kconfig of its own (`SMMSTORE_OPTION_LOCK_ALL`), on in
  `boards/m920x/fsp.defconfig` only: the W541 keeps the lock of v1.6.3
  until it has run this one ([Decisions](#decisions-for-the-owner)).
  ramstage logs which lock the build has, so that `cbmem -1` tells.

### What the rule costs, to measure before it is built

- **An erase that takes an option away is refused**, so the reclaim of
  the store at runtime cannot run while the lock is armed (F5): a write
  from the OS that does not fit fails until the next boot. For that to
  be rare and to heal by itself, the payload reclaims at its start when
  the store is used above a threshold: `PcdReclaimVariableSpaceAtEndOfDxe`
  is the standard switch, a PCD and no patched module. Measure how much
  the OS can write in one boot (F2), and that a full store is usable
  again after a reboot.
- **A write in pieces** (F4): if an ordinary write passes through a
  state that the reader cannot read, the rule refuses its first piece.
  Then either the pieces are checked as one write (the handler has the
  whole record when the payload sends it whole), or the reader accepts
  an unfinished last record, which changes
  [what upstream chose](roadmap.md#variable-store-robustness) and is
  the owner's to decide. Not a state that the rule lets through because
  it looks like an unfinished write: what is let through can be left
  there.
- **The fault tolerant write** (F6): if a pending record can rewrite the
  store at the next start, the working and spare blocks are part of what
  the rule covers. With the reclaim at runtime refused anyway, the
  plain form is that they do not change while the lock is armed, if F6
  says that no other write needs them.
- **The setup after a boot attempt**: the lock is armed at ReadyToBoot.
  A boot option that returns to the menu leaves the setup unable to save
  until the next start, for every option now. The setup must say so
  rather than seem to save (`OptionLockStatus` is there to read); the
  row is the owner's.

### In the payload

Only what the rule needs: the PCD of the reclaim, the message of the
setup, the status. The lock of the variable driver for the options
(`CFR_OPTFLAG_LOCK_AT_BOOT`, repaired by `edk2/0058`) is the standard
half of the same lock, for code that runs between ReadyToBoot and the
OS: turning it on for every option of the boards is part of this stage
if the owner agrees, and changes nothing for the OS.

## The proof

Unit tests of the decision, in coreboot's `tests/`, next to
`tests/drivers/efivars.c`, on stores that the test builds (never a copy
of a machine's). The decision function compiled for the host with the
store as a memory region. At least:

| Case | Decision |
|---|---|
| not armed: anything | allowed |
| a new variable of another GUID appended; one updated (the new record, then the states of the old one), step by step | allowed at each step |
| a boot entry created and deleted | allowed |
| the value of an option changed (a new record of the same name) | refused |
| an option deleted (the state of its record) | refused |
| a variable of the options GUID that was not there | refused |
| the same name with other attributes | refused |
| the block of an option erased | refused |
| the header of a record damaged, the options before and after it | refused |
| bytes written after the last record | refused |
| a read error during the check | refused |
| the working and spare blocks, as stage 0 decides | as decided, with the pending record of F6 |
| the sequences of F4 for an ordinary write, as the payload sends them | allowed at each step |
| more options than the latch holds | the lock of the two options, the status |
| the Kconfig off: the two options of today turned off, deleted, the store erased | the decisions of v1.6.3 |

The CI does not run coreboot's unit tests today
(`make run-tests/device/ddr3-test`, `tests/drivers/efivars` run by
hand). A step of the *Build* workflow that runs the ones the project
adds or changes (they need `libcmocka-dev` and vboot's submodule) is
part of this work: a check that does not run does not hold.

### On the machine

What must keep working, on each candidate, with *BIOS Lock* on. The
record is `docs/tests/v1.7.0/m920x-fsp/README.md`, as the ones before:
a table *ID, Result, Notes* with the numbers, the files next to it, no
copy of the flash.

| ID | Check | Expected |
|---|---|---|
| LOCK-01 | FLASH-06 of [docs/testing.md](testing.md): `od -An -tx1 /sys/firmware/efi/efivars/OptionLockStatus-ceae4c1d-335b-4685-a4a0-fc4a94eea085`; `cbmem -1 \| grep -i "option lock"` | armed; the line of ramstage names the lock for every option |
| LOCK-02 | VAR-01: twenty writes of `Timeout`, `MSR_SMI_COUNT` around each | the numbers against F1 and against each step of stage 1 |
| LOCK-03 | a boot entry created and deleted with `efibootmgr`; a variable of the test's own GUID created, changed and deleted through efivarfs | each works, the entries as before at the end |
| LOCK-04 | three suspends and resumes, then LOCK-01 and LOCK-03 | the lock still armed, the writes work |
| LOCK-05 | the next candidate as a capsule (`update.py stage`), with the lock armed | installed; the settings, the VPD and the event log kept |
| LOCK-06 | the setup options as the store has them (F2), before and after the whole run | the same, name by name |
| LOCK-07 | `hw-report.py`, `cbmem -t` | the report of the baseline (v1.6.3); the boot no slower |
| LOCK-08 | CONF-03 and CONF-04: `fwts`, `chipsec_main`, as in the record of v1.6.3 | no new failure |
| LOCK-09 | a variable of the test's own GUID written again and again until a write fails, the bytes counted; a reboot; one more write; the variable deleted | how much one boot can write; after the reboot the write works and the store has its space again (F2 before and after). Last of the run, and only on a build where F5 says the payload reclaims at its start |

The owner's rows: an option changed in the setup and kept; the setup
after a boot option that came back; *Go back to*; VAR-01 with *BIOS
Lock* off; a boot of the W541 with the same candidate, with its lock
unchanged.

## Decisions for the owner

1. **No reclaim of the store at runtime while the lock is armed**, with
   the reclaim at the start of the payload instead: the numbers of
   LOCK-09 say what it costs.
2. **The reader and an unfinished last record**, only if F4 says an
   ordinary write needs it.
3. **The lock of the variable driver for every option**
   (`CFR_OPTFLAG_LOCK_AT_BOOT`), and the message of the setup.
4. **The W541**: the same Kconfig in its defconfigs, after FLASH-06 and
   the regressions there, with macOS (the NVRAM that OpenCore uses is
   written through the same store).
5. **The candidates** (rule 11), and when the branch goes to `next`.
6. What stage 0 finds about the fault tolerant write, if it concerns
   the releases already out.

## Risks

- **RISCHIO BRICK class**: SMM and the payload of the RW slots, not the
  read-only part. A check that refuses too much leaves variable writes
  failing, the setup not saving or a capsule not installing; a handler
  that hangs leaves a slot that does not boot. The way back is the other
  slot (rule 7), by vboot after two failed boots or `update.py rollback`.
- **The variable store**: a write refused half way through a sequence
  of the payload must leave a store that the payload reads at its next
  start; LOCK-09 is the test, and rule 8 the stop.
- **The W541**: the code is shared. With the Kconfig off its build must
  give the same decisions as v1.6.3 (the last row of the unit tests),
  and the CI builds it.
- **Not covered by any of this**: code that runs before ReadyToBoot
  (`Driver####`, `SysPrep####`, option ROMs with Secure Boot off) can
  write the options as the setup does. That is the other open point of
  the roadmap, and the owner's decision.
