# ouroBIOS hw-report

- Macchina: ThinkPad W541 (board w541)
- Firmware: `CBET4000 ouroBIOS-v1.6.2-nri`
- Kernel: 7.3.0-4-cachyos, acceso da 110 min
- Data: 2026-11-09 21:56
- Esito: **FAIL** (1 FAIL, 3 WARN, 23 PASS; uscita 2)

| ID | Esito | Controllo | Riepilogo |
|---|---|---|---|
| BOOT-01 | PASS | Firmware | CBET4000 ouroBIOS-v1.6.2-nri (release) |
| BOOT-02 | PASS | Tempo di avvio | 0.88 s dal reset al ritorno nell'OS (ripresa da S3) (soglie 6/12 s per ThinkPad W541) |
| BOOT-03 | PASS | Log di coreboot | nessun errore ne' avviso |
| BOOT-04 | PASS | Log del kernel | 1 messaggi del firmware su 49 avvisi (journalctl), 0 non noti |
| MEM-01 | PASS | RAM init | RAM init 0.11 s con la ripresa da S3 (soglie 2/5 s) |
| MEM-02 | PASS | Memoria | 4 moduli, 32 GB; Linux vede 30.8 GB |
| CPU-01 | PASS | CPU | Intel(R) Core(TM) i7-4810MQ CPU @ 2.80GHz, PL1 47 W, PL2 59 W |
| IDLE-01 | FAIL | Stati C del package | PC6 e oltre 0.0% (soglie 50/10%), il piu' frequente PC2 88.5%, package 9.12 W |
| S3-01 | PASS | Sospensione | S3 offerto (default); 1 sospensioni riuscite |
| PCI-01 | PASS | PCIe ASPM e LTR | ASPM L1 e LTR accesi su ogni link che li supporta (criterio del kernel: default) |
| PCI-09 | PASS | Aperture PCI del payload | ogni BAR di memoria del bus 0 nell'apertura del root bridge del payload |
| FAN-01 | PASS | Ventola e temperature | CPU 51 C (soglie 80/95 C), ventola 1621 rpm |
| TPM-01 | PASS | TPM | TPM 1.x, tabella TCPA |
| TPM-03 | PASS | Measured boot | measured boot: 9 misure di coreboot e 3 di vboot, il registro da' i PCR 0-7 (sha1) |
| ME-01 | WARN | Intel ME | ferma nel BUP (stato 0x4d), stato di lavoro 1, modo 2, codice di errore 0, fase 1 stato 0x4d; HECI nascosta, come chiede me_disable |
| EC-01 | WARN | Firmware dell'EC | EC GMHT29WW piu' vecchio della 1.15 (GMHT30WW), senza la correzione di CVE-2019-6171 |
| VB-01 | PASS | vboot | slot A, avvio prima slot A - |
| UPD-01 | PASS | Aggiornamenti | v1.6.2, variante nri |
| FLASH-01 | PASS | Protezione del flash | WP_RO protetto (PR0) e SI_ALL (PR1), registri bloccati |
| WDT-01 | PASS | Firmware watchdog | spento (opzione firmware_watchdog Off) |
| ELOG-01 | PASS | Registro degli eventi | 320 eventi, 64 avvii, 3801 byte su 16384 |
| VB-02 | WARN | vboot nella copia del flash | prossimo slot A, 1 tentativi; corrente A confermato, precedente B - |
| OPT-01 | PASS | Opzioni salvate | 67 opzioni di coreboot in SMMSTORE |
| ID-01 | PASS | SMBIOS e VPD | LENOVO 20EGS24J00, S/N ****ZH6S |
| ID-02 | PASS | Tabelle ACPI | DMAR, HPET, TCPA presenti; MSDM assente |
| CONF-01 | PASS | WSMT | WSMT revisione 1, flag 0x7 |
| CONF-07 | PASS | ECAM | ECAM riservata nella mappa della memoria e tra le risorse della scheda madre |

## BOOT-01 Firmware: PASS

