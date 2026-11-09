# ouroBIOS hw-report

- Macchina: ThinkPad W541 (board w541)
- Firmware: `CBET4000 ouroBIOS-v1.6.3-rc1-nri`
- Kernel: 7.3.0-4-cachyos, acceso da 5 min
- Data: 2026-11-09 22:35
- Esito: **WARN** (4 WARN, 22 PASS, 1 INFO; uscita 1)

| ID | Esito | Controllo | Riepilogo |
|---|---|---|---|
| BOOT-01 | PASS | Firmware | CBET4000 ouroBIOS-v1.6.3-rc1-nri (release) |
| BOOT-02 | PASS | Tempo di avvio | 1.43 s dal reset al payload (soglie 6/12 s per ThinkPad W541) |
| BOOT-03 | PASS | Log di coreboot | 2 messaggi diversi (1 errori), 0 non noti |
| BOOT-04 | PASS | Log del kernel | nessun avviso sul firmware (39 avvisi in tutto, journalctl) |
| MEM-01 | PASS | RAM init | RAM init 0.11 s con la cache valida (soglie 2/5 s) |
| MEM-02 | PASS | Memoria | 4 moduli, 32 GB; Linux vede 30.8 GB |
| CPU-01 | PASS | CPU | Intel(R) Core(TM) i7-4810MQ CPU @ 2.80GHz, PL1 47 W, PL2 59 W |
| IDLE-01 | PASS | Stati C del package | PC6 e oltre 88.6% (soglie 50/10%), il piu' frequente PC7 88.2%, package 1.19 W |
| S3-01 | INFO | Sospensione | S3 offerto (default); nessuna sospensione in questo avvio (prova: systemctl suspend) |
| PCI-01 | WARN | PCIe ASPM e LTR | 1 problemi (criterio ASPM del kernel: default) |
| PCI-09 | PASS | Aperture PCI del payload | ogni BAR di memoria del bus 0 nell'apertura del root bridge del payload |
| FAN-01 | PASS | Ventola e temperature | CPU 44 C (soglie 80/95 C), ventola 1762 rpm |
| TPM-01 | PASS | TPM | TPM 1.x, tabella TCPA |
| TPM-03 | PASS | Measured boot | measured boot: 9 misure di coreboot e 3 di vboot, il registro da' i PCR 0-7 (sha1) |
| ME-01 | WARN | Intel ME | ferma nel BUP (stato 0x4d), stato di lavoro 1, modo 2, codice di errore 0, fase 1 stato 0x4d; HECI nascosta, come chiede me_disable |
| EC-01 | WARN | Firmware dell'EC | EC GMHT29WW piu' vecchio della 1.15 (GMHT30WW), senza la correzione di CVE-2019-6171 |
| VB-01 | PASS | vboot | slot B, avvio prima slot A confermato |
| UPD-01 | PASS | Aggiornamenti | v1.6.3-rc1, variante nri |
| FLASH-01 | PASS | Protezione del flash | WP_RO protetto (PR0) e SI_ALL (PR1), registri bloccati |
| WDT-01 | PASS | Firmware watchdog | spento (opzione firmware_watchdog Off) |
| ELOG-01 | PASS | Registro degli eventi | 255 eventi, 49 avvii, 3034 byte su 16384 |
| VB-02 | WARN | vboot nella copia del flash | prossimo slot B, 1 tentativi; corrente B confermato, precedente A confermato |
| OPT-01 | PASS | Opzioni salvate | 67 opzioni di coreboot in SMMSTORE |
| ID-01 | PASS | SMBIOS e VPD | LENOVO 20EGS24J00, S/N ****ZH6S |
| ID-02 | PASS | Tabelle ACPI | DMAR, HPET, TCPA presenti; MSDM assente |
| CONF-01 | PASS | WSMT | WSMT revisione 1, flag 0x7 |
| CONF-07 | PASS | ECAM | ECAM riservata nella mappa della memoria e tra le risorse della scheda madre |

