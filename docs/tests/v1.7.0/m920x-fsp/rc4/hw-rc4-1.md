# ouroBIOS hw-report

- Macchina: ThinkCentre M920x (board m920x)
- Firmware: `ouroBIOS-v1.7.0-rc4-m920x-fsp`
- Kernel: 7.0.14-15-pve, acceso da 2 min
- Data: 2026-11-11 14:12
- Esito: **SKIP** (22 PASS, 2 INFO, 1 SKIP; uscita 0)

| ID | Esito | Controllo | Riepilogo |
|---|---|---|---|
| BOOT-01 | PASS | Firmware | ouroBIOS-v1.7.0-rc4-m920x-fsp (release) |
| BOOT-02 | PASS | Tempo di avvio | 10.78 s dal reset al payload (soglie 12/20 s per ThinkCentre M920x) |
| BOOT-03 | PASS | Log di coreboot | 1 messaggi diversi (0 errori), 0 non noti |
| BOOT-04 | PASS | Log del kernel | 4 messaggi del firmware su 12 avvisi (journalctl), 0 non noti |
| MEM-01 | PASS | RAM init | FspMemoryInit 0.25 s con la cache valida (soglie 2/5 s) |
| MEM-02 | PASS | Memoria | 2 moduli, 40 GB; Linux vede 39.0 GB |
| CPU-01 | PASS | CPU | Intel(R) Core(TM) i3-8100 CPU @ 3.60GHz, PL1 65 W, PL2 65 W |
| IDLE-01 | PASS | Stati C del package | PC6 e oltre 87.1% (soglie 50/10%), il piu' frequente PC9 84.4%, package 0.56 W |
| S3-01 | INFO | Sospensione | S3 offerto (default); nessuna sospensione in questo avvio (prova: systemctl suspend) |
| PCI-01 | PASS | PCIe ASPM e LTR | ASPM L1 e LTR accesi su ogni link che li supporta (criterio del kernel: default) |
| PCI-02 | PASS | Porta PEG del riser | porta PEG spenta (nessuna scheda sul riser) |
| PCI-09 | INFO | Aperture PCI del payload | 1 BAR fuori dall'apertura del payload, di dispositivi che i suoi driver non usano |
| FAN-01 | PASS | Ventola e temperature | CPU 49 C (soglie 80/95 C), ventola 825 rpm |
| TPM-01 | PASS | TPM | TPM 2.x, tabella TPM2 |
| TPM-03 | PASS | Measured boot | measured boot: 11 misure di coreboot e 3 di vboot, il registro da' i PCR 0-7 (sha1, sha256) |
| ME-01 | PASS | Intel ME | spento (soft temporary disable) come chiesto, HECI nascosto |
| VB-01 | PASS | vboot | slot A, avvio prima slot B confermato |
| UPD-01 | PASS | Aggiornamenti | v1.7.0-rc4, variante m920x-fsp |
| FLASH-01 | PASS | Protezione del flash | WP_RO protetto (PR0) e SI_ALL (PR1), registri bloccati |
| WDT-01 | PASS | Firmware watchdog | spento (opzione firmware_watchdog Off) |
| ELOG-01 | SKIP | Registro degli eventi | nessuna copia del flash (--dump, da sudo flashrom -p internal -r flash.bin) |
| ID-01 | PASS | SMBIOS e VPD | LENOVO 10S2S00V00, S/N ****ZK26 |
| ID-02 | PASS | Tabelle ACPI | DMAR, HPET, TPM2 presenti; MSDM presente |
| CONF-01 | PASS | WSMT | WSMT revisione 1, flag 0x7 |
| CONF-07 | PASS | ECAM | ECAM riservata nella mappa della memoria e tra le risorse della scheda madre |

## BOOT-01 Firmware: PASS

```
SMBIOS: coreboot, ouroBIOS-v1.7.0-rc4-m920x-fsp (11/11/2026)
romstage  26.09-607-g524189e299-ouroBIOS-v1.7.0-rc4-m920x-fsp, log level 7
ramstage  26.09-607-g524189e299-ouroBIOS-v1.7.0-rc4-m920x-fsp, log level 7
il banner del bootblock (parte RO) non e' nel log: la console prima di CBMEM e' traboccata
console: 6.1 s negli stage (righe BS:, processore di avvio), livello 7
seriale, COM1 a 115200 baud: ~6.1 s agli stage dello slot (romstage, postcar, ramstage, AP compresi) al livello 7 (Debug); a Info ~1.5 s, a Notice ~0.1 s, a Error ~0.1 s; spenta (Console > Serial Console) 0. Il log di CBMEM resta fino a DEBUG a ogni livello
```

## BOOT-02 Tempo di avvio: PASS

```
fino a romstage (bootblock, verstage)    0.98 s
romstage                                 0.64 s
  di cui FspMemoryInit                   0.25 s
postcar e caricamento di ramstage        0.07 s
ramstage                                 7.99 s
  di cui FspSiliconInit                  0.06 s
caricamento del payload                  0.52 s
dal payload caricato al salto            0.59 s
i passi piu' lunghi: 2.57 s fino a 'started elog init'; 1.24 s fino a 'calling FspNotify(AfterPciEnumeration)'; 0.87 s fino a 'finalize chips'; 0.64 s fino a 'device configuration'; 0.62 s fino a 'device enable'
Clear memory at power-on: When the OS asks, richiesta del sistema operativo (MOR) si': memoria cancellata (~0.5 s ogni 10 GB)
```

