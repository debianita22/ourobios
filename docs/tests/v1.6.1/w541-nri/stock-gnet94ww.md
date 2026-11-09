# The Lenovo firmware of the W541 (GNET94WW), read for v1.6.1

Read-only notes from the BIOS image of Lenovo's `gnuj39us.iso` (2.42), made on
2026-11-08 to guide patches 0246-0261; nothing of the image was run or
copied into the project. Sections 1-4: watchdog, I/O Port Access, RTC
power loss, Hyper-Threading; 5-7: Wake on LAN, the EC's CPU limits, the
HKEY queue; 8: the hard disk password at S3 resume.

## Reproduction

```
D=/home/domenico/ourobios-test-v1.6.0/stock; cd $D
curl -sSfL -o gnuj39us.iso https://download.lenovo.com/pccbbs/mobiles/gnuj39us.iso; sha256sum gnuj39us.iso
dd if=gnuj39us.iso of=hdd.img bs=2048 skip=27; mkdir disk; 7z x -odisk hdd.img
python3 -m venv venv; venv/bin/pip install uefi-firmware capstone
mkdir fw; cp 'disk/FLASH/GNET94WW/$01E2000.FL1' fw/bios.fl1
venv/bin/python -I venv/bin/uefi-firmware-parser --brute -e -O fw/bios.fl1
cd fw; python3 -I ../tools/flat.py bios.fl1_output mods > ../modules.tsv
for f in mods/*; do ../venv/bin/python -I ../tools/dis.py $f > dis/$(basename $f).s; done
python3 -I ../tools/ifr.py mods/LenovoSetupSecurityDxe_6a7b1c86.pe > ../ifr_security.txt
```

The ISO holds an El Torito hard-disk image (catalog at sector 20, image
at 27). Phoenix SCT over Intel's Lynx Point/Haswell reference code:
Lenovo DXE copies `LenovoConfig`/`LenovoSecurityConfig` into Intel's
`*SetupVar`, Phoenix PEI turns them into policy PPIs.

## 1. Watchdog (PMBASE + 0x54), high confidence

Only `WdtPeim` and `WdtDxe` (stock Intel) touch it; no SMM part.

- WdtPeim, every boot: reads it; EN set → records "active" and the
  timeout in a HOB, does not clear EN. Bits 24/25 set (reset by the
  watchdog) → sets bit 23 (failure), clears bit 22, write-1-clears 24/25.
  Else, bit 22 set (unexpected reset while armed) and not an S3/S4 wake →
  `ReloadAndStart(1)` and a dead loop (a forced 1 s watchdog reset). Else
  clears 23 and 24/25. Installs a reset callback that clears bits 22 and
  15 before every reset through PchResetPeim. EndOfPei on S3 only:
  re-arms with max(saved, 10 s) if it was running, else disables.
- Bit 12 (LCK) is never set anywhere.
- Armed on a normal boot: never. CpuInitPeim/SaInitPeim arm 60 or 8 s
  only around an overclocking change; PchMeUma 2 s with CF9 0x0E for an
  ME cold reset. The MRC does not use it.
- Stopped: PlatformStage2Pei, EndOfPei notify, `Disable()` at every boot
  (clears EN, FORCE_ALL, bit 22). WdtDxe at ExitBootServices: arms with
  bits 21:16 × 16 s if non-zero (OS hand-off), else disables.
- The code expects EN, the timeout and the status bits to survive
  non-G3 resets.

## 2. I/O Port Access

`LenovoSecurityConfig` offsets (0 = off; Thunderbolt off = 3): Ethernet
0x15, WLAN 0x16, WWAN 0x18, Bluetooth 0x19, USB 0x1b, ExpressCard 0x1d,
Ultrabay 0x1e, Memory card 0x20, Smart card 0x21, Camera 0x22,
Microphone 0x23, Fingerprint 0x24, NFC 0x30, Thunderbolt 0x33.

- Ethernet (high): PchInitPeim. Nothing if BUC (RCBA+0x3414) bit 5
  already matches; FDSW (0x3420) bit 7 locked → global reset. On: clears
  bit 5 only if a GbE flash region exists. Off: sets it, a reset only if
  the GbE firmware-valid bit is set (MBARA+0x5B54 bit 15). Reset: power
  cycle if FD2 bit 1, else global reset (ETR3 0xAC bit 20 CF9GR, then
  CF9 = 0x0E). FD is not used for the LAN.
- WLAN, ExpressCard (medium): root ports disabled through FD
  (RCBA+0x3418 bit 16+n) in PchInitDxe, with an S3 boot-script entry.
- USB devices: USB2PDO (xHCI 0xE4), USB3PDO (0xE8), EHCI 0x64, only with
  "USB Per-Port Disable Control" (PchProtocolSetupVar 0x13) on, default
  not traced. USB2 ports (0-based): WWAN 5, Bluetooth 12, USB switch
  0/1/2/4/9, smart card 8, camera 13, fingerprint 10.