## BOOT-01 Firmware: PASS

```
SMBIOS: coreboot, CBET4000 ouroBIOS-v1.6.3-rc1-nri (11/09/2026)
bootblock 26.09-438-g206078d6d990-ouroBIOS-ci-205-d123865-nri, log level 7
romstage  26.09-607-g524189e299-ouroBIOS-v1.6.3-rc1-nri, log level 7
ramstage  26.09-607-g524189e299-ouroBIOS-v1.6.3-rc1-nri, log level 7
console: 0.0 s negli stage (righe BS:, processore di avvio), livello 7
```

## BOOT-02 Tempo di avvio: PASS

```
fino a romstage (bootblock, verstage)    0.45 s
romstage                                 0.18 s
  di cui RAM init                        0.11 s
postcar e caricamento di ramstage        0.08 s
ramstage                                 0.46 s
caricamento del payload                  0.27 s
dal payload caricato al salto            0.00 s
i passi piu' lunghi: 0.28 s fino a 'device setup done'; 0.14 s fino a 'finished loading body'; 0.14 s fino a 'finished LZMA decompress (ignore for x86)'; 0.13 s fino a 'starting LZMA decompress (ignore for x86)'; 0.11 s fino a 'after RAM initialization'
Clear memory at power-on: When the OS asks, richiesta del sistema operativo (MOR) no: memoria non cancellata
```

## BOOT-03 Log di coreboot: PASS

```
[ERROR] ME: MBP not ready  -- noto: ME ridotto da me_cleaner -S
[WARN ] CBFS: 'fallback/slic' not found.  -- noto: la tabella SLIC e' facoltativa: acpi.c la cerca sempre in CBFS
```

## MEM-01 RAM init: PASS

```
cache del training: 'RW_MRC_CACHE' valida, usata
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

## IDLE-01 Stati C del package: PASS

```
package: PC2 3.1%  PC3 1.8%  PC6 0.3%  PC7 88.2%
potenza (RAPL): package 1.19 W, core 0.19 W, grafica 0.00 W, RAM 1.61 W
core occupati in media 1.1%; cpuidle: C1E 0.2%  C3 0.2%  C7s 99.0%
interrupt/s: Local timer interrupts 483, Function call interrupts 30, ahci[0000:00:1f.2] 28, TLB shootdowns 9, acpi 8, iwlwifi 7
processi (% di un core): nordvpnd 1.0, 2.1.318 1.0, tailscaled 0.5, kworker 0.4, containerd 0.1, claude 0.1
```

## S3-01 Sospensione: INFO

```
mem_sleep: s2idle shallow [deep]
sospensioni riuscite 0, fallite 0
```

## PCI-01 PCIe ASPM e LTR: WARN

```
00:1c.0  8086:8c10 pcieport     rp  ASPM L0sL1/- LTR +/+ 2.5GT/s x1
00:1c.1  8086:8c12 pcieport     rp  ASPM L0sL1/L1 LTR +/+ 5GT/s x1
00:1c.2  8086:8c14 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
00:1c.4  8086:8c18 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
01:00.0  1217:8520 sdhci-pci    ep  ASPM L0sL1/L0sL1 LTR +/+ 2.5GT/s x1
02:00.0  8086:2526 iwlwifi      ep  ASPM L1/L1 LTR +/+ 5GT/s x1
problema: 00:1c.0-01:00.0: ASPM L1 supportato dai due lati ma spento
```

## PCI-09 Aperture PCI del payload: PASS

```
apertura del root bridge sotto i 4 GiB 0xc0000000-0xefffffff, sopra vuota (10 BAR di memoria sul bus 0)
```

## FAN-01 Ventola e temperature: PASS

```
acpitz: temp1 38 C
iwlwifi_1: temp1 33 C
thinkpad: CPU 38 C, GPU 0 C, temp3 0 C, temp4 0 C, temp5 0 C, temp6 0 C
thinkpad fan1: 1762 rpm
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
contesto: FW_SLOT_B
avvio prima: slot A, confermato
RW_NVRAM in verstage: prossimo slot B, 1 tentativo; corrente slot B in prova
slot in prova (una capsula, update.py other-slot o rollback): il payload lo conferma quando arriva alla sua console
```

## UPD-01 Aggiornamenti: PASS

```
variante nri, GUID 457afc2a-b6ee-4477-b41b-cc995e6110ae
versione v1.6.3-rc1, minima per una capsula v1.3.9
ultimo aggiornamento: v1.6.3-rc1, riuscito
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

