# ouroBIOS hw-report

- Macchina: ThinkPad W541 (board w541)
- Firmware: `CBET4000 ouroBIOS-v1.6.3-rc3-nri`
- Kernel: 7.3.0-4-cachyos, acceso da 6 min
- Data: 2026-11-10 12:54
- Esito: **FAIL** (1 FAIL, 3 WARN, 19 PASS, 1 INFO, 1 SKIP; uscita 2)

| ID | Esito | Controllo | Riepilogo |
|---|---|---|---|
| BOOT-01 | PASS | Firmware | CBET4000 ouroBIOS-v1.6.3-rc3-nri (release) |
| BOOT-02 | PASS | Tempo di avvio | 0.87 s dal reset al ritorno nell'OS (ripresa da S3) (soglie 6/12 s per ThinkPad W541) |
| BOOT-03 | PASS | Log di coreboot | nessun errore ne' avviso |
| BOOT-04 | FAIL | Log del kernel | 20 messaggi del firmware su 371 avvisi (journalctl), 17 non noti |
| MEM-01 | PASS | RAM init | RAM init 0.11 s con la ripresa da S3 (soglie 2/5 s) |
| MEM-02 | PASS | Memoria | 4 moduli, 32 GB; Linux vede 30.8 GB |
| CPU-01 | PASS | CPU | Intel(R) Core(TM) i7-4810MQ CPU @ 2.80GHz, PL1 47 W, PL2 59 W |
| IDLE-01 | PASS | Stati C del package | PC6 e oltre 87.6% (soglie 50/10%), il piu' frequente PC7 87.3%, package 1.24 W |
| S3-01 | PASS | Sospensione | S3 offerto (default); 3 sospensioni riuscite |
| PCI-01 | WARN | PCIe ASPM e LTR | 1 problemi (criterio ASPM del kernel: default) |
| PCI-09 | PASS | Aperture PCI del payload | ogni BAR di memoria del bus 0 nell'apertura del root bridge del payload |
| FAN-01 | INFO | Ventola e temperature | CPU 40 C (soglie 80/95 C), ventola 0 rpm |
| TPM-01 | PASS | TPM | TPM 1.x, tabella TCPA |
| TPM-03 | PASS | Measured boot | measured boot: 9 misure di coreboot e 3 di vboot, il registro da' i PCR 0-7 (sha1) |
| ME-01 | WARN | Intel ME | ferma nel BUP (stato 0x4d), stato di lavoro 1, modo 2, codice di errore 0, fase 1 stato 0x4d; HECI nascosta, come chiede me_disable |
| EC-01 | WARN | Firmware dell'EC | EC GMHT29WW piu' vecchio della 1.15 (GMHT30WW), senza la correzione di CVE-2019-6171 |
| VB-01 | PASS | vboot | slot B, avvio prima slot A - |
| UPD-01 | PASS | Aggiornamenti | v1.6.3-rc3, variante nri |
| FLASH-01 | PASS | Protezione del flash | WP_RO protetto (PR0) e SI_ALL (PR1), registri bloccati |
| WDT-01 | PASS | Firmware watchdog | spento (opzione firmware_watchdog Off) |
| ELOG-01 | SKIP | Registro degli eventi | nessuna copia del flash (--dump, da sudo flashrom -p internal -r flash.bin) |
| ID-01 | PASS | SMBIOS e VPD | LENOVO 20EGS24J00, S/N ****ZH6S |
| ID-02 | PASS | Tabelle ACPI | DMAR, HPET, TCPA presenti; MSDM assente |
| CONF-01 | PASS | WSMT | WSMT revisione 1, flag 0x7 |
| CONF-07 | PASS | ECAM | ECAM riservata nella mappa della memoria e tra le risorse della scheda madre |

## BOOT-01 Firmware: PASS

