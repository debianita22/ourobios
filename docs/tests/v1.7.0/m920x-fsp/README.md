# v1.7.0 on the M920x: the option lock

The work of [docs/dev-v1.7.0-m920x.md](../../../dev-v1.7.0-m920x.md) on
the ThinkCentre M920x of the port, by an agent on the machine (Proxmox,
root, lockdown `[none]`), branch `ci-test/v1.7.0-m920x-option-lock`.

At the start, 2026-11-10: v1.6.3-rc4 in slot A, v1.6.2 in slot B, the
read-only part of `ci-203`, *BIOS Lock* and *Firmware protection* on, no
guest running (VM 101 stopped). A copy of the flash first, kept on the
machine only (no other place reachable). Then v1.7.0-rc1 as a capsule
from rc4 into slot B (UPD-02, *ultimo: v1.7.0-rc1, riuscito*): slot B
holds a candidate that booted, slot A will take the next one (rule 7).

## Stage 0: the facts

On v1.7.0-rc1 (slot B) and from the sources of the branch (coreboot
with the series, MrChromebox's EDK II `6c14abf865e0` with
`patches/edk2`).

| # | Answer | From |
|---|---|---|
| F1 | 20 writes of `Timeout`: median **0.285 s**, worst 0.293, best 0.284; 6 to 8 SMIs a write (126 for the 20), **45 ms an SMI** | `MSR_SMI_COUNT` around each `efibootmgr -q -t` ([f1-var01.txt](f1-var01.txt)) |
| F2 | `SMMSTORE` 512 KiB at 0xc10000, one firmware volume over all of it (header 0x48). The variable store (authenticated) is the first **192 KiB** (196536 bytes, to 0x30000): 95480 bytes used, 101028 free, 625 records, 106 valid and 519 deleted (a reclaim ran since the 137 KiB used of 2026-11-09). **36 options** of the options GUID, one record each, no duplicate name; 35 with attributes NV+BS (0x3), `me_state_counter` NV+BS+RT (0x7). The other 70 valid records: 20 GUIDs, the most of them EDK II's own (31 of `39b68c46-…` and 17 of the global variable GUID). After the store: the **FTW working block at 0x30000** (64 KiB, 148 bytes written: its header and records) and the **spare area at 0x40000** (256 KiB), erased | a copy of the flash read with `var_store()` of `tools/update.py` ([f2-store.txt](f2-store.txt)); `SmmStoreFvbRuntime.c`: spare = half the blocks, working = one block, the variables the rest |
| F3 | coreboot writes the options GUID only before the payload: `efi_option_reset_all()` in romstage (the reset on an RTC loss, patches 0175, 0256, 0270), `set_uint_option()` (here `me_state_counter` from `cse.c`, ramstage). The payload writes them in the setup (`CfrSetupMenuDxe`), before ReadyToBoot. After ReadyToBoot nothing of the firmware writes them | `grep` of the coreboot tree and the package |
| F4 | A variable write of EDK II's variable driver is a sequence of raw writes: the header, its state *header valid*, name and data, the state *added*, then the old copy *in deleted transition* and *deleted*: 6, and 7 or 8 when a piece crosses a 64 KiB block (`SmmStoreFvb` writes block by block), as F1 counts. A header can cross a block boundary, so between two pieces the store can hold a record whose sizes are not written yet: coreboot's reader then calls the store corrupt. Today's check takes that as "default" for the two options and lets it through; the rule of stage 2 would refuse it. The lines of the handler with `DEBUG_SMI` are still to be read on a candidate built for it | the sources of `Variable.c` (`UpdateVariableStore()`), `SmmStoreFvbRuntime.c`, `walk_variables()` |
| F5 | The variable driver reclaims at its start only when the free area is not erased, and at **ReadyToBoot** (`ReclaimForOS()`, as `PcdReclaimVariableSpaceAtEndOfDxe` is FALSE by default and the payload does not set it) when the space left is below one variable (`PcdMaxVariableSize`, 0x8000 from coreboot's Makefile); at runtime when a write does not fit. A reclaim goes through the fault tolerant write (`FtwVariableSpace()`): the spare blocks erased and written, the working block's records, then the store's blocks erased and written | `Variable.c`, `VariableDxe.c`, `MdeModulePkg.dec` |
| F6 | **The fault tolerant write is a way around the option lock.** At its start, before ReadyToBoot and so before the lock is armed, `FaultTolerantWriteDxe` (`InitFtwProtocol()`) finds a last write record with *spare complete* and not *complete* and **restarts it: it copies the spare blocks over the variable store**. The working and spare blocks are in `SMMSTORE`, outside the variable store, which is all that the check reads: a raw write there leaves the store as it is, so the check of today allows it. A record and a spare copy written with the raw commands during one boot can then make the payload of the next boot write the store with the two protected options off, which coreboot reads at the boot after. The same holds for the MOR lock. It concerns every release with the lock, from v1.6.1. **Not tried on the machine** (rule 3); the proof is to be a unit test of the decision | `FtwMisc.c` (`InitFtwProtocol()`, the *Restart* branch), `store.c` (`options_lock_allows()`, the part of a write inside `SMMSTORE`), `options_lock.c` (the overlay of the variable store only) |
| F7 | In SMM only the two raw commands write `SMMSTORE` (`smmstore_rawwrite_region()`, `smmstore_rawclear_region()`), the capsules included (`SMMSTORE_CMD_USE_FULL_FLASH` goes through the same functions, and the check takes the part of a write inside `SMMSTORE`); vboot writes `RW_NVRAM`, the MRC cache its own region. Nothing goes around the check | `grep` of `rdev_writeat`, `rdev_eraseat` in the `smm` sources |
| F8 | vboot's library is built for the SMM stage (`vboot_lib.c`, `vboot_fw.a` for `smm`), so its SHA-256 can link there. The space of the handler (static data, stack) is to be read from the build of the first candidate | `src/security/vboot/Makefile.mk` |

## Decisions asked of the owner

After F6, before any code of stage 2: whether the working and spare
blocks are refused to writes and erases while the lock is armed, which
also stops the reclaim at runtime (decision 1 of the plan), with the
reclaim moved to EndOfDxe (`PcdReclaimVariableSpaceAtEndOfDxe`) so that
it runs before the lock; and whether the fix goes to a v1.6.x release
too (decision 6).

The owner's answers (2026-11-10): the fault tolerant write is covered
**inside stage 2**, with the lock for every option, in one candidate,
not before it; the fix stays on the v1.7.0 branch, and after the run
on rc2 the owner decided that a v1.6.x backport is not needed
(2026-11-11).

## Stage 1: the time of a write

Where the 45 ms of an SMI go (F1): the check walks the store as it would
be after the write, and the walk reads every header and name and then
the whole erased tail (101 KiB of the 192, `region_is_erased()` in
64-byte reads) through the overlay's `readat`, which has no `mmap`.

Step 1 of the plan, *the erased tail read once* (in patch 0282): the
walk of the arm says where the records end (`efi_fv_walk_guid()`), and
the handler, the only writer of the store while armed (F7), keeps that
mark: a write past it moves it to the end of the write. The overlay of
a check answers reads past the mark with erased bytes, then lays the
write over them, so a write into the tail is still seen and the
decision does not change; what a walk reads from the flash is the 625
headers, about 40 KiB of the 150. The mark is with the handler's
statics, taken again with the set of options after a resume.

Step 2, the store in SMRAM, only if LOCK-02 on the candidate leaves the
SMI well above the flash write.

## Stage 2: the lock for every option, and the fault tolerant write

One candidate, v1.7.0-rc2 (patches 0281 to 0283, `edk2/0061`), as the
owner asked: the same candidate has the W541's work on rc1 (patches 0278,
0280, 0290).