## ELOG-01 Registro degli eventi: PASS

```
conteggi: Management Engine 50, Management Engine extra 50, System boot 49, System reset 49, Wake source 19, ACPI wake 15, ACPI enter 11, Memory cache update 4, SUS power fail 3, Log area cleared 3, RTC reset 2
gli ultimi eventi:
  2026-11-09 21:29:18  System reset             
  2026-11-09 21:29:18  Wake source              RTC alarm
  2026-11-09 21:29:18  Management Engine        disabled
  2026-11-09 21:29:18  Management Engine extra  0106020001064d
  2026-11-09 21:30:12  System boot              526
  2026-11-09 21:30:12  System reset             
  2026-11-09 21:30:12  Management Engine        disabled
  2026-11-09 21:30:12  Management Engine extra  01060200010b4d
```

## VB-02 vboot nella copia del flash: WARN

```
RO      ouroBIOS-ci-205-d123865-nri
slot A  ouroBIOS-v1.6.2-nri
slot B  ouroBIOS-v1.6.3-rc1-nri
CBET4000 ouroBIOS-v1.6.3-rc1-nri non e' in nessuno slot della copia
RW_NVRAM: 124 record su 4096
```

## OPT-01 Opzioni salvate: PASS

```
store: 191 KiB, 146 KiB usati, 45 liberi, stato 0xfe
acpi_cpu_objects=1, backlight=0, battery_charge_limit=0, bios_lock=1, bluetooth=1, boot_menu_prompt=1, bootmedia_lock=1, c_states=1, camera=1, card_reader=1, cfg_lock=0, clear_dram_on_boot=2, cooling_policy=0, cpu_power_limit_lock=0, csmwrap_boot=1, debug_level=7, dgpu_macos_off=1, dma_untrusted_ports=0, eist=1, enable_dual_graphics=0, expresscard=1, f1_to_f12_as_primary=1, fingerprint_reader=1, firmware_watchdog=0, first_battery=1, fn_ctrl_swap=0, gfx_aperture_size=3, gfx_fb_limit=1, gfx_resume_init=0, gfx_uma_size=16, hyper_threading=1, internal_mic=1, ipxe_boot=1, keyboard_beep=1, low_battery_beep=1, macos_device_properties=1, macos_panel=1, macos_pme_wake=0, me_disable=1, minihd_audio=1, nmi=0, onboard_ethernet=1, peg_link_tuning=3, power_management_beeps=1, power_on_ac=0, power_on_after_fail=0, sata_port1=1, sata_port4=1, sata_port5=0, serial_console=0, sticky_fn=0, tcc_offset=0, tdp_pl1_override=0, tdp_pl2_override=0, thunderbolt=1, touchpad=1, trackpoint=1, turbo_mode=1, usb_always_on=0, usb_boot=1, uwb=1, vmx=1, volume=3, vtd=1, wake_on_lan=1, wlan=1, wwan=1
```

## ID-01 SMBIOS e VPD: PASS

```
system-manufacturer: LENOVO
system-product-name: 20EGS24J00
system-version: ThinkPad W541
baseboard-product-name: 20EGS24J00
bios-vendor: coreboot
bios-version: CBET4000 ouroBIOS-v1.6.3-rc1-nri
bios-release-date: 11/09/2026
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