```
SMBIOS: coreboot, CBET4000 ouroBIOS-v1.6.3-rc3-nri (11/10/2026)
bootblock 26.09-438-g206078d6d990-ouroBIOS-ci-205-d123865-nri, log level 7
romstage  26.09-607-g524189e299-ouroBIOS-v1.6.3-rc3-nri, log level 7
ramstage  26.09-607-g524189e299-ouroBIOS-v1.6.3-rc3-nri, log level 7
console: 0.0 s negli stage (righe BS:, processore di avvio), livello 7
```

## BOOT-02 Tempo di avvio: PASS

```
fino a romstage (bootblock, verstage)    0.44 s
romstage                                 0.14 s
  di cui RAM init                        0.11 s
postcar e caricamento di ramstage        0.01 s
i passi piu' lunghi: 0.18 s fino a 'device setup done'; 0.14 s fino a 'finished loading body'; 0.11 s fino a 'after RAM initialization'; 0.10 s fino a 'finished TPM initialization'; 0.09 s fino a 'start of bootblock'
```

## BOOT-04 Log del kernel: FAIL

```
[warn] [Firmware Bug]: TSC ADJUST differs: CPU0 0 --> 322728097838. Restoring  -- noto: a ogni resume da S3 il kernel trova IA32_TSC_ADJUST del processore 0 diverso da zero e lo rimette a zero da solo (il TSC resta coerente); non e' il firmware: misurato con una build di prova, il registro e' 0 fino al salto al wake vector e il TSC di prima della sospensione viene riscritto dopo, lato Linux (docs/tests/v1.6.0/w541-nri/diag.md); c'era anche con la v1.5.0
[err] i915 0000:00:02.0: [drm] PCH PWM1 enabled (x8)
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#3: kworker/u32:41/1816
[err] intel_uncore snd_intel_sdw_acpi mtd bluetooth i2c_mux gpio_ich snd_hwdep cfg80211 e1000e snd_pcm ip6t_REJECT nf_reject_ipv6 snd_timer ptp coreboot_table pps_core xt_hl ip6t_rt mac_hid ipt_REJECT nf_reject_ipv4 xt_LOG nf_log_syslog nft_limit xt_limit xt_addrtype xt_tcpudp xt_conntrack nf_conntrack nf_defrag_ipv6 nf_defrag_ipv4 nft_compat x_tables nf_tables pkcs8_key_parser crypto_user i2c_dev ntsync dm_mod zram 842_decompress 842_compress lz4hc_compress i915 sdhci_pci thinkpad_acpi drm_buddy cqhci rfkill intel_gtt sdhci_uhs2 sdhci ttm snd spi_intel_platform i2c_algo_bit spi_intel soundcore mmc_core sparse_keymap drm_display_helper video cec wmi serio_raw lpc_ich (x8)
[err] Hardware name: LENOVO 20EGS24J00/20EGS24J00, BIOS CBET4000 ouroBIOS-v1.6.3-rc3-nri 11/10/2026 (x8)
[err] RIP: 0010:hsw_enable_pc8+0xede/0xfa0 [i915] (x8)
[err] intel_display_driver_pm_runtime_suspend_late+0x12/0x40 [i915 cbbc58a306b0926cf8f06bdb88b3fc29ed854f50] (x6)
[err] i915_pm_runtime_suspend+0xef/0x2f0 [i915 cbbc58a306b0926cf8f06bdb88b3fc29ed854f50] (x6)
[err] pci_pm_runtime_suspend+0x5e/0x1a0 (x6)
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#0: kworker/u32:46/1821
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#6: kworker/u32:23/1797
[err] intel_display_power_suspend_late+0x237/0x240 [i915 cbbc58a306b0926cf8f06bdb88b3fc29ed854f50] (x2)
[err] i915_drm_suspend_late+0x7c/0xf0 [i915 cbbc58a306b0926cf8f06bdb88b3fc29ed854f50] (x2)
[warn] [Firmware Bug]: TSC ADJUST differs: CPU0 0 --> 115045636790. Restoring  -- noto: a ogni resume da S3 il kernel trova IA32_TSC_ADJUST del processore 0 diverso da zero e lo rimette a zero da solo (il TSC resta coerente); non e' il firmware: misurato con una build di prova, il registro e' 0 fino al salto al wake vector e il TSC di prima della sospensione viene riscritto dopo, lato Linux (docs/tests/v1.6.0/w541-nri/diag.md); c'era anche con la v1.5.0
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#1: kworker/u32:15/581
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#7: kworker/u32:32/1806
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#3: kworker/u32:12/578
[warn] [Firmware Bug]: TSC ADJUST differs: CPU0 0 --> 114881229530. Restoring  -- noto: a ogni resume da S3 il kernel trova IA32_TSC_ADJUST del processore 0 diverso da zero e lo rimette a zero da solo (il TSC resta coerente); non e' il firmware: misurato con una build di prova, il registro e' 0 fino al salto al wake vector e il TSC di prima della sospensione viene riscritto dopo, lato Linux (docs/tests/v1.6.0/w541-nri/diag.md); c'era anche con la v1.5.0
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#5: kworker/u32:17/1791
[warn] WARNING: drivers/gpu/drm/i915/display/intel_display_power.c:1402 at hsw_enable_pc8+0xc80/0xfa0 [i915], CPU#2: kworker/u32:34/1808
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

## IDLE-01 Stati C del package: PASS

```
package: PC2 3.5%  PC3 1.9%  PC6 0.3%  PC7 87.3%
potenza (RAPL): package 1.24 W, core 0.17 W, grafica 0.00 W, RAM 1.62 W
core occupati in media 1.2%; cpuidle: C1E 0.1%  C3 0.2%  C7s 99.2%
interrupt/s: Local timer interrupts 516, Function call interrupts 20, TLB shootdowns 8, acpi 8, iwlwifi 7, Rescheduling interrupts 2
processi (% di un core): 2.1.318 1.0, nordvpnd 0.8, plasma-login-gr 0.5, tailscaled 0.5, claude 0.2, systemd-oomd 0.1
```

## S3-01 Sospensione: PASS

```
mem_sleep: s2idle shallow [deep]
sospensioni riuscite 3, fallite 0
```

## PCI-01 PCIe ASPM e LTR: WARN

```
00:1c.0  8086:8c10 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ 2.5GT/s x1
00:1c.1  8086:8c12 pcieport     rp  ASPM L0sL1/L1 LTR +/+ 5GT/s x1
00:1c.2  8086:8c14 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
00:1c.4  8086:8c18 pcieport     rp  ASPM L0sL1/L0sL1 LTR +/+ giu'
01:00.0  1217:8520 sdhci-pci    ep  ASPM L0sL1/L0sL1 LTR +/- 2.5GT/s x1
02:00.0  8086:2526 iwlwifi      ep  ASPM L1/L1 LTR +/+ 5GT/s x1
problema: 01:00.0: LTR supportato ma spento
```

## PCI-09 Aperture PCI del payload: PASS

```
apertura del root bridge sotto i 4 GiB 0xc0000000-0xefffffff, sopra vuota (10 BAR di memoria sul bus 0)
```

## FAN-01 Ventola e temperature: INFO

```
acpitz: temp1 35 C
iwlwifi_1: temp1 34 C
thinkpad: CPU 35 C, GPU 0 C, temp3 0 C, temp4 0 C, temp5 0 C, temp6 0 C
thinkpad fan1: 0 rpm
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
contesto: FW_SLOT_B S3_RESUME
avvio prima: slot A, -
RW_NVRAM in verstage: prossimo slot B, 1 tentativo; corrente slot B confermato
slot in prova (una capsula, update.py other-slot o rollback): il payload lo conferma quando arriva alla sua console
```

## UPD-01 Aggiornamenti: PASS

```
variante nri, GUID 457afc2a-b6ee-4477-b41b-cc995e6110ae
versione v1.6.3-rc3, minima per una capsula v1.3.9
ultimo aggiornamento: v1.6.3-rc3, riuscito
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
bios-version: CBET4000 ouroBIOS-v1.6.3-rc3-nri
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
