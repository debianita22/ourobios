# ouroBIOS hw-report

- Macchina: ThinkCentre M920x (board m920x)
- Firmware: `ouroBIOS-v1.7.0-rc13-m920x-fsp`
- Kernel: 7.0.14-15-pve, acceso da 3 min
- Data: 2026-11-13 21:22
- Esito: **INFO** (26 PASS, 2 INFO; uscita 0)

| ID | Esito | Controllo | Riepilogo |
|---|---|---|---|
| BOOT-01 | PASS | Firmware | ouroBIOS-v1.7.0-rc13-m920x-fsp (release) |
| BOOT-02 | PASS | Tempo di avvio | 6.11 s dal reset al ritorno nell'OS (ripresa da S3) (soglie 12/20 s per ThinkCentre M920x) |
| BOOT-03 | PASS | Log di coreboot | nessun errore ne' avviso |
| BOOT-04 | PASS | Log del kernel | 1 messaggi del firmware su 7 avvisi (journalctl), 0 non noti |
| MEM-01 | PASS | RAM init | FspMemoryInit 0.23 s con la ripresa da S3 (soglie 2/5 s) |
| MEM-02 | PASS | Memoria | 2 moduli, 40 GB; Linux vede 39.0 GB |
| CPU-01 | PASS | CPU | Intel(R) Core(TM) i3-8100 CPU @ 3.60GHz, PL1 65 W, PL2 65 W |
| IDLE-01 | PASS | Stati C del package | PC6 e oltre 85.8% (soglie 50/10%), il piu' frequente PC9 83.2%, package 0.50 W |
| S3-01 | PASS | Sospensione | S3 offerto (default); 3 sospensioni riuscite |
| PCI-01 | PASS | PCIe ASPM e LTR | ASPM L1 e LTR accesi su ogni link che li supporta (criterio del kernel: default) |
| PCI-02 | PASS | Porta PEG del riser | porta PEG spenta (nessuna scheda sul riser) |
| PCI-09 | INFO | Aperture PCI del payload | 1 BAR fuori dall'apertura del payload, di dispositivi che i suoi driver non usano |
| FAN-01 | PASS | Ventola e temperature | CPU 55 C (soglie 80/95 C), ventola 855 rpm |
| TPM-01 | PASS | TPM | TPM 2.x, tabella TPM2 |
| TPM-03 | PASS | Measured boot | measured boot: 11 misure di coreboot e 3 di vboot, il registro da' i PCR 0-7 (sha1, sha256) |
| ME-01 | INFO | Intel ME | disattivata (soft temporary disable), stato di lavoro 4, codice di errore 2; HECI (00:16.0) nascosta al sistema (dalle stringhe OEM di SMBIOS: nel log niente righe 'ME:', dopo una ripresa da S3 la console ricomincia) |
| VB-01 | PASS | vboot | slot A, avvio prima slot A - |
| UPD-01 | PASS | Aggiornamenti | v1.7.0-rc13, variante m920x-fsp |
| FLASH-01 | PASS | Protezione del flash | WP_RO protetto (PR0) e SI_ALL (PR1), registri bloccati |
| WDT-01 | PASS | Firmware watchdog | spento (opzione firmware_watchdog Off) |
| ELOG-01 | PASS | Registro degli eventi | 326 eventi, 100 avvii, 3728 byte su 16384 |
| VB-02 | PASS | vboot nella copia del flash | prossimo slot A; corrente A confermato, precedente A confermato |
| OPT-01 | PASS | Opzioni salvate | 36 opzioni di coreboot in SMMSTORE |
| ID-01 | PASS | SMBIOS e VPD | LENOVO 10S2S00V00, S/N ****ZK26 |
| ID-02 | PASS | Tabelle ACPI | DMAR, HPET, TPM2 presenti; MSDM presente |
| CONF-01 | PASS | WSMT | WSMT revisione 1, flag 0x7 |
| CONF-07 | PASS | ECAM | ECAM riservata nella mappa della memoria e tra le risorse della scheda madre |
| CONF-08 | PASS | HSTI | 9 di 13 test superati, 0 mancati non noti |