```
SMBIOS: coreboot, CBET4000 ouroBIOS-v1.6.2-nri (11/09/2026)
bootblock 26.09-438-g206078d6d990-ouroBIOS-ci-205-d123865-nri, log level 7
romstage  26.09-607-g524189e299-ouroBIOS-v1.6.2-nri, log level 7
ramstage  26.09-607-g524189e299-ouroBIOS-v1.6.2-nri, log level 7
console: 0.0 s negli stage (righe BS:, processore di avvio), livello 7
```

## BOOT-02 Tempo di avvio: PASS

```
fino a romstage (bootblock, verstage)    0.45 s
romstage                                 0.14 s
  di cui RAM init                        0.11 s
postcar e caricamento di ramstage        0.01 s
i passi piu' lunghi: 0.18 s fino a 'device setup done'; 0.14 s fino a 'finished loading body'; 0.11 s fino a 'after RAM initialization'; 0.11 s fino a 'finished TPM initialization'; 0.09 s fino a 'start of bootblock'
```

## BOOT-04 Log del kernel: PASS

```
[warn] [Firmware Bug]: TSC ADJUST differs: CPU0 0 --> 316728104440. Restoring  -- noto: a ogni resume da S3 il kernel trova IA32_TSC_ADJUST del processore 0 diverso da zero e lo rimette a zero da solo (il TSC resta coerente); non e' il firmware: misurato con una build di prova, il registro e' 0 fino al salto al wake vector e il TSC di prima della sospensione viene riscritto dopo, lato Linux (docs/tests/v1.6.0/w541-nri/diag.md); c'era anche con la v1.5.0
```

## MEM-01 RAM init: PASS

```
cache del training: ripresa da S3
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

## IDLE-01 Stati C del package: FAIL

```
package: PC2 88.5%  PC3 0.0%  PC6 0.0%  PC7 0.0%
potenza (RAPL): package 9.12 W, core 0.46 W, grafica 0.00 W, RAM 1.71 W
core occupati in media 2.3%; cpuidle: C1 0.2%  C1E 0.2%  C3 0.4%  C6 0.2%  C7s 97.6%
interrupt/s: Local timer interrupts 932, Function call interrupts 125, TLB shootdowns 24, ahci[0000:00:1f.2] 21, iwlwifi 19, acpi 10
processi (% di un core): 2.1.318 4.0, mpvpaper 0.9, tailscaled 0.6, nordvpnd 0.6, systemd-oomd 0.1, containerd 0.1
```

## S3-01 Sospensione: PASS

```
mem_sleep: s2idle shallow [deep]
sospensioni riuscite 1, fallite 0
```

## PCI-01 PCIe ASPM e LTR: PASS

```
00:1c.0  8086:8c10 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ 2.5GT/s x1
00:1c.1  8086:8c12 pcieport     rp  ASPM L0sL1/L1 LTR +/+ 5GT/s x1
00:1c.2  8086:8c14 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
00:1c.4  8086:8c18 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
01:00.0  1217:8520 sdhci-pci    ep  ASPM L0sL1/L0sL1 LTR +/+ 2.5GT/s x1
02:00.0  8086:2526 iwlwifi      ep  ASPM L1/L1 LTR +/+ 5GT/s x1
```

## PCI-09 Aperture PCI del payload: PASS

```
apertura del root bridge sotto i 4 GiB 0xc0000000-0xefffffff, sopra vuota (10 BAR di memoria sul bus 0)
```

## FAN-01 Ventola e temperature: PASS

```
acpitz: temp1 46 C
iwlwifi_1: temp1 37 C
thinkpad: CPU 46 C, GPU 0 C, temp3 0 C, temp4 0 C, temp5 0 C, temp6 0 C
thinkpad fan1: 1621 rpm
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
```

## EC-01 Firmware dell'EC: WARN

```
log, Version 4.01B: GMHT29WW-3.23
SMBIOS tipo 11: GMHT29WW-3.23
ouroBIOS non aggiorna l'EC: lo fa solo il firmware Lenovo 2.42 (GNUJ39US), cioe' rimettere tutto il firmware originale con un programmatore esterno, aggiornare, poi di nuovo ouroBIOS (docs/flashing.md)
```

## VB-01 vboot: PASS

```
contesto: S3_RESUME
avvio prima: slot A, -
RW_NVRAM in verstage: prossimo slot A, 1 tentativo; corrente slot A confermato
slot in prova (una capsula, update.py other-slot o rollback): il payload lo conferma quando arriva alla sua console
```

## UPD-01 Aggiornamenti: PASS

```
variante nri, GUID 457afc2a-b6ee-4477-b41b-cc995e6110ae
versione v1.6.2, minima per una capsula v1.3.9
ultimo aggiornamento: v1.6.2, riuscito
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
conteggi: System boot 64, System reset 64, Management Engine 64, Management Engine extra 64, Wake source 19, ACPI enter 14, ACPI wake 14, Memory cache update 8, SUS power fail 4, Log area cleared 3, RTC reset 2
gli ultimi eventi:
  2026-11-09 19:05:22  Management Engine extra  0106020001064d
  2026-11-09 19:06:17  System boot              524
  2026-11-09 19:06:17  System reset             
  2026-11-09 19:06:17  Management Engine        disabled
  2026-11-09 19:06:17  Management Engine extra  01060200010b4d
  2026-11-09 19:08:10  ACPI enter               S3
  2026-11-09 19:08:41  ACPI wake                S3
  2026-11-09 19:08:41  Wake source              RTC alarm