## BOOT-03 Log di coreboot: PASS

```
[WARN ] CBFS: 'fallback/slic' not found.  -- noto: la tabella SLIC e' facoltativa: acpi.c la cerca sempre in CBFS
la console prima di CBMEM e' traboccata: l'inizio della romstage non c'e' (i boot che fanno il training della RAM ne scrivono di piu')
```

## BOOT-04 Log del kernel: PASS

```
[warn] Warning: PCIe ACS overrides enabled; This may allow non-IOMMU protected peer-to-peer DMA  -- noto: pcie_acs_override sulla riga di comando del kernel
[err] x86/cpu: SGX disabled or unsupported by BIOS.  -- noto: SGX non e' attivato (SOC_INTEL_COMMON_BLOCK_SGX_ENABLE, default n)
[warn] hpet_acpi_add: no address or irqs in _CRS  -- noto: il _CRS dell'HPET (soc/intel/common/block/acpi/acpi/lpc.asl) ha solo l'indirizzo, senza IRQ
[warn] faux_driver regulatory: Direct firmware load for regulatory.db failed with error -2  -- noto: un file di linux-firmware del driver, non il BIOS
```

## MEM-01 RAM init: PASS

```
cache del training: 'RW_MRC_CACHE' valida, usata
```

## MEM-02 Memoria: PASS

```
Channel-0-DIMM-0: 32 GB DDR4 SODIMM, 2400 MT/s (configurata 2400 MT/s), Crucial CT32G4SFD8266.C16FE, rank 2
Channel-1-DIMM-0: 8 GB DDR4 SODIMM, 2400 MT/s (configurata 2400 MT/s), Hynix/Hyundai HMA81GS6JJR8N-VK, rank 1
log di coreboot: 2 DIMM trovati
```

## CPU-01 CPU: PASS

```
microcode: Linux 0xf6, coreboot 0xf6 (il log dice 0xf5: con PRMRR la patch del FIT riporta la revisione meno uno, noto)
MSR 0x610: PL1 65.0 W attivo, PL2 65.0 W attivo
rapporto base 36 (3600 MHz), turbo a 1 core 36, TjMax 100 C
offset TCC programmabile: si' (PLATFORM_INFO bit 30), offset attuale 0 (MSR 0x1A2 bit 29:24)
EC: platform 42 42 07, classe della CPU 65 W
coreboot: Turbo non disponibile su questa CPU
```

## IDLE-01 Stati C del package: PASS

```
package: PC2 3.9%  PC3 4.8%  PC6 1.3%  PC7 0.0%  PC8 1.4%  PC9 84.4%  PC10 0.0%
potenza (RAPL): package 0.56 W, core 0.53 W, grafica 0.00 W, RAM 0.75 W
core occupati in media 0.7%; cpuidle: C1E 0.1%  C6 1.3%  C8 1.1%  C9 0.2%  C10 96.5%
interrupt/s: Local timer interrupts 217, nic0 18, Function call interrupts 9, TLB shootdowns 5
processi (% di un core): 2.1.312 0.8, pve-firewall 0.2, kworker 0.2, pvestatd 0.2
```

## S3-01 Sospensione: INFO

```
mem_sleep: s2idle [deep]
sospensioni riuscite 0, fallite 0
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
00:1f.5 8086:a324 intel-spi    BAR0 0xfe010000-0xfe010fff fuori: tra la BAR e l'apertura c'e' ECAM 0xe0000000-0xefffffff
```

## FAN-01 Ventola e temperature: PASS

```
nct6686: PECI 0.0 50 C, PCH CHIP 46 C, Diode 0 (curr) 45 C, Diode 1 (curr) 14 C, Diode 2 (curr) 44 C
nvme: Composite 40 C, Sensor 1 40 C, Sensor 2 39 C
pch_cannonlake: temp1 46 C
nct6686 fan2: 825 rpm
```

## TPM-01 TPM: PASS

```
registro delle misure del firmware: 69136 byte
```

## TPM-03 Measured boot: PASS

```
120 eventi nel registro; 11 misure di coreboot in PCR 2, 3 di vboot in PCR 1
```

## ME-01 Intel ME: PASS

```
HFSTS1: working state 4, operation mode 3, error code 2
opzione me_state: 1 (Disabled)
HECI 00:16.0 nel sistema: no
```

## VB-01 vboot: PASS

```
contesto: -
avvio prima: slot B, confermato
RW_NVRAM in verstage: prossimo slot A, 1 tentativo; corrente slot A in prova
slot in prova (una capsula, update.py other-slot o rollback): il payload lo conferma quando arriva alla sua console
```

## UPD-01 Aggiornamenti: PASS

```
variante m920x-fsp, GUID ceef6456-ca3b-4cf3-a784-4895efaf1bde
versione v1.7.0-rc4, minima per una capsula v1.3.9
ultimo aggiornamento: v1.7.0-rc4, riuscito
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

## ID-01 SMBIOS e VPD: PASS

```
system-manufacturer: LENOVO
system-product-name: 10S2S00V00
system-version: ThinkCentre M920x
baseboard-product-name: ThinkCentre M920x Tiny
bios-vendor: coreboot
bios-version: ouroBIOS-v1.7.0-rc4-m920x-fsp
bios-release-date: 11/11/2026
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