## BOOT-01 Firmware: PASS

```
SMBIOS: coreboot, ouroBIOS-v1.7.0-rc13-m920x-fsp (11/13/2026)
romstage  26.09-607-g524189e299-ouroBIOS-v1.7.0-rc13-m920x-fsp, log level 7
ramstage  26.09-607-g524189e299-ouroBIOS-v1.7.0-rc13-m920x-fsp, log level 7
il banner del bootblock (parte RO) non e' nel log: la console prima di CBMEM e' traboccata
console: 4.2 s negli stage (righe BS:, processore di avvio), livello 7
seriale, COM1 a 115200 baud: ~4.2 s agli stage dello slot (romstage, postcar, ramstage, AP compresi) al livello 7 (Debug); a Info ~1.0 s, a Notice ~0.1 s, a Error ~0.0 s; spenta (Console > Serial Console) 0. Il log di CBMEM resta fino a DEBUG a ogni livello
```

## BOOT-02 Tempo di avvio: PASS

```
fino a romstage (bootblock, verstage)    0.84 s
romstage                                 0.41 s
  di cui FspMemoryInit                   0.23 s
postcar e caricamento di ramstage        0.03 s
  di cui FspSiliconInit                  0.06 s
i passi piu' lunghi: 1.22 s fino a 'calling FspNotify(AfterPciEnumeration)'; 0.63 s fino a 'device configuration'; 0.62 s fino a 'device enable'; 0.59 s fino a 'device enumeration'; 0.47 s fino a 'calling FspSiliconInit'
```

## BOOT-03 Log di coreboot: PASS

```
la console prima di CBMEM e' traboccata: l'inizio della romstage non c'e' (i boot che fanno il training della RAM ne scrivono di piu')
```

## BOOT-04 Log del kernel: PASS

```
[warn] Warning: PCIe ACS overrides enabled; This may allow non-IOMMU protected peer-to-peer DMA  -- noto: pcie_acs_override sulla riga di comando del kernel
```

## MEM-01 RAM init: PASS

```
cache del training: ripresa da S3
```

## MEM-02 Memoria: PASS

```
Channel-0-DIMM-0: 32 GB DDR4 SODIMM, 2400 MT/s (configurata 2400 MT/s), Crucial CT32G4SFD8266.C16FE, rank 2
Channel-1-DIMM-0: 8 GB DDR4 SODIMM, 2400 MT/s (configurata 2400 MT/s), Hynix/Hyundai HMA81GS6JJR8N-VK, rank 1
```

## CPU-01 CPU: PASS

```
microcode: Linux 0xf6, coreboot 0xf6 (il log dice 0xf5: con PRMRR la patch del FIT riporta la revisione meno uno, noto)
MSR 0x610: PL1 65.0 W attivo, PL2 65.0 W attivo
rapporto base 36 (3600 MHz), turbo a 1 core 36, TjMax 100 C
offset TCC programmabile: si' (PLATFORM_INFO bit 30), offset attuale 0 (MSR 0x1A2 bit 29:24)
coreboot: Turbo non disponibile su questa CPU
```

## IDLE-01 Stati C del package: PASS

```
package: PC2 3.5%  PC3 6.9%  PC6 1.4%  PC7 0.0%  PC8 1.2%  PC9 83.2%  PC10 0.0%
potenza (RAPL): package 0.50 W, core 0.47 W, grafica 0.00 W, RAM 0.75 W
core occupati in media 0.6%; cpuidle: C1E 0.2%  C6 1.4%  C8 1.1%  C9 0.2%  C10 96.7%
interrupt/s: Local timer interrupts 203, nvme0q1 14, nic0 10, Function call interrupts 8, TLB shootdowns 4
processi (% di un core): 2.1.312 0.7, pvestatd 0.2, pve-firewall 0.2, claude 0.2
```

## S3-01 Sospensione: PASS

```
mem_sleep: s2idle [deep]
sospensioni riuscite 3, fallite 0
```

## PCI-01 PCIe ASPM e LTR: PASS

