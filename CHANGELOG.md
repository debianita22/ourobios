# Changelog

What changes from one release to the next. The notes of each release on
GitHub include its section; release candidates take the section of the
version they lead to. For the releases before v1.3.0, see their notes on
the [releases page](https://github.com/debianita22/ourobios/releases).

## v1.7.0

Not released. What ran on a machine: rc1 on the W541 (`nri`), as a
capsule from v1.6.3-rc4, with the modules of the port, which have no
XMP profile: MEM-10 to MEM-12 and MEM-14 passed, MEM-13 needs XMP
modules (2026-11-10,
[docs/tests/v1.7.0/w541-nri](docs/tests/v1.7.0/w541-nri/README.md)); rc1
on the M920x for the facts of the option lock work
([docs/tests/v1.7.0/m920x-fsp](docs/tests/v1.7.0/m920x-fsp/README.md)),
whose changes below are still to run on a machine.

- **The option lock and the MOR lock cannot be gone around through the
  fault tolerant write** (patch 0281, `edk2/0061`): the locks refused a
  raw SMMSTORE write that turns a protected option, or the MOR request,
  off, but only checked the variable store; the payload rewrites the
  store at its start from the fault tolerant write blocks, which are in
  the SMMSTORE region past the store and which the check did not cover,
  so a program with root could change a protected option across two
  boots. The locks now refuse a write past the store while armed; the
  store is reclaimed before the lock is armed (EndOfDxe) so a runtime
  reclaim, which uses those blocks, is rare and fails safely. This closes
  the bypass, which every release with the lock has (v1.6.1 to v1.6.3):
  those are not corrected, the fix comes with v1.7.0.
- **M920x: the option lock is for every setup option** (patch 0282,
  `SMMSTORE_OPTION_LOCK_ALL`): once the payload has armed it, a program
  of the OS can no longer write the variable store with the raw SMMSTORE
  commands so that coreboot reads another option at the next boot: a
  device turned off in the setup stays off, as *BIOS Lock* and
  *Firmware protection* stayed on. The variables of the OS (boot
  entries, the capsule variables) are written as before. One thing
  changes for the OS: a variable write that needs a reclaim of a full
  store fails until the next boot, which reclaims. The decisions are
  unit tests of coreboot, which the CI now runs. The W541 keeps the lock
  of the two security options.
- **M920x: the DDR4 refresh doubled when the memory is hot** (patch
  0285): FSP-M's `Refresh2X` on, for the hot range only, as JEDEC asks
  above 85 C; at normal temperatures nothing changes. The memory
  settings version goes up, so the first boot after the update trains
  the memory again (a few seconds more, once).
- **M920x: the variable store is reclaimed while the lock is armed**
  (patch 0288, `edk2/0064`): with the option lock armed, a store full
  of old records was cleaned up only at the next boot; meanwhile each
  variable write took longer, and once the store was full the writes of
  the OS failed. Now the payload builds the cleaned-up store and
  coreboot checks it whole in SMM with the rules of the lock before it
  replaces the old one, behind a commit record, so that a power loss
  during the swap is finished at the next boot. At most four times a
  boot, only when the store is nearly full; about a second each.
- **The firmware reports its security tests (HSTI)** (`edk2/0063`):
  when a boot starts, the payload reads the protections of the flash,
  SMRAM, the debug interface, Secure Boot, the TPM and the setup and MOR
  locks, and publishes the result as the HSTI table that Windows reads
  and as the variable `HstiTable` for Linux (`tools/hw-report.py`,
  CONF-08). The tests these machines cannot pass are reported as failed:
  the descriptor and the ME region writable by the host, no pre-boot DMA
  protection ([docs/hsti.md](docs/hsti.md)).
- **Two warnings fewer in the coreboot log of the M920x** (patches 0286
  and 0287): with the ME disabled, an S3 resume no longer warns that
  the ME's interface is disabled (the boot before the suspend turned
  it off), and a boot no longer warns that the optional `slic` file is
  missing from CBFS (the MSDM table comes from the VPD). The kernel's
  `hpet_acpi_add` and `SGX disabled` lines are not the firmware's: the
  kernel turns the HPET off itself on a processor that can enter PC10,
  and SGX is off on purpose
  ([docs/tests/v1.7.0/m920x-fsp](docs/tests/v1.7.0/m920x-fsp/README.md#the-warnings-of-the-logs)).
- **The setup says when the settings are locked** (`edk2/0062`): the
  option lock is armed when a boot is started. If the boot option
  returns and the setup is opened again, a change cannot be saved until
  the next restart; the setup now says so (*The settings are locked
  until the next restart: a boot was started. Restart and open the setup
  again to change them.*) instead of *Submit Fail For Form*. On the
  M920x the payload's variable driver also refuses those writes itself
  from that moment (patch 0284: every option has
  `CFR_OPTFLAG_LOCK_AT_BOOT`), before they reach the flash. Not seen on
  a machine yet: it needs someone at the setup.
- **A variable write no longer fails at the end of a flash block**
  (patch 0283): with the MOR lock holding a request, or the option lock
  armed, a variable whose header crossed the end of a 64 KiB block of
  the store could not be written from the OS, at any try, until the
  firmware wrote something there itself (about one append in a
  thousand; the first piece of the header alone leaves a store that the
  locks rightly refuse). The handler now checks and writes the two
  pieces as one.
- **W541 (`nri`): an XMP profile of the memory as an option** (patches
  0275-0279): *Hardware* → *Memory* → *Memory profile*, *SPD (JEDEC)* by
  default, or *XMP profile 1* or *2*. With a profile the native RAM init
  trains with the timings and the speed of that profile, when every
  module has it for the number of modules installed, at the voltage the
  board feeds (1.35 V with DDR3L modules: nothing raises it) and up to
  the speed the processor supports; otherwise the SPD timings are used
  and the log says why. A profile that fails the training or the memory
  test, or that does not reach the payload twice in a row, is given up
  by itself until the option is changed (CMOS byte 0x7d), so a profile
  that does not work cannot keep the machine from booting
  ([docs/raminit.md](docs/raminit.md#xmp-profiles)). **Not tried with
  XMP modules**: the four of the W541 of the port have none (bytes 176
  and 177 of their SPD read `ff ff`); with them the fallback to the SPD
  timings and the giving up passed (MEM-11, MEM-12). With the default the
  memory is set up as before; the first boot trains once, as the
  version of the saved training has the profile now. `mrc.bin` has no
  such option.
- **W541 (`nri`): the write Vref of the memory modules is centred**
  (patch 0280), the first of the training steps that the native RAM
  init lacked against `mrc.bin`. The modules sample what is written to
  them against a reference voltage, one per channel, which the native
  RAM init left in the middle of its range (`mrc.bin` ends 3 and 2
  steps above it on the W541). After the command training, every value
  of the reference is tried with a write and read test on every rank,
  and each channel gets the centre of the values that pass; a channel
  whose range of passing values is not closed on both sides, or is
  narrower than 8 steps, keeps what it had, and a training redone after
  a failed memory test does not run the step. `sudo cbmem -1 | grep
  'WRV:'` on the boot that trained has the range, which is the write
  voltage margin of the machine. On the W541 with rc1 (MEM-14): 3 and
  -1 on the two channels, 4 and 1 at a second training, in eyes 32 to
  39 steps wide; the same after a reboot, a cold boot and a resume;
  the memory test and 30 minutes of `stress-ng` clean. A boot that
  trains takes 0.98 s in the RAM init (0.83 s before); the boots from
  the saved training do not change. From rc2 a move of the reference of
  more than one step waits for the circuit (rc1 logged *Vref circuit N
  failed to converge* once per channel, harmless).
- **W541 (`nri`): the command Vref of the memory modules is centred**
  (patch 0290), the second of those steps: the reference of the
  command, address and control inputs, one for both channels, which
  `mrc.bin` leaves 3 steps below the middle. After the command
  training, every other value is tried with a JEDEC init and the test
  of that training on every rank, and the reference gets the centre of
  the values that pass, unless their range is not closed on both
  sides, is narrower than 20 steps, or the test does not pass at the
  centre with the reference 8 steps to each side. `sudo cbmem -1 |
  grep 'CMDV:'` has the range. On the W541 with rc2: -5, and -4 at a
  second training, in a range of 70 steps (MEM-15).
- **W541 (`nri`): the margins of the memory in the log** (patches
  0291-0297): after the training, how far the read and the write timing
  and voltage of every rank can move before errors, with a warning below
  the retrain limits of the MRC. A report, 1 to 2 s in a boot that
  trains. It comes from the upstream author's code, which he put on
  Gerrit as work in progress in these days (CB:97117 to 97267), with a
  fix for a search that never ended there. On the W541 with rc3: every
  search ended, and three voltage margins of channel 1 are one or two
  steps below the limit (MEM-17).
- **W541 (`nri`): the read and write timing centred in two dimensions**
  (patches 0295, 0299, from rc4): the upstream author's 2D centring,
  with the per-bit deskew, on top of the 1D training, with a correction
  of its units, and from rc5 the time for a Vref move that is late
  (patch 0301). On the W541 with rc4 (MEM-18): channel 0 wider on every
  rank, channel 1's first DIMM narrower in the read timing; rc5 is
  measured with two trainings.
- **W541 (`nri`): the training steps that the native RAM init lacked
  against the MRC, as the MRC of the Lenovo firmware does them** (patches
  0302-0307, from rc6). They were read in the MRC of the stock firmware of
  the W541 (GNET94WW), step by step:
  - the **write to read turnaround between ranks**: one clock under the
    JEDEC sum if the turnaround test passes with the read and write eyes
    squeezed by 7 to each side (4 to 3 here, as with `mrc.bin`). rc3 and
    rc4 tried a scan for the shortest value that passes (patches 0298,
    0300, out of the series): the test passes down to 0, and the MRC does
    not scan;
  - the **write and command Vref** centred with the margin search after
    their scans (the write Vref on three write timings, all ranks at
    once), where one test per value let the result move by up to 3 steps
    between trainings;
  - the **read Vref**: the offset of every bit's receiver centred on the
    read data, then the reference of every byte on three read timings;
    the sense amplifier training had set the bits from one sample each;
  - the **signal settings of each byte** (write drive strength and
    equalisation, read termination and receiver bias), each byte at the
    value with the widest eye: the MRC gives the narrow bytes of channel
    1 a stronger termination, where the native RAM init set the same for
    all;
  - a **summary** of what these steps decided, in the part of the log of
    a training boot that is kept (`sudo cbmem -1 | grep -A20 'NRI
    summary'`).

  With rc6 on the W541 the turnaround went to 3 and the write margins
  came out even; the read margins were narrower, as the global
  compensation step moved the per-byte read termination with its static
  legs off: patch 0307 (from rc7) moves it only near the end of the
  offsets' field. With rc5 channel 1 came out of one training in three
  with margins 5 to 9 steps narrower: rc7 is to show whether the spread
  is gone (MEM-20, MEM-21). A boot that trains takes 3.7 s in the RAM
  init (2.3-2.5 s with rc5).
- **`tools/ddr-report.py` shows the per-bit deskew** (`RxPerBit`,
  `TxPerBit`, one nibble per bit), and **`tools/hw-report.py` knows the
  report of the margins of the native RAM init**: margins below the
  retrain limits are an event (INFO) of BOOT-03 on the W541, not an
  unknown error; a search that does not end still is one.
- **W541 (`nri`): the lines about an XMP profile are in the log of a
  boot that trains** (patch 0278, from rc2): such a boot overflows the
  console of romstage and loses its start, with the lines that say a
  profile was asked for, refused or given up. They are said again once
  the console is in CBMEM, as a module left out already was.
- **XMP 1.3 profiles decoded exactly** (patch 0275): the fine offsets
  of a profile were not read, so a DDR3-1866 profile gave a cycle time
  of 1.125 ns, one standard speed lower, and the times of a profile
  with a timebase of 1/14 or 1/12 ns came out up to 1.6% short. With a
  unit test, which the CI runs.
- **The saved training of the `nri` variant also follows the SPD
  decoder** (patch 0276): a change of the code that reads the timings
  from the SPD trains once, as a change of the RAM init does.

## v1.6.3

Not released. What ran on a machine: rc1 on both boards, as a capsule
from v1.6.2, and rc2 on the M920x, by an agent with nobody there (2026-11-09 and 10,
[docs/tests/v1.6.3/w541-nri](docs/tests/v1.6.3/w541-nri/README.md),
[docs/tests/v1.6.3/m920x-fsp](docs/tests/v1.6.3/m920x-fsp/README.md)),
from the lists of `docs/test-v1.6.3-w541.md` and
`docs/test-v1.6.3-m920x.md`; patches 0271-0272 came after rc2.

- **The firmware watchdog is stopped whatever happens to the command**
  (patch 0266): the SMI handler stopped it only once the payload's
  confirmation of the slot had gone through its checks (the store
  initialized, the vboot nvdata in the flash). A confirmation that
  failed one of them left the watchdog armed, and the OS was reset at
  every timeout, in a loop when the slot was confirmed already. The
  handler now stops it as soon as the command arrives. Only with
  *Firmware watchdog* on (off by default).
- **No arming after three resets by the watchdog in a row** (patch
  0268): romstage counts the resets by the watchdog that follow one
  another with no boot confirmed in between (CMOS byte 0x7e), and at the
  third logs *Firmware watchdog: 3 resets in a row and no boot confirmed,
  not armed* and leaves it off, until a boot is confirmed again. The two
  resets that make vboot fall back from a slot on trial stay as they
  were. Tested on both boards with rc1 and a reset by the watchdog
  armed from Linux (WDT-02): the status bit is set after it, romstage
  logs *1 in a row*, and SMM clears the count when the payload confirms
  the boot; the third reset in a row was tried only by writing the byte
  ([docs/tests/v1.6.3/m920x-fsp](docs/tests/v1.6.3/m920x-fsp/README.md),
  [docs/tests/v1.6.3/w541-nri](docs/tests/v1.6.3/w541-nri/README.md)).
- **M920x: a reset by the watchdog is reported once** (patch 0267): its
  status in `OC_WDT_CTL` was logged and never cleared, so every boot
  after one would have said *the last reset came from the watchdog*; it
  is cleared after the log, as on the W541.
- **Firmware watchdog and a slot older than v1.6.1**: such a slot has
  no code for the watchdog. On both boards its reset is a global reset
  of the platform that keeps the training cache, and the enable bit
  does not survive it (WDT-02 with rc1 and v1.6.2; on the W541
  `OC_WDT_CTL` reads `0x02002000` after it), so a fallback to an older
  slot is not reset again. Still, turn the watchdog on only with v1.6.1
  or later in both slots.
- **M920x: the setup options are reset only when the CMOS was lost
  too** (patch 0270): the OS can set the RTC power loss bit on Cannon
  Point as on Lynx Point (OPT-06, set and cleared from Linux on the
  M920x), so the bit alone would have reset every option at the next
  boot, *BIOS Lock* and *Firmware protection* among them. As on the W541
  (patch 0256), the CMOS must have lost the last boot's POST code too; a
  bit set by software is cleared and logged (*Setup options: not reset,
  RTC power lost but the CMOS kept the last boot*). On the M920x with
  rc2 the bit set from Linux and a reboot kept the 36 options; a real
  CMOS clear (OPT-05) is still to run.
- **Variable writes faster with the option lock armed** (patch 0273):
  every write of the variable store walked the whole store once for
  each protected option before it was allowed, about 85 ms an SMI and
  0.6 s a variable write from the OS on the M920x (VAR-01). One walk now
  serves both options: 0.29 s a write with rc4. What is allowed and
  refused does not change.
- **A coreboot table of 64 KiB** (patch 0269): the setup menu is one
  record of the coreboot table, 28.2 KiB of the 32 on the W541, and
  help texts were shortened twice to add an option (patches 0261,
  0264). The table has 64 KiB now; what is written to it does not
  change. `tools/cfr-dump.sh` takes the size from the tree and leaves
  4 KiB of it to the other records: 60 KiB for the menu.
- **W541: the card reader no longer keeps the package awake** (patches
  0271, 0272): after most resumes from S3, and after some boots, the
  O2 Micro card reader reported latencies over LTR that kept the
  package in PC2 at idle: about 9 W instead of 1 W with the screen off
  or the lid closed. coreboot now leaves LTR off on that device, and the
  `_OSC` of the PCI host bridge keeps the control of LTR from the OS, so
  that it does not enable it again; the other devices keep their LTR.
  On the W541 with rc3: PC7 at 1.1-1.6 W with the screen off after the
  boot and after three resumes, where rc1 stayed in PC2 at 9 W.
- **W541: no backlight PWM left on after a resume with the screen off**
  (patch 0274): on every resume from S3 coreboot sets the backlight PWM
  at 50% and enables it, also when it leaves the display to the OS; with
  the screen off, Linux did not touch it and i915 warned *PCH PWM1
  enabled* in the kernel log every 20-30 s for as long as the screen
  stayed off (seen once the card reader no longer kept the package in
  PC2). After S3 the ACPI wake method turns the PWM off when the panel is
  not powered, but under macOS, which keeps the firmware's PWM.
  On the W541 with rc4: the PWM off after each resume, no warning, and
  the backlight back at its level with the screen on.
- **`tools/hw-report.py`: VB-02 recognizes the running slot on the
  W541**: it compared the SMBIOS version, which the W541 writes with the
  Lenovo ID in front (`CBET4000 ouroBIOS-...`), against the build names
  of the slots the wrong way round, and gave WARN at every boot.
- **The author of patches 0246-0265**: their `From:` was git's
  placeholder identity, as the author of the commits of 2026-11-08 and
  2026-11-09 that are in the tags v1.6.1 and v1.6.2. The patches are
  corrected, `.mailmap` shows those commits with their author, and
  `tools/ci-check.sh` refuses a placeholder identity in a patch or in a
  new commit.

## v1.6.2

What ran on a machine for v1.6.2: rc1 on the W541 (MEM-06, the
fingerprint switch, an S3 resume) and the release itself as a capsule
from rc1 (UPD-01/02, an S3 resume, 2026-11-09,
[docs/tests/v1.6.2/w541-nri](docs/tests/v1.6.2/w541-nri/README.md));
the release on the M920x, as a capsule from v1.6.1 with both protections
on (2026-11-09, [docs/tests/v1.6.2/m920x-fsp](docs/tests/v1.6.2/m920x-fsp/README.md)).

- **Two commits of MrChromebox less in the payload** (`edk2/0059`,
  `edk2/0060`): HS400 Enhanced Strobe, which he added to the eMMC side of
  `SdMmcPciHcDxe` for the Intel eMMC of his Chromebooks, is reverted: no
  board here has an eMMC. The SD reader of the W541 is driven by the same
  driver's SD path, which does not change. His changes to the start of
  the UEFI Shell (no `startup.nsh`, no mapping table, a banner) are
  reverted too: the boards' payload has no Shell. In the W541 `nri` ROM
  of the release against rc1, `BdsDxe` (the same size, the code relinked)
  and `SdMmcPciHcDxe` are the two payload modules that differ; the other
  837 files of the volume are byte for byte the same. `patches/tianocore` loses `0012` and `0062` (`REVERTED` of
  `tools/edk2-import.py`).

- **The package declares its own names** (`edk2/OuroBiosPkg`): the GUIDs,
  protocols, library classes and PCDs that only its modules use leave
  TianoCore's `UefiPayloadPkg.dec` and `MdeModulePkg.dec` for
  `OuroBiosPkg.dec`, their headers for the package's `Include/`, and
  MrChromebox's time and date page moves from `MdeModulePkg` into the
  package (`PACKAGE_DECLS`, `PACKAGE_HEADERS` and `OTHER_MOVED` of
  `tools/edk2-import.py`). The PCDs take the package's token space; all
  are FixedAtBuild, so the payload is the same (those of iPXE and CSMWrap
  stay: coreboot sets them by name). `patches/tianocore` loses 11
  patches that had nothing else; the "package" commits whose rest
  changes TianoCore's own modules are now carry or upstream in
  [docs/edk2-migration.md](docs/edk2-migration.md).

- **coreboot 26.09-607** (2026-11-09, from 26.09-517 of 2026-11-03): the
  pin moved by 90 upstream commits. The native RAM init of Haswell got
  its first Broadwell support and a refactoring upstream (16 commits):
  patches 0008 and 0086 were rebased onto it, 0185 (the rank mapping
  fix) is upstream and leaves the series, the other 257 apply as they
  were; the initial round trip delta of the NRI is now 0 upstream
  (CB:96893); on a W541 the round trip step of patch 0088 still
  shortens it, and ends at the 4 + 21 of v1.6.1 (MEM-06); the first
  boot of a v1.6.2 slot trains the memory once, as the version of the
  training cache follows the NRI code. The read-only
  interface was checked by hand: the vboot, TPM and cache-as-RAM code the
  slots share with the read-only part did not change
  ([configs/ro-interface.txt](configs/ro-interface.txt)).
- **Fingerprint reader switch on the W541** (patch 0265): *Hardware* →
  *Expansion ports* → *Fingerprint reader*, off disables its USB port at
  every start and wake, as the camera switch. The port comes from the
  Lenovo firmware's table; on a W541 without the reader the switch
  touches that port alone (Bluetooth and the camera stay).

## v1.6.1

What ran on a machine for v1.6.1: the M920x with rc1 to rc4
([docs/tests/v1.6.1/m920x-fsp/README.md](docs/tests/v1.6.1/m920x-fsp/README.md)),
a W541 with the `nri` CI builds of the W541 patches and then rc4 as a
capsule, with the Ethernet switch off and on and a resume from S3
([docs/tests/v1.6.1/w541-nri/README.md](docs/tests/v1.6.1/w541-nri/README.md)).
Not run: the `mrc` variant of the W541 (its features below are shared
with `nri`, but the test machine boots only `nri` slots), Wake on LAN
from off (NET-02), the armed firmware watchdog on the M920x, and a real
hang caught by the watchdog on either board.

- **Camera switch on the W541** (patches 0244-0245): *Hardware* →
  *Expansion ports* → *Integrated camera*, on by default. Off, its USB
  port (xHCI USB2 port 12) is disabled at every start and wake, so no OS
  sees the camera; an OS that routes the port to the USB 2.0 controller
  instead would still find it, as the help says. Passed on a W541
  (DEV-W01, [docs/tests/v1.6.1/w541-nri/README.md](docs/tests/v1.6.1/w541-nri/README.md)).
- **Internal microphone switch on the W541** (patch 0243): *General* →
  *Sound* → *Internal microphone*, on by default. Off, the firmware tells
  the OS that the lid's microphone is not connected, so it is not offered
  as an input; a soft switch, as its help says (the audio chip stays
  powered). The headset jack is not affected. Passed on a W541
  (DEV-W01).
- **Ethernet switch on the W541** (patches 0241-0242, 0262-0264):
  *Hardware* → *Expansion ports* → *Ethernet*, on by default, the
  *Ethernet LAN* of the Lenovo setup. Off, the chipset turns the I217-LM
  controller off for every OS and for network boot (the LAN disable bit
  of `BUC`, kept across updates and fallbacks until it is turned on here
  again). Measured on a W541 and fixed in two places: the chipset
  lockdown that coreboot sets at every boot blocked the write, so the
  firmware now resets first, as the Lenovo firmware does (patch 0262);
  and the controller did not come back when turned on again, not even
  after a power-down, because its PHY wakes only on a pin that the hidden
  controller never drives: the firmware now drives it itself before the
  reset, and once by itself when the controller is missing with the
  option on, which brought the W541 of the port back (patch 0263). A
  change takes up to three restarts, done by the firmware.
- **Firmware watchdog on the M920x** (patches 0238-0240), off by default:
  *General* → *Boot* → *Firmware watchdog* (5 or 10 minutes) arms the
  overclocking watchdog of the chipset before the memory init and stops it
  when the payload confirms the firmware slot, so that a boot that hangs
  before the logo resets by itself, and a new slot that hangs twice falls
  back to the other one with nobody at the power button. Not armed on a
  wake from S3; the setup and the boot menu are not watched. With the
  option off, the firmware clears the watchdog at every boot.
  `hw-report.py` WDT-01 checks that it is off once the OS runs. The armed
  path is not tested on a machine yet: the first armed boot is the
  owner's call (RISCHIO: should the stop fail, the machine resets after
  the timeout until the option is turned off in the setup).
- **The setup's lock-at-boot works** (edk2 0058): a CFR option marked
  `CFR_OPTFLAG_LOCK_AT_BOOT` was meant to be writable from the setup and
  write-locked from ReadyToBoot, but the payload registered its Variable
  Policy rule at ReadyToBoot, after EndOfDxe had closed Variable Policy to
  new rules, so the registration failed and nothing was locked. The rules
  are now registered when the setup driver starts and take effect when a
  trigger variable is set at ReadyToBoot. No option of these boards uses
  the flag yet, so nothing changes on the machines today.
- **The security options write-locked in SMM**: coreboot reads `bios_lock`
  and `bootmedia_lock` from the variable store (`SMMSTORE`) to decide the
  flash protections. They are BootService-only, so the OS cannot change
  them with `SetVariable`, but it could write the variable store with the
  raw `SMMSTORE` SMI, turn them off and, at the next boot, start the
  firmware without its protections. Now, the way the TCG MOR lock already
  works, the payload arms `SMMSTORE_CMD_OPTION_LOCK` at ReadyToBoot and,
  while armed, coreboot refuses the writes of the variable store that
  would turn a protected option off (`SMMSTORE_OPTION_LOCK`, patches
  0236-0237, edk2 0056; the UEFI VariablePolicy model applied in MM). The
  setup still changes the options, before the lock is armed, so the
  flashing workflow is unchanged; capsules and `other-slot` are
  unaffected. Only meaningful with *BIOS Lock* on, which the lock requires.
  The authenticated Secure Boot variables are not covered: that would need
  the signature check in SMM (a known limit in the README). Run on the
  M920x with v1.6.1-rc1: the regressions pass, but the arm left no trace
  (SMM's console is compiled out without `DEBUG_SMI`); from rc2 the payload
  reports what coreboot answered in the volatile variable
  `OptionLockStatus` of the coreboot options GUID, read-only to the OS by
  a lock-on-create Variable Policy (edk2 0057), and `hw-report.py` reads
  it (FLASH-01, FLASH-06).

- **The memory training kept across updates on the W541** (patches
  0250-0252): the version of the training cache is now a tag and a key
  made from the code (`nri`: a hash of the native RAM init's sources and
  Kconfig, with the memory settings of the board) or from the inputs of
  `mrc.bin`, instead of a number bumped by hand, so no slot ever resumes
  a training saved by other code. The capsules write the two slots only
  and *Go back to* keeps the cache, as on the M920x: the new slot trains
  once only when its RAM init changed (0.7 s with `nri`). `update.py`
  still stages the capsules of before, which clear it. Passed on a W541
  (MEM-03: a new slot with the same NRI code kept the cache).
- **Firmware watchdog on the W541** (patches 0254-0255): *General* →
  *Boot* → *Firmware watchdog* (Off, 5 or 10 minutes), the M920x's design
  on the watchdog of Lynx Point: armed before the memory init, stopped
  when the payload confirms the slot, so that a new slot that hangs twice
  falls back by itself. Off by default; WDT-01 of `hw-report.py` reads it
  on the W541 too. Passed on a W541 (WDT-01: armed at 300 s, stopped at
  the slot confirmation, the laptop up past 7 minutes); a real hang not
  tried.
- **Settings reset on the W541** (patch 0256): on, as on the M920x, with
  one more condition: the OS can set the RTC power loss bit of Lynx Point
  (checked on a W541), so the options are reset only when the CMOS lost
  its contents too. Passed on a W541 (OPT-05, with a simulated loss: the
  bit alone reset nothing, the bit with the CMOS cleared reset all 66
  options).
- **Card reader switch on the W541** (patch 0257): *Hardware* →
  *Expansion ports* → *Card reader*, a soft switch: off, the link of its
  PCIe port is disabled at every start and wake. Passed on a W541
  (DEV-W01).
- **Wake on LAN from off on the W541** (patch 0259): *Energy Saver* →
  *Power* → *Wake on LAN* (Off, AC only - the default, as the Lenovo
  setup -, AC and battery), programmed as the Lenovo firmware does at
  every sleep and power-off: a magic packet turns the laptop on from off,
  and from sleep when the OS armed the port. Not yet run on a machine
  (NET-02).
- **HKEY events no longer lost** (patch 0260): one pending event per
  class, as the Lenovo firmware: a dock or thermal event right after a
  hotkey no longer replaces it.
- **No hang logged for the resets of the options** (patches 0246, 0253):
  the resets that apply *Ethernet*, *Intel VT-x* and *Hyper-Threading*
  leave POST code `0xfc`, which the event log does not report as the last
  code of a hung boot.
- **Hyper-Threading on the W541** (patches 0247-0249): *Energy Saver* →
  *Processor* → *Hyper-Threading*, on by default as in the Lenovo setup,
  turns the second thread of each core off (4 threads on a quad-core
  i7). On Haswell the PCH applies it from the next reset (bit 0 of
  `SOFT_RESET_DATA`, measured on a W541 with rc6), so romstage does one
  warm reset when the option and the bit differ: with the option off,
  at every power-on. The bit survives S3, so a resume keeps the threads
  the OS suspended with, and the option applies at the next boot. The
  reset leaves a POST code of its own (`0xfc`) that the event log does
  not take for a hang, and the native RAM init keeps its training cache
  across it (the boot after the reset is a cold one for it). From patch
  0258 the straps are locked until the next reset, as the Lenovo
  firmware does. Passed on a W541 (CPU-06): 4 threads with the option
  off, locked, kept across S3, the cache kept; 8 with it on. The `mrc`
  variant has the option too, not measured.
- **The descriptor, the GbE and the ME regions under *Firmware
  protection***: the images leave the descriptor unlocked
  (`CONFIG_UNLOCK_FLASH_REGIONS`, so that flashrom can rewrite the
  read-only part, the ME or the descriptor from the OS), which also let any
  root process write them at any time, while the lock covered `WP_RO` only
  and *BIOS Lock* the BIOS region only (chipsec's `spi_desc`). With
  *Firmware protection* on, both boards now set a second Protected Range
  of the SPI controller over `SI_ALL` (the descriptor, the GbE and the ME:
  W541 `0x0-0x4fffff`, M920x `0x0-0xbfffff`), write-only, locked with the
  first until the next reset or S3 resume, where coreboot sets them again
  (`BOOTMEDIA_LOCK_SI_ALL`, patch 0235). They stay readable, the firmware
  still writes them before the lock (the HAP bit of *Intel ME*), the ME
  and the GbE use their own masters, and the option that lifts the lock of
  `WP_RO` lifts this one too: a flashrom write of those regions needs
  *Firmware protection* off, as the read-only part does. The permissions in
  the descriptor do not change, so `spi_desc` keeps reporting them: the
  protected range is what refuses the write (FLASH-05 of
  [docs/testing.md](docs/testing.md)). `update.py protection` and `status`
  print an `SI_ALL:` line next to `WP_RO:`, with *firmware senza la
  protezione di SI_ALL* on a firmware before this one, and hw-report's
  FLASH-01 reports it (`WARN` when `WP_RO` is protected and `SI_ALL` is
  not). Passed on both boards: on the M920x with v1.6.1-rc1 (FLASH-01,
  FLASH-05), on a W541 with the CI build of 2026-11-08 (FLASH-01: PR1
  `0x0000000-0x04fffff` over `SI_ALL`, *Enabled bootmedia protection for
  SI_ALL*); no write was tried.
- **Tools**: `update.py protection` and `other-slot` say when the kernel's
  `spi-intel` driver holds the SPI controller (a `BIOS` MTD partition):
  flashrom 1.5 and later go through it without the Protected Ranges, the
  descriptor regions or, on the W541, the second chip, and the `modprobe
  -r` line to run first. hw-report's FLASH-01 rates `SI_ALL` from the log
  too when the kernel refuses the registers.
- **README**: two known limits written down, the descriptor left unlocked
  (above) and the variable store (`SMMSTORE`) that code at ring 0 can
  rewrite through the same SMI the payload uses, without the variable
  driver that authenticates it.

## v1.6.0

- **WSMT**: both boards publish the Windows SMM Security Mitigations
  Table with its three flags (patch 0214), after the SMI handlers were
  read against them: the parameters of every SMMSTORE command are taken
  only from the page after the data block of the com buffer, fixed
  since boot, where the payload now passes them from the first command
  (0215, `edk2/0044`; a command with them elsewhere fails and the
  console says so); the GSMI commands of the OS (add an event, clear
  the event log) are answered as unsupported (0211), as no OS on these
  boards uses them and any ring 0 code could clear the log, and the
  pointers they follow are checked against SMRAM anyway (0212); on the
  W541 the xHCI rerouting SMI is refused once the chipset is finalized
  (0213). After the finalize the SMI handlers answer the ACPI enable
  and disable commands, SMMSTORE, the vboot slot commands and the MOR
  lock: all of them write the flash and nothing else. Windows reads the
  table for Device Guard, Credential Guard with HVCI and VBS; `fwts
  wsmt` and `acpidump` show it.
- **Capsules write only the regions of an update**: the payload refuses,
  before it writes anything, a capsule whose manifest names a region other
  than the two vboot slots and `RW_MRC_CACHE`
  (`PcdFmpDeviceSmmAllowedRegions`, `edk2/0045`), and, on a flash with
  both slots, one that does not name both (a slot alone could be the one
  that runs): *immagine non valida* (0x1800) in the ESRT and in
  `update.py status`. Up to v1.5.0 the payload wrote whatever a signed manifest
  named, checked only by the build and `update.py`; the capsules of every
  release name only those regions, so they still install, rollbacks
  included. A boot with capsules also confirms the slot that runs before
  it applies them (`edk2/0046`): a capsule that fails, or is refused, no
  longer uses up a try of a slot that vboot is trying after an update.
  The host unit tests of `FmpDeviceSmmLib` run in CI (`tools/build.sh
  edk2-unit-test`, in `check.yml` and before the update test), and
  `tools/qemu-update.py` refuses a capsule naming `SMMSTORE` and one with
  the running slot alone, with nothing written.
- coreboot `26.09-517-geab226a1c3f7`, 79 commits after the pin of v1.5.x
  (26.09-438): the 213 patches rebased with the same changes, 22 of them
  exported again (0010, 0086-0088 and 0188 with `nri_status`, the new
  upstream name of the native RAM init's `raminit_status`; 0185 at
  upstream's lines next to 96647; the others for their context). For these
  boards it brings the consumer flag of the coreboot table device (`CTBL`
  in coreboot's SSDT) in bit 0 of its `_CRS`, as ACPI 6.5 Table 6.48
  defines it, no longer in reserved bit 4, and three changes of the native
  RAM init that leave what the W541 programs as it was
  ([docs/raminit.md](docs/raminit.md#limits)): the training saved by
  v1.4.0-v1.5.0 stays valid. vboot, the TPM log, the commonlib structures
  and the x86 and CPU code are the same in the two commits, so the slots
  still run behind the read-only part of v1.5.0 (`rw-ok` in
  `configs/ro-interface.txt` and `boards/m920x/ro-interface.txt`, with
  what was compared): v1.6.0 installs from its capsule.
- Five fixes that TianoCore merged after `edk2-stable202608`, taken into
  the payload as they are (`edk2/0047-0051`, `tianocore/0113-0117`): in
  the USB enumeration, a read through a NULL descriptor when a
  SuperSpeed device comes up below SuperSpeed on a root port, the
  capabilities of a device's BOS descriptor walked past their buffer when
  their lengths are malformed, a buffer left behind by a failed BOS
  request; in the boot manager, a double free of the GOP device paths of
  a video controller whose GOP driver makes children of its own (an
  option ROM of a card in the M920x could, not the boards' own graphics)
  and one of `OptionOrder` when memory runs out. Nothing changes with
  well-formed devices.
- **The ECAM window reserved** (patches 0218 and 0219, `edk2/0052`):
  the window that the MCFG table gives (64 MiB at 0xf0000000 on the
  W541, 256 MiB at 0xe0000000 on the M920x) is a motherboard resource in
  the `_CRS` of `\_SB.PCI0.PDRC` (PNP0C02), as the PCI Firmware
  Specification asks, and reserved memory in the memory map that the OS
  reads. Up to v1.5.x it was neither, and `fwts mcfg` failed
  (*MCFGMMIONotReserved*, HIGH); Linux used the window anyway, as its
  early check takes MCFG as it is. ACPI: one `Memory32Fixed` more in
  `PDRC`, no device or path changes, so OpenCore's patches stay as they
  are. `tools/hw-report.py` checks both (CONF-07); the update test checks
  the memory map in QEMU q35.
- **LVGL v9.6** in the setup (`patches/lvglpkg/0019-0021`): the graphics
  library under LvglPkg is LVGL v9.6, the last release of v9, at the head
  of its `release/v9.6` branch (`v9.6.0-23-gbb1ff0af416c`, with the fixes
  to the software renderer that came after the tag), in place of the
  v9.5.0 of LvglPkg's submodule (`LVGL_COMMIT` of `tools/build.sh`, in
  both EDK II trees, so that `edk2-parity` compares the same LVGL).
  LvglLib lists the sources where v9.6 moved them, `lv_conf.h` takes the
  names v9.6 gave its options (the same color format, asserts and
  calendar names as before; new in v9.6, its functions check their
  pointer arguments, `LV_USE_CHECK_ARG`), and `lvgl.h` no longer
  includes the gnu-efi binding of LVGL's UEFI driver, which stopped
  every EDK II module that includes it (0019, a fix for LVGL upstream
  too). In place of the flag functions that v9.6 deprecates and v10
  removes, the setup calls the setter and the getter of each flag (0021,
  the 54 calls one for one), with the deprecation warning on again
  ([docs/roadmap.md](docs/roadmap.md#lvgl-v10)).
  `lvglpkg/0016`, the fix of the circle mask that the W541 needs at
  2880×1620, is gone, as v9.6.0 has it. The display engine is 20 KiB
  larger (8 KiB in the compressed volume); the update screen draws the
  Montserrat glyphs of v9.6, regenerated by LVGL with a few pixels one
  level apart. `upstream.yml` opens an issue "LVGL: ..." when the
  branch has commits after the pin or LVGL has a newer release
  (`tools/upstream.sh lvgl`), and the bill of materials lists LVGL with
  its commit.
- **TCC activation offset on the W541** (patches 0220-0221): *Energy
  Saver* → *Thermal* → *TCC activation offset*, 0-15 degrees below TjMax
  where the processor starts to throttle, default 0 as before; the CPU
  code writes it to bits 27:24 of MSR 0x1A2, 0 included, and the menu
  lists it only on a processor whose `PLATFORM_INFO` has bit 30. Intel
  marks the field reserved on Haswell client processors, but on a W541
  with an i7-4810MQ bit 30 is set, and CPU-05 of `docs/testing.md`
  passed there: the offset on every core, also after S3, and the package
  throttling at TjMax less the offset under load. The T440p shares the
  menu.
- [docs/hlk.md](docs/hlk.md): the checklist of a Windows HLK run on the
  M920x (CONF-06): the test server and the client, the three passes of
  Microsoft's *System testing with Secure Boot* (Secure Boot off, on with
  the default keys, Setup Mode) with the tests of each, and what is known
  not to pass (HSTI, DMA protection, System Guard Secure Launch). Two
  checks from Windows itself in `docs/testing.md`: WIN-09, the security
  properties that Windows takes from the firmware (`Win32_DeviceGuard`: the
  WSMT is 6, the MOR lock 4), and WIN-10, a capsule handed over by Windows
  with `UpdateCapsule()`, which no one has tried yet, with the driver
  package that `tools/win-firmware-inf.py` writes for a capsule (the INF of
  Microsoft's firmware update platform, the GUID of the ESRT and the
  version of the capsule).
- `docs/testing.md`: a conformance suite (CONF): the WSMT and its flags
  (`hw-report.py` CONF-01), the tables compiled again with `iasl -w3`,
  FWTS, chipsec with what each module must say on these boards (the
  descriptor left writable by design), the UEFI SCT and the HLK
  families for the M920x.
- `upstream.yml` compares every week the dbx that the payload enrolls at
  the first boot with the hash lists of Microsoft's latest signed release
  of `microsoft/secureboot_objects` (`tools/upstream.sh dbx`, by git blob
  id, nothing downloaded) and opens an issue when they differ. On
  2026-11-03 they are those of v1.7.2-signed, the same since
  v1.7.0-signed; its SVN entries (the Windows boot manager at SVN 12
  from v1.7.2) stay out of the defaults, as Windows writes them itself
  after updating its boot manager. It also looks for a
  stable tag of TianoCore after the one of `edk2-upstream`, and says
  whether the patches of `edk2/OuroBiosPkg` still apply to its
  `UefiPayloadPkg` (`tools/upstream.sh tianocore`).
- `tools/build.sh roms` stops when the DSDT of a build, compiled again
  with `iasl -w3`, has a warning: v1.6.0 compiles without one on every
  board, the *object is not referenced* (4089) of the names and fields
  that only the OS reads aside, which the check leaves out.
- The memory training of the M920x, which a capsule keeps, has the
  settings that coreboot gives FSP-M in its version too, by hand:
  `CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION` (patch 0222), 0 in
  `boards/m920x/fsp.defconfig` as before, goes up with the release that
  changes those settings, whose first boot then trains once.
  `tools/fspm-settings.sh`, in `check.yml`, stops when the files that set
  them change (`fsp_params.c` and `cnl_memcfg_init.c` of Cannon Lake, the
  romstage and the devicetree of the board, in
  `boards/m920x/fspm-settings.txt`) until the change has been looked at.
  No training with this release.
- `check.yml` holds the series to the style that coreboot's Gerrit and
  TianoCore's CI ask for: `util/lint/lint lint-stable` on the coreboot
  tree with the series, and `checkpatch.pl` with the tree's
  `.checkpatch.conf` on the patches of the project
  (`tools/coreboot-lint.sh`; the four errors of the native RAM init's
  0087-0088 are false positives on code written as upstream's NRI writes
  it, the member of a compound literal and the sign of `+1`, listed in
  `patches/checkpatch-known.txt`), and `PatchCheck.py` of TianoCore on
  the code of the project's patches in `patches/edk2`
  (`tools/edk2-patchcheck.sh`). The WSMT options of patch 0214 moved into
  a menu of their own, as `lint-stable` wants every prompt in a menu:
  the `.config` of every board keeps the same values.
- `tools/hw-report.py` MEM-02 reads the sizes of the memory devices in
  the binary units of recent dmidecode versions (GiB, MiB) too: a W541
  got *SMBIOS non elenca moduli* with every slot populated; when the
  entries are there and no size is read, it lists what dmidecode said.
- `tools/hw-report.py` BOOT-01 compares the stages of the slot with the
  version of SMBIOS without the Lenovo-format ID that the W541 puts
  before it (`CBET4000 `): every W541 got a WARN with the same version
  everywhere. IDLE-01 is INFO, to be run again, not a FAIL, when a
  process uses more than 5% of a core or an internal panel stays on below
  the pass limit (the PC6 of about 90% of the W541 is with the screen
  off), and points to `docs/testing.md` for the screen off; with its 3K
  panel on, the W541 stays in PC2, which IDLE-01 now calls known rather
  than asking for the measurement again. CPU-01 names the TCC option.
- `tools/hw-report.py` PCI-09 replays on the machine how the payload
  builds the aperture of its PCI root bridge (`ScanForRootBridges()` of
  PciHostBridgeLib with `tianocore/0024`): a memory BAR of bus 0 whose
  addition would make the aperture cover reserved memory stays out of it,
  and from v1.6.0 the ECAM window is reserved (`edk2/0052`), so that a BAR
  on its other side from the first one scanned would stay out. coreboot
  keeps every 32-bit BAR of both boards below the ECAM window
  (`DOMAIN_RESOURCE_32BIT_LIMIT`), so nothing is left out: PCI-09 watches
  that it stays so. FAIL when a USB, SATA, NVMe or SD controller is left
  out, which the payload's drivers reach only through the aperture; INFO
  for the other devices, the graphics among them, as the payload's GOP
  draws into coreboot's framebuffer without the aperture.
- The move to upstream TianoCore EDK II starts in CI:
  `tools/build.sh edk2-upstream` builds `edk2-stable202608` as it is
  into two q35 images with this tree's coreboot, one with
  `SECURE_BOOT_ENABLE`, and runs the steps of the smoke test that need no
  setup of the project, each reported on its own (`qemu-smoke.py
  --upstream`; the workflow `edk2-upstream.yml`, by hand or on a push to
  `ci-edk2/**`). The upstream payload keeps variables in SMMSTORE across
  a reboot, and keeps a store in the authenticated format that the
  current payload gives; the runtime services moved as boot.efi moves them,
  the TPM 1.2 and an authenticated store on an erased SMMSTORE are known
  gaps, each with what closes it. No release image changes.
- **EDK II from upstream TianoCore**: the payload of every board is built
  from TianoCore's `edk2-stable202608` with the project's package
  [`edk2/OuroBiosPkg`](edk2/README.md) and the patches it carries on
  TianoCore's packages, no longer from MrChromebox's fork (step (d) of
  [the move](docs/edk2-migration.md#step-d-the-boards-on-the-package)): the
  same sources as MrChromebox's `6c14abf865e0` with `patches/edk2`, and the
  same payload byte for byte (`tools/build.sh edk2-parity`, in
  `edk2-upstream.yml`), so the setup, the boot options, Secure Boot, the
  capsules and the NVRAM are those of `patches/edk2`, whatever tree they
  are built on. The defconfigs pin the tag (`EDK2_PACKAGE_CONFIG` of
  `tools/build.sh`); the release notes, the layout and the bill of
  materials name the tag, the carried patches, the package and the
  MrChromebox commit they come from.
- Steps (b) and (c) of the move: the payload of the ROMs as a package
  on TianoCore's tag, with the same sources. `tools/edk2-import.py` makes
  [`edk2/OuroBiosPkg`](edk2/README.md) (the modules that TianoCore does
  not have: the setup, the splash, the password, the default Secure Boot
  keys, the update screen..., and the platform, `UefiPayloadPkg.dsc` and
  `.fdf` as patches on TianoCore's, and `PlatformBootManagerLib` and
  `FmpDeviceSmmLib`, carried whole) and `patches/tianocore` (70 commits of
  MrChromebox and 30 patches of `patches/edk2`, each without the files of
  the package; two commits
  and their reverts, which cancel out, stay out) from MrChromebox's tree
  with `patches/edk2`, and checks
  that the tag with the series is that tree in every other file; LvglPkg
  is a package of its own next to it. coreboot builds it with patch 0216
  (`EDK2_PLATFORM_DSC`, `EDK2_PACKAGES_PATH`, relative to the coreboot
  tree) and 0217 (the LVGL renderer and the default Secure Boot for a
  custom repository; for MrChromebox's nothing changes), into the third
  image of `edk2-upstream`, and `tools/build.sh edk2-parity` builds the
  payload of each board from it to compare it, byte for byte, with the
  one of MrChromebox's tree (`tools/fv-diff.py` says which modules
  differ). `tools/upstream.sh tianocore` also checks every week that
  `patches/tianocore` applies to a newer stable tag, `edk2` watches
  MrChromebox's branch from the commit the package comes from, `dbx`
  reads the dbx of the package.
- `tools/sbom.py` counts the flash descriptor, the GbE NVM and the VBT
  as data in the openness figures, as Dasharo's Openness Score does
  (they were closed binaries: 0.1% of the code at most). The report says
  where it still differs from Dasharo's tool: the ME region counts by
  the bytes that are not erased flash, not whole
  ([docs/roadmap.md](docs/roadmap.md#openness-score)).
- Two drivers of MrChromebox's tree for controllers these boards do not
  have are out of the payload (`edk2/0054`, `edk2/0055`), the first
  *drop* commits of the move: SdMmcPciGliDxe, for the SDHCI of Genesys
  Logic (the SD reader of the W541, an O2 Micro OZ777, is driven by
  `SdMmcPciHcDxe` as before), and SdhciNonPciDxe, for the SDHCI off the
  PCI bus, with its record of the coreboot table, the parser of
  `CbParseLib` and `NonDiscoverablePciDeviceDxe`, which only it fed.
  Each was dispatched at every boot to bind nothing; the payload of the
  W541 is 9,357 bytes smaller (1,798,200), that of the M920x 8,863
  (1,800,049). `tools/edk2-import.py` keeps their directories out of
  TianoCore's tree (`LEFT_OUT`), so the numbers of `patches/tianocore`
  stay.
- [docs/edk2-migration.md](docs/edk2-migration.md): the 100 commits of
  MrChromebox's branch over `edk2-stable202608`, each with what it
  becomes in the move to TianoCore (the project's package, a patch to
  carry, a fix to propose upstream, left out, or already upstream).
- README and docs/m920x.md: the M920x releases are releases, as they
  have been since v1.4.0.
- The release notes, README, docs/update.md and docs/m920x.md say that the
  capsule installs on v1.5.0 or later, the read-only part of measured boot
  (`BOARD_RO_SINCE` of `boards/*/board.sh`); the notes of v1.5.0 said
  v1.3.0 on the W541 and any release on the M920x. The notes give the
  flashrom command for the older releases: the read-only part and both
  slots from v1.3.9-v1.4.x (v1.4.x on the M920x), every region but the
  runtime ones from v1.0.3-v1.3.8.
- **No UEFI Shell in the payload** (`EDK2_HAVE_EFI_SHELL` off on `mrc`,
  `nri` and `fsp`): 234 KiB less in each slot (the payload of the W541
  from 2,046,796 to 1,807,557 bytes, now 528-597 KiB free in its slots),
  and no program left that anyone at the boot menu could start with
  Secure Boot on without a signature (`DxeImageVerificationLib` lets
  every file of the firmware volume run). The boot manager deletes the *UEFI Shell* entry that an
  earlier version left in the boot order and the boot menu
  (`edk2/0053`), and the help of *Boot from USB drives* no longer lists
  it (patch 0227). A Shell on a USB drive still starts as any loader
  does: from its entry, *Boot From File* or `\EFI\BOOT\BOOTX64.EFI`,
  signed for the keys in `db` or with Secure Boot off. The smoke test
  writes its variables, `BootNext` for iPXE and CSMWrap included, with
  `tools/efi/setvar.c` from an EFI system partition, which takes them
  from QEMU's fw_cfg, where it typed `setvar` into the Shell.
- *BIOS Lock* (*Security* → *Flash protection*) is on by default, on both
  boards (`CONFIG_BOOTMEDIA_SMM_BWP`, the default of the option only): a
  setting already saved in `SMMSTORE` is kept, a store without one and a
  settings reset get the lock on. With it the flash is written only by
  the firmware in SMM: the capsule updates, the settings, the event log
  and the lock of TCG MOR work as before, and flashrom from the OS only
  reads. To write with flashrom (the read-only part, a fresh ROM) turn it
  off in the setup first ([docs/flashing.md](docs/flashing.md)).
  `tools/update.py protection` and `status` report the default of the
  running version.
- Two packages of the M920x's SSDT were declared longer than their
  lists (iasl remark 2063 on CONF-02): the PIC branch of `_PRT` with the
  45 entries of the APIC branch for its 34 (patch 0228, the pins without
  a PIRQ are now counted out), and a constraint of PEPD's `_DSM` for the
  PCH thermal controller at `00:12.0`, which no ACPI node names, written
  without its device (patch 0229, such a device is left out). An OS reading either found
  uninitialized elements; Linux showed nothing, the tables are now what
  they declare.
- The warm reset of the SuperSpeed ports at an S3 resume on `nri` waits
  up to 200 ms for the port reset bit (patch 0231): with a device on a
  port the reset lasts longer than the 100 ms of before by design (an
  LFPS burst of 80 to 120 ms, then detection, handshake and training),
  and the log of every resume of the W541 with a drive plugged in had
  `warm_reset_usb3_ports: timed out` for a reset that completed about
  10 ms later, the port in U0. An empty port clears the bit at once, so
  the limit costs nothing there
  ([docs/tests/v1.6.0/w541-nri/diag.md](docs/tests/v1.6.0/w541-nri/diag.md)).
- The `_PLD` of the W541's four USB connectors put them on the panels
  they are on (patch 0232), measured by plugging a drive into each with
  `PORTSC` watched: port 1 (HS01/SS01) is the connector on the left side
  farthest from the screen, port 2 (HS02/SS02) the one on the right side
  farthest from the screen, port 3 (HS03, the Always On connector, which
  the OEM tables put on port 1) the one on the left nearest the screen,
  port 6 (HS06) the one on the right nearest the screen; the OEM buffers
  of patch 0071 had three of them on another panel. Only the positions
  the OS shows change (Windows's port names, Linux's
  `physical_location`); no device path or name changes. The T440p keeps
  the OEM buffers until someone measures its connectors.
- On the M920x the *Intel graphics* switch under *Hardware* is gone
  and the processor graphics stays on (patch 0224): off, the DisplayPort
  and HDMI ports went dark with the firmware screen and the setup
  itself, and without a graphics card on the riser nothing but a write
  to the option from the OS or an external programmer brought the setup
  back. A machine that had it off comes back with this update: romstage
  no longer reads the option (`SOC_INTEL_CANNONLAKE_IGD_ALWAYS_ON`), and
  still turns the graphics off for a processor without them. The stolen
  memory and the aperture stay in the menu, under *Intel graphics*.
- Measured boot leaves the PCRs alone on a resume from S3 (patch 0223):
  up to v1.5.0 the stages loaded again on the resume path were measured
  again into PCR 2 (on the M920x the microcode, FSP-M, FSP-S and the VBT
  too), while the TPM keeps its PCRs through S3 and the event log of the
  OS is the one of the boot, so after a suspend PCR 2 no longer replayed
  from the log (TPM-03 of `hw-report.py` failed; a remote attestation
  after a suspend would have): seen on the M920x of the port with five
  suspends. Nothing is extended nor logged on that path now, in the
  bootblock and verstage too (on rc1 they still logged three entries per
  resume: they know a resume from the PM registers only, the power
  state comes with romstage), the log in cbmem keeps the entries of the
  boot, and the resume path no longer hashes what it loads for the
  measurement, the payload included. On the W541 the romstage keeps
  the state `southbridge_detect_s3_resume()` found after it clears
  SLP_TYP, so `mrc.bin` is not measured again either. The bootblock is
  in the read-only part, which capsules do not write: with a read-only
  part from before this release it still logs the FMAP, itself and
  romstage into cbmem's log at every resume (three entries, none
  extended, none in the log of the OS), until the read-only part is
  written again.
- On the M920x the event log of ramstage was lost at every boot, up to
  v1.5.0, with *BIOS Lock* on and off alike (seen with both on the M920x
  of the port, on v1.5.0 next to this release's candidate): the chipset
  lockdown set EISS and the BIOS locks at `BS_DEV_RESOURCES`, before the
  boot count, the wake sources and the resets are logged, and each write
  failed (*SPI Transaction Error*, *ELOG: NV Write failed*, BOOT-03 of
  `hw-report.py`); the entries written from SMM (S3, S5) still went in. Patch 0209
  (`SOC_INTEL_COMMON_PCH_LOCKDOWN_SMM_BWP_LATE`) has the SMI handler set
  them at the finalize instead, after ramstage is done with the flash
  and before any boot option or OS runs, as Lynx Point does on the W541.
- coreboot prints its measurement log before the payload at DEBUG
  instead of INFO (patch 0225): on the M920x, whose serial console runs
  at INFO by default, the 14 entries with both digests no longer go to
  the UART at every boot, 2.7 KiB and 0.27 s at 115200 baud on rc5.
  `cbmem -1` keeps them, as the CBMEM console takes every line up to
  DEBUG at any level; the OS reads the log from the TPM2 and TCPA
  tables as before.
- On the M920x *Security* → *Management Engine* → *Intel Management
  Engine* has a third choice, *Disabled (HAP bit)* (patch 0226): the ME
  stops after its bring-up, with no HECI and no message to answer, so
  the boot loses the up to 5 s wait of the soft disable at FSP-M's DRAM
  Init Done. At the first boot after *Save* coreboot writes the HAP bit
  into the flash descriptor, which this board's descriptor lets the
  host do, reads it back and logs `HAP: written`; the ME takes it at the
  next start from power off (shut down, unplug for ten seconds).
  *Enabled* or *Disabled* clear it the same way. **RISCHIO BRICK**: a
  power cut during that one write (about 50 ms) leaves the board unable
  to start until the descriptor is written back with an external
  programmer ([docs/m920x.md](docs/m920x.md#intel-me)), as would a board
  that does not start with the ME stopped (not tried on an M920x yet,
  ME-05 of docs/testing.md). ME-01 of
  `hw-report.py` knows the new state. The W541 is unchanged: its
  descriptor has had AltMeDisable set from the start.
- On the M920x the serial console of coreboot is off by default
  (*Console* → *Serial Console*, `CONSOLE_SERIAL` off with
  `CONSOLE_SERIAL_RUNTIME`): COM1 of the Super I/O sits behind an
  optional module, and at 115200 baud the port cost time at every boot
  with or without it (6.2 s at the DEBUG level on rc5, and the lines of
  the other processors on top). With the module, turn it on in the menu:
  it prints from romstage on. `cbmem -1` keeps every line up to DEBUG
  either way, and Linux still finds the port (`ttyS0`). A setting saved
  before stays as it was.
- `tools/hw-report.py` counts from the coreboot log what the M920x's
  serial port costs at the level of the boot and at Info, Notice and
  Error, the other processors' lines included, and says whether
  *Serial Console* is on (BOOT-01, from the SPCR table); BOOT-02 splits
  the payload into its loading and the steps before the jump
  ([docs/m920x.md](docs/m920x.md#boot-time)).
- The graphics stolen memory of the `nri` variant (*Hardware* → *Intel
  graphics* → *DVMT pre-allocated memory*) defaults to 32 MB, what
  `mrc.bin` reserves (patch 0208): the two variants boot with the same
  memory map and the same OpenCore configuration. A saved setting is
  kept; 64 MB stays among the values.
- The DSDT of the W541, disassembled and compiled again with `iasl -w3`,
  no longer reports *Not all control paths return a value* for `PWMX`,
  `SBLV` and the two `_PSW` (patch 0210); the remaining warnings at that
  level are the disassembler's (objects it cannot see referenced) and
  the named objects that the BAR-at-the-moment methods create on
  purpose (0101-0103).
- `tools/build.sh roms` compiles the DSDT of each build once more with
  `iasl -w3` (coreboot builds at `-w1`, warnings as errors) and prints
  the count and the kinds of warnings of that level, with the whole
  output in `build-<variant>/dsdt-w3.log`; not fatal yet.
- README: the specifications the firmware is built against, as the pinned
  trees declare them, and the known limits of the two machines (Windows
  11 on the W541, DMA protection, WSMT and HSTI, the MOR lock, XMP).
- Run on the machines before the release, with the records in
  [docs/tests/v1.6.0/](docs/tests/v1.6.0/): the W541 `nri` behind the
  read-only part of a CI build from before v1.5.0, and the M920x `fsp`
  behind that of v1.5.0, from the first candidate to the last. The
  `mrc` variant is built, booted in QEMU and updated A/B there by the
  CI like the others, but no machine ran it for this release: the
  W541's read-only part takes `nri` slots only.

## v1.5.0

- **Measured boot**, on both boards: coreboot measures what it runs into
  the TPM, from the read-only part on, and logs each measurement, and
  Linux's event log replays to PCR 0-7, so a disk can be sealed to the
  firmware that booted it (systemd-cryptenroll, clevis) and a remote
  attestation sees coreboot too. verstage starts the TPM
  (`CONFIG_TPM_MEASURED_BOOT`, in place of starting it in ramstage) and
  extends vboot's boot mode, HWID and firmware version into PCR 1;
  coreboot measures the FMAP, the bootblock, every stage, FSP-M and FSP-S
  on the M920x, the microcode, the VBT, the DSDT and the payload into
  PCR 2, each the digest of its bytes in the flash. vboot's anti-rollback
  data stays mocked: the TPM is there for the measurements only.
- **v1.5.0 writes the read-only part once more, with flashrom**: the
  TPM's early log in cache-as-RAM moves what the slots read there, so its
  slots do not boot behind the read-only part of v1.3.9-v1.4.x, nor older
  slots behind the new one. It has new ESRT GUIDs (`mrc`
  `75f840a2-af55-4481-84b7-5e2f56cf3a4d`, `nri`
  `457afc2a-b6ee-4477-b41b-cc995e6110ae`, M920x
  `ceef6456-ca3b-4cf3-a784-4895efaf1bde`): its capsule does not install on
  an older firmware nor an older capsule on it, and `update.py other-slot`
  refuses a slot of the other generation even with `--force`. The
  command, which keeps settings, keys, VPD, event log and memory
  training, is in [docs/flashing.md](docs/flashing.md#measured-boot-the-read-only-part);
  on a W541 with an EC older than 1.15, flash it with the programmer after
  the EC update.
- On the M920x (TPM 2.0, SHA-1 and SHA-256 banks): coreboot measures into
  both banks, each event with both digests (patch 0201); the payload hands
  coreboot's events to Tcg2Dxe, which puts them first in the EFI log, and
  then leaves the ACPI TPM2 table without a log area, which Linux would
  otherwise read instead, with coreboot's events alone (`edk2/0042`). On
  the W541 (TPM 1.2) the payload appends its events to coreboot's log, the
  log area of the ACPI TCPA table (`edk2/0019`, patch 0200).
- The logs are 256 KiB (`PcdTcgLogAreaMinLen`, patch 0205): with EDK2's
  64 KiB the Secure Boot variables, shim and GRUB filled the M920x's log
  before ExitBootServices, and the events after it were extended without
  being logged.
- A TPM that does not start, or fails to extend vboot's PCRs, costs the
  measurements, not the boot (patch 0199): the machine boots without them
  and the log says *TPM setup failed ... booting without measurements*.
  Before, vboot would have asked for recovery mode, which these boards do
  not have.
- vboot's firmware version goes into PCR 1, not PCR 10, which is the one
  of Linux IMA (patch 0202); the measured boot log starts before vboot's
  first measurement (patch 0204), and the pre-RAM log stays inside its
  2 KiB of cache-as-RAM (patch 0203).
- **The lock of TCG MOR** (`MemoryOverwriteRequestControlLock`, revision
  2 of the Platform Reset Attack Mitigation specification, which Windows
  Credential Guard uses), on both boards, with *Clear memory at power-on*
  on *When the OS asks* and *BIOS Lock* on. coreboot keeps the lock in
  SMM (patch 0207): while the OS holds it, every write of the variable
  store that would clear the OS's request to clear the memory is refused,
  judged on the store as the flash would be after the write with the
  same reader that decides the clearing at boot, so code that runs in
  the OS after the lock cannot drop the request and reset to read the
  memory. The lock lasts one boot, survives suspend, takes a key or
  none, and a wrong key locks it until the next boot. The variable
  driver of the payload offers it through a protocol of the platform
  (`edk2/0043`); with *BIOS Lock* off, where the OS can write the flash
  without SMM, it stays unsupported, as before. The SMM stack grows to
  4 KiB for the walk of the store. Tried on the M920x from Linux: the
  lock taken, other variables still written, the clearing of the request
  refused, the memory cleared at the next boot and the lock reset
  ([docs/testing.md](docs/testing.md#memory-and-training-cache-mem),
  MEM-09). Two test builds before it hung the machine in SMM at the
  first protected write: the check's region device was recovered with
  `container_of()` from a copy, then chained to itself as a root.
- `tools/update.py stage`, `rollback` and `other-slot` warn of the disks
  an update will lock: BitLocker (unaffected with Secure Boot on, which
  seals to PCR 7 and 11), and LUKS2 volumes sealed by systemd-cryptenroll
  to PCR 0, 1 or 2, or with a clevis token, with the command that enrolls
  them again ([docs/update.md](docs/update.md#disks-sealed-to-the-tpm)).
- The help of *Intel VT-d* on the M920x no longer promises Windows Kernel
  DMA Protection, which needs protection before the OS that the firmware
  does not give (patch 0206). [docs/testing.md](docs/testing.md#windows-11-win)
  has a Windows 11 suite for the M920x, which meets Windows 11's
  requirements; not yet run. The W541 does not (Haswell, TPM 1.2).
- `tools/hw-report.py`: TPM-03 replays the firmware's event log against
  PCR 0-7 of each bank and counts coreboot's and vboot's measurements;
  TPM-01 no longer reads PCR 0 alone (coreboot measures into PCR 2).
- Tests: the QEMU smoke test boots a UEFI application that reads the PCRs
  (`tools/efi/tpm-pcr-test.c`) with swtpm as a TPM 1.2 and as a TPM 2.0
  with the M920x's banks, replays the log and checks each of coreboot's
  digests against the image; the A/B update test runs vboot's path of the
  M920x with a TPM 2.0 at every boot, and one boot without a TPM.
- On the M920x of the port (Infineon SLB9670): Linux's event log, 121
  events with shim and GRUB, replays to PCR 0-7 in SHA-1 and SHA-256, and
  each of coreboot's 11 measurements matches the flash. On a W541 (`nri`,
  ST33ZP24 TPM 1.2), the read-only part written with the command above
  from v1.4.1: its log, 82 events, replays to PCR 0-7, with coreboot's 9
  measurements and vboot's 3 (TPM-03).

## v1.4.1

- *Security* → *Memory protection* → *Clear memory at power-on*, on both
  boards, has a third setting, *When the OS asks*: the memory is cleared
  only after a reset while the OS held secrets in it, as the TCG Platform
  Reset Attack Mitigation specification (MOR) has it, and a clean reboot
  is that much shorter (2 s on an M920x with 40 GB, 1.7 s on a W541 with
  32 GB). coreboot reads the request of the OS, bit 0 of the UEFI
  variable `MemoryOverwriteRequestControl`, from the variable store
  before the payload (patches 0192-0194); the payload offers the
  variable only with this setting and clears the bit before the next OS
  starts (`edk2/0039`, `edk2/0040`); a boot that finds no variable, as
  the first one with the setting, clears too. *Always*, the default, and
  *Never* do what on and off did, and the OS sees no MOR with them, as
  before. Windows with BitLocker clears its request after a clean
  shutdown; Linux kernels with `CONFIG_RESET_ATTACK_MITIGATION` (Debian,
  Ubuntu, Proxmox) set it at every boot and never clear it, so their
  memory is still cleared at every boot, which is right for an OS that
  does not remove its secrets at shutdown
  ([docs/flashing.md](docs/flashing.md#clearing-the-memory-at-power-on)).
- EDK2 moves to `6c14abf865e0` of MrChromebox's `uefipayload_2608`: the
  branch was rewritten after v1.4.0, and the commit v1.4.0 pins
  (`ddf612165c8b`) is no longer on it. The fall-through to the next boot
  entry when an automatic boot fails, which v1.4.0 always did, becomes a
  setting next to *Auto Boot Time-out*, on by default. The 38 patches of
  `patches/edk2` apply unchanged.
- A fix of mainline EDK2 after the base of MrChromebox's branch
  (`edk2/0041`, tianocore 027e7a437): a boot entry with a short-form hard
  drive path, as efibootmgr, shim and Windows make them, could be skipped
  when the boot manager's cache of that path missed before the disks were
  connected, instead of being tried again after connecting them.
- The builds no longer depend on MrChromebox keeping a pinned commit on a
  branch: `tools/build.sh` takes a pinned EDK2 or LvglPkg commit that his
  repositories no longer give from the project's forks, under a tag
  `pin-<12 digits>`; [`configs/edk2-pins.txt`](configs/edk2-pins.txt)
  lists the EDK2 commit of every release since v1.0.0, and
  `tools/upstream.sh mirror`, every week, opens an issue while one of
  them has no tag.
- `tools/hw-report.py`: BOOT-02 says which *Clear memory at power-on*
  setting the boot read, whether the OS had asked, and whether the memory
  was cleared.
- On the M920x (and the M720q/M920q), the voltage regulator design of
  the Lenovo firmware for FSP-S (`VrPowerDeliveryDesign` 11, patch 0195),
  found in the setup variable of its image: Intel's current limits and
  load lines for this board instead of generic values. With an i3-8100
  power and voltage are the same; it is the setting Lenovo validated for
  every processor these boards take.
- On the M920x (and the M720q/M920q), C1E and the C1/C3 auto-demotion of
  the processor, as Intel's defaults and the Lenovo firmware have them
  (patch 0196): coreboot's CPU init left them off. Idle 0.54 W instead of
  0.57 W with an i3-8100, the same package C-states.
- On the W541 with its ME halted by `me_cleaner -S`, the event log no
  longer records a *Management Engine error* at every boot, nor the
  console a critical `mbp is not ready!`: an ME that stops in its
  bring-up on purpose takes the disable path (patch 0197), so a real
  error of the ME stands out again.
- On the W541, package C-state demotion off, as Intel's reference code and
  the Lenovo firmware (GNET94WW, its update package analyzed) have it
  (patch 0198): coreboot turned it on. Not yet measured on the laptop,
  which stays in PC6 at idle and never reaches PC7.
- docs/m920x.md: the fan readout under Linux at every boot
  (`/etc/modules-load.d`, the EC has nothing that loads `nct6683` by
  itself).

## v1.4.0

- After rc3, on the M920x with the Intel ME disabled in the setup, boots
  are at most 5 s slower than the others instead of 15 s: FSP-M no
  longer retries its HECI messages to the disabled ME nor reads its MBP
  (0191). FspMemoryInit takes 0.23 s or, on most boots, 5.23 s: the ME
  answers the DRAM Init Done message late, as it applies its disable
  there, and the message cannot be left out (the boot hangs).
- **ThinkCentre M920x Tiny** (Intel Coffee Lake, Q370): a release of its
  own in every version, `vX.Y.Z-m920x-fsp`, built from coreboot's
  `lenovo/m720q_m920q` board with Intel's FSP-M RAM init and the rest of
  the W541 releases: the EDK II payload and its setup menu, vboot with two
  signed RW slots and a minimal read-only part, signed capsules and fwupd,
  with an ESRT GUID of its own ([docs/m920x.md](docs/m920x.md)). A
  pre-release until it is confirmed on the machine. Patches 0136-0141:
  vboot's data in flash on Cannon Lake, the M920x with its 24 MiB flash,
  vboot with two RW slots, SpeedStep and Turbo Boost as setup options, the
  setup menu; patch 0065 and `edk2/0020` take the `fsp` slots too.
- More than one board in the repository: `boards/<board>/board.sh`
  describes each (variants, flash and chips, blobs, the checks of
  `tools/verify-rom.sh`), and `tools/build.sh --board w541|m920x|all`
  builds them. The W541 files, release names and GUIDs stay as they were;
  the fwupd metadata of the `mrc` release carries the `.cab` of every board,
  and fwupd offers each machine its own.
- `tools/vpd.py`: the machine types and SKU of the M920x, `--sku`.
- From rc2, on the M920x: Latency Tolerance Reporting on the PCIe root
  ports in use, as with the OEM firmware. Without it the NVMe SSD and the
  Wi-Fi card could not use LTR nor ASPM L1.2, and at idle the package
  stayed at PC3 while the cores sat in C10 (0142). The audio codec, a
  Realtek ALC233, gets the whole verb table of the OEM firmware, with its
  Realtek coefficients and the speaker path; coreboot's page for the board
  lists the front audio jacks as not working (0143). DDI-E gets two of
  the four lanes of DDI-A, which has no panel on this desktop: the VBT has
  a DisplayPort on DDI-E, most likely for the VGA option, and i915 warned
  at every boot that it had no lanes (0144).
- From rc3, on the M920x, what macOS needs of the firmware on a Coffee
  Lake desktop, as for the W541, not yet tried with macOS
  ([docs/macos.md](docs/macos.md#thinkcentre-m920x)): the setup options
  *ACPI processor objects* (`Processor`, with `plugin-type` on the
  first) and *C-state configuration lock*, in *Compatibility* → *macOS*
  (0145-0147, 0149); under macOS only, an embedded controller by name,
  `\_SB.USBX` and the PMC of the PCH, as the SSDT-EC, SSDT-USBX and
  SSDT-PMC samples of OpenCore (0148).
- From rc3, the fan of the M920x follows the temperature
  ([docs/m920x.md](docs/m920x.md#fan)). Up to rc2 it stayed at about 850
  rpm whatever the load, and the CPU went to 95-100 °C: coreboot's
  NCT6687D driver cleared the temperature sources of the EC, with none
  in the devicetree, so its firmware read 0 °C everywhere. The board now
  sets the sources the EC firmware has itself, and at every boot tells
  the EC the platform as Lenovo's firmware does (PEG card, TDP class,
  power-loss policy), so that it loads its profile for it (0150-0153).
  The ICE mode of the OEM setup is in *Hardware* → *Cooling*: *Better
  acoustics* (the default), *Better cooling*, *Full speed*.
- From rc3, the M920x wakes on LAN after a shutdown, as with the OEM
  firmware: the override of the PCH for the wake of the LAN from S4 and
  S5 is on, *Energy Saver* → *Wake on LAN from off* (0154-0155). Without
  it Linux arms the port up to S4 only, as the ACPI tables say.
- From rc3, the M920x boots about 4 s faster: the serial console of
  coreboot (COM1 of the Super I/O, a real UART behind an optional
  connector) prints from INFO instead of DEBUG, which at 115200 baud took
  5 s per boot; `cbmem -1` still has every line. The level is a saved
  option: on an installed machine, *Console* → *Console Log Level*
  ([docs/m920x.md](docs/m920x.md#boot-time)). The help of *Clear memory
  at power-on* gives its time there, 2 s with 40 GB (0156).
- `tools/vpd.py set --from-lenovo DUMP`: the serial number, MTM and UUID
  of an M920x from the dump of its Lenovo firmware (the `DmiVar`
  variables of the AMI NVRAM), the UUID of the factory included, which
  is not on the label ([docs/m920x.md](docs/m920x.md#serial-number-and-machine-type-vpd)).
- From rc3, the DMI and SATA Power Optimizers of the PCH on the M920x, off by
  default in the Coffee Lake FSP-S and never set on Cannon Lake: with LTR on
  every link (0142), the package still stopped at PC3 at idle (0157-0158).
- From rc3, the Windows product key of a machine that came with it, in an
  ACPI MSDM table as with the OEM firmware, from the `msdm_product_key`
  key of the VPD (0159); `tools/vpd.py set --from-lenovo` takes it from
  the dump of the Lenovo firmware, `--windows-key` by hand.
- From rc3, *Hardware* → *Devices* on the M920x, as the Devices menu of the
  OEM setup: Ethernet, audio, Wi-Fi with its Bluetooth, front and rear USB
  ports (0160-0162). The
  TCO watchdog of the PCH works (`iTCO_wdt`), which Proxmox blacklists:
  [docs/m920x.md](docs/m920x.md#status) says how to use it for its HA.
- After rc3, on the M920x: *Console* → *Serial Console* in the setup, to turn
  the serial console off (about 1 s less per boot at INFO); the speed of
  the CPU fan in the boot log, or an error when it does not turn (0163);
  no more "LPC IO decode base 0!" error at every boot (0164), nor the
  warnings for the minimum D-state of the PCH thermal device, the GPE
  routing and the missing RW_VPD (0165-0167); under Linux, no more "failed
  to evaluate _DSM 2c176672-..." from iwlwifi: the Wi-Fi card has an ACPI
  node (0168).
- After rc3, the PEG port of the M920x riser slot off when no card is on
  it (0169): FSP-M's Auto left the empty port on at almost every boot,
  and with it the package stopped at PC3 at idle (about 1.1 W) even with
  0157-0158; the PC9 measured with ci-143 came from a boot on which it
  was off. *Hardware* → *Devices* → *PCIe riser slot*: Auto, Enabled
  (for a card that Auto does not see), Disabled.
- After rc3, about 0.5 s less at every boot of the M920x and of the W541:
  SMM no longer reads the *BIOS Lock* option from the flash without
  cache at the end of the boot, ramstage gives it the value (0170).
- After rc3, the M920x with other processors and cards than the port
  machine's: PL2 1.25 times the TDP as the OEM firmware, instead of 65 W
  for every processor (a T model drew 65 W in bursts, a 65 W one with
  Turbo Boost stopped under its 81 W); the fan class follows PL1 when it
  is set; Turbo Boost and Hyper-Threading are in the menu only where the
  processor has them (0171). The *Wireless* switch also turns off a CNVi
  card; without processor graphics (an F processor, or *Intel graphics*
  off in the setup) the riser port stays on; EDK2 loads the option ROMs
  of the cards, so a graphics card on the riser shows the firmware screen
  and the setup (0172 and the M920x defconfig).
  A machine that already saved its settings keeps the PL2 it had:
  *Energy Saver* → *Processor* → *CPU PL2 power limit* → 0.
- After rc3, on the M920x, two bugs reported upstream for the M720q and the
  M920q: the DisplayPort output was described as HDMI in the VBT, so a DP
  monitor was not detected under Linux (coreboot bug #670, 0174); a
  memory training cache made with another processor or with
  Hyper-Threading the other way is no longer given back to FSP-M, which
  trains again (0173). The first boot after the update trains the memory
  once, about 40 s with a black screen. The global reset of bug #655
  was already fixed in the coreboot of rc3.
- `tools/update.py other-slot` also takes the test builds of the CI
  (`ouroBIOS-ci-N-...`), to try one in the slot that is not running.
- After rc3, on the M920x, an RTC power loss (the coin cell out or flat, the
  clear-CMOS jumper) resets the setup options to their defaults, as with
  the Lenovo firmware: coreboot deletes them before the memory training
  reads the first one, and the setup writes each default back (0175,
  [docs/m920x.md](docs/m920x.md#resetting-the-settings)). The ME comes
  back on, *Firmware protection* too (turn it off again before writing the
  flash with flashrom), and so do the boot entries a setup switch had
  removed (iPXE, CSMWrap, USB drives); the other boot entries, the Secure
  Boot keys, the setup password, the VPD and the event log stay. With a
  flat coin cell every loss of AC power does it. Only the slots of v1.4.0 and
  later do it.
- After rc3, the state of the Intel ME of the M920x, which the OS cannot ask
  once the ME is disabled (no HECI device): *General* → *About this
  ThinkCentre* → *Management Engine* in the setup, with its status
  registers in the help, and two SMBIOS OEM strings (type 11, `ME: ...`
  and `ME HFSTS: ...`) for `dmidecode -t 11` and `tools/update.py status`
  (0176, [docs/m920x.md](docs/m920x.md#intel-me)).
- After rc3, *Hardware* → *Cooling* → *TCC activation offset* on the M920x,
  as in the OEM setup: the processor throttles that many °C below its
  TjMax (0-15, default 0), cooler and quieter under a long load; listed
  on the processors that can take it (0177,
  [docs/m920x.md](docs/m920x.md#fan)).
- After rc3, three switches of the OEM setup in *General* → *Boot* of the
  M920x, which the payload reads (0178, `edk2/0036-0037`,
  [docs/m920x.md](docs/m920x.md#boot-options)): *Option ROMs of the cards*,
  *All* or *Graphics cards only* (NVMe, SATA and USB cards still boot with
  the firmware's own drivers); *Boot from USB drives*, off to keep them out
  of the boot order and the boot menu (not a security setting: the Shell,
  CSMWrap, an OS entry and the fallback path still start them); *Boot menu
  prompt*, off to hide "Press ESC" on the logo, while Esc still works.
- After rc3, updates of the M920x keep the memory training: the capsules
  rewrite the two RW slots only, `tools/update.py other-slot` leaves
  `RW_MRC_CACHE` as it is (`--retrain` empties it), and *Go back to* in
  the setup no longer erases it (0179, `edk2/0038`). The new slot trains
  again only when the cache was made with another FSP-M, processor or
  Hyper-Threading setting (0173), so an update no longer takes the 20-40 s
  of a training; the first update from rc3 or earlier usually still does,
  once. Staging these capsules takes the `tools/update.py` of v1.4.0 or later,
  which still takes those of rc1-rc3: the release notes now download it
  from the commit of the release instead of `main`. The W541 still empties
  the cache at every update
  ([docs/update.md](docs/update.md#what-changes-and-what-stays)).
- After rc3, on the W541, the state of its Intel ME, which `me_cleaner -S`
  stops in its bring-up loader and whose HECI interface the firmware hides
  by default, so that only the boot log told what it did: *General* →
  *About this ThinkPad* → *Management Engine* in the setup, with the six
  status registers (HFS1-6), the working state, the mode, the error code
  and the progress phase in its help, and the two SMBIOS OEM strings of
  the M920x (type 11, `ME: ...` and `ME HFSTS: ...`) for `dmidecode -t 11`
  and `tools/update.py status` (0181). Lynx Point hides HECI before the
  tables are written, so coreboot reads the registers earlier, when the
  devices are initialized, without a message to the ME and not on S3
  resume. The progress phase comes first: an ME stopped in the bring-up
  loader by the AltMeDisable strap, as the one of the release images, is
  *Disabled (AltMeDisable, BUP)*, any other stop there *Stopped in BUP
  (state 0xNN)*, and only then the operation mode gives the texts of the
  M920x. The help of *Intel ME interface (HECI)* no longer says that the ME
  keeps running. None of the W541 changes of v1.4.0 has run on the laptop
  yet: [docs/testing.md](docs/testing.md) lists their tests, marked *not
  yet tried*.
- After rc3, *General* → *Boot* of the W541 has two of the switches of the
  M920x, which its payload reads (0182, `edk2/0037`), both on by default:
  *Boot from USB drives*, off to keep the USB drives of the laptop and the
  dock out of the boot order and the boot menu (not a security setting: an
  entry made by an OS, the Shell, CSMWrap, *Boot From File* and the
  fallback path still start them), and *Boot menu prompt*, off to hide
  "Press ESC" on the logo while Esc still opens the boot menu. The *Boot*
  card is now always shown. No *Option ROMs* switch: the W541 payload runs
  no option ROMs (`EDK2_LOAD_OPTION_ROMS` stays off), as the VBIOS of the
  NVIDIA GPU is a legacy image for the OS only, and the one other card with
  a ROM would be an ExpressCard, whose unsigned code would then run in the
  firmware.
- After rc3, three EC settings of the Lenovo setup of the W541, decoded from
  its firmware, GNET94WW (0183): *Energy Saver* → *Power* → *Power on with
  AC attached*, off by default, which starts the laptop, or resumes it from
  hibernation, when the AC adapter is plugged in; *General* → *Sound* →
  *Keyboard beep*, on by default, the beep of the EC for a key combination
  that it does not handle; and *USB always on* → *AC and battery*, which
  now does what it says. Before v1.4.0 the devicetree set the EC bit that
  keeps the yellow USB port unpowered on battery, so *AC and battery* most
  likely acted as *AC only* in hibernation and power-off. **A W541 already
  set to *AC and battery* powers that port on battery in hibernation and
  power-off from v1.4.0 on, which runs the battery down**; *AC only* keeps the
  old behaviour, and the help of *USB always on* says what each value does.
  The EC keeps these bits only while it has power, and a slot before v1.4.0
  (after a vboot fallback, or with `update.py other-slot`) writes the old
  ones again. The other H8 ThinkPads, the T440p included, are unchanged.
  Whether *Keyboard beep* changes anything is for the test on the laptop:
  the Lenovo firmware also writes a beep mask that differs from ours by one
  bit.
- After rc3, *Security* → *Virtualization* → *Untrusted ExpressCard and
  Thunderbolt* on the W541 (0184), off by default and shown with *Intel
  VT-d* on: the root ports of the ExpressCard slot and of the Thunderbolt
  port get the ACPI `ExternalFacingPort` property, and Linux with its
  IOMMU on (`intel_iommu=on`) treats the devices behind them as untrusted,
  with a DMA domain of their own and bounce buffers. The DMAR opt-in flag
  stays off: nothing protects the memory before the OS (the payload has no
  IOMMU driver), and Windows Kernel DMA Protection needs TPM 2.0, which the
  W541 does not have. The comments of the DSDT, which called the two ports
  the WWAN and the ExpressCard slot, are fixed.
- After rc3, the EC events that the Lenovo firmware of the W541 reports to
  the OS, which our DSDT dropped (0190), with the same HKEY codes: dock and
  undock (0x4010, 0x4011), the thermal alarm of the EC (the thermal zone
  notified, and 0x6022 at its critical level), the battery alarms (0x6011,
  0x6012), NumLock (0x6000) and the 0x1009 hotkey when the OS enables it;
  `thinkpad_acpi` makes kernel messages and netlink events of the alarms.
  And the software mute handshake (`HAUM`, `SAUM`): `thinkpad_acpi` no
  longer adds its *ThinkPad Console Audio Control* mixer on top of the EC,
  and mute goes through the codec, as with the Lenovo firmware
  (`thinkpad_acpi.software_mute=0` keeps the old way). The T440p, whose
  Lenovo DSDT handles these events the same way, gets them too, NumLock
  aside. Left out, with the reason in `ec.asl`: the events that the Lenovo
  firmware drops too or handles in its SMM code, the CPU limits that the EC
  asks for (they need a `_PPC` policy and a test with a smaller adapter),
  the radio switch, the Ultrabay and sticky Fn
  ([docs/roadmap.md](docs/roadmap.md#ec-events-left-out)). Checked in
  `acpiexec` on the DSDTs of the W541 and the T440p.
- After rc3, `nri`: the 1D training of the read timing, the write timing and
  the read voltage of ranks 1-3 of each channel ran with the register file
  of rank 0, and the W541 of [docs/raminit.md](docs/raminit.md) has four
  ranks per channel. The fix of Angel Pons, not merged upstream yet
  ([Gerrit 96694](https://review.coreboot.org/c/coreboot/+/96694), 0185),
  with the revision of the saved training bumped to 3 (0186): a slot with
  the fix never boots on a training made without it, and an older slot
  never boots on one made with it, also after a vboot fallback. The first
  boot of a v1.4.0 slot trains, as after every W541 capsule. A DIMM with
  more than the 10 column address bits that Haswell drives, as a 16 GiB
  SO-DIMM of 8 Gb chips ([coreboot ticket
  626](https://ticket.coreboot.org/issues/626): margins that look fine,
  then corrupted memory), is left out with an error that names its slot,
  and the laptop boots on the others (0188; `mrc.bin` and the Lenovo
  firmware do not support them either). The native RAM init records its
  timestamps as `mrc.bin` does, so `cbmem -t` and `tools/hw-report.py`
  (MEM-01, BOOT-02) see it (0189). On both variants SMBIOS gives each slot
  the size and ranks of its own module, also with two DIMMs of different
  sizes in a channel (0187).
- After rc3, the settings reset on an RTC power loss of the M920x (0175) has
  its trigger for Haswell (0180): romstage deletes the setup options before
  the first one is read, with a POST code before and one after, so that a
  boot that follows one that hung there skips it; on Haswell the option
  needs `CMOS_POST`. It stays off in the W541 builds
  (`CONFIG_DRIVERS_EFI_RESET_OPTIONS_ON_RTC_FAILURE` is not set in
  `configs/w541-*.defconfig`) until the M920x passes its test (OPT-05 of
  [docs/testing.md](docs/testing.md#setup-options-opt)) and the W541 is
  checked for whether software can set its RTC power loss bit, which would
  then turn *BIOS Lock* off at the next boot. A CMOS clear still keeps the
  settings of a W541
  ([docs/roadmap.md](docs/roadmap.md#settings-reset-on-the-w541)).
- `tools/update.py status` also shows the state of the ME (from v1.4.0,
  on both boards) and of the flash
  protection, on both boards: whether `WP_RO` is in a locked Protected
  Range, *BIOS Lock*, whether flashrom can write the slots.
  `tools/update.py protection` reads it in detail from the registers of
  the SPI controller, each Protected Range mapped onto the regions of the
  flash map, without writing anything; `--expect-ro on|off` gives an exit
  status for scripts, 2 whenever it cannot tell
  ([docs/update.md](docs/update.md#flash-protection)). On the W541 it reads
  the SPI controller of Lynx Point, behind the LPC bridge, after a check of
  its RCBA, through one read-only page of `/dev/mem`; *BIOS Lock* counts as
  on with SMM_BWP set, or with BLE set and BIOSWE clear; `other-slot` warns
  about *BIOS Lock* and the Protected Ranges there too. A kernel that
  refuses the page (lockdown, or `IO_STRICT_DEVMEM` while `intel-spi` and
  `iTCO_wdt` hold it) gets the reason and a hint, and *BIOS Lock* and the
  saved options are still shown. On both boards the texts now say that the
  protection holds until the next reset or S3 resume, and that a change of
  the options applies from the next boot or resume. The names of the
  release candidates and CI builds of `nri` (`-rc3-nri`, `ci-N-...-nri`),
  which read as `mrc`, are recognised.
- `tools/hw-report.py`: a read-only report of a running machine, PASS, WARN
  or FAIL per area with thresholds: boot time, the RAM init against the
  training cache (FspMemoryInit over 2 s with a valid cache is a warning,
  over 5 s a failure), firmware and kernel log, package C-states, PCIe ASPM
  and LTR, the riser port, fan, ME, TPM, vboot slot, flash protection,
  SMBIOS and ACPI tables; with a copy of the flash also the event log,
  `RW_NVRAM` and the saved options. [docs/testing.md](docs/testing.md): the
  release test matrix of the M920x and the W541.
- `tools/hw-report.py` on the W541, written from the code of v1.4.0 (it has not
  run there yet): BOOT-03 no longer fails at every boot on the `[CRIT]` line
  of the reduced ME (`intel_me_path: mbp is not ready!`); BOOT-04 no longer
  takes the GPLV and `_DSM` messages, gone since v1.3.5, for known ones,
  which would hide them coming back; MEM-01 and BOOT-02 take the RAM init of
  `nri` from its timestamps (0189; the whole romstage on older slots), and
  *Using cached memory parameters* counts as a valid cache; FLASH-01 reads
  the registers through the probe of `update.py` on both boards and, when
  the kernel refuses them, compares the Protected Range that coreboot logged
  with `WP_RO` (`INFO`, never `PASS`); a Protected Range over `WP_RO` with
  FLOCKDN off is a `WARN` on both boards; ME-01 takes the state from the
  SMBIOS strings of 0181, or the `ME: HFSTS1-6` line of the log, against
  *Intel ME interface (HECI)*. A new EC-01 warns when the EC firmware is
  older than 1.15 (GMHT30WW), which fixes CVE-2019-6171 and which only the
  Lenovo firmware can install
  ([docs/flashing.md](docs/flashing.md#before-you-start)). CPU-01 also gives
  whether the TCC offset can be set and its value (both boards), FAN-01 a
  hint for `thinkpad_acpi`, TPM-01 the state of a TPM 1.2, and a check that
  misses its log lines names the console log level of the boot.
- `tools/sbom.py`: the software bill of materials of a ROM, read from the
  image itself: coreboot, vboot, libgfxinit, EDK II, LvglPkg, iPXE, CSMWrap
  and SeaBIOS with versions and licenses; Intel's FSP-M and FSP-S,
  microcode, ME, flash descriptor, GbE and VBT (on the W541 also `mrc.bin`
  and the NVIDIA VBIOS) with versions and SHA-256; how much of the image is
  open-source code, closed binaries, data and empty flash. Each release
  carries it as `…-sbom.md` and as CycloneDX 1.5 (`….cdx.json`), both in
  its `SHA256SUMS`, and its notes a short table from it and the checksums.
- The notes of the M920x releases say what a first install with `flashrom
  --ifd -i bios` empties (settings, boot entries and Secure Boot keys, the
  event log, the memory training, vboot's state, the VPD) and copy the VPD
  of the backup into the image before writing it (`tools/vpd.py copy
  --in-place`).
- Issue forms for the repository: *Bug report* (component, device and
  variant, firmware version, how it was written, how often, the
  `tools/hw-report.py` report and the coreboot log), *Feature request*
  and *Hardware report* (processor, memory, cards, what works and what
  does not); no blank issues, links to the docs instead. What was looked
  at for this version and left for later: [docs/roadmap.md](docs/roadmap.md).

## v1.3.10

- macOS with OpenCore ([docs/macos.md](docs/macos.md)): two setup options,
  *C-state configuration lock* (CFG Lock; off, macOS boots without
  OpenCore's `AppleXcpmCfgLock` quirk) and *ACPI processor objects*
  (*Processor*: the CPUs declared the way macOS looks for them, without an
  SSDT that wraps them); under macOS only, the HPET with IRQ 0 and 8 and
  the 8254 timer without IRQ 0, as on a Mac, and the last backlight level
  put back at wake, which the resume path starts at 50% (patches
  0089-0091, 0095, 0096). With the `_OSI` to `XOSI` rename of some
  OpenCore configurations the parts under macOS stay off: remove it
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- `nri`: v1.3.10-rc1 hid the two EHCI controllers, as the native RAM init
  puts every USB port on the xHCI one. With it a USB drive plugged in was
  mostly not found, under Linux and macOS: under Linux, whenever the xHCI
  controller was in runtime suspend (kept in D0, it found the drive), and
  in a USB 3.0 port the SuperSpeed link went to compliance mode, so the
  drive ran at USB 2.0 speed. It was the only change to USB, and rc2 drops
  it: the EHCI controllers stay as in v1.3.9. Verified on the W541 with
  rc2 (nri, installed with the capsule): the drive is found in all four
  ports, and in a USB 3.0 one it links at SuperSpeed (U0, 5 Gb/s).
- ACPI: the model, serial number, type and OEM name of the battery as
  strings (they were buffers); the CPUs notified by `_PSR` only when the
  power source changes, not at every read; the EC wake cause read as one
  byte (patches 0092-0094).
- From rc3, more for macOS ([docs/macos.md](docs/macos.md)): the wake
  source left in PM1_STS and GPE0_STS at S3 resume, for every OS, as with
  the OEM firmware (macOS tells a wake by the user from a dark wake by
  it), with SCI_EN set before the SMIs come on so that a power button wake
  cannot turn into a power off (0099); under macOS, the sleep LEDs and the
  wake on lid opening set in `_PTS`, as `_SST` and `_PSW` do under Linux
  (0100); the backlight registers and the MMIO of the xHCI controller
  addressed at the BAR they have when the methods run, all 64 bits of it,
  not the one of boot (0101, 0102); the battery read one byte at a time,
  so that macOS reads it without ECEnabler (0103); two options in
  *Hardware* → *Graphics*: the display left to the OS at wake, without the
  mode set of libgfxinit, and the firmware screen at the panel's
  2880×1620 (0104-0107, off by default).
- From rc4: with *Firmware screen resolution* on *Panel, up to 2880 x
  1620*, the setup of rc3 opened on a black screen, at any UI scale: a page
  fault in LVGL v9.5.0, whose circle mask writes past its buffer for some
  radii from 922 px on, and the orbs of the wallpaper reach 939 and 1004 px
  at 1620 px of height. rc4 takes the fix of LVGL v9.6.0 and draws the orbs
  without a circle mask, which only clipped pixels that their gradient
  leaves transparent (lvglpkg/0016-0017); the smoke test of the payload
  (`tools/build.sh smoke`) now also opens the setup at 2880×1620, and stops
  on an exception of the payload. Verified in QEMU (q35) with the payload
  of rc4: at 2880×1620 the setup opens and answers the keys at each of the
  four UI scales (rc3: page fault at each); at 1920×1080 the whole smoke
  test passes, and the wallpaper differs from rc3's by at most 2 levels per
  color. A capsule update at 2880×1620 too, from a ROM of
  `tools/build.sh update-test` with the screen at that size: the update
  screen drawn through the whole write, the capsule applied, the other slot
  equal to it, then booted by vboot; so rc4 installs with `update.py stage`
  on rc3 with the option on. Verified on the W541 with rc4 (nri), installed
  that way on rc3 with the option on: the update succeeded, the firmware
  screen is at 2880×1620 and the setup opens. Out of the black screen on
  rc3 without updating, from Linux: `sudo efibootmgr -n` with the number of
  the *UEFI Shell* entry, a restart, then in the Shell
  `setvar gfx_fb_limit -guid ceae4c1d-335b-4685-a4a0-fc4a94eea085 -bs -nv
  =00000000` and `reset`: the firmware screen is at 1920×1080 again. A
  Linux started by OpenCore with `RequestBootVarRouting` sees OpenCore's
  boot entries, not the firmware's, and no *UEFI Shell*: there, update.
- From rc5: rc3 and rc4 powered the laptop off at every wake from S3, by
  the power button, the lid or a key, under Linux and macOS. The EC wakes
  the system through the power button line, so PWRBTN_STS is set at every
  wake, and rc3 leaves it to the OS (0099); but the SMI handler ran its PM1
  handler at any SMI# with that status set, also with `SCI_EN` set, and
  ramstage sends APMC commands before the OS resumes (finalize, the lock of
  the other vboot slot): the first one turned the wake into a power off.
  The SMI handler now leaves PM1 and GPE0 events to the OS when `SCI_EN` is
  set, as `soc/intel/common` does (0108). The event log of the W541 with
  rc4 (`tools/elog.py`) shows it at each wake: *ACPI wake* S3 from the
  power button, then *Power button*, written by the PM1 handler, and *ACPI
  enter* S5; the next boot reads POST code 0x76 (`BS_POST_DEVICE`, where
  `lpc_final()` sends the finalize command). Verified on the W541 with rc5
  (nri) under CachyOS: the laptop resumes from S3 again.
- From rc6: no "No handler for Region [ERAM]" for `BAT0._STA` and
  `BAT1._STA` in the log of macOS at boot. macOS evaluates them before its
  EC driver is up; they now read no EC RAM before `_REG` (3, 1) and return
  "no battery" until then, and `_REG` notifies both batteries (0x81) when
  the handler arrives, so that the OS checks them again (0109). Linux runs
  `_REG` before it looks at the batteries: nothing changes there. Checked
  in `acpiexec` on the DSDT of the W541.
- From rc6, for *Light the display up at wake* off, with which macOS left
  the display off at wake on rc5: it reads the live HPD state of the panel
  port (`SDEISR`) before it powers the panel up, and an eDP panel raises
  HPD only once it has power, which that path did not give it (with the
  option on, libgfxinit powers the panel up to probe it). Measured on the
  W541 under Linux: the HPD of the panel port is high with the panel
  powered and low with it off, with its detection enabled. At wake with
  the option off the firmware now forces the panel VDD on, without the
  power sequence and the backlight, and waits its power-up delay, 200 ms
  (0111); enables the hotplug detection of the ports whatever the
  register holds (0110); and logs what the OS finds, `GMA: SDEISR ...
  PP_STATUS ... PP_CONTROL ...` in `cbmem -c`. Linux takes the forced
  VDD over. Verified on the W541 with rc6 under CachyOS, with the option
  off: at wake the log reads `PCH_PORT_HOTPLUG 00000000 -> 00101010` (S3
  clears the register, and the code before 0110 enabled the detection
  again too) and `SDEISR 00800000 PP_STATUS 00000000 PP_CONTROL
  00000008`: HPD high, the panel with VDD and no power sequence; i915
  shows no warning. Under macOS the display still stays black at wake
  with the option off (the laptop wakes): leave it on there, unless the
  OS side does what is missing (next point).
- rc7 and rc8, for macOS with *Light the display up at wake* off: macOS
  drives the panel of the W541, on DDI D, as a DisplayPort sink. At wake
  it trains the link and runs the pipe, but it never powers the panel up
  through the panel power sequencer nor enables the backlight, which
  libgfxinit does with the option on. rc7 did both from the `_WAK` of
  the firmware under macOS (0112); but then the backlight came on at
  every wake from S3, the dark wakes of macOS too, before macOS had
  decided to light the display up. From rc8 0112 is gone: that is for
  the OS to do when it lights the display up, as a Lilu plugin for
  AppleIntelFramebufferAzul does (after `LightUpDP`, the power sequence
  and then the backlight; before `DisableDisplay`, the backlight only,
  so that the panel keeps power and HPD), and dark wakes stay dark. 0110
  and 0111 stay: Azul checks HPD before anything else at wake.
  SSDT-PNLWAK, with the `_WAK` of the DSDT renamed, does what 0112 did.
- From rc9, under macOS on AC, closing the lid sleeps (0113). macOS takes
  the panel of the W541 for an external display: with no built-in
  display online, IOGraphics puts it in desktop mode, and in desktop mode
  on AC macOS does not sleep on lid close; the panel stayed lit inside
  the closed lid. On a lid close event under macOS on AC, the EC methods
  now press the sleep button, as Fn+4 does; on battery macOS sleeps by
  itself. No clamshell mode under macOS on AC: a closed lid sleeps there
  also with an external display. Linux and Windows as before. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc10, the lid reads no EC RAM before the EC driver of the OS is up
  (0114), as the batteries since rc6 (0109): macOS read it at boot before
  its EC driver, logged "No handler for Region [ERAM]", took the lid for
  closed and found it open only some 20 s later, which would turn off a
  panel that it drives as built in. Until `_REG` the lid now reads open,
  and `_REG` notifies it so that the OS reads it again. Linux runs `_REG`
  before it looks at the lid: nothing changes there. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc10, under macOS with *NVIDIA discrete GPU* on in the setup, the
  GPU is powered off at boot (0115): macOS has no driver for it (Apple
  removed the Kepler drivers in Monterey), and it stayed powered in D0
  for nothing. `-wegnoegpu` only hides it, and the SSDTs that call the
  `_OFF` of the OEM firmware find no such path in this DSDT. The `_INI` of
  the PEG port calls the `_OFF` of its power resource, the sequence of
  the runtime power management of Linux, and `_WAK` calls it again if
  the wake powered the GPU: the firmware powers it at boot, so at a
  resume from S4. *Hardware* → *Graphics* → *NVIDIA GPU off under
  macOS*, on by default and shown with the GPU on: off leaves the GPU
  powered, e.g. for the Kepler drivers that OpenCore Legacy Patcher
  installs, without the `_OSI` rename, which would turn off all the
  other fixes under macOS. Linux and Windows as before. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc11, after a review of all the patches (0116-0119): no full
  flash access for the OS at S3 resume, when the boot that the OS
  resumes from had the firmware update mode on and the payload found
  no capsule (0116; until now the lock of the vboot slot switch ran
  first and covered it, by link order); the SMI handler in SCI mode no
  longer clears PM1_STS and GPE0_STS when their bits are the only ones
  in SMI_STS, which threw away an event the OS had yet to see (0117,
  as the common SMM code of soc/intel); at wake with *Light the display
  up at wake* off, the firmware waits for the HPD of the panel instead
  of the whole 200 ms power-up delay, and logs `GMA: HPD up after N ms
  with VDD` (0118); the framebuffer limit and the aperture size options
  are read once per boot instead of twice, each read a walk of the
  option store in flash (0118, 0119). The DSDT does not change.
- From rc11 too, the AC adapter reads no EC RAM before the EC driver of the
  OS is up (0120), as the batteries (0109) and the lid (0114): the last
  two "No handler for Region [ERAM]" of macOS at boot. Until `_REG` the
  adapter reads as at the last check, on AC at boot, and `_REG`
  notifies it. And *Hardware* → *Expansion ports* has a switch for each
  SATA port of the W541 besides the drive bay (0121): the M.2 slot on
  the I/O subcard (port 1), the M.2 WWAN/SSD slot (port 4) and the
  Ultrabay (port 5), on by default. A port turned off is not implemented
  in the controller, and the OS does not wait for a link on it at boot
  and at every wake, about a second per empty port. Keep the port of a
  slot with a drive on: macOS on the M.2 SATA drive needs port 4.
- From rc12, coreboot `26.09-438-g206078d6d990`, 158 commits after the pin
  of the earlier release candidates (26.09-280): the 117 patches apply
  with the same bodies, only their context moves (the PLATFORM_INFO and VR
  MSR refactoring of cpu/intel/haswell); upstream does not touch the
  cache-as-RAM layout, vboot, the console, the timestamps nor the FMAP and
  CBFS caches, and bootblock and romstage have the same regions
  (`configs/ro-interface.txt`, `rw-ok`), so the slots still run behind the
  read-only part of v1.3.9. EDK2 from MrChromebox `uefipayload_2608` at
  `ddf612165c8b`, three commits after the pin (the setup hotkey, failed
  automatic boot options, the SubForm parsing fix that our patch 0002
  already covered).
- From rc12, *Compatibility* → *macOS* → *Intel display audio* (0122):
  the HD Audio controller of the display ports of the Intel GPU (0:3.0),
  on by default: the audio over the mini DisplayPort and a port of the
  dock (DP-B and DP-C in the VBT; the panel and VGA have none). Under
  macOS AppleHDAHDMI_DPDriver waited 10 s for its codec at every wake and
  at every sleep with the display off: 10-20 s of wake time instead of
  about 1.3 s, with the battery polling held meanwhile. Off, the
  controller is hidden for every OS, and with it the audio over those
  ports.
- From rc12, more of an OpenCore configuration in the firmware, under
  macOS only ([docs/macos.md](docs/macos.md)):
  - with *ACPI processor objects* on *Processor*, `plugin-type` on the
    first thread, which turns XCPM on, as `SSDT-PLUG` does (0123);
  - *Compatibility* → *macOS* → *Panel under macOS* (0124, 0129), how the
    Intel framebuffer of the configuration has macOS drive the panel.
    *External display*, the default on the W541, whose panel is on DDI D
    where the laptop framebuffers have no built-in connector: macOS has
    no backlight control for it, so the brightness keys set the PWM
    themselves, as the `_Q14`/`_Q15` renames and their SSDT did, and
    closing the lid on AC sleeps the laptop (0113). *Built-in display*,
    for a laptop framebuffer with its built-in connector on DDI D (not
    tried when rc12 came out; tried since, see rc14): the backlight
    device of macOS, `\_SB.PCI0.GFX0.PNLF`
    (`_UID` 15, the PWM at the 0xad9 of the Haswell Macs from boot and
    after every wake, as `SSDT-PNLF`), an ambient light sensor (`ALS0`, as
    `SSDT-ALS0`), the keys as ACPI events for BrightnessKeys.kext, and the
    lid left to macOS;
  - *Compatibility* → *macOS* → *USB, audio and LAN wake* (0130), off by
    default: macOS does not arm the wake of the USB, HD Audio and
    Ethernet controllers (`_PRW` with S0), as the `_PRW` renames of
    OpenCore configurations did against wakes right after sleep;
  - `\_SB.USBX`, the USB power properties of the SMBIOS of the Macs from
    Skylake on, as `SSDT-USBX` (0131).

  Remove from the configuration what each of them replaces: macOS takes a
  second definition of an object for an error and drops the SSDT. The
  NVRAM of macOS needs no emulation either
  ([docs/macos.md](docs/macos.md#native-nvram)).
- **From rc12, OpenCore needs the `Booter` quirks for the memory
  attributes table of the firmware**: `RebuildAppleMemoryMap` on and
  `EnableWriteUnprotector` off (`SyncRuntimePermissions` on too, up to
  rc15: see rc16 and rc17 below). With the
  quirks of the configuration of the W541 up to rc11
  (`EnableWriteUnprotector` on, the other two off) macOS restarts the
  laptop at the resume from S3, with no panic report, and `pmset -g log`
  reads `Failure during wake: IGPU(),HDEF(),SATA(AppleIntelPchSeriesAHCI)
  : Some drivers failed to handle setPowerState`. Seen on the W541 with
  rc12 (`nri`); with the three quirks set it resumes
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- From rc12, *Compatibility* → *macOS* → *Device properties for macOS*
  (0128), off by default: on, the firmware gives macOS, through the `_DSM`
  of each device, the `DeviceProperties` of the OpenCore configuration of
  this W541 (`configs/macos/DeviceProperties.plist`): AAPL,ig-platform-id
  0x0D220003, device-id 0x0412 and the framebuffer patches on the Intel
  GPU, `layout-id` 28 on the audio, the card reader and the LPC bridge as
  Apple's, `class-code` 0xFFFFFFFF on the Intel display audio. Then that
  section of the configuration can go.
- From rc12, the setup menu in six categories, each option in one card
  only (0125-0127, edk2/0028, lvglpkg/0018); the option names and values
  stay, and so do the settings. *General*: *About this ThinkPad*, *Boot*,
  *Sound*, and links to *Time and Date Settings*, *Firmware Update*,
  *Boot Splash Settings* and *Graphical UI Configuration*, which *System
  Configuration* still lists too; *Energy Saver*: *Battery*, *Processor*,
  *Processor voltage* (the undervolting options, a category of their own
  until now), *Thermal*, *Power*; *Hardware*: *Intel graphics*, *NVIDIA
  graphics*, *Storage* (the SATA ports), *Expansion ports* (ExpressCard
  and Thunderbolt), *Wireless*; *Keyboard*: *Keys*, *Pointing devices*;
  *Security*: *Flash protection*, *Memory protection*, *Virtualization*,
  *Management Engine*, and links to *Secure Boot Configuration* and to
  the password; *Compatibility*, new: *macOS* (*ACPI processor objects*,
  *C-state configuration lock*, *NVIDIA GPU off under macOS*, *Light the
  display up at wake*, *Panel under macOS*, *Intel display audio*, *USB,
  audio and LAN wake*, *Device properties for macOS*) and *Advanced*
  (*Non-maskable interrupts*). The options that the entries above place
  in *Hardware* → *Graphics*, *General* → *Advanced* or *Energy Saver* →
  *Processor* are in these cards now. The help of every option says what
  it does, its default and when to change it, and some names say more:
  *After a power loss* (was *Restore AC Power Loss*), *Intel ME interface
  (HECI)* (was *Intel Management Engine*), *Keyboard light*
  (*Illumination Control*), *Battery charged first* (*Battery Charge
  Priority*). The build checks the menu of each variant, built on the host
  from the same sources (`tools/build.sh menu`): an option in two cards,
  or in none, stops it; `tools/qemu-setup-shots.py` takes screenshots of
  the setup with the menu of the W541 in QEMU
  ([patches/README.md](patches/README.md#the-setup-menu-and-its-screenshots)).
- From rc13, the `_PSW` of the lid and of the sleep button write no EC RAM
  before `_REG` (3, 1) (0132), as the batteries (0109), the lid (0114)
  and the AC adapter (0120) read none: macOS called the one of the lid at
  boot, before its EC driver, and logged "No handler for Region [ERAM]"
  for `WKLD = Zero`, the last of them at boot. Until `_REG` each keeps the
  setting it is asked for, and `_REG` writes the last one to the EC.
  Linux calls `_PSW` after `_REG`: nothing changes there. Checked in
  `acpiexec` on the DSDT of the W541.
- From rc14, *Device properties for macOS* follows *Panel under macOS*
  (0133): with *Built-in display* the firmware gives the Intel GPU a
  laptop framebuffer, 0x0A260006 with its built-in connector (con0) on
  DDI D, where the panel of the W541 is
  (`configs/macos/DeviceProperties-builtin.plist`); with *External
  display* the desktop framebuffer 0x0D220003, as before. *Built-in
  display* has been tried on the W541 (rc12 `nri`, macOS 14.8.9,
  OpenCore 1.0.8, the same properties in OpenCore): macOS drives the
  panel as its built-in display, with the backlight through `PNLF`,
  sleep on lid close and the panel back at wake. It takes AzulFix 1.1.7
  or later and *Light the display up at wake* off
  ([docs/macos.md](docs/macos.md#the-panel-as-built-in-display)).
  `tools/devprops2asl.py --builtin` writes the properties of both;
  checked in `acpiexec` on the DSDT of the W541.
- From rc15, what trimming the OpenCore configuration of the W541 (rc14,
  OpenCore 1.0.8) found for the firmware. Checked in QEMU with the payload
  of the W541, then on the W541 with rc16 (below):
  - the com buffer of SMMSTORE, which the runtime variable services
    write, is runtime services data in the memory map (`edk2/0029`). It
    was reserved memory with `EFI_MEMORY_RUNTIME` (0x7F635000-0x7F644FFF
    on the W541), which XNU does not map: without OpenCore's
    `ProtectMemoryRegions` macOS restarted right after boot.efi, with no
    panic report. Linux maps both kinds; in QEMU it writes variables as
    before;
  - the payload runs from 1 GiB, and its HOB memory, where the DXE core
    starts, follows it (`edk2/0030`): the memory from 1 MiB to 1 GiB is
    free for the OS loaders. With the payload at 8 MiB and the HOB memory
    after it, up to 83 MiB, the slides of the kernel of macOS below 41
    were taken ("Only 215/256 slide values are usable!"), and OpenCore
    needed `ProvideCustomSlide`, and `EnableSafeModeSlide` with it;
  - the firmware revision of the UEFI system table is the release:
    X << 24 | Y << 16 | Z << 8 | N for vX.Y.Z-rcN, N = 0 for vX.Y.Z,
    0 for a build that is not a release (`tools/build.sh`, as
    `PcdFirmwareRevision` of EDK2; it was 0x00010000 for every release).
    Under macOS, where OpenCore replaces the SMBIOS, it is the place
    that tells the release: `firmware-revision` <0f0a0301> for rc15
    ([docs/update.md](docs/update.md#versions-variants-downgrades)).

  Without `ProtectMemoryRegions`, `ProvideCustomSlide` and
  `EnableSafeModeSlide` OpenCore boots macOS (seen on the W541 with rc16;
  [docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
  `AvoidRuntimeDefrag` stays, as before: without it boot.efi moves the
  runtime services data, and the com buffer of SMMSTORE, which SMM
  writes at its physical address, is runtime services data from rc15.
- From rc16, OpenCore's `AvoidRuntimeDefrag` should not be needed either
  (patch 0134, `edk2/0029`). boot.efi of macOS moves the runtime services
  code and data after `ExitBootServices()`, and leaves MMIO in place: SMM
  read the arguments of SMMSTORE, and from rc15 its com buffer, where
  they had been (the quirk hides the runtime services from boot.efi). The
  com buffer is now MMIO with `EFI_MEMORY_RUNTIME`, as
  `ProtectMemoryRegions` made it up to rc14, which every OS maps for the
  runtime services, with one page more in CBMEM after the block, where
  the runtime driver puts the arguments once the OS has called
  `SetVirtualAddressMap()`. Nothing that SMM reads or writes is runtime
  services code or data. Checked in QEMU with the payload of the W541:
  the com buffer of 68 KiB as runtime MMIO in the memory map, for Linux
  too, the variables that Linux writes at runtime with the arguments in
  that page (`DEBUG_SMI`) and read at the next boot; the smoke test. On
  the W541 macOS boots without it, and its NVRAM works
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)). Not
  with `DevirtualiseMmio` on, which takes `EFI_MEMORY_RUNTIME` away from
  MMIO, unless the com buffer is in `MmioWhitelist`.
- From rc16, the tests check what rc15 brought: the update test, in the
  memory map an OS gets at `ExitBootServices()`, no reserved range with
  `EFI_MEMORY_RUNTIME`, all of the memory from 1 MiB to 1 GiB free and
  the com buffer of SMMSTORE runtime MMIO with its page of arguments;
  `tools/verify-rom.sh`, the firmware revision of a release ROM
  ([docs/vboot.md](docs/vboot.md#how-it-is-tested)).
- From rc17, the smoke test of each variant does to the runtime services
  of the payload what boot.efi of macOS does without OpenCore's
  `AvoidRuntimeDefrag` (`tools/efi/rt-reloc-test.c`): after
  `ExitBootServices()` and `SetVirtualAddressMap()` their code and data go
  elsewhere, the old copies are filled with 0xCC, and the services are
  called only at their virtual addresses. Every service must answer, the
  two variables written must be in the flash with their data, nothing may
  write to the old copies, and `ResetSystem()` must reset: a physical
  address that the payload or SMM still uses at runtime fails it
  ([README](README.md#building)). The payload of rc16 passes it; the one
  of rc15 does not (`SetVariable()` returns `EFI_DEVICE_ERROR`: the
  arguments of SMMSTORE were runtime services data).
- From rc17, a DEBUG build of the payload, which no release is, no longer
  faults in `ResetSystem()` under macOS or Windows: the first `DEBUG()`
  of a runtime driver, which for ResetSystemRuntimeDxe came at runtime,
  looked for the print level in the HOB list, boot services memory.
  Runtime drivers read it from `PcdDebugPrintErrorLevel` (`edk2/0031`),
  as every module does with coreboot, which passes no such HOB. The
  release payload, without `DEBUG()`, builds byte for byte the same.
- From rc17, OpenCore's `SyncRuntimePermissions` should not be needed
  (`edk2/0032`). The memory attributes table (MAT), from which macOS
  sets what the runtime services may run and write, did not describe a
  runtime driver loaded after ReadyToBoot, as OpenCore loads
  OpenRuntime: the table was installed again at each runtime allocation
  of the load, before the DXE core had the record of the sections of
  the driver, which stayed runtime code without an image, read-only and
  not executable, until runtime memory was allocated again. Now the
  table is installed again once the record is in: the code read-only,
  the header and the data not executable. Checked in QEMU with
  OpenShell, MmapDump and a runtime driver loaded from the shell. With
  OpenRuntime 1.0.8 a later allocation corrected the table anyway, and
  on the W541 the quirk is off with rc16 already; the patch takes away
  the dependence on that allocation
  ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- The OpenCore configuration of the W541 with rc16 (OpenCore 1.0.8): of
  `Booter` → `Quirks` only `RebuildAppleMemoryMap` is on, and macOS
  works. `AvoidRuntimeDefrag` (not needed from rc16),
  `ProtectMemoryRegions`, `ProvideCustomSlide` and `EnableSafeModeSlide`
  (from rc15), `SyncRuntimePermissions` and `EnableWriteUnprotector` are
  off ([docs/macos.md](docs/macos.md#in-the-opencore-configuration)).
- From rc18, one payload for the two variants. FmpDxe, the driver that
  publishes the firmware in the ESRT and applies the capsules, had the
  GUID of its variant as its FILE_GUID, so the two payloads differed in
  those bytes only and EDK2 was built twice. Its FILE_GUID is now one
  fixed GUID in both defconfigs (`EDK2_CAPSULE_MAIN_FW_GUID`, patch 0135);
  the GUID of each variant in the ESRT, the one its capsules carry, comes
  from the coreboot table at every boot, as the one FmpDxe publishes
  already did (`edk2/0033`). `tools/build.sh` builds EDK2 once and gives
  the second variant the payload of the first, after checking that the
  two `.config` differ only in the RAM init, the name and the GUID
  ([README](README.md#building)). The update test of the CI runs with
  the fixed FILE_GUID too. FmpDxe keeps the result of its last update
  (`FmpState`, the `last_attempt_*` fields of the ESRT) under its
  FILE_GUID, so the first boot with rc18 shows no last attempt, until the
  next capsule; the variables under the old GUID stay in the store,
  unused ([docs/update.md](docs/update.md#how-it-works)).
- From rc18, the CI builds each release a second time from scratch on
  another runner, in parallel with the first build, and compares the two
  bit by bit (jobs `repro` and `compare`, `tools/ci.sh compare`: on a
  difference, the regions of the flash map and the compilers of the two)
  instead of building again on the same runner after the first build:
  the run is shorter, and two machines agree on the ROM, not one with
  itself. `tools/build.sh repro` still does it on one machine.
- From rc19, the smoke test runs once per payload (the two variants share
  one since rc18), and `tools/build.sh prepare` fetches of EDK2 only the
  submodules the payload uses (OpenSSL without its own, the brotli of
  BaseTools, LvglPkg with LVGL: 0.9 GB instead of 2.8, a third of the
  time), keeping coreboot's EDK2 Makefile from fetching the others. KVM
  for the QEMU tests was tried on GitHub's runners and is not used: under
  nested virtualization every SMI of SMMSTORE costs an exit to the
  hypervisor, and the update test, which writes the flash through SMM,
  took longer than with TCG (`OUROBIOS_QEMU_ACCEL=kvm` turns it on by
  hand).
- From rc19, every patch of the three series says how it was tested
  (`TEST=`: the tests of the CI, QEMU, the W541, or that there is no
  recorded test), its subject fits in 72 columns and the lines it adds
  in 96 (the Kconfig default of 0053, a string, excepted); the ones
  renamed keep their numbers. What the patches do does not change: 23
  lines of the coreboot series are wrapped, nothing else.
- From rc19, one OpenSSL in the payload: the Secure Boot, capsule,
  password and TPM drivers used a copy each (five, 800-1000 KiB apiece);
  they now share the one of CryptoDxe through its protocol
  (`CRYPTO_PROTOCOL_SUPPORT` of EDK2, which patch `edk2/0034` makes
  reach them). The modules of the payload go from 9.8 to 7.5 MiB in
  memory and the compressed payload in flash loses 115 KiB in each slot;
  the variable driver keeps its own OpenSSL, as runtime code must.
  Verified in QEMU: the smoke test and the capsule update, whose
  signature check goes through the protocol.
- rc20 fixes what the shared OpenSSL of rc19 changed in the order the
  DXE drivers come up: the drivers that use it now wait for CryptoDxe,
  so the TPM driver started after the Secure Boot keys of a fresh
  variable store had been written, and their measurements in PCR 7 (PK,
  KEK, db, dbx, SecureBoot: seven events of the TPM log) were dropped
  on that first boot of a TPM 1.2 machine. Patch `edk2/0035` starts
  CryptoDxe from the a priori list, before every other driver, and the
  order is the one of rc18 again. Verified with a TPM 1.2 in QEMU: the
  TPM log of rc18, 21 events, digest for digest. Nothing changes for
  the boots after the first, where no key is written. In
  `tools/build.sh prepare`, the submodules of EDK2 a tree prepared
  before rc19 had marked active one by one are unmarked, so the list
  of the ones the payload uses applies to that tree too, and a
  placeholder folder left in the path of a submodule is removed before
  the submodule is fetched.
- From rc21, the smoke test of the CI also checks Secure Boot and the
  ESRT (`tools/efi/secure-boot-test.c`): the payload must verify the
  signature of a test application against a CA put in db, accept a shim
  signed by Microsoft, refuse an image signed by a certificate in no
  database, an unsigned one and one whose hash is in dbx despite a good
  signature, compute SHA-256 and the PBKDF2 of the setup password right
  through CryptoDxe, and the ESRT must carry the entry of the
  variant with the GUID from the coreboot table. The second variant,
  whose payload is the first one's, runs this step on its own q35 image:
  since rc19 nothing booted the nri payload in the CI. With the TPM 1.2
  of swtpm, the measurement log must have the Secure Boot keys measured
  in PCR 7 at the first boot, with the right digests: the check that
  would have caught the rc19 regression.

## v1.3.9

**Installs with flashrom, not with the capsule**: it writes the read-only
part again ([docs/flashing.md](docs/flashing.md#from-v13x-to-v139)).

- The read-only part of v1.3.9 (patch 0085, `LENOVO_HASWELL_COMMON_CAR`;
  [docs/vboot.md](docs/vboot.md#the-read-only-part-of-v139)): one
  cache-as-RAM layout for `mrc.bin` and the native RAM init, with the stack
  after the regions that the bootblock and verstage leave to romstage, so
  that the `mrc` read-only part, the one with `mrc.bin`, starts the slots
  of either variant; an early console of 16 KiB in place of 3, where the
  messages of the bootblock and of vboot fit; the CBFS caches 8 KiB each in
  place of 16. The read-only part is now built from the coreboot pin of the
  slots, 26.09-280 (v1.3.0's was 26.09-53). Verified on a W541 with
  v1.3.9-rc1 (`mrc`, written with flashrom): it starts its slot, the log
  keeps the messages of the bootblock and of verstage, and the same
  read-only part starts the `nri` slots of rc2 and rc3.
- New ESRT GUIDs for both variants: the slots of v1.3.9 do not boot behind
  the read-only part of v1.3.0-v1.3.8, nor those behind the new one, so the
  capsule of v1.3.9 does not install on them (`update.py stage`, fwupd and
  the setup refuse it) and the releases after v1.3.9 install with their
  capsule on v1.3.9 only. Verified on a W541: the capsule of v1.3.9-nri,
  staged with `update.py stage --latest` on the `nri` slot of rc3, wrote
  the other slot, which trained and passed the memory test; the ESRT
  reports v1.3.9 and the last update as successful.
- Native RAM init (`nri`), from its comparison with the MRC's steps and
  with `mrc.bin` on the W541: the DRAM voltage from the SPDs (patch 0086:
  1.35 V on the W541's DDR3L, as `mrc.bin` sets it; the code assumed
  1.5 V, which selects the DDRIO settings), and a memory test after
  training with the training redone once if it fails (patch 0087, as the
  MRC's MEMTST; nothing on fast boots). On the W541 with four DIMMs the
  `nri` slot of rc2 trained, passed the test and took the fast path after
  ([docs/raminit.md](docs/raminit.md)).
- Native RAM init: a shorter read round trip (patch 0088). Compared on
  the W541 with `ddr-report.py`, `mrc.bin` reads 2.5-3.1 ns sooner: same
  receive enable delays, but the read data kept fewer qclks in the I/O.
  The NRI now takes those qclks off after the command training while a
  read test passes on every rank, and keeps one as a guard band. On the
  W541 the `nri` slot of rc3 ends with the latencies of `mrc.bin` (round
  trips of 44 and 45 qclks) and reads from Linux as fast; it passed 30
  minutes of `stress-ng --vm` with verification under load, and after an
  S3 resume the registers are the trained ones, shorter round trips
  included. The other differences, the power training and the voltage
  centering of `mrc.bin`, are listed in
  [docs/raminit.md](docs/raminit.md#on-the-w541).
- The `nri` variant is published as a release together with the `mrc`
  one, never as the latest (the fwupd remote reads the `mrc` release);
  release candidates stay pre-releases for both. Up to v1.3.8 `nri` was
  always a pre-release.
- `tools/ddr-report.py`: the memory controller as the RAM init left it
  (timings, turnarounds, command rate, latencies, trained delays and Vrefs
  per byte, comp, ODT, equalisation), read only, and two dumps compared:
  `mrc.bin` against the native RAM init on the same machine;
  `tools/mem-latency.c`, how long a read from the memory takes.
- `tools/update.py other-slot`: the slot of a release, from its image,
  written into the slot that is not running, with flashrom in three
  regions only, and vboot asked to try it with two tries, so that a slot
  that does not boot falls back to the one that ran, as after a capsule.
  From v1.3.9 behind the `mrc` read-only part also the other variant; the
  tool checks what the read-only part on the laptop can start
  ([docs/update.md](docs/update.md#a-release-from-its-image-in-the-other-slot)).
  Verified on a W541: from `mrc` (rc1) to the `nri` slot of rc2, back to
  `mrc`, then to the `nri` slot of rc3.

## v1.3.8

- EDK2 moved to MrChromebox `f7cbaab0d5a2` (`uefipayload_2608`, two
  commits after the pin of v1.3.7): the complete Microsoft DBX (the
  revocation list of Secure Boot, 24 KiB) enrolled with the default keys,
  with the newer update appended, instead of the last update alone; the
  same union in `dbxDefault`, so that fwupd can tell the DBX version. All
  the patches apply as they are. About 24 KiB more in each slot.
- A lighter payload (patch `edk2/0027`): the drivers the W541 has no use
  for are left out, UFS and UHCI host controllers (the PCH has EHCI and
  xHCI), EFI byte code option ROMs, and the NTFS, exFAT and ext2
  filesystems (FAT and ext4 stay, for the ESP and a Linux boot volume).
  About 110 KiB less in each slot, DBX included: about 304 KiB free with
  `mrc` and 237 KiB with `nri` (194 and 128 in v1.3.7). Verified on a W541
  with v1.3.8-rc2: fwupd reports the DBX version (20260707), the boot
  manager still boots a USB stick, and OpenBSD installed from it.

## v1.3.7

- The PCIe link to the NVIDIA GPU, as the Lenovo firmware of the W541 sets
  it up (patches 0078-0084). With `mrc.bin` the graphics port of the
  processor (PEG, `00:01.0`) is hidden from it, so that the integrated GPU
  stays the primary one, and `mrc.bin` then leaves the port as it comes
  out of reset; the native RAM init did not program it either. Measured on
  a W541 with v1.3.6: 75 of the 107 fields of Intel's analog front-end
  (AFE) settings for the port at their hardware defaults, the 8 GT/s
  presets at 0 on all 16 lanes, phase 3 of the 8 GT/s equalization not
  done. The Lenovo firmware (GNET94WW), read in its System Agent reference
  code and its setup data, programs the AFE settings and the 8 GT/s
  presets before the link trains: preset 3 for the root port, 7 with hint
  2 for the GPU. Once the link is up it reads the full swing of the GPU
  and writes the coefficients of its preset to each lane, then equalizes
  again for 8 GT/s; its search of the best preset per lane is off on the
  W541. The firmware now does the same, *As the Lenovo firmware* in
  *Hardware* → *NVIDIA GPU link tuning*, shown while *NVIDIA discrete GPU*
  is on. The same setting also offers *AFE and 8 GT/s presets* (the
  presets without the equalization; the default of v1.3.7-rc1, with
  Intel's presets 8, 7 and 2), *AFE* alone and *Off* (as up to v1.3.6), to
  compare them with the same image. The coreboot log reports the link and
  the equalization (`cbmem -1 | grep PEG`), and `tools/peg-report.py`
  shows the link from Linux with the errors of both ends
  ([docs/flashing.md](docs/flashing.md#the-link-to-the-nvidia-gpu)).
  When Linux powers the GPU off and on again (runtime PM), the ACPI
  power resource equalizes the link again the same way (patch 0084).
  Verified on a W541 with v1.3.7-rc2 (`mrc`): the GPU reports a full
  swing of 60, the link comes up at 8 GT/s x16 with all three
  equalization phases done, and no error is recorded on either end at
  8 GT/s, after 20 reclock cycles of nouveau, after a power-off and on of
  the GPU by Linux, or after a suspend and resume. The optional patch
  `test-peg-afe`, the AFE part alone, is gone.
- The firmware powers the GPU up with 100 ms from its power to the end of
  its reset and 100 ms after it, as the PCIe specifications want and as
  the ACPI power resource already did (10 and 50 ms before): 140 ms more
  at a boot that powers it up.

## v1.3.6

- coreboot and EDK2 moved to their upstream of October 2026 (coreboot
  `26.09-280-gacdbfd47295d`, 227 commits after the pin of v1.3.0; EDK2
  `9c0cb3a58343`). All the patches apply as they are. The read-only part
  on the laptops stays the one of v1.3.0: the slots of the new pin still
  read what it leaves in cache-as-RAM (vboot's shared data and nvdata, the
  early console, the timestamps, the FMAP and CBFS caches: same structs,
  same addresses), checked by hand and recorded as a `rw-ok` line in
  `configs/ro-interface.txt`, which `tools/ci-check.sh` and
  `tools/verify-rom.sh` accept. The update test in QEMU and the two
  variants pass on the new pin.
- The version in the ESRT and in the capsules is four bytes, X.Y.Z.R
  (fwupd's *quad* format): a release is X.Y.Z.0, its candidate N the
  release before with R = N (v1.3.7-rc2 is 1.3.6.2). Before, the
  candidates had the number of their release, so fwupd saw one version and
  offered neither a later rc nor the release after an rc. The setup page and
  `tools/update.py` show the tag (v1.3.7-rc2), `fwupdmgr` the four numbers;
  a W541 on v1.3.6-rc1 or older (X.Y.Z in the old layout, read as 1.3.0.6)
  updates to any of the new numbers as usual
  ([docs/update.md](docs/update.md#versions-variants-downgrades)), and the
  setup page and `tools/update.py` still show the old numbers by their tag
  (v1.3.5, not v1.3.1-rc5); `tools/update.py` still reads the `.cab` of
  those releases (format *triplet*). `tools/ci-check.sh` refuses a lowest
  supported version between v1.3.0 and v1.3.6, where the two layouts
  overlap. The *Go back to* of the setup and coreboot's check behind it
  (patches `edk2/0020` and 0065) read the version from the release name in
  the other slot in the same layout, `-rcN` included: in the old one, once
  the lowest supported version is raised, they would have refused a newer
  release (v1.3.7 read as `0x01030007`, below v1.3.6). The update test in
  QEMU numbers its ROMs so that a parser left on the old layout fails it.
- A testing remote for fwupd, `configs/fwupd/ourobios-testing.conf`, off
  until turned on (`fwupdmgr enable-remote ourobios-testing`): the metadata
  of the latest release, candidates included, from the assets of the fixed
  `testing` entry of the releases page, which every release replaces when
  it is the highest so far ([docs/update.md](docs/update.md#the-fwupd-remote)).
- Network boot: *iPXE Network Boot* in the boot menu (iPXE 2025.12 with its
  Intel driver, for the I217 of the W541, and nothing of EDK2's network
  stack: patches 0075 and `edk2/0022`), at the end of the boot order. PXE,
  HTTP and iPXE scripts; Ctrl-B at the banner for its shell.
- Legacy BIOS boot: *CSMWrap Legacy Boot* in the boot menu
  ([CSMWrap](https://github.com/CSMWrap/CSMWrap), the CSM and VGA BIOS of
  SeaBIOS as a UEFI application, built by `tools/build.sh prepare`:
  patches 0076 and `edk2/0023`), for what does not boot from UEFI, from
  SATA, NVMe and USB drives through SeaBIOS's own drivers; one logical
  processor stays with CSMWrap. While Secure Boot is on the entry goes,
  and the firmware refuses to start CSMWrap even from a `Boot####`,
  `BootNext` or `SysPrep####` written from the OS (a file of the firmware
  volume is not checked against the Secure Boot keys: patch `edk2/0025`,
  after v1.3.6-rc2).
- *General* → *Boot* in the setup turns each of the two off (patch 0077).
  The smoke test in QEMU starts both from the boot manager: iPXE gets its
  address from QEMU's DHCP, downloads a script over TFTP and runs it;
  CSMWrap boots the master boot record of a SATA disk. The payload's
  image in memory grows to 11 MiB (patch `edk2/0024`); each flash slot
  keeps about 215 KiB free with `mrc` and 148 KiB with `nri` (about 510
  and 443 before).
- A screen of its own for the firmware update (patch `edk2/0026`, after
  v1.3.6-rc3), instead of a white bar under the logo: the ouroboros of the
  logo lights up from its head around to its tail as the progress, and the
  bar under it is a map of the flash region being written, one column per
  4 KiB block (rewritten, already as in the capsule, still to do, the one
  being written). Around them the versions and the vboot slots, what is
  being done, the percentage, how much was rewritten and how much was
  already there, the time left, and what not to do; at the end the snake
  winks and the screen counts down to the reset; after a failure it shows
  the block that failed and that the slot in use was not touched.
  FmpDeviceSmmLib publishes what it writes for the screen; the text is
  Montserrat, as in the setup, which `tools/ui-font.py` turns into a compact
  font from the files of LvglPkg when the tree is prepared. The firmware
  that is running draws it: it shows from the update after the one that
  installs it. It takes about 18 KiB of each flash slot, measured between
  v1.3.6-rc3 and rc4: about 195 KiB stay free with `mrc` and 129 KiB with
  `nri`.
- Reproducible builds: the release build of each variant is built a second
  time from scratch in CI, CSMWrap and iPXE included, and compared bit by
  bit with the first (`tools/build.sh repro`). The build date was already
  the date of the commit; the payload now has no debug directory in its PE
  images (patch `edk2/0021`, `GenFw --zero`), whose CodeView entries named
  the `.dll` of each module with the absolute path of the build, 116 of
  them. With the same compilers (coreboot's cross toolchain; GCC and
  binutils of Ubuntu 24.04 for the payload, iPXE and CSMWrap, named in the
  `-layout.txt` of the releases after v1.3.6-rc2) the stages and the
  payload of a release can be rebuilt from its tag and compared; the whole
  ROM also needs the project's vboot key, which signs the slots.

## v1.3.5

- No more `thinkpad_acpi: acpi_evalf(\BLTH, vd, ...) failed: AE_NOT_FOUND`
  (and `\WGSV`) on the console at every shutdown and reboot: the two
  methods the driver calls to save the Bluetooth and WWAN state for S4/S5
  are in the DSDT now (patch 0067).
- A clean kernel log: no more *ACPI Warning: SystemIO range ... conflicts
  with OpRegion ... (\_SB.PCI0.GPLV)*, three times at every boot (the
  GPIO methods of Lynx Point's ASL, which no board uses, are gone: patch
  0068), and no more *ACPI: \: failed to evaluate _DSM ... (0x1001)* from
  iwlwifi (the cards behind the root ports have a device node, as on the
  OEM firmware: patch 0069).
- The USB ports described as the OEM firmware does (`_UPC`, `_PLD`): the
  OS knows which port is a connector and on which side, which carries the
  camera or the fingerprint reader, and which has nothing; the port devices
  of the Lynx Point-H xHCI were those of the -LP chipset (patches 0070,
  0071).
- Wake-on-LAN is possible: the Ethernet controller has its ACPI device
  with `_PRW`, and the Wi-Fi and WWAN root ports theirs, as on the OEM
  firmware (patch 0072). Nothing wakes the laptop unless the OS enables
  it (`ethtool -s enp0s25 wol g`).
- The battery trip point (`_BTP`, the `alarm` attribute of the battery in
  Linux), as on the OEM firmware (patch 0073).
- `_S3D` on the devices and `_RMV` on the WWAN and ExpressCard slots, as
  on the OEM firmware (patch 0074).

## v1.3.4

- Going back without an OS: the *Firmware Update* page of the setup shows
  the slot that runs and the release in the other one, and *Go back to*
  restarts into that release, which vboot tries at the next two boots and
  leaves if it does not boot, as `update.py rollback` does. The setup
  checks what a capsule would (not the release that runs, the same
  variant, not older than the oldest accepted update), and only the setup
  can do it: the payload locks the switch before it starts a boot option
  (an OS loader, the UEFI Shell) and at `ExitBootServices()`, coreboot on
  resume from suspend (patches 0065, `edk2/0020` and `lvglpkg/0015`,
  [docs/update.md](docs/update.md#from-the-setup)). What runs before the
  lock (a `Driver####` or `SysPrep####` option, an option ROM) gets the
  same checks from coreboot itself: the variant, and not older than the
  lowest supported version of the running release.
- An fwupd remote: the mrc release carries the metadata of both variants,
  signed by the capsule key (`ourobios.xml.gz`, `.jcat`), and
  `configs/fwupd/ourobios.conf` downloads it from the latest release, so
  that `fwupdmgr update`, GNOME Software and KDE Discover offer the
  releases (not the release candidates). It needs the project certificate
  in `/etc/pki/fwupd`, as the packages already did
  ([docs/update.md](docs/update.md#the-fwupd-remote)).
- The battery charge behaviour from Linux on the W541 too
  (`/sys/class/power_supply/BAT0/charge_behaviour`: `inhibit-charge`,
  `force-discharge`), as on the T440p (patch 0066, until v1.3.3 the
  optional `test-charge-behaviour`): the Lenovo ACPI tables of the two
  laptops declare the same embedded controller registers.
- The update test in QEMU goes back from the setup too, with the keys sent
  by QEMU, and checks that a boot option cannot switch slot, before or after
  `ExitBootServices()` (`tools/efi/slot-lock-test.c`). It also fills
  `RW_NVRAM` before a capsule, cuts the power halfway through a slot (vboot
  stays on the old one, the capsule staged again finishes it) and applies a
  capsule from a USB drive.

## v1.3.3

- EDK2 at MrChromebox's `0d39245e6`: writing a Secure Boot key from
  Linux (`sbctl enroll-keys`, `efi-updatevar`) no longer faults in the
  variable driver, which verifies authenticated variables outside SMM,
  and no longer takes the EFI runtime services down (CryptoPkg,
  `RuntimeFreeMem()`). The three commits before it load an Intel GOP
  driver and VBT from CBFS, which this firmware does not use: libgfxinit
  draws the screen.
- v1.3.3-rc1 is the same firmware with another version, tested on the
  W541: the capsule update from v1.3.2, suspend and resume. From it:
  `sudo python3 update.py stage --latest`.
- The smoke test of the build also checks the UEFI variables: in two
  boots of the emulated laptop the UEFI Shell writes a test variable, and
  it must be in SMMSTORE, then rewritten with the first copy deleted.
- The build tests the capsule update in QEMU before a release
  (`tools/build.sh update-test`, `tools/qemu-update.py`, a job beside the
  ROMs): three q35 images with vboot's two RW slots and its nvdata in flash,
  the EDK2 payload of these patches and capsules made as those of the
  releases. Each capsule must write only the slot that is not running;
  vboot tries it and the payload confirms it; the capsule of the release
  already in the other slot (`update.py rollback`) writes nothing to the
  slots; vboot goes back to the old slot when the new one does not verify
  or does not reach the payload; the ESRT is checked at every boot
  ([docs/vboot.md](docs/vboot.md#how-it-is-tested)).
- `tools/update.py status` adds a note when the version that runs is not
  the one of the last capsule, written with success: vboot went back to the
  other slot, or the flash was rewritten afterwards.

## v1.3.2

- The firmware is built from the same coreboot, EDK2, patches and blobs
  as v1.3.1; only its version changes. It takes a laptop on v1.3.2-rc1,
  which also had patch 0064, back to that code:
  `sudo python3 update.py stage --latest`.
- `tools/idle-report.py`: package and core C-states, RAPL and battery
  power and memory traffic at idle, and the power state of the devices
  that can keep the processor awake: ASPM, LTR and runtime PM of each PCI
  device, SATA link power management, USB autosuspend, graphics
  ([docs/flashing.md](docs/flashing.md#power-at-idle)).
- `tools/pm-regs.py`: the power management registers of processor,
  System Agent and PCH, as the firmware left them.
- `tools/update.py stage` goes from a release candidate to its release,
  or to a later candidate, without `--allow-older`.
- `tools/update.py rollback FLASH.bin`: back to the release in the slot
  that is not running, the one before the last update, with its signed
  capsule; the firmware rewrites nothing and only switches slot
  ([docs/update.md](docs/update.md#going-back)).
- The build boots the EDK2 payload of each variant in QEMU before a
  release (`tools/build.sh smoke`, `tools/qemu-smoke.py`): it must open
  the setup and answer the keys.
- Docs: the boot menu timeout is set in the setup menu, *Boot Manager* →
  *Auto Boot Time-out*; NVIDIA's own driver never powers this GPU down;
  where the boot time goes; a SATA link that never sleeps keeps the
  processor out of the package C-states below PC2, about 7 W at idle
  ([docs/flashing.md](docs/flashing.md#power-at-idle)). v1.3.2-rc1 also
  asked for the maximum ratio of the processor before `mrc.bin` (patch
  0064): the processor stayed at 800 MHz, and the patch is gone.

## v1.3.1

- VT-d: the remapping engine of the devices other than the graphics now
  handles the 2 MiB and 1 GiB pages it reports (patch 0063). Up to
  v1.3.0, with `intel_iommu=on`, Linux 7.2 used them for SATA transfers,
  which faulted and read back zeros (`csum failed` on btrfs); with those
  releases use `intel_iommu=on,sp_off` or `iommu=pt`.
- TPM 1.2: one TCPA table, coreboot's, with the events EDK2 measures
  (patch edk2/0019), so Linux reads the whole event log.
- The build checks that the RW slots still fit the read-only part that
  is already on the laptops.

## v1.3.0

- Verified boot with two RW slots: a capsule writes the slot that is not
  running and tries it, and vboot goes back to the other one if the new
  one does not verify or does not boot ([docs/vboot.md](docs/vboot.md)).
  *Firmware protection* (*Security*) write-protects the read-only part at
  every boot. From v1.2.x the move is one write with flashrom.
- The firmware is named ouroBIOS, with its logo in the setup menu and on
  the boot splash.
- The ESRT reports the result of the last update (patch edk2/0018).
- verstage reads the real sleep state (patch 0058): before, it could take
  a cold boot for a resume from S3 and keep the slot of the last boot
  instead of trying a new one.
- With *Intel Management Engine* disabled, the ME's PCI interface is
  hidden also when the ME is reduced by me_cleaner (patch 0059); the HD
  audio of the NVIDIA GPU gets its interrupt (patch 0060); the flash size
  is read right from the descriptor (patches 0061-0062).
- `tools/update.py`: `vboot`, `vboot-work` and `vars`.
