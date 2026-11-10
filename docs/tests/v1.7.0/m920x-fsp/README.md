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
not before it; the fix stays on the v1.7.0 branch for now, a v1.6.x
backport decided after the tests on the machine.

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

One candidate, v1.7.0-rc2 (patches 0281 and 0282, `edk2/0061`), as the
owner asked.

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

**F4, a header split at the end of a flash block:** the payload's
driver writes a variable header (60 bytes) in two raw writes when it
crosses the end of a 64 KiB block. After the first piece the reader
cannot read the store, so the rule refuses it: that `SetVariable` fails
and the store stays as it was (unit test `test_split_header`). It
happens when the next record starts in the last 60 bytes of a block,
about one append in a thousand; the driver then tries the same place
again, so variable writes of the OS fail until something moves the end
of the records (a write of the firmware before the arm, or a reclaim).
The store of this machine is at 0x17500 of 0x30000: the next such
place is the block end at 0x20000. This is decision 2 of the plan, for
the owner: either coreboot's reader takes "less than a header left in
the block, the rest of the store erased" as the end of the records
(then the piece can be allowed, and a power loss at that point no
longer resets every option to its default, which it does today), or
the payload pads past the block end before it arms the lock.

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
| the first piece of a split header | refused (F4) | `test_split_header` |
| after a resume, with an option written by ramstage | the set of the flash at the resume | `test_resume` |
| the set unreadable at the arm | the lock of the two options, `SMMSTORE_RET_FAILURE`, the blocks past the store refused | `test_no_latch` |
| the Kconfig off: another option changed; a security option turned off; one deleted | allowed; refused; allowed (it reads as its default) | `test_two_options` |

The rows of the machine, to run on rc2:

| ID | Check | Expected |
|---|---|---|
| UPD-02 | rc2 as a capsule from rc1, slot A; rc1 kept in slot B | installed |
| LOCK-01 | `OptionLockStatus`; `cbmem -1 \| grep -i "option lock"` | armed; ramstage: *option lock for every setup option* |
| LOCK-02 | 20 writes of `Timeout`, `MSR_SMI_COUNT` around each | against F1 (0.285 s, 45 ms an SMI) |
| LOCK-03 | a boot entry created and deleted; a variable of the test's GUID created, changed, deleted through efivarfs | each works, the entries as before |
| LOCK-04 | three resumes, then LOCK-01 and LOCK-03 | the lock still armed, the writes work |
| LOCK-05 | the next candidate as a capsule, with the lock armed | installed |
| LOCK-06 | the 36 options before and after the run | the same, name by name |
| LOCK-07, LOCK-08 | `hw-report.py`, `cbmem -t`; fwts, chipsec | the baseline of v1.6.3; no new failure |
| LOCK-09 | a variable written until a write fails, a reboot, one more write, the variable deleted | how much a boot can write; after the reboot the write works and the space is back |