```
00:1b.0  8086:a32c pcieport     rp  ASPM L0sL1/L1 LTR +/+ 8GT/s x4
00:1c.0  8086:a33d pcieport     rp  ASPM L0sL1/L1 LTR +/+ 2.5GT/s x1
01:00.0  144d:a808 nvme         ep  ASPM L1/L1 LTR +/+ 8GT/s x4
02:00.0  8086:3166 iwlwifi      ep  ASPM L1/L1 LTR +/+ 2.5GT/s x1
```

## PCI-02 Porta PEG del riser: PASS

```
log: PEG: PCIe flags 0x0142, slot status 0x0000, link status 0x1001
log: PEG: no card on the riser slot, port off (a card there not seen: Hardware > Devices > PCIe riser slot > Enabled)
```

## PCI-09 Aperture PCI del payload: INFO

```
apertura del root bridge sotto i 4 GiB 0xbecb9000-0xdfffffff, sopra 0xa7c800000-0xa7c800fff (16 BAR di memoria sul bus 0)
00:1f.5 8086:a324 -            BAR0 0xfe010000-0xfe010fff fuori: tra la BAR e l'apertura c'e' ECAM 0xe0000000-0xefffffff
```

## FAN-01 Ventola e temperature: PASS

```
nct6686: PECI 0.0 56 C, PCH CHIP 48 C, Diode 0 (curr) 50 C, Diode 1 (curr) 15 C, Diode 2 (curr) 44 C
nvme: Composite 41 C, Sensor 1 41 C, Sensor 2 40 C
pch_cannonlake: temp1 48 C
nct6686 fan2: 855 rpm
```

## TPM-01 TPM: PASS

```
registro delle misure del firmware: 69556 byte
```

## TPM-03 Measured boot: PASS

```
120 eventi nel registro; 11 misure di coreboot in PCR 2, 3 di vboot in PCR 1
```

## ME-01 Intel ME: INFO

```
opzione me_state: non nel log
```

## VB-01 vboot: PASS

```
contesto: S3_RESUME
avvio prima: slot A, -
RW_NVRAM in verstage: prossimo slot A, 0 tentativi; corrente slot A confermato
```

## UPD-01 Aggiornamenti: PASS

```
variante m920x-fsp, GUID ceef6456-ca3b-4cf3-a784-4895efaf1bde
versione v1.7.0-rc13, minima per una capsula v1.3.9
ultimo aggiornamento: v1.7.0-rc13, riuscito
```

## FLASH-01 Protezione del flash: PASS

```
log: BM-LOCKDOWN: Enabled bootmedia protection
log: BM-LOCKDOWN: Enabled bootmedia protection for SI_ALL
option lock: armato: bios_lock e bootmedia_lock di sola lettura per l'OS (OptionLockStatus del payload)
fast SPI 00:1f.5: BIOS_CNTL 0xaa (BIOSWE 0, BLE 1, EISS 1), FLOCKDN si'
PR0 0x1700000-0x17fffff scrittura protetta (WP_RO)
PR1 0x0000000-0x0bfffff scrittura protetta (SI_ALL)
WP_RO: protetta fino al prossimo reset o ripresa da S3 (PR0)
SI_ALL: protetta fino al prossimo reset o ripresa da S3 (PR1)
BIOS Lock: acceso: scrive solo il firmware in SMM
slot RW: scrivibili con la capsula; flashrom no (BIOS Lock)
```

## WDT-01 Firmware watchdog: PASS

```
OC_WDT_CTL 0x00002000: enable 0, timeout 1 s, stato di reset 0
```

## ELOG-01 Registro degli eventi: PASS

```
conteggi: System boot 100, System reset 95, ACPI wake 65, Wake source 63, Log area cleared 2, Memory cache update 1
gli ultimi eventi:
  2026-11-13 20:19:13  System boot              183
  2026-11-13 20:19:13  System reset             
  2026-11-13 20:21:03  ACPI wake                S3
  2026-11-13 20:21:03  Wake source              RTC alarm
  2026-11-13 20:21:41  ACPI wake                S3
  2026-11-13 20:21:41  Wake source              RTC alarm
  2026-11-13 20:22:14  ACPI wake                S3
  2026-11-13 20:22:14  Wake source              RTC alarm
```