**The fault tolerant write, F6 (patch 0281):** the option lock and the
MOR lock refuse, while armed, any raw SMMSTORE write or erase that
reaches past the variable store, into the fault tolerant write blocks
(`efi_fv_store_end()`), from which the payload would rewrite the store
at its next start. A reclaim of the store uses them and is refused too;
its first writes are to those blocks, before it erases the store, so a
refused reclaim leaves the store intact and the variable write fails
until the next boot. `edk2/0061` moves the reclaim to EndOfDxe, before
the lock is armed.

**The rule (patch 0282, `SMMSTORE_OPTION_LOCK_ALL`, on in
`boards/m920x/fsp.defconfig` only):** the set is every live variable of
the options GUID (added, or added and in deleted transition) with its
state, attributes, name and data, in the order of the store, from the
walk of the reader that the boot uses; kept as a count and a SHA-256
(vboot's, in C). A write or an erase is refused when the store as it
would be after it has another set, or the reader cannot read it. This
is stricter than "what the reader returns for each name" and needs no
table of names: a second record of an option's name is one more
variable, so it is refused when it becomes one, whatever its
attributes. Nothing of the firmware writes those variables after the
arm (F3).

Decided while writing it, each with its reason:

- *The set is not in the SMRAM region.* SMM is loaded again on a resume
  from S3 and ramstage may write an option before it
  (`me_state_counter`), so a set kept across the resume would refuse
  every later write. The first check after a load takes the set from
  the flash again: between the suspend and the resume only the
  firmware writes it. The region keeps that the lock is armed, and for
  what.
- *No limit of options*: the mark is one digest, so "more options than
  fit" does not exist. The lock of the two options remains for a store
  that cannot be read at the arm, with `SMMSTORE_RET_FAILURE`, which the
  payload publishes in `OptionLockStatus` as an error status.
- *`me_state_counter`* has the runtime attribute (coreboot writes its
  own options so): the OS could write it with `SetVariable` and now
  cannot. Nothing known does.
- *The SMM stack* is 8 KiB with the option (4 KiB before): the hash runs
  inside the walk, the deepest call chain of SMM.
- *Not with `VBOOT_X86_SHA256_ACCELERATION`* (Kconfig): vboot's SHA
  extension code would use XMM registers inside SMM.

**F4, a header split at the end of a flash block (decision 2, left to
the agent by the owner; patch 0283):** the payload's driver writes a
variable header (60 bytes) in two raw writes when it crosses the end of
a 64 KiB block. After the first piece the reader cannot read the store,
so the rule refuses it, as the MOR lock already did since v1.6.0 when it
held a request; the variable write of the OS failed, and at every later
try, since the driver starts again at the same place (about one append
in a thousand; on this machine the records end at 0x17500, the next
such place is the block end at 0x20000).

Of the ways out, the one taken changes neither the reader nor the
payload: *the pieces are checked as one write*, in the handler. A raw
write that the locks refuse and that ends where a flash block ends is
kept in SMRAM, neither written nor failed; when the next raw write
begins where it ended, the two are checked and written together; any
other write or erase drops the piece (`split.c`). Not taken: a reader
that accepts an unfinished last record (it would have to follow what
EDK II's driver makes of each kind of half header, in the parser that
decides the options, and the flash would hold the state the rule is
there to keep out); a padding variable written by the payload before
the arm (it moves the first write of a boot only, the later ones reach
the next block end all the same). The rule stays as written: nothing
reaches the flash that the locks have not allowed as a whole, and while
a lock is armed the half header is never in the flash, not even across
a power loss. Before the arm the driver's two writes are as they were.

**The proof**, `tools/build.sh coreboot-unit-test` (in `check.yml` and
the update job of `build.yml`, with `libcmocka-dev`):
`tests/drivers/smmstore_options_lock.c`, built with the option (13
tests) and without it (5), and `efivars-test` (33).

| Case | Decision | Test |
|---|---|---|
| not armed: anything | allowed | `test_not_armed` |
| a variable of another GUID appended, updated (the new record, then the states of the old one), deleted, step by step; again past the tail of the arm | allowed at each step | `test_other_variables` |
| the value of an option changed: the new record | refused when it becomes a variable (the header, *header valid*, name and data are allowed and leave a dead record) | `test_option_changed` |
| an option deleted, in either state step | refused | `test_option_deleted` |
| a variable of the options GUID that was not there; the same name with other attributes | refused | `test_option_added` |
| the data, the name or the attributes of an option programmed over | refused | `test_option_bits` |
| the block of an option erased, the store still readable; the block of the headers | refused | `test_option_erased` |
| an erase of a block of the store with nothing in it | allowed | `test_option_erased` |
| the size or the start mark of a record damaged; the headers of the store; bytes after the last record, near and far | refused | `test_store_damaged` |
| a read error during the check | refused | `test_read_error` |
| the working and spare blocks written or erased | refused | `test_ftw_blocks` |
| the first piece of a header split at the end of a block | refused by the lock; kept by the handler, the flash unchanged, and written whole with the second piece; dropped by any other write; two pieces refused together | `test_split_header` |
| after a resume, with an option written by ramstage | the set of the flash at the resume | `test_resume` |
| the set unreadable at the arm | the lock of the two options, `SMMSTORE_RET_FAILURE`, the blocks past the store refused | `test_no_latch` |
| the Kconfig off: another option changed; a security option turned off; one deleted | allowed; refused; allowed (it reads as its default) | `test_two_options` |

## rc2 on the machine

v1.7.0-rc2 (`01a3449`: patches 0281 to 0283, `edk2/0061`,
`SMMSTORE_OPTION_LOCK_ALL`, with the W541's work of the same candidate)
as a capsule from rc1, 2026-11-11: slot A, rc1 kept in slot B, both
protections on, no guest running. Files in [rc2](rc2).

| ID | Result | Notes |
|---|---|---|
| UPD-02 | PASS | signature valid, rc2 from slot A, *ultimo: v1.7.0-rc2, riuscito*; the training kept |
| LOCK-01 | PASS | `OptionLockStatus` `06 00 00 00` and eight zeros: armed for the whole set (the arm answers an error when it falls back to the two options); ramstage: *SMMSTORE: option lock for every setup option, armed by the payload* |
| LOCK-02 | PASS | 20 writes of `Timeout`: median **0.100 s**, 6 to 8 SMIs a write, **15 ms an SMI** (F1 on rc1: 0.285 s, 45 ms), with the store at 117 KiB used and 855 records; after three resumes 0.129 s. After the reclaim of LOCK-09 (48 KiB used, 112 records): **0.026 s, 4 ms an SMI** ([rc2/lock02-rc2.txt](rc2/lock02-rc2.txt), [rc2/lock02-rc2-after.txt](rc2/lock02-rc2-after.txt)) |
| LOCK-03 | PASS | a boot entry created (`Boot0002`) and deleted, the entries as before; a variable of the test's GUID created, changed and deleted through efivarfs |
| LOCK-04 | PASS | three `rtcwake -m mem -s 30`, `suspend_stats/fail` 0; then the lock armed, PR0 and PR1 back, LOCK-03 again and the twenty writes: all work (the set taken from the flash again after the resume) |
| LOCK-05 | not run | needs the next candidate |
| LOCK-06 | PASS | the 36 options from a copy of the flash before the capsule (rc1), before LOCK-09 and at the end: the same, name by name |
| LOCK-07 | PASS | report 22 PASS at the first boot, 25 with a copy of the flash at the end ([rc2/hw-rc2-end.md](rc2/hw-rc2-end.md)); 10.75 s and 10.31 s to the payload (rc1: 10.43 s), FspMemoryInit 0.25 s |
| LOCK-08 | PASS | fwts `acpitables mcfg wsmt uefirtvariable` 43 passed, 0 failed (its variable stress test runs with the lock armed); chipsec `bios_wp`, `spi_lock`, `smm`, `smrr`, `bios_ts`, `uefi.access_uefispec` PASSED, `spi_desc` FAILED by design |
| LOCK-09 | PASS | below |

**A header across the end of a block, on the machine (patch 0283).**
Before LOCK-09 the records ended at 0x1ca0c. One write of the test's
variable with 13698 bytes of data took them to 0x1ffec, 20 bytes before
the block end at 0x20000; the next write (100 bytes) then has its
60-byte header across that end, in two raw writes. It went through
(0.160 s); in a copy of the flash the record at 0x1ffec is valid and
coreboot's reader reads the store. Without 0283 the lock refuses the
first piece and that write fails.

**LOCK-09.** Then writes of 1000 bytes of the same variable until one
failed: 55 went through (60280 bytes of records), the 56th failed with
`ENOMEM` (`EFI_OUT_OF_RESOURCES`) with 5080 bytes free of 196536, the
5 KiB that Linux keeps back; `efibootmgr -t` failed the same way. The
runtime reclaim did not run: the working block has the 148 bytes of
before, the spare area is erased, the store reads with coreboot's
reader, the 36 options are there. From the 79 KiB free at the start of
the test, a boot can write about 74 KiB of records before writes fail;
after a reclaim, 148 KiB. After a reboot: 47792 bytes used, 148716 free,
112 records (the reclaim at EndOfDxe of `edk2/0061`), the lock armed,
`efibootmgr -t 3` and a write of the test's variable work; the variable
deleted, the boot entries and `Timeout` as at the start, Secure Boot as
it was (off).

**Stage 1, closed.** With the erased tail no longer read, an SMI of an
armed write costs what the walk of the records costs: 15 ms with 855
records, 4 ms with 112. The payload reclaims only when the store is
nearly full, so the number of dead records, and the time, grows between
two reclaims: from 0.026 s to about 0.13 s a write. That is within
"a few milliseconds an SMI of the flash write" after a reclaim and 3
times better than v1.6.3 before one; step 2, the store in SMRAM, would
take the rest and is not built: it needs 192 KiB of SMRAM and a copy
kept in step, for 10 ms an SMI at most.

Left for the owner: LOCK-05 with the next candidate; the rows of the
setup (an option changed and kept, the setup after a boot option that
came back, *Go back to*); VAR-01 with *BIOS Lock* off; the W541 with its
lock unchanged, which rc2 also is.

## After rc2: the setup with the lock armed

The plan's row *the setup after a boot attempt*: a boot option that
returns leaves the lock armed, and with the lock for every option no
setting can be saved until the next restart. As rc2 is, the browser
shows *Submit Fail For Form* and the choice to discard, which keeps the
store right but explains nothing; an option locked by the variable
driver (`CFR_OPTFLAG_LOCK_AT_BOOT`, no option of the boards yet) would
even be reported as saved.

`edk2/0062`, for the next candidate: when the write of an option fails
and `OptionLockStatus` says that the payload armed the lock, the setup
says once that the settings are locked until the next restart and why,
and `RouteConfig` returns `EFI_ACCESS_DENIED`. The write is still tried:
the payload cannot tell the lock of every option from the lock of the
two (the W541, or the fallback), where the other options are saved.
Each refused try leaves a dead header in the store, 60 bytes and a name.

**Decision 3, left to the agent by the owner: the lock of the variable
driver for every option, on the M920x (patch 0284).**
`DRIVERS_OPTION_CFR_LOCK_AT_BOOT` gives `CFR_OPTFLAG_LOCK_AT_BOOT` to
every option that is not read-only when coreboot writes the CFR
records; the payload registers a rule for each before EndOfDxe and sets
the trigger at ReadyToBoot (`edk2/0058`). Taken because it is the
standard half of the same lock and costs nothing where the SMM lock
already holds: a write after ReadyToBoot is refused by the variable
services with `EFI_WRITE_PROTECTED`, before it becomes SMIs and a dead
record in the flash; it also holds for code that runs between
ReadyToBoot and the OS, and when the SMM lock is not armed (*BIOS Lock*
off) or fell back to the two options. Nothing of the firmware writes an
option through the variable services after ReadyToBoot (F3: coreboot
writes its own from romstage and ramstage, straight to the flash). A
Kconfig and not a flag on each option of `cfr.c`: an option added later
is locked without anyone remembering it. Not on the W541, whose lock
stays as it is until decision 4. `edk2/0062` takes the trigger as a lock
in force too, so that with *BIOS Lock* off the refused write is not
reported as saved.

The lock of the variable driver has not run on a machine before (no
option had the flag). What the next candidate must show, at the setup:
an option changed before any boot is kept (the rules must not lock
early); after a boot option that returned, the message. From the OS:
`tools/cfr-dump.sh` shows the flag on every option; LOCK-01 to LOCK-09
again.

Built by the CI; EDK II's PatchCheck passes. Not run: it needs a boot
option that returns and someone at the setup, the owner's row.

## rc3 on the machine

v1.7.0-rc3 (`f9dedc6`: rc2 with patch 0284, `edk2/0062` and the W541's
patches 0291-0298) as a capsule from rc2, 2026-11-11, **with the lock
of every option armed** (LOCK-05): slot B over rc1, rc2 kept in slot A,
both protections on, no guest running. Files in [rc3](rc3).

| ID | Result | Notes |
|---|---|---|
| LOCK-05, UPD-02 | PASS | the capsule staged and written with rc2's lock armed; rc3 from slot B, *ultimo: v1.7.0-rc3, riuscito*; the only new live variable is the capsule's result (`Capsule001F`), written by the payload before the arm |
| 0284 | PASS | the CFR record of the live coreboot table ([scripts/cfrflags.py](scripts/cfrflags.py), [rc3/cfrflags-rc3.txt](rc3/cfrflags-rc3.txt)): the 35 options that the setup can change have `CFR_OPTFLAG_LOCK_AT_BOOT`; the 9 others are the read-only rows of information (volatile) |
| LOCK-01 | PASS | `OptionLockStatus` `06 00 00 00` and eight zeros; ramstage: *option lock for every setup option* |
| LOCK-02 | PASS | 0.031 s a write, 4.9 ms an SMI, with 132 records at the start; 0.059 s after three resumes and the tests (363 records) |
| LOCK-03 | PASS | a boot entry created and deleted, the entries as before; the test's variable created, changed, deleted |
| LOCK-04 | PASS | three resumes, `suspend_stats/fail` 0; the lock armed, PR0 and PR1 back, LOCK-03 and the twenty writes again |
| LOCK-06 | PASS | the 36 options before the capsule and at the end: the same, name by name |
| LOCK-07 | PASS | report 22 PASS at the first boot, 24 PASS and 3 INFO with a copy of the flash at the end (the third INFO the ME's wait after a resume); 10.80 s to the payload, FspMemoryInit 0.25 s |
| LOCK-08 | PASS | fwts 43 passed, 0 failed; chipsec as on rc2 |
| LOCK-09 | as rc2 | not repeated: nothing of the store's handling changed since rc2 |

What only someone at the setup can see, for the owner: an option
changed before any boot is kept after a restart (the variable driver's
rules of 0284 must not lock before ReadyToBoot), and the message of
`edk2/0062` in the setup opened again after a boot option that
returned. From the OS the variable driver's lock cannot be tried: the
options are boot-service variables, invisible to it, and the only one
with the runtime attribute (`me_state_counter`) would be a setup option
changed from the OS, which the rules of the run forbid.

## The scripts of the run

In [scripts](scripts), run as root on the machine: `var01.py` (LOCK-02,
twenty writes of `Timeout` with `MSR_SMI_COUNT` around each),
`lock03.sh` (LOCK-03, a boot entry and a variable of a test GUID),
`storeinfo.py` (F2, the variable store of a copy of the flash, read
only), `lock09.py` (LOCK-09, writes of the test variable until one
fails), `cfrflags.py` (the flags of the options in the live CFR record,
from `cbmem -r 43425442`). They write only the test's own variable, the
boot entries and `Timeout`, through the UEFI variable services; none
sends SMMSTORE commands.
