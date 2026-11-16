# Hardware tests of v1.8.0

What to run on the two machines for v1.8.0: the reclaim of the variable
store with fewer erases (patch 0314, `edk2/0067`), the locks armed
before code that is not the firmware's (`edk2/0068`) and, on the W541,
the DRAM voltage from the devicetree (patch 0315). The IDs are those of
[docs/testing.md](testing.md); what each change is, in
[CHANGELOG.md](../CHANGELOG.md).

Written for an agent that works on a machine by itself, under Linux,
as root or with `sudo`. It runs every row marked **agent** without
asking, in the order of the file, and leaves the rows marked **owner**
in the record as *not run, needs the owner*. A row it cannot run is
recorded with the reason, not skipped in silence, and never turned into
a PASS by changing the test.

## Rules

Those of [test-v1.6.3-w541.md](test-v1.6.3-w541.md#rules) and
[dev-v1.7.0-m920x.md](dev-v1.7.0-m920x.md), which hold here word for
word. The ones that matter most:

1. **A copy of the flash first**, and after every write
   (`flashrom -p internal -r FILE`, with the SPI driver of the kernel
   released first). flashrom only reads.
2. **The only writes of the flash are capsules** (`update.py stage`).
3. **No setup option is changed from the OS**, and no tool issues
   SMMSTORE SMIs. The probe of LOCK-12 reads two variables and writes a
   volatile one of its own: it is the one new program these tests run
   before a boot, and it writes nothing to the store.
4. **Never ask the firmware for its setup** (`systemctl reboot
   --firmware-setup`, `efibootmgr` with `OsIndications`): from v1.8.0
   the machine then stops in the setup with nobody at the keyboard, and
   stays there. That is LOCK-13, the owner's.
5. **Stop the whole run** and report on: a `FAIL` of FLASH-01 with the
   protections on, a slot that vboot marks failed, a machine check or a
   memory error, a store that the payload formats (the options at their
   defaults, the boot entries gone), a write of a variable that fails
   outside LOCK-11.
6. **The repository**: the record only, `docs/tests/v1.8.0/<board>/`,
   committed on the branch the candidate was built from, with the git
   identity of the repository and no trailer of an AI
   (`tools/ci-check.sh` refuses one). No tag, no release, no force push.

## The builds

- **Before**: v1.7.0 (or its last candidate, rc15) in the running slot.
  The numbers of LOCK-11 and LOCK-12 are taken on it first, as the
  reference: the same scripts, the same store.
- **Candidate**: a pre-release `v1.8.0-rcN`, with its capsule, published
  at the owner's request. A test build of the CI (`ci-NNN`) has ROMs and
  no capsule: nothing to install from it. A candidate of v1.8.0 has a
  version above v1.7.0: after it, v1.7.0 itself installs only with *Go
  back to* in the setup, not as a capsule.
- **Way back**: the other slot (v1.7.0), by vboot after two failed boots
  or with `update.py rollback`. **RISCHIO BRICK class**: SMM, ramstage
  and the payload of the RW slots, and on the W541 one line of the
  devicetree that the native RAM init reads; nothing of the read-only
  part.

## The order

| Step | Row | Who | What to keep |
|---|---|---|---|
| 1 | LOCK-11 on v1.7.0 | agent | the time of each reclaim (`lock09.py fill 1000` prints the slow writes), `storeinfo.py` on a copy of the flash before and after |
| 2 | LOCK-12 on v1.7.0 | agent | the four numbers of the probe: the first must be `800000000000000e` |
| 3 | the capsule of the candidate, a reboot | agent | UPD-01; on the W541 `sudo cbmem -1` of that boot (it trains: MEM-25) |
| 4 | `hw-report.py`, FLASH-01, FLASH-06, LOCK-01; `ls /sys/firmware/efi/efivars/ \| grep OptionLockEarly` | agent | the report; no `OptionLockEarly` variable (LOCK-12, the boot as the machine is). One that is there with no `Driver####` and no `SysPrep####` option is a finding: stop and report |
| 5 | MEM-25 (W541) | agent | *DRAM voltage: 1350 mV (devicetree)*, one training, then none; `ddr-report.py --compare` with the dump of v1.7.0 |
| 6 | LOCK-11 on the candidate, four reclaims, then the write that fails | agent | the times, next to those of step 1; `storeinfo.py`: one more slot used by each reclaim, the note of the limit the last of the notes; the options of the copy at the end those of the start (LOCK-06) |
| 7 | a reboot, LOCK-09 and LOCK-03 | agent | the payload reclaims at boot, the writes work, no record left to finish in `cbmem -1` |
| 8 | LOCK-12 on the candidate | agent | the first two numbers `0`, `OptionLockEarly` there and in FLASH-01; then the option removed and a reboot: both variables gone |
| 9 | three `rtcwake -m mem -s 30`, LOCK-04 | agent | the lock still armed, the protected ranges back |
| 10 | `fwts` (M920x), `stress-ng` 30 minutes (W541) | agent | nothing failed, no memory error |
| 11 | LOCK-13, LOCK-10 | owner | the setup's question, the restart into the setup, a change that holds |
| 12 | macOS (W541): boot, `nvram` write kept after a restart, sleep and wake three times, dark wake, the dGPU off | owner | as for v1.7.0 |
| 13 | Windows: boot, *Device security*, *Advanced startup* into the setup | owner | optional |

Steps 1 and 2 on v1.7.0 are the measure before; without them the
numbers of steps 6 and 8 have nothing to stand against.

## The scripts

In [tests/v1.8.0/scripts](tests/v1.8.0/scripts): `lock09.py` (the
writes of the test variable, with the time of the slow ones) and
`storeinfo.py` (the store and the commit block of a copy of the flash,
in the format of v1.8.0 and of v1.7.0). The others are those of
[tests/v1.7.0/m920x-fsp/scripts](tests/v1.7.0/m920x-fsp/scripts).

The probe of LOCK-12, built on the machine (`clang` and `lld`):

```sh
clang --target=x86_64-unknown-windows -std=c11 -O2 -ffreestanding \
      -fno-stack-protector -mno-red-zone -mgeneral-regs-only -nostdlib \
      -fuse-ld=lld -Wl,-subsystem:efi_application -Wl,-entry:efi_main \
      -o lock-probe.efi CLONE/tools/efi/lock-probe.c
sudo mkdir -p ESP/EFI/ourobios && sudo cp lock-probe.efi ESP/EFI/ourobios/
sudo efibootmgr --sysprep --create --disk DISK --part N \
     --loader '\EFI\ourobios\lock-probe.efi' --label lock-probe
sudo efibootmgr --sysprep            # the number of the option, for its removal
```

With Secure Boot on the unsigned probe is refused before the firmware
arms anything, and the row is *not run*: say so, do not turn Secure
Boot off (it is a setup option).

## What the numbers should be

- **LOCK-11**: with v1.7.0-rc15, 7.70 to 7.73 s a reclaim on the W541
  (8.66 s the first of a boot) and 2.2 to 2.4 s on the M920x. With
  v1.8.0 a reclaim erases four blocks of 64 KiB in place of seven, when
  the reclaimed store fits one block (less than 64 KiB used after the
  reclaim; `storeinfo.py` says). The first reclaim after a boot in which
  the payload reclaimed the store by itself, as the boot after a run
  that reached the limit of four, erases one more: the block of the
  commit record, where the payload left a copy of its own. On the W541, where an erase is about a second, some
  three seconds less are expected; nothing was measured yet, and a time
  that does not go down is a result to record, not to explain away.
- **LOCK-12**: `0 0` in the first two numbers, against
  `800000000000000e ffffffffffffffff` with v1.7.0.
- **MEM-25**: the training of that one boot, about as long as the one
  after the update to v1.7.0-rc14.
