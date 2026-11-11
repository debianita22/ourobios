# ouroBIOS hw-report

- Macchina: ThinkPad W541 (board w541)
- Firmware: `CBET4000 ouroBIOS-v1.7.0-rc2-nri`
- Kernel: 7.3.0-4-cachyos, acceso da 1 min
- Data: 2026-11-11 06:41
- Esito: **WARN** (2 WARN, 19 PASS, 3 INFO, 1 SKIP; uscita 1)

| ID | Esito | Controllo | Riepilogo |
|---|---|---|---|
| BOOT-01 | PASS | Firmware | CBET4000 ouroBIOS-v1.7.0-rc2-nri (release) |
| BOOT-02 | PASS | Tempo di avvio | 2.44 s dal reset al payload, 1.34 s senza il training (soglie 6/12 s per ThinkPad W541) |
| BOOT-03 | PASS | Log di coreboot | 2 messaggi diversi (1 errori), 0 non noti |
| BOOT-04 | PASS | Log del kernel | nessun avviso sul firmware (36 avvisi in tutto, journalctl) |
| MEM-01 | INFO | RAM init | RAM init 1.10 s, avvio con il training (MRC: cache data 'RW_MRC_CACHE' needs update): al prossimo avvio deve stare sotto 2 s |
| MEM-02 | PASS | Memoria | 4 moduli, 32 GB; Linux vede 30.8 GB |
| CPU-01 | PASS | CPU | Intel(R) Core(TM) i7-4810MQ CPU @ 2.80GHz, PL1 47 W, PL2 59 W |
| IDLE-01 | INFO | Stati C del package | pannello 3K acceso (eDP-1 2880x1620): il W541 resta in PC2 (noto), PC6+ 0.0%; la soglia vale a schermo spento, package 8.61 W |
| S3-01 | INFO | Sospensione | S3 offerto (default); nessuna sospensione in questo avvio (prova: systemctl suspend) |
| PCI-01 | PASS | PCIe ASPM e LTR | ASPM L1 e LTR accesi su ogni link che li supporta (criterio del kernel: default) |
| PCI-09 | PASS | Aperture PCI del payload | ogni BAR di memoria del bus 0 nell'apertura del root bridge del payload |
| FAN-01 | PASS | Ventola e temperature | CPU 50 C (soglie 80/95 C), ventola 1633 rpm |
| TPM-01 | PASS | TPM | TPM 1.x, tabella TCPA |
| TPM-03 | PASS | Measured boot | measured boot: 9 misure di coreboot e 3 di vboot, il registro da' i PCR 0-7 (sha1) |
| ME-01 | WARN | Intel ME | ferma nel BUP (stato 0x4d), stato di lavoro 1, modo 2, codice di errore 0, fase 1 stato 0x4d; HECI nascosta, come chiede me_disable |
| EC-01 | WARN | Firmware dell'EC | EC GMHT29WW piu' vecchio della 1.15 (GMHT30WW), senza la correzione di CVE-2019-6171 |
| VB-01 | PASS | vboot | slot A, avvio prima slot B - |
| UPD-01 | PASS | Aggiornamenti | v1.7.0-rc2, variante nri |
| FLASH-01 | PASS | Protezione del flash | WP_RO protetto (PR0) e SI_ALL (PR1), registri bloccati |
| WDT-01 | PASS | Firmware watchdog | spento all'OS (la riga di romstage non e' nel log, quella del payload si') |
| ELOG-01 | SKIP | Registro degli eventi | nessuna copia del flash (--dump, da sudo flashrom -p internal -r flash.bin) |
| ID-01 | PASS | SMBIOS e VPD | LENOVO 20EGS24J00, S/N ****ZH6S |
| ID-02 | PASS | Tabelle ACPI | DMAR, HPET, TCPA presenti; MSDM assente |
| CONF-01 | PASS | WSMT | WSMT revisione 1, flag 0x7 |
| CONF-07 | PASS | ECAM | ECAM riservata nella mappa della memoria e tra le risorse della scheda madre |

## BOOT-01 Firmware: PASS