```

## VB-02 vboot nella copia del flash: WARN

```
RO      ouroBIOS-ci-205-d123865-nri
slot A  ouroBIOS-v1.6.2-nri
slot B  ouroBIOS-v1.6.2-rc1-nri
CBET4000 ouroBIOS-v1.6.2-nri non e' in nessuno slot della copia
RW_NVRAM: 119 record su 4096
```

## OPT-01 Opzioni salvate: PASS

```
store: 191 KiB, 123 KiB usati, 67 liberi, stato 0xfe
acpi_cpu_objects=1, backlight=0, battery_charge_limit=0, bios_lock=1, bluetooth=1, boot_menu_prompt=1, bootmedia_lock=1, c_states=1, camera=1, card_reader=1, cfg_lock=0, clear_dram_on_boot=2, cooling_policy=0, cpu_power_limit_lock=0, csmwrap_boot=1, debug_level=7, dgpu_macos_off=1, dma_untrusted_ports=0, eist=1, enable_dual_graphics=0, expresscard=1, f1_to_f12_as_primary=1, fingerprint_reader=1, firmware_watchdog=0, first_battery=1, fn_ctrl_swap=0, gfx_aperture_size=3, gfx_fb_limit=1, gfx_resume_init=0, gfx_uma_size=16, hyper_threading=1, internal_mic=1, ipxe_boot=1, keyboard_beep=1, low_battery_beep=1, macos_device_properties=1, macos_panel=1, macos_pme_wake=0, me_disable=1, minihd_audio=1, nmi=0, onboard_ethernet=1, peg_link_tuning=3, power_management_beeps=1, power_on_ac=0, power_on_after_fail=0, sata_port1=1, sata_port4=1, sata_port5=0, serial_console=0, sticky_fn=0, tcc_offset=0, tdp_pl1_override=0, tdp_pl2_override=0, thunderbolt=1, touchpad=1, trackpoint=1, turbo_mode=1, usb_always_on=0, usb_boot=1, uwb=1, vmx=1, volume=3, vtd=1, wake_on_lan=1, wlan=1, wwan=1
```

## ID-01 SMBIOS e VPD: PASS

```
system-manufacturer: LENOVO
system-product-name: 20EGS24J00
system-version: ThinkPad W541
baseboard-product-name: 20EGS24J00
bios-vendor: coreboot
bios-version: CBET4000 ouroBIOS-v1.6.2-nri
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