- Memory card (high, Realtek variant): DxeRealtekCrcInit, root port left
  on; internal registers of the reader through its config register 0xE8
  (bit 31 busy, bit 30 write, address, mask, data), replayed on S3:
  0xFF03 |= 0x40, 0xFE75 = 0xF1, 0xFE76 = 0xFF, 0xFE5B |= 0x08. The O2
  Micro variant (this unit's reader) not analysed.
- Microphone (high): PchConfigDxe patches the ALC3232 verb table: the
  coefficient write `0x02050005, 0x0204FF1F` becomes `0x0204CF1F`
  (coefficient 0x05, bits 13:12 cleared). Pin configs untouched.
- NFC: a board GPIO (medium). Thunderbolt: not analysed.

## 3. RTC power loss

- Nothing resets the Setup variables on RTC_PWR_STS. The bit only
  re-initialises the RTC (PchInitPeim: divider reset; PlatformStage2Pei:
  B=0x82, A=0x26, D=0, B=0x02, century 0x32 = 0). VRT read, ignored.
- "0251 Checksum bad": DxeCmosInit, a checksum over CMOS 0x10-0x2d
  (word at 0x2e); on mismatch only CMOS bytes go to defaults (signature
  0x79 = 0x5A, CRC16 at 0x9e/0x9f). Invalid century/year → 2001-01-01,
  error 0271.
- RTC_PWR_STS cleared in PchInitDxe (`and 0xA4, 0xFB`, which also clears
  PWR_FLR). GEN_PMCON_LOCK |= 0x06 (ABASE_LK, SLP_STR_POL_LOCK) in
  PchInitDxe, with an S3 boot-script entry; nothing locks bit 2.

## 4. Hyper-Threading (high)

- LenovoConfig 0x21 → CpuProtocolSetupVar[0] → CPU policy bit 1.
- CpuInitPeim, on PchInitPpi: reads the strap (SOFT_RESET_DATA only if
  SOFT_RESET_CTRL bit 0 is set, else 0). If CPUID 0xB reports more than
  one thread and strap bit 0 differs: writes SOFT_RESET_DATA, sets
  SOFT_RESET_CTRL bit 0, sets SOFT_RESET_LOCK (0x38F0) bit 0, cold reset
  (CF9 0x02 then 0x06). Same callback: active cores (bits 2:1), BIST
  (bit 5), flex ratio (11:6). Unchanged: locks SOFT_RESET_LOCK.
  PchInitDxe locks it again with an S3 boot-script entry. No boot-mode
  check.

## Open

Thunderbolt, the O2 Micro reader, the default of USB Per-Port Disable
Control, the consumer of "Use Watchdog Timer for ICC" (Setup 0x66), the
order of the two EndOfPei notifies on S3. The USB2 port numbers of
section 2 do not match the xHCI ports of the W541 under Linux (Bluetooth
11, camera 12, 1-based) by one offset for all: the fingerprint port
stays to be measured on a unit that has the reader.

```text
GNET94WW (ThinkPad W541 BIOS 2.42): findings, part 2
=====================================================

Read-only analysis of the same image as findings.md (fw/bios.fl1), 2026-11-08.
Nothing from the image was executed. Sections 1-4 are in findings.md.
RVAs are relative to the module image (fw/img/<module>.img, image base 0).

Commands used (from /home/domenico/ourobios-test-v1.6.0/stock)
--------------------------------------------------------------

  # ACPI tables: scan every extracted file for tables with a valid length and
  # checksum, write the unique ones to acpi/ (one DSDT, 24 SSDTs, a FACS)
  python3 -I tools/acpiscan.py fw/bios.fl1_output acpi
  cd acpi
  iasl -e SSDT_*.aml -d DSDT_TP_GN_5d80fa3fbb.aml
  for f in SSDT_*.aml; do iasl -e DSDT_TP_GN_5d80fa3fbb.aml -d $f; done
  cd ..
  # byte.bit offsets of every field of an OperationRegion
  python3 -I tools/aslfields.py acpi/DSDT_TP_GN_5d80fa3fbb.dsl ECOR > acpi/ecor_offsets.txt
  python3 -I tools/aslfields.py acpi/DSDT_TP_GN_5d80fa3fbb.dsl MNVS > acpi/mnvs_offsets.txt
  python3 -I tools/aslfields.py acpi/DSDT_TP_GN_5d80fa3fbb.dsl GNVS
  # disassembly from an exact RVA (the linear fw/dis/*.s are misaligned
  # after data in places)
  venv/bin/python -I tools/disat.py fw/img/BoardInfoSmm_0770e7a0.pe.img d90 f38
  # GUID / string searches
  python3 -I tools/gfind.py fw/mods u:LenovoConfig g:b8167809-e73a-4387-8323-0afe83d3074f
  grep -n 'Wake On LAN' ifr_config.txt

The FADT template (raw, in the same FV as the DSDT) gives SMI_CMD 0xB2,
ACPI_ENABLE 0xF2, ACPI_DISABLE 0xF1, PM1a_EVT 0x1800, GPE0_BLK 0x1820 with
length 16 (so GPE n = bit n of the 64-bit GPE0_STS/EN at 0x1820/0x1828;
GPE 0x0D = PME_B0, GPE 0x23 = bit 35 = GPIO27).

ASL SMI interface (used by sections 5 and 6): \SMI(cmd, p0..p3) writes MNVS
0xFC0 CMD, 0xFC1 ERR=1, 0xFC5.. PAR0..PAR3 and writes 0xF5 to port 0xB2.
The only SW SMI 0xF5 handler is SmmAslSmi (c3ee3ef0-63e6-4f59-a437-
afa63c46c835), RVA 0x10e0: if CMD < 0x16 it calls the pointer table at
RVA 0x310 [CMD], then clears ERR. Other modules may install entries < 0x14
through protocol b8167809-e73a-4387-8323-0afe83d3074f (Register RVA 0x1014);
the only user is LenovoSetupUnderOsSmm, which installs CMD 0x10 (WMIS).
Table entries for CMD 0x04 (\STEP) and CMD 0x12 (\AWON) are RVA 0x24a4 =
"xor eax,eax; ret": both SMIs do nothing in this firmware.


```

## 5. Wake on LAN

```text

Setup option
  ifr_config.txt, form "Network": ONEOF "Wake On LAN" qid 0x64,
  var LenovoConfig offset 0x00, size 1: 0 Disabled, 1 AC Only,
  2 AC and Battery. Hidden Intel options in PchProtocolSetupVar: 0x1AC
  "Wake on PCH LAN" (WoL in Moff), 0x1AB (PME_B0_S5_DIS, suppressed),
  0x1AD "GP27 Wake From DeepSx".

Boot (DXE), high confidence
  1. LenovoSecurityVariableDxe (06de824a), RVA 0x983-0x9b1: reads
     LenovoConfig (0x90 bytes) and sets PchProtocolSetupVar[0x1AC] =
     (LenovoConfig[0] != 0), saving the variable if it changed. So "Wake On
     LAN" != Disabled turns on Intel's WolEnableOverride policy.
  2. PchConfigDxe (9fa2f805), RVA 0x2aa1-0x2ade: PCH PM policy byte 1
     (WakeConfig): bit0 = Setup[0x1AB], bit1 = Setup[0x1AC], bit2 =
     Setup[0x1AD], bit3 = 0.
  3. PchInitDxe (de23acee), RVA 0x43cc-0x4472 (Intel RC):
     GEN_PMCON_3 (D31:F0 0xA4, 16 bit): bits 15 and 13 cleared, bit 15
     (PME_B0_S5_DIS) set and written only if policy bit0.
     If WolEnableOverride: D31:F0 0xA2 (16 bit) = (x & 0x9FFF) | 0x1800, then
     GEN_PMCON_3 |= 0x2000 (bit 13, WOL_EN_OVRD).
     Else: 0xA2 = (x & 0xE7FF) | 0x6000, GEN_PMCON_3 &= ~0x2000.
     (The names of 0xA2 bits 14:11 are not known here; values as read.)
  No module programs the GbE WUC (MBARA+0x5800) or WUFC (+0x5808) at boot
  (searched all modules except the UNDI driver LanUefi). The EC RAM is not
  used for WoL.

Sleep entry, Lenovo part (SMM), high confidence
  SmmSleepEvent (e8dc00ba-411f-4d52-b925-50785436ac81) registers Sx
  dispatch handlers (protocol 14fc52be-...): S3 RVA 0xf60, S4 0xd80,
  S5 0xcf8, and SW SMI 0xD0 RVA 0x10dc. Protocols it uses:
    0x1d48 = EC RAM access (aade7c97-..., EcIoSmm; +0 read(off), +8 write)
    0x1d90 = PMH7 access (98840739-d6df-4564-8b9f-cddea3dc32e9, installed
             by MiscGaIoSmm): read = out 0x15EC idx, in 0x15EE; write = out
             0x15EC idx, out 0x15EE val. This is the PMH7 of coreboot's
             src/ec/lenovo/pmh7 (index 0x15EC, data 0x15EE; the DSDT calls
             it IMGA/GAIX/GADT). The stock code does not write 0x15ED.
    0x1d60 = board protocol (f67fee3a-dbe2-4228-9732-b4dd1e5ff6af,
             BoardInfoSmm 0770e7a0), interface at RVA 0x1a20.
    0x1d58 = MNVS base (TpAcpiNvs protocol e6f014ab-...).

  WoL routine, SmmSleepEvent RVA 0x1348 (cl = 3, 4 or 5):
    S5 (RVA 0x12c0): w = LenovoConfig[0]; mask = GetWakeStatus(NPME, NULL,
       &mask). w is used whatever the OS did.
    S3/S4 (RVA 0x121c): GetWakeStatus(NPME, &gbe, &mask); w = gbe ?
       LenovoConfig[0] : 0. So in S3/S4 the setting applies only if the OS
       armed the wake.
    NPME = MNVS 0xD1A bit 4, set by \_SB.PCI0._OSC when the OS takes native
    PCIe PME control.
    BoardInfoSmm GetWakeStatus, RVA 0xdbc:
      NPME set:  gbe = !(PM1_EN bit 14 PCIEXP_WAKE_DIS) (in16 0x1802);
                 mask bit n = root port n (table RVA 0x280, wake-capable:
                 RP2 and RP3 only) with RTCTL (cfg 0x5C) bit 3 set.
      NPME clear: gbe = (GbE PMCSR D25:F0 0xCC bit 8 PME_En) AND
                 (in16 0x182C bit 3 = GPE0_EN bit 35, GPIO27_EN); mask bit n
                 = root port PMCSR (0xA4) bit 8 and its GPE0_EN-high bit
                 (table byte 1; 0xFF for all ports here, so 0).
    Then SetLanWake(enable = (w != 0), mask), BoardInfoSmm RVA 0x1168:
      a. per wake-capable root port: callback(mask bit) (RP2/RP3: no-op;
         port 4 would set PMH7 0x41 bit 3, RVA 0x1000; not present).
      b. RVA 0x1038:
         GEN_PMCON_3 (D31:F0 0xA4, 16 bit) &= 0xDEFF; if enable |= 0x2100
           -> bit 13 WOL_EN_OVRD and bit 8 (SLP_LAN# default value per the
              6/7/8-series datasheets; name not verified for LPT-H here)
         GP_LVL (GPIOBASE 0x800 + 0x0C, 32 bit) bit 29 = enable
           (GPIO29 = SLP_LAN#; only has an effect if GPIO29 is in GPIO
            mode; coreboot's W541 gpio.c, from the stock state, leaves it
            native)
      c. PM1_EN (0x1802, 16 bit): bit 14 PCIEXP_WAKE_DIS = !(enable || mask)
    Back in SmmSleepEvent:
      PMH7 reg 0x41: bit 1 = (w == 1)   ("AC Only")
      PMH7 reg 0x26: bit 2 cleared
    "AC and Battery" therefore differs from "AC Only" only by PMH7 0x41
    bit 1; the cut-off on battery is done by the PMH7/EC hardware, not by
    the BIOS (nothing runs at an AC change in S5). No H8 EC RAM bit is
    involved.

  Order in the S5 handler (RVA 0xcf8):
    1. GetVariable LenovoSystemConfig (0x34 bytes); if byte 0 == 0: RVA
       0x13f4(5) = Always On USB: EC 0x0D bit 0 = (LenovoConfig[6]==1),
       EC 0x02 bit 3 = !(LenovoConfig[6]==1 && LenovoConfig[7]==1).
    2. WoL routine (above).
    3. RVA 0x11e8 (protocol fe2965bb-... +0x10) and protocol
       95924e18-... +0 (LenovoSmmKbdConfig / SmmCf9Trap): not analysed.
    4. EC reads 0x4E, 0x4F (HWAK, wake cause).
    5. RVA 0x1150(5): unless CpuProtocolSetupVar byte 0 == 1, Deep Sx off:
       S3: RCBA+0x3328 &= ~3; S4: RCBA+0x332C &= ~3; S5: RCBA+0x3330 &=
       0xFFFF3FFF; always RCBA+0x3334 bit 0 (GP27 pin) cleared.
  S3 (0xf60) and S4 (0xd80) do the same WoL routine with type 3/4 (S3 also
  clears GPIO10 level through BoardInfo +0x20, sets EC LED 0x0C = 0x87,
  0xA0, 0xAA, clears PM1_STS bit 14 if set). SW SMI 0xD0 (0x10dc) sets
  PM1_CNT SCI_EN and restores the Deep Sx bits.

Sleep entry, Intel RC part (SMM), medium-high confidence
  PchSmiDispatcher (b0d6ed53-b844-43f5-bd2f-61095264e77e), Sx callback RVA
  0x4f70: for SLP_TYP S3/S4/S5 it calls RVA 0x46fc (GbE Sx handler); then,
  if RCBA+0x3334 bit 0 (GP27 DeepSx wake), sets GPE0_EN bit 35 (in32
  ABASE+0x2C |= 8; LPT-LP: ABASE+0x9C |= 0x10000).
  GbE Sx handler 0x46fc, runs only if GbE enabled (BUC RCBA+0x3414 bit 5 =
  0), in D0 (PMCSR 0xCC bits 1:0 = 0) and MAC WUC (MBARA+0x5800) bit 0 APME
  set (APM wake, normally from the GbE NVM):
    - EXTCNF_CTRL (MBARA+0xF00) |= 0x20, poll for bit 5 (SW flag), 4000x50us
    - if FWSM (MBARA+0x5B54) bit 15 FW_VALID is clear (ME not handling it):
      PHY_CTRL (0xF10) bit 1 = PHY_CTRL bit 2; MDIC (MBARA+0x20) writes to
      PHY 1: reg 31 = 0 (page 0), reg 25 (HV_OEM_BITS) = 0x0400 |
      0x40 if PHY_CTRL bit 3 | 0x04 if PHY_CTRL bit 2
    - MDIC: reg 31 = 0x6400 (page 800, wake-up registers); PHY_CTRL |= 0x40
      (GbE disable in Sx); via reg 17 (address) / 18 (data): 0x10 = RAL0
      bits 15:0 (MBARA+0x5400), 0x11 = RAL0 bits 31:16, 0x12 = RAH0 bits
      15:0 (0x5404), 0x13 = 0x8000 (valid); 0x01 (PHY WUC) |= 1 (read-
      modify-write); reg 31 = 0x6460, reg 17 = 0x42; reg 31 = 0x6020 (page
      769), reg 17 read and written back | 0x10 (host wake-up bit)
    - EXTCNF_CTRL &= ~0x20; GPE0_STS PME_B0 (bit 13) write-1-cleared.
  It is what Linux e1000e does itself on suspend/shutdown with "wol g"
  (e1000_init_phy_wakeup / OEM bits); the firmware copy only matters when
  the OS left APM set without programming the PHY.

ACPI (stock DSDT), high confidence
  Device IGBE (_ADR 0x00190000): _S3D 3, _PRW {0x0D, 0x04}: PME_B0,
  deepest S4. No _L0D method (implicit notify). Not wake from S5 for the
  OS, hence WOL_EN_OVRD. _PTS(4) and _PTS(5) call \AWON(4/5), _WAK(3) calls
  \AWON(0): SMI CMD 0x12, a no-op (see top). _PTS(>=4) clears EC HWLB
  (0x32 bit 1), _PTS(>=3) sets HCMU (0x3A bit 0), _WAK clears it.

Sequence for coreboot (lynxpoint + W541)
  At boot (ramstage):
    - GEN_PMCON_3 bit 13 WOL_EN_OVRD = (wake_on_lan != 0) (as stock DXE).
    - Leave Deep Sx disabled (RCBA 0x3328/0x332C bits 1:0, 0x3330 bits
      15:14, 0x3334 bit 0 = 0); coreboot lynxpoint does not enable it.
    - Keep GLAN _PRW (0x0D, 4) as now.
  In mainboard_smi_sleep(slp_typ) for S3/S4/S5:
    1. w = option (0 off, 1 AC only, 2 AC and battery).
    2. S3/S4: if the OS did not arm the GbE (stock test above; a simpler
       equivalent is D25:F0 PMCSR 0xCC bit 8 PME_En == 0), w = 0. S5: keep w.
    3. GEN_PMCON_3 (16 bit) &= ~0x2100; if w: |= 0x2100 (bits 8 and 13).
    4. GPIOBASE+0x0C bit 29 = (w != 0) (harmless if GPIO29 is native).
    5. PM1_EN bit 14 PCIEXP_WAKE_DIS = !(w || root-port wake armed). Note:
       clearing it also lets PCIe WAKE# of other ports wake the machine.
    6. pmh7: reg 0x41 bit 1 = (w == 1); reg 0x26 bit 2 = 0.
    7. Deep Sx off (as step above) and, optionally, the Intel GbE PHY
       sequence (only needed for APM/NVM wake without an OS driver).
  Expect the OS (e1000e) to program MAC/PHY WUC/WUFC itself.


```

## 6. EC CPU limits (0x48, 0x49, 0x5B) and NVIDIA power steering

```text

EC fields (stock ECOR, offset.bit): CALM 0x0D.4; HFSP 0x2F; HWLB 0x32.1;
PIBS 0x34.3; HPLO 0x34.7; HB0S 0x38 bits 6:0, HB0A 0x38.7; HB1S 0x39 bits
6:0, HB1A 0x39.7; HCMU 0x3A.0; HPAC 0x46.4; HWAK 0x4E (16 bit); TSL0..TSL3
0x88..0x8B bits 6:0; PLSL 0xBB; PLMS 0xBC; PLLS 0xBD; PLTU 0xBE; ATMX 0xC8;
HWAT 0xC9; FQ5B 0xFF.0; OCPF 0xFF.5; PSFG 0xFF.6. Full list in
acpi/ecor_offsets.txt.
NVS: PWRS GNVS 0x0F, PPCM GNVS 0x2C (unused by these paths), PPMF GNVS
0x2D (32 bit); MNVS: TCFA 0xD5C bits 3:0, TCFD 0xD5D bits 3:0, PPCR 0xDBD,
PPCA 0xDCF, OSPX 0xDF6.0, OSC4 0xDF6.1, CPPX 0xDF6.2, SPEN 0xDF7.0, GFPL
0xDF7.2, TDNV 0xDF7.7, FTPS 0xDF8, LPST 0xDFA, LWST 0xDFB, DGTP/XECU/CPUC
0xEE9 bits 0/1/2.

ASL bodies (DSDT lines 5155, 5241, 5258), high confidence
  Method (_Q5B) {
      If (\OSPX || \CPPX) { \PNTF (0x80) } Else { \STEP (0x04) }
      \_SB.PCI0.LPC.EC.FQ5B = 0x01          // EC 0xFF bit 0 = 1
  }
  Method (_Q48) {
      If (\PPMF & 0x01) {
          If (\OSPX || \CPPX) { \PNTF (0x80) } Else { \STEP (0x04) }
          \_SB.PCI0.LPC.EC.CALM = 0x01      // EC 0x0D bit 4 = 1
      }
  }
  Method (_Q49) {
      If (\PPMF & 0x01) {
          If (\OSPX || \CPPX) { \PNTF (0x80) } Else { \STEP (0x05) }
      }                                      // no write-back
  }
  (FQ5B and CALM are single-bit fields of a ByteAcc/Preserve region: the
  ASL does a read-modify-write of the whole byte.)

PNTF (DSDT line 104)
  If (Arg0 == 0x80 && !OSPX): Notify (\_SB.PCCD, 0x82) only if PPMF bit 0
  and CPPX; no CPU notify. ElseIf (PPMF & 0x200): Notify (\_PR.CPUn, Arg0)
  for each CPU whose PDCn has bit 3 (for 0x80/0x82) or bit 4 (for 0x81).
  Else Notify (\_PR.CPU0, Arg0). So a _PPC re-evaluation (Notify 0x80)
  reaches the CPUs only with OSPX = 1.
  OSPX is set only by SW SMI 0xF3 (PowerMgmtS3 8f0b5301, handler RVA
  0xd04, "or byte [MNVS+0xDF6], 1"; 0xF4 sets OSC4). Nothing in the ASL or
  in the other modules issues 0xF3 (presumably Lenovo's Windows software
  does). CPPX = 1 only from \_SB._OSC with CPPC capability when
  \_SB.PCCD.PENB == 1 (CPPC SSDT, _STA only for "Windows 2012"). Under
  Linux both are expected to be 0, so _Q48/_Q49/_Q5B end in \STEP, which
  is a no-op SMI (see top), plus the ack writes.

_PPC (SSDT Cpu0Ist, \_PR.CPU0; CPU1-7 return CPU0._PPC), in order
  1. Local0 = EC.LPMD():
       AC (HPAC 0x46.4) and HPLO (0x34.7): LPST.
       AC and HWAT (0xC9, adapter watts) < 90 (0x5A) and, for each battery,
       it is absent (HBnA = 0) or (HBnS bit 4 set or HBnS bits 2:0 < 2):
       LPST. Otherwise 0. (Without H8DR the same through RBEC 0x46, 0x34,
       0xC9, 0x38, 0x39.)
  2. If 0: thermal: (AC and TCFA) or (DC and TCFD): if TSL0 (0x88) & 0x76
     -> LWST; else if TSL0 & 0x77 -> LWST.
  3. If still 0: if PPCA or FTPS: max(PPCA, FTPS) (PPCA from HKEY.MHCT,
     FTPS from MHAT).
  4. If (GFPL && !Local0) || (!GFPL && Local0): wait for PIBS (0x34.3) = 0
     up to 1000 ms (timeout: PPCR = Local0, return). Then:
       limiting (Local0 != 0, GFPL 0 -> 1): PLSL = 4, PLTU = 1, PLLS = 0x0D,
         PLMS = 0
       release (GFPL 1 -> 0): PLSL = 4, PLTU = MTAU or 0x1C, PLLS = PL1L,
         PLMS = PL1M
     (the EC applies a CPU power limit itself from these registers).
  5. If PSFG (EC 0xFF bit 6, NVIDIA power steering active):
       if VIGD && !VDSC: unchanged; elif TDNV (dGPU in D0, set by
       PEG.VID._PS0, cleared by _PS3): DGTP ? (CPUC ? 5 : LPST) :
       XECU ? LPST : CPUC ? 2 : 5.
  6. PPCR = Local0, return Local0.
  NVIDIA GPS _DSM (\_SB.PCI0.PEG.VID.NVPS): function 0x21 returns
  \_PR.CPU0._PSS, 0x22 stores Arg3 byte 0 in VID.CPPC and calls PNTF(0x80),
  0x23 returns CPPC. VID.CPPC is not read by _PPC (dead store), and the
  _PDC's "\_PR.CPU0._PPC = CPPC" refers to \_PR.CPPC, another object.
  So _Q5B's effect is through PSFG in step 5.
  AC events _Q26/_Q27: PWRS = 1/0, PNTF(0x80) if PPMF bit 0 and (OSPX ||
  CPPX), PNTF(0x81) if OSC4, MHKQ(0x6040), ATMC.

OCPF (EC 0xFF bit 5)
  Set by the ACPI-enable SMI (SW SMI 0xF2, PlatformSmm cb73c3d9 handler
  RVA 0x1af8, at 0x1d6f: read EC 0xFF, |= 0x20, write; same handler routes
  GPIO1 in GPIO_ROUT and clears ALT_GP_SMI_EN bit 1), by _WAK(3)/_WAK(4),
  cleared by _PTS. Name and EC meaning not known; coreboot does not touch
  EC 0xFF at all. The EC may gate these events on it (not verifiable).

Does the EC need the ack?
  SMM: no. \STEP (CMD 4) is a no-op and no SMM module reads or writes EC
  0x0D bit 4 or 0xFF bit 0 (the only EC 0xFF access in SMM is the OCPF set
  above). The ack is the ASL's EC RAM write only.
  EC: what the EC does without the ack is in the EC firmware (inside
  EcFwUpdateDxe, H8S code, not analysed), so whether 0x48/0x5B repeat
  cannot be shown from this image. Note the asymmetry: 0x5B is always
  acked (FQ5B), 0x48 only when PPMF bit 0 (EIST on), 0x49 never. A safe
  coreboot choice is to do the same writes (CALM = 1 in _Q48, FQ5B = 1 in
  _Q5B) even if the _PPC part is not implemented.


```

## 7. HKEY event queue

```text

Storage (Device HKEY, _HID LEN0068, DSDT line 5666), high confidence
  Integers, one slot per event class, the last event of a class wins:
    DHKH  0x1xxx and 0x5xxx (shared slot!)
    DHKW  0x2xxx
    DHKS  0x3xxx
    DHKD  0x4xxx
    DHKT  0x6xxx
    DHWW  0x7xxx
  Events < 0x1000 or >= 0x8000 are dropped. Other names: DHKC (hotkey
  control, MHKC), DHKB (queue enable, MHKE, initial 1), DHKN (hotkey mask,
  initial 0x0808), Mutex XDHK (sync 7), MHKV returns 0x0100, MHKA returns
  0xFFFFFFFB. No other ASL writes the slots.

  Method (MHKQ, 1)
  {
      If (DHKB) {
          If (DHKC) {
              Acquire (XDHK, 0xFFFF)
              If (Arg0 < 0x1000) {}
              ElseIf (Arg0 < 0x2000) { DHKH = Arg0 }
              ElseIf (Arg0 < 0x3000) { DHKW = Arg0 }
              ElseIf (Arg0 < 0x4000) { DHKS = Arg0 }
              ElseIf (Arg0 < 0x5000) { DHKD = Arg0 }
              ElseIf (Arg0 < 0x6000) { DHKH = Arg0 }
              ElseIf (Arg0 < 0x7000) { DHKT = Arg0 }
              ElseIf (Arg0 < 0x8000) { DHWW = Arg0 }
              Else {}
              Release (XDHK)
              Notify (HKEY, 0x80)
          } ElseIf (Arg0 == 0x1004) {
              Notify (\_SB.SLPB, 0x80)      // Fn+F4 without a hotkey driver
          }
      }
  }

  Method (MHKP, 0)                          // pop, fixed priority
  {
      Acquire (XDHK, 0xFFFF)
      If (DHWW)     { Local1 = DHWW  DHWW = Zero }
      ElseIf (DHKW) { Local1 = DHKW  DHKW = Zero }
      ElseIf (DHKD) { Local1 = DHKD  DHKD = Zero }
      ElseIf (DHKS) { Local1 = DHKS  DHKS = Zero }
      ElseIf (DHKT) { Local1 = DHKT  DHKT = Zero }
      Else          { Local1 = DHKH  DHKH = Zero }
      Release (XDHK)
      Return (Local1)                       // 0 when empty
  }

  Method (MHKE, 1)                          // _PTS: MHKE(0), _WAK: MHKE(1)
  {
      DHKB = Arg0
      Acquire (XDHK, 0xFFFF)
      DHKH = Zero  DHKW = Zero  DHKS = Zero
      DHKD = Zero  DHKT = Zero  DHWW = Zero
      Release (XDHK)
  }

  MHKC(Arg0): DHKC = Arg0 (nothing else).
  MHKK(Arg0): Return (DHKC ? (DHKN & Arg0) : 0); the _Qxx hotkeys call
    MHKK(1 << (n-1)) before MHKQ(0x1000 + n).
  MHKM(Arg0, Arg1): under XDHK, if Arg0 <= 0x20: Local0 = 1 << (Arg0-1);
    if Local0 & 0xFFFFFFFB (bit 2 cannot be changed): set or clear it in
    DHKN.
  thinkpad_acpi calls MHKP in a loop on each Notify(HKEY, 0x80) until it
  returns 0, so all classes pending at that moment are delivered; two
  events of the same class before the OS runs keep only the last one.
  Event codes the DSDT queues: 0x1001-0x1020 (hotkeys), 0x3003, 0x3006,
  0x4010/0x4011 (dock), 0x5001/0x5002 (lid), 0x6000, 0x6001, 0x6005, 0x6011,
  0x6012, 0x6022, 0x6030, 0x6040, 0x6050, 0x6060, 0x6070, 0x6080, 0x60D0,
  0x7000. No 0x2xxx is queued by this DSDT (the slot exists).

  coreboot today (src/ec/lenovo/h8/acpi/thinkpad.asl): one slot BTN (RHK
  stores 0x1000+n, RHKX stores any code) plus BTAB (tablet, returned
  +0x5000); a second event before MHKP replaces the first. To reproduce
  the stock behaviour: replace BTN with the six slots above, make
  RHK/RHKX store by class as MHKQ does (keeping the EMSK/EN checks), make
  MHKP pop in the order DHWW, DHKW, DHKD, DHKS, DHKT, DHKH, and clear all
  slots in _PTS/_WAK as MHKE does (BTAB can stay separate, or go to DHKH,
  which is where stock puts 0x5xxx).

EC writes asked about (EcIoDxe 114ca60c, boot init RVA 0x2178-0x25f0, rbx
= LenovoConfig), high confidence
  - Beep mask: EC 0x04 = 0x00, EC 0x05 = 0x87 (RVA 0x2222, 0x2231). The
    DSDT EC._INI then clears EC 0x05 bit 0 (HSPA = 0, or MBEC(0x05, 0xFE,
    0)), and _WAK(4) again, so the OS sees 0x00/0x86 - the values of
    coreboot's beepmask0/beepmask1 in the W541 devicetree. EC RAM 0x86/0x87
    themselves are not in the DSDT; LenovoEcService (15c80344) reads them as
    a 16-bit flag word for its EC 0x3D/0x3E-0x45 data mailbox (tests bits
    12/13), not as a beep mask.
  - EC 0x02 bit 7: cleared at boot (RVA 0x23ed-0x240e: read 0x02, bit 5 =
    (LenovoConfig[0x0C] "ThinkPad NumLock" == 0), "and al, 0x7f", write).
    Later RVA 0x2453: 0x02 bit 3 = (LenovoConfig[7] == 0).
  - EC 0x03 bits 5-6 (HAUM): set to 3 at boot (RVA 0x22bb: read 0x03,
    &= ~1, |= 0x60, bit 1 = (LenovoConfig[0x1E] "Keyboard Beep" == 0),
    write); RVA 0x23d2 clears bit 4. DSDT EC.SAUM(Arg0) (no Return): if
    Arg0 <= 3, HAUM = Arg0 (or MBEC(0x03, 0x9F, Arg0 << 5)); \_SB._INI calls
    SAUM(2) only when _OSI("Linux") or _OSI("FreeBSD") answered true.
  - Same routine, for reference: EC 0x00 |= 4; 0x32 = 0x14 (wake on lid
    open and Fn), 0x33 = 0; 0x0C (LED) = 0x80, 0x8A, 0x07, 0x0D, 0x0E;
    0x01 |= 1, bit 1 = LenovoConfig[0x29] (Power On with AC Attach);
    0x3A &= ~1; 0x30 = LenovoConfig[0x25] | 0x80; 0x3B &= ~2; 0xCE bit 4 =
    LenovoConfig[0x0A] (Fn/Ctrl swap); 0x00 &= ~8; 0x83 = 6.


Confidence
  5. High for the SMM sequence, the setup mapping and AWON being a no-op;
     medium for the name of GEN_PMCON_3 bit 8, the meaning of PMH7 0x41
     bit 1 / 0x26 bit 2 beyond what the code does, and the PHY register
     meanings in the Intel GbE handler.
  6. High for the ASL, offsets, acks and STEP being a no-op; low (not
     determinable here) for the EC repeating events without the ack.
  7. High.
```

## 8. Hard disk password at S3 resume

```text
GNET94WW (ThinkPad W541 BIOS 2.42): ATA Hard Disk Password unlock across S3 resume
====================================================================================

Read-only analysis, 2026-11-08. Same image as findings.md
(bios.fl1 extracted from gnuj39us.iso). Nothing was run or flashed.
Disassembly in fw/dis/*.s, modules in fw/mods/, GUIDs via tools/.

Commands used
-------------
    D=/home/domenico/ourobios-test-v1.6.0/stock; cd $D
    grep -iE "hdp|ata|opal|passw|lock|sata" modules.tsv
    # ATA SECURITY opcodes written into the command block (mov byte [rsp+0x32],0xXX)
    grep -nE "mov byte ptr \[rsp \+ 0x[0-9a-f]+\], 0x(ec|f1|f2|f3|f4|f5|f6)\b" \
        fw/dis/LenovoHdpManagerSmm_89173692.pe.s fw/dis/LenovoHdpManagerDxe_ca9725c0.pe.s
    strings -el fw/mods/LenovoHdpManagerDxe_ca9725c0.pe     # -> LenovoHddSecInfoVar, LenovoConfig
    # GUID helpers added to tools/ for this task:
    #   tools/guidat.py  <module.pe> <rva...>   : print the GUID stored at an RVA
    #   tools/guidgrep.py <guid> <dir>          : list modules that embed a GUID
    ./venv/bin/python -I tools/guidat.py  fw/mods/LenovoHdpManagerSmm_89173692.pe 520 2e8 2c8
    ./venv/bin/python -I tools/guidgrep.py 470e1529-b79e-4e32-a0fe-6a156d29f9b2 fw/mods  # BootScriptSave
    sed -n '980,1210p' fw/dis/LenovoHdpManagerSmm_89173692.pe.s   # IDENTIFY/UNLOCK builders + loop
    sed -n '628,850p'  fw/dis/LenovoHdpManagerSmm_89173692.pe.s   # unlock-all worker + notify handler

Modules and GUIDs involved
---------------------------
    LenovoHdpManagerDxe   ca9725c0-12e5-4fac-ad58-d9aab03b8f11   (BDS/DXE: full management)
    LenovoHdpManagerSmm   89173692-9ac2-4c86-9ecc-f37782ddebaa   (SMM: resume unlock only)
    LenovoSecuritySmiDispatch 4c7d1568-...                       (APMC / port-0xB2 SW-SMI dispatcher)
    SystemAhciAtaAtapiPassThruDxe/Smm 44f23590 / bcb59c90        (AHCI ATA pass-thru, DXE + SMM)
    SystemAhciBusDxe/Smm  0167ccc4 / b31ff060                    (AHCI host / port control)
    SystemIdeAtaAtapiPassThruDxe/Smm 37a0d020 / 7391a960         (legacy IDE pass-thru, both handled)
    NVRAM variable  LenovoHddSecInfoVar  (per-drive HDP metadata, see Q2)

"Hdp" = Hard Disk Password. There is NO EDK2 SecurityPkg HddPasswordPei /
HddPasswordDxe and NO Opal/OpalPassword module in this image; the whole
feature is Lenovo-proprietary (LenovoHdpManager Dxe + Smm). The drive is
unlocked with ATA SECURITY UNLOCK (0xF2), not TCG Opal.


1. Which modules implement the HDD password            [confidence: HIGH]
------------------------------------------------------------------------
LenovoHdpManagerDxe (ca9725c0) is the full manager. It drives the standard
EDK2 DXE ATA Pass Thru protocol gEfiAtaPassThruProtocolGuid
(1d3de7f0-0807-424f-aa69-11a54e19a46f, data @RVA 0x390) and builds every
ATA SECURITY command by writing the opcode into the ATA command block at
command-block+2 (stack temp [rsp+0x32]):

    RVA 0x2650  mov byte[rsp+0x32],0xEC   IDENTIFY DEVICE
    RVA 0x273f  mov byte[rsp+0x32],0xF6   SECURITY DISABLE PASSWORD
    RVA 0x2812  mov byte[rsp+0x32],0xF3   SECURITY ERASE PREPARE
    RVA 0x28ff  mov byte[rsp+0x32],0xF4   SECURITY ERASE UNIT
    RVA 0x29d2  mov byte[rsp+0x32],0xF5   SECURITY FREEZE LOCK
    RVA 0x2ac3  mov byte[rsp+0x32],0xF2   SECURITY UNLOCK
    RVA 0x2d13  mov byte[rsp+0x32],0xF1   SECURITY SET PASSWORD

So the DXE does the whole lifecycle (set/change/disable password, secure
erase, unlock, freeze lock). It also uses gEfiDevicePathProtocol
(09576e91-6d3f-11d2-8e39-00a0c969723b, @RVA 0x540) and reads the setup
config (LenovoConfig) and the per-drive state variable LenovoHddSecInfoVar.

LenovoHdpManagerSmm (89173692) is the minimal resume agent. It contains
ONLY two ATA opcodes:

    RVA 0x10f3  mov byte[rsp+0x32],0xEC   IDENTIFY DEVICE   (builder at 0x104c)
    RVA 0x11c6  mov byte[rsp+0x32],0xF2   SECURITY UNLOCK   (builder at 0x111c)

No 0xF1/0xF5/0xF6 anywhere in the SMM module -> SMM never sets passwords
and never issues FREEZE LOCK; it only re-unlocks. This split (full manager
in DXE, tiny unlock stub in SMM) is the tell-tale of the S3 design.

Both builders assemble an EDK2 EFI_ATA_PASS_THRU_COMMAND_PACKET on the
stack and call PassThru = vtable+8 of an SMM ATA-pass-thru protocol cached
in global ->1830 (see Q3). Confirmed field layout (from RVA 0x104c):
    Asb              = &[rsp+0x48]
    Acb              = &[rsp+0x30]   (AtaCommand at Acb+2 = [rsp+0x32])
    Timeout          = 0x2FAF080 = 50,000,000 x100ns = 5 s
    InDataBuffer     = [rsp+0x78]    (IDENTIFY) / OutDataBuffer (UNLOCK)
    TransferLength   = 0x200 = 512 bytes
    Protocol         = 4 (PIO DATA IN, IDENTIFY) / 5 (PIO DATA OUT, UNLOCK)
    Length flags     = 0x80


2. Where the password is kept for the resume            [confidence: MED-HIGH]
----------------------------------------------------------------------------
In SMRAM, inside LenovoHdpManagerSmm, NOT in a LockBox and NOT in NVRAM.

- LockBox: the SctSmmLockBox{Pei,Dxe,Smm} trio exists, but a GUID sweep
  shows the LockBox communication GUID is referenced ONLY by the LockBox
  driver itself; LenovoHdpManager Dxe/Smm do not use it. (The LockBox here
  stores the S3 boot script / chipset restore data, not the HDD password.)

- NVRAM: LenovoHdpManagerDxe owns a UEFI variable LenovoHddSecInfoVar
  (UTF-16 string embedded at RVA 0x5c0). From its name and usage it holds
  per-drive security *metadata* - which SATA ports have HDP enabled, the
  saved device path, user/master state - used to decide what to unlock and
  to detect a swapped drive. I found no plaintext 32-byte ATA password
  written to any variable; the password is entered/obtained at boot and
  lives in RAM/SMRAM only.

- SMRAM: LenovoHdpManagerSmm keeps a fixed table of up to 4 per-drive
  entries (global array ->1800, iterated as offset 0..0x20 step 8). Each
  entry (base = rbx in the worker at RVA 0x988) holds:
      +0x28  SMM AtaPassThru device/port handle
      +0x30  dispatch/key id (matched to select one drive)
      +0x34  the 32-byte ATA SECURITY password block (the secret)
      +0x54  word: user(0)/master(1) selector
      +0x58  password length (<=32)
      +0x60  Port (word)
      +0x62  PortMultiplierPort (word)
      +0x68  pointer to a >=512-byte IDENTIFY/scratch buffer
  The DXE pushes {password, port, pmport, user/master} into this SMRAM
  table at boot (over the Lenovo SMM communication/dispatch protocol
  1390954d-da95-4227-9328-7282c217daa8, which LenovoHdpManagerDxe and
  ...Smm both reference and which is reachable through the APMC SW SMI).

Protection: the secret sits in locked SMRAM (TSEG), reachable only from
SMM. A LenovoCryptService protocol family (73e47354.., 3b3e7b1f.., shared
with LenovoDriveEraseDxe) is present, so the 32-byte block is plausibly
derived from the user passphrase rather than the raw ASCII; I did not
fully trace the derivation (see "Not fully resolved").


3. Who sends the unlock at S3 resume, and the AHCI programming   [confidence: HIGH on mechanism, MED on the exact resume trigger]
----------------------------------------------------------------------------
Who/when: an SMM handler, invoked by a software SMI (APMC, port 0xB2), NOT
a PEIM and NOT the OS. The unlock-all worker is LenovoHdpManagerSmm RVA
0x988. In the SMM entry point (RVA 0xd2c) it is registered on the SW-SMI /
SwDispatch2-style dispatch protocol e541b773-dd11-420c-b026-df993653f8bf
(register call at RVA 0xf19-0xf23). The companion dispatcher
LenovoSecuritySmiDispatch reads the CPU save-state and matches the APMC
value 0xB2<<16 (RVA 0x5cc: cmp ecx,0xB20000) before routing to the
registered sub-handlers - i.e. 0x988 fires when the allocated SW-SMI value
is written to port 0xB2. A second entry-point registration installs a
protocol-notify handler (RVA 0xc08) that lazily locates the SMM ATA
pass-thru protocol (by GUID @RVA 0x298/0x2a8, covering both the AHCI and
IDE SMM pass-thru) and caches it in ->1830 for the builders above.

Importantly, LenovoHdpManager Dxe/Smm do NOT reference the boot-script
save protocol (gEfiBootScriptSaveProtocolGuid
470e1529-b79e-4e32-a0fe-6a156d29f9b2 is present only in Pch/Platform/
SystemBootScriptSaveDxe/PlatformS3SaveDxe). So Hdp does not insert its own
"I/O write 0xB2" boot-script opcode; it relies on the stock platform S3
path to raise the SW SMI on resume. In a Phoenix SCT S3 resume the flow is
reset -> PEI -> S3Resume PEIM executes the saved ACPI S3 boot script ->
the boot script's APMC write triggers the SW SMI -> 0x988 runs in SMM ->
control returns and resume jumps to the OS waking vector. (I confirmed the
SMM mechanism and the SW-SMI registration directly; that the resume-time
0xB2 write comes specifically from the PEI boot script is the standard
Phoenix mechanism and is inferred, not byte-proven, because the trigger is
owned by the platform S3 framework rather than by Hdp.)

AHCI programming done by worker 0x988 (per table entry, in SMM, through
the SMM pass-thru and an AHCI host protocol ->1780):
  a. Port enable / ready wait (RVA 0xa8f-0xb25): calls the AHCI host
     protocol method at vtable+0x40 to (re)enable the port (selector
     0xF80FA092 + port number), then polls up to 0xFA0=4000 times with
     1000 us stalls (~up to 4 s) for the port to come ready - this is the
     post-power-on COMRESET/ready wait, needed because the drive returns
     from S3 powered off and locked.
  b. Device reset (RVA 0xff8, called at 0xb44): AtaPassThru reset-port then
     reset-device with a 100 us gap.
  c. IDENTIFY DEVICE (0xEC) via builder 0x104c, Protocol=4 (PIO IN),
     512-byte buffer, 5 s timeout.
  d. Locked check: RVA 0xb66  test byte[buf+0x100],4 - byte 0x100 = IDENTIFY
     word 128 (SECURITY status); bit2 = "locked". If not locked, skip.
  e. Build the 512-byte UNLOCK block: zero it, set word0 bit0 =
     master/user from entry+0x54 (RVA 0xb7f-0xb85), copy the 32-byte
     password from entry+0x34 into block+2 (RVA 0xb95-0xbaa).
  f. SECURITY UNLOCK (0xF2) via builder 0x111c, Protocol=5 (PIO OUT),
     512-byte buffer, 5 s timeout.
  g. On PassThru failure the status is checked (js -> skip) and a 1 s retry
     stall path exists (RVA 0xbd4, 0xf4240 us).

FREEZE LOCK after unlock: NO. The SMM module has no 0xF5. FREEZE LOCK is
applied only on the full DXE path (RVA 0x29d2). So after an S3 resume the
drive is left unlocked but NOT re-frozen by firmware (unless the OS freezes
it) - a real-world weakness, noted in Q5.

Normal boot vs resume: at a cold/normal boot LenovoHdpManagerDxe itself
does IDENTIFY->UNLOCK->(set/change)->FREEZE LOCK over the DXE AtaPassThru,
and populates the SMRAM table. On S3 resume DXE/BDS does not run; only the
SMM worker 0x988 re-does IDENTIFY+UNLOCK from the saved SMRAM copy.


4. Password <-> SATA port / device path, hot-plug, swap     [confidence: HIGH]
----------------------------------------------------------------------------
At boot the DXE enumerates drives, builds a device path
(gEfiDevicePathProtocol) and records, per locked drive, the
{Port, PortMultiplierPort, user/master, password, length} saved into the
SMRAM table (entry fields +0x60/+0x62/+0x54/+0x34/+0x58) and the
LenovoHddSecInfoVar metadata. On resume the SMM worker addresses each drive
by those saved Port/PortMultiplierPort numbers via the freshly re-enumerated
SMM AHCI pass-thru (AHCI is re-initialized on the resume path, so the port
numbering is stable).

Swapped / hot-plugged / unlocked drive handling is robust because every
entry is validated by IDENTIFY before UNLOCK:
  - If no device answers IDENTIFY at that port, PassThru fails and the
    entry is skipped (status js at RVA 0xb64).
  - If a device is present but its SECURITY status word 128 bit2 (locked)
    is clear, UNLOCK is skipped (RVA 0xb66) - so a swapped-in unlocked or
    passwordless drive is left alone.
  - If a locked drive is present but its password differs from the saved
    one, UNLOCK is issued and fails at the drive; the firmware does not
    unlock it (and the attempt counter in word 128 decrements on the drive
    itself). The valid flag (entry+0x68 cleared at RVA 0xa85) stops endless
    retries within the pass.


5. Dependence on things coreboot's S3 path lacks, and what coreboot needs
   [confidence: HIGH on the gap, design-level on the recommendation]
----------------------------------------------------------------------------
What the stock design leans on that coreboot S3 does NOT have:
  - A PEI phase on resume and an executed ACPI S3 boot script that raises
    the APMC SW SMI. coreboot resumes from S3 straight to the OS waking
    vector: no PEI, no boot-script replay. So the stock trigger (boot
    script -> OUT 0xB2 -> SMM 0x988) has nothing to fire it.
  - The EDK2/Lenovo SMM ATA pass-thru + AHCI host protocols. The stock
    unlock does not bit-bang AHCI; it calls EFI_ATA_PASS_THRU in SMM. In a
    coreboot+SMM world those protocols live in the payload's DXE/SMM, which
    is gone by OS-wake time.
  What DOES carry over: coreboot's own SMM handler persists across S3, and
  coreboot can run ramstage code and/or raise an SMI on the resume path
  before jumping to the OS waking vector.

What a coreboot (coreboot + UefiPayloadPkg) implementation would need:
  1. At boot: the payload collects the HDD password(s) (user/master) and
     per-port info, and hands the derived 32-byte ATA block + Port/PMPort
     to coreboot's persistent SMM via an SMI (an SMMSTORE-like APMC
     sub-command), mirroring the stock DXE->SMM handoff. Store it in TSEG.
  2. On S3 resume: before the OS wake vector, run an unlock pass - either
     in ramstage or by raising an SMI into the SMM store - that for each
     saved drive programs AHCI directly: map a temporary ABAR, bring the
     port up (COMRESET / spin-up, poll PxTFD/PxSSTS ready, ~a few seconds
     budget), issue IDENTIFY (0xEC) via a PIO-in command FIS, check word
     128 "locked", then SECURITY UNLOCK (0xF2) with a PIO-out 512-byte
     password block (word0 bit0 = master/user, bytes 2..33 = password).
     coreboot must supply this AHCI code itself (no EFI pass-thru at wake).
  3. Recommended (hardening the stock behaviour): also issue SECURITY
     FREEZE LOCK (0xF5) after unlock, which the stock SMM path omits.

Security caveats of the stock design:
  - The password/derived key sits in cleartext in SMRAM across every S3
    cycle; any SMM-escalation or SMRAM-disclosure bug leaks it. A coreboot
    port inherits the same exposure.
  - The cleartext password crosses the SATA link on every resume (PIO-out
    UNLOCK), sniffable with physical bus access.
  - FREEZE LOCK is applied only at full boot, not after the SMM resume
    unlock, so post-resume the drive is unlocked-and-unfrozen until the OS
    (if ever) freezes it - a window for SECURITY SET PASSWORD / unlock-
    attempt abuse.


Not fully resolved
------------------
- Exact derivation of the 32-byte block from the typed passphrase
  (LenovoCryptService is in the loop but not traced end to end).
- Byte-level proof that the resume-time OUT 0xB2 comes from the PEI S3
  boot script vs. another platform resume SMI (owned by Platform/Pch S3
  modules, not by Hdp).
- The precise semantics of the SMM state protocols 98840739-d6df-4564-...
  (the "test al,8" check at RVA 0x9bc, likely a resume/boot-mode gate) and
  the ->1780 AHCI host protocol's vtable+0x40 register encoding.
```