```
SMBIOS: coreboot, CBET4000 ouroBIOS-v1.7.0-rc2-nri (11/10/2026)
ramstage  26.09-607-g524189e299-ouroBIOS-v1.7.0-rc2-nri, log level 7
il banner del bootblock (parte RO) non e' nel log: la console prima di CBMEM e' traboccata
console: 0.0 s negli stage (righe BS:, processore di avvio), livello 7
```

## BOOT-02 Tempo di avvio: PASS

```
fino a romstage (bootblock, verstage)    0.45 s
romstage                                 1.19 s
  di cui RAM init                        1.10 s
postcar e caricamento di ramstage        0.08 s
ramstage                                 0.46 s
caricamento del payload                  0.27 s
dal payload caricato al salto            0.00 s
i passi piu' lunghi: 1.10 s fino a 'after RAM initialization'; 0.28 s fino a 'device setup done'; 0.14 s fino a 'finished loading body'; 0.14 s fino a 'finished LZMA decompress (ignore for x86)'; 0.13 s fino a 'starting LZMA decompress (ignore for x86)'
Clear memory at power-on: When the OS asks, richiesta del sistema operativo (MOR) no: memoria non cancellata
```

## BOOT-03 Log di coreboot: PASS

```
[ERROR] ME: MBP not ready  -- noto: ME ridotto da me_cleaner -S
[WARN ] CBFS: 'fallback/slic' not found.  -- noto: la tabella SLIC e' facoltativa: acpi.c la cerca sempre in CBFS
la console prima di CBMEM e' traboccata: l'inizio del bootblock non c'e'
```

## MEM-01 RAM init: INFO

```
cache del training: MRC: cache data 'RW_MRC_CACHE' needs update; salvata di nuovo
```

## MEM-02 Memoria: PASS

```
Channel-0-DIMM-0: 8 GiB DDR3 SODIMM, 1600 MT/s (configurata 1600 MT/s), Samsung M471B5273DH0-CK0, rank 2
Channel-0-DIMM-1: 8 GiB DDR3 SODIMM, 1600 MT/s (configurata 1600 MT/s), Samsung M471B5273DH0-CK0, rank 2
Channel-1-DIMM-0: 8 GiB DDR3 SODIMM, 1600 MT/s (configurata 1600 MT/s), Samsung M471B5273DH0-CK0, rank 2
Channel-1-DIMM-1: 8 GiB DDR3 SODIMM, 1600 MT/s (configurata 1600 MT/s), Samsung M471B5273DH0-CK0, rank 2
```

## CPU-01 CPU: PASS

```
microcode: Linux 0x28, coreboot 0x28
MSR 0x610: PL1 47.0 W attivo, PL2 58.8 W attivo
rapporto base 28 (2800 MHz), turbo a 1 core 38, TjMax 100 C
offset TCC programmabile: si' (PLATFORM_INFO bit 30), offset attuale 0 (MSR 0x1A2 bit 27:24); sul W541 l'opzione e' Energy Saver > Thermal > TCC activation offset (dalla v1.6.0)
```

## IDLE-01 Stati C del package: INFO

```
package: PC2 14.3%  PC3 64.3%  PC6 0.0%  PC7 0.0%
potenza (RAPL): package 8.61 W, core 0.25 W, grafica 0.21 W, RAM 1.80 W
core occupati in media 1.2%; cpuidle: C1E 0.2%  C3 0.2%  C7s 98.9%
interrupt/s: Local timer interrupts 509, Function call interrupts 41, IRQ work interrupts 19, i915 17, ahci[0000:00:1f.2] 16, iwlwifi 14
processi (% di un core): 2.1.318 0.9, nordvpnd 0.8, tailscaled 0.5, plasma-login-gr 0.4, kwin_wayland 0.2, systemd-oomd 0.1
pannello acceso durante la misura: eDP-1 2880x1620 (a schermo spento: docs/testing.md, IDLE-01)
```

## S3-01 Sospensione: INFO

```
mem_sleep: s2idle shallow [deep]
sospensioni riuscite 0, fallite 0
```

## PCI-01 PCIe ASPM e LTR: PASS