## VB-02 vboot nella copia del flash: PASS

```
RO      ouroBIOS-ci-203-045bf06-m920x-fsp
slot A  ouroBIOS-v1.7.0-rc13-m920x-fsp
slot B  ouroBIOS-v1.7.0-rc10-m920x-fsp
RW_NVRAM: 257 record su 4096
```

## OPT-01 Opzioni salvate: PASS

```
store: 191 KiB, 47 KiB usati, 144 liberi, stato 0xfe
acpi_cpu_objects=0, bios_lock=1, boot_menu_prompt=1, bootmedia_lock=1, cfg_lock=1, clear_dram_on_boot=2, csmwrap_boot=1, debug_level=7, eist=1, firmware_watchdog=0, front_usb=1, hyper_threading=1, ice_mode=0, igd_aperture_size=2, igd_dvmt_prealloc=4, igd_enabled=1, ipxe_boot=1, legacy_8254_timer=0, me_state=1, me_state_counter=0, onboard_audio=1, onboard_ethernet=1, onboard_wlan=1, option_roms=2, peg_slot=0, pkg_power_limit_lock=0, power_on_after_fail=1, rear_usb=1, serial_console=1, tcc_offset=0, tdp_pl1_override=0, tdp_pl2_override=65, turbo_mode=1, usb_boot=1, vtd=1, wake_on_lan=1
```

## ID-01 SMBIOS e VPD: PASS

```
system-manufacturer: LENOVO
system-product-name: 10S2S00V00
system-version: ThinkCentre M920x
baseboard-product-name: ThinkCentre M920x Tiny
bios-vendor: coreboot
bios-version: ouroBIOS-v1.7.0-rc13-m920x-fsp
bios-release-date: 11/13/2026
system-serial-number: ****ZK26
system-uuid: ****1800
baseboard-serial-number: (vuoto)
```

## ID-02 Tabelle ACPI: PASS

```
tabelle: APIC DMAR DSDT FACP FACS HPET LPIT MCFG MSDM SPCR SSDT TPM2 WSMT
MSDM: presente, chiave nel formato giusto (non stampata)
```

## CONF-01 WSMT: PASS

```
flag: FIXED_COMM_BUFFERS COMM_BUFFER_NESTED_PTR_PROTECTION SYSTEM_RESOURCE_PROTECTION
```

## CONF-07 ECAM: PASS

```
segmento 0, bus 00-ff: 0xe0000000-0xefffffff, 256 MiB; riservati nella mappa della memoria 256 MiB; tra le risorse della scheda madre (pnp) 256 MiB
```

## CONF-08 HSTI: PASS

```
si': configurazione del flash bloccata (FLOCKDN)
si': regione BIOS protetta (BIOS_CNTL)
si': Protected Range bloccato
no: descrittore non scrivibile dall'host  -- noto: regioni sbloccate (ifdtool)
no: regione ME non scrivibile dall'host  -- noto: regioni sbloccate (ifdtool)
si': TSEG bloccato
si': interfaccia di debug bloccata
si': microcode caricato
no: Secure Boot  -- noto: una scelta del proprietario
si': TPM
si': lock delle opzioni del setup
si': lock MOR
no: protezione DMA prima dell'avvio  -- noto: l'FSP-M non ha i dati dei PMR
errore: 0x00010003 Flash: the host can write the flash descriptor (FRAP) https://github.com/debianita22/ourobios/blob/main/docs/hsti.md
errore: 0x00010004 Flash: the host can write the ME region (FRAP) https://github.com/debianita22/ourobios/blob/main/docs/hsti.md
errore: 0x00010008 Secure Boot: Secure Boot is off https://github.com/debianita22/ourobios/blob/main/docs/hsti.md
errore: 0x0001000C DMA: no pre-boot DMA protection https://github.com/debianita22/ourobios/blob/main/docs/hsti.md
```
