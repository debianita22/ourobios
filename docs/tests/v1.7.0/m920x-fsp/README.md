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

Step 1 of the plan, *the erased tail read once*, does not come out as a
change of its own here. The walk finds where the records end only by
walking; the erased-tail scan runs at that point, and the overlay cannot
tell a tail read from a header read, so the tail cannot be skipped
except where the write lands without the walk knowing where the tail
begins — which is step 2, the store held in SMRAM. So step 1 folds into
step 2: a copy of the variable store in SMRAM, made at the arm (the
latch of stage 2 is the same copy) and kept in step by the handler, the
only writer; the check of a write then reads no flash, and the erased
tail is a length, not a scan. Stage 1 is therefore done inside stage 2,
and LOCK-02 measures it on each candidate against the 0.285 s of F1.

## Stage 2, first part: the fault tolerant write (F6), on rc2

The owner chose to cover F6 inside stage 2. v1.7.0-rc2 (this branch,
patch 0281 and `edk2/0061`) carries its fix; the lock for every option
(the SHA-256 latch of the whole set in SMRAM) and the SMRAM store copy
of stage 1 are the next candidate, with the one decision left: the size
of the SMRAM subregion that would hold the 192 KiB store for the "reads
no flash" fast path, against keeping it at 4 KiB with a digest-only
latch and the walk cost of today.

**The fix (patch 0281):** the option lock and the MOR lock refuse, while
armed, any raw SMMSTORE write or erase that reaches past the variable
store, into the fault tolerant write blocks (`efi_fv_store_end()`).
Those blocks are where the payload restarts a pending fault tolerant
write at its start, before the lock is armed, so a write of them could
rewrite the store with a protected option off. A reclaim of the store
uses them and is refused too; it writes the spare area first, before it
erases the store, so a refused reclaim leaves the store intact and the
variable write fails until the next boot. `edk2/0061` moves the reclaim
to EndOfDxe, before the lock is armed, so it is not refused in the
normal flow. Unit test: `efi_test_store_end` (a valid and a broken
firmware volume), with the 32 tests of `drivers/efi` passing.

The rows below are filled from the run on rc2 once it is built,
installed and tested (to run):

| ID | Check | Expected |
|---|---|---|
| UPD-02 | rc2 as a capsule from rc1, slot A; rc1 kept in slot B | installed |
| LOCK-01 | the option lock armed (`OptionLockStatus`) | `06 00 00 00` and eight zeros |
| LOCK-02 | 20 writes of `Timeout`, `MSR_SMI_COUNT` around each | near F1 (0.285 s, 45 ms an SMI): the fix is a bounds check, no walk added |
| LOCK-03 | a boot entry created and deleted; a variable of the test's GUID created, changed, deleted through efivarfs | each works, the entries as before |
| LOCK-04 | three resumes, then LOCK-01 and LOCK-03 | the lock still armed, the writes work |
| LOCK-06 | the 36 options before and after the run | the same, name by name |
| LOCK-07, LOCK-08 | `hw-report.py`, `cbmem -t`; fwts, chipsec | the baseline of v1.6.3; no new failure |
| LOCK-09 | a variable written until a write fails, a reboot, one more write, the variable deleted | how much a boot can write; after the reboot the write works and the space is back |