```
00:1c.0  8086:8c10 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ 2.5GT/s x1
00:1c.1  8086:8c12 pcieport     rp  ASPM L0sL1/L1 LTR +/+ 5GT/s x1
00:1c.2  8086:8c14 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
00:1c.4  8086:8c18 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
01:00.0  1217:8520 sdhci-pci    ep  ASPM L0sL1/L0sL1 LTR +/- 2.5GT/s x1
         01:00.0: LTR spento dal firmware (noto: patch 0272)
02:00.0  8086:2526 iwlwifi      ep  ASPM L1/L1 LTR +/+ 5GT/s x1
```

## PCI-09 Aperture PCI del payload: PASS

```
apertura del root bridge sotto i 4 GiB 0xc0000000-0xefffffff, sopra vuota (10 BAR di memoria sul bus 0)
```

## FAN-01 Ventola e temperature: PASS

```
acpitz: temp1 44 C
iwlwifi_1: temp1 34 C
thinkpad: CPU 44 C, GPU 0 C, temp3 0 C, temp4 0 C, temp5 0 C, temp6 0 C
thinkpad fan1: 1633 rpm
```

## TPM-01 TPM: PASS

```
registro delle misure del firmware: 7616 byte
TPM 1.2: enabled 1, active 1, owned 1
```

## TPM-03 Measured boot: PASS

```
81 eventi nel registro; 9 misure di coreboot in PCR 2, 3 di vboot in PCR 1
```

## ME-01 Intel ME: WARN

```
opzione me_disable: 1 (in SMMSTORE)
HECI 00:16.0 nel sistema: no
log: ME: Progress Phase State    : 0x4d
log: ME: Progress Phase State    : 0x4d
```

## EC-01 Firmware dell'EC: WARN

```
log, Version 4.01B: GMHT29WW-3.23
SMBIOS tipo 11: GMHT29WW-3.23
ouroBIOS non aggiorna l'EC: lo fa solo il firmware Lenovo 2.42 (GNUJ39US), cioe' rimettere tutto il firmware originale con un programmatore esterno, aggiornare, poi di nuovo ouroBIOS (docs/flashing.md)
```

## VB-01 vboot: PASS

```
contesto: -
avvio prima: slot B, -
RW_NVRAM in verstage: prossimo slot A, 1 tentativo; corrente slot A in prova
slot in prova (una capsula, update.py other-slot o rollback): il payload lo conferma quando arriva alla sua console
```

## UPD-01 Aggiornamenti: PASS

```
variante nri, GUID 457afc2a-b6ee-4477-b41b-cc995e6110ae
versione v1.7.0-rc2, minima per una capsula v1.3.9
ultimo aggiornamento: v1.7.0-rc2, riuscito
```

## FLASH-01 Protezione del flash: PASS

```
log: BM-LOCKDOWN: Enabled bootmedia protection
log: BM-LOCKDOWN: Enabled bootmedia protection for SI_ALL
option lock: armato: bios_lock e bootmedia_lock di sola lettura per l'OS (OptionLockStatus del payload)
Lynx Point 00:1f.0: BIOS_CNTL 0x2a (BIOSWE 0, BLE 1, SMM_BWP 1), GCS 0x00000c21 (BILD 1), FLOCKDN si'
PR0 0x0b60000-0x0bfffff scrittura protetta (WP_RO)
PR1 0x0000000-0x04fffff scrittura protetta (SI_ALL)
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
system-product-name: 20EGS24J00
system-version: ThinkPad W541
baseboard-product-name: 20EGS24J00
bios-vendor: coreboot
bios-version: CBET4000 ouroBIOS-v1.7.0-rc2-nri
bios-release-date: 11/10/2026
system-serial-number: ****ZH6S
system-uuid: ****c24c
baseboard-serial-number: (vuoto)
```

## ID-02 Tabelle ACPI: PASS

```
tabelle: APIC BGRT DMAR DSDT FACP FACS HPET MCFG SSDT TCPA WSMT
MSDM: assente (nessuna chiave Windows nella VPD: facoltativa)
```

## CONF-01 WSMT: PASS

```
flag: FIXED_COMM_BUFFERS COMM_BUFFER_NESTED_PTR_PROTECTION SYSTEM_RESOURCE_PROTECTION
```

## CONF-07 ECAM: PASS

```
segmento 0, bus 00-3f: 0xf0000000-0xf3ffffff, 64 MiB; riservati nella mappa della memoria 64 MiB; tra le risorse della scheda madre (pnp) 64 MiB
```
