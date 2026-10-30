# shellcheck shell=bash
# La board di tools/build.sh, tools/verify-rom.sh e tools/ci-check.sh
# (--board m920x): ThinkCentre M920x Tiny (docs/m920x.md).

BOARD_NAME="ThinkCentre M920x Tiny"
# una variante, la RAM init di FSP-M; le release: vX.Y.Z-m920x-fsp
BOARD_VARIANTS=(fsp)
BOARD_FLAVOUR_PREFIX="m920x-"
# la prima versione con la board, rc comprese: la v1.3.10 e le sue rc, gia'
# in corso, restano del solo W541 (tools/build.sh --board all, tools/ci.sh)
BOARD_SINCE=v1.4.0
BOARD_TREE=m920x
board_defconfig() { printf 'boards/m920x/%s.defconfig' "$1"; }
# il boot splash con la macchina: tools/logo.py splash OUT "THINKCENTRE M920X"
BOARD_TREE_FILES=(boards/m920x/blobs/ifd.bin boards/m920x/blobs/gbe.bin
	boards/m920x/blobs/me.bin boards/m920x/flash.fmd:m920x.fmd
	assets/bootsplash-m920x.bmp:bootsplash.bmp)
BOARD_SUMS=(boards/m920x/blobs/SHA256SUMS)
# W25Q128JV (BIOS1) e W25Q64JV (BIOS2): la RO e lo slot B nel secondo
BOARD_ROM_SIZE=$((24 << 20))
BOARD_CHIPS=("16mb 0 $((16 << 20))" "8mb $((16 << 20)) $((8 << 20))")
BOARD_BOOT_CHIP=8mb
BOARD_INTEL_SIZE=$((0xc00000))
# i primi 12 MiB attesi: lo SHA-256 di IFD (sbloccato), GbE e ME di
# boards/m920x/blobs/ come li mette la build (verify-rom.sh)
BOARD_REFERENCE=boards/m920x/intel.sha256
BOARD_RO_INTERFACE=boards/m920x/ro-interface.txt
# Coffee Lake e Coffee Lake Refresh (S, 6+2, 8+2)
BOARD_CPUIDS=(906ea 906eb 906ec 906ed)
# i file CBFS che ogni slot RW deve avere oltre a stage, payload, DSDT,
# VBT, microcode e config (verify-rom.sh): FSP-M e FSP-S
BOARD_SLOT_FILES=(fspm.bin fsps.bin)
# le regioni che scrive la capsula (tools/build.sh, CAPSULE_REGIONS sul
# W541): solo i due slot, il payload scrive quello che non gira. Il training
# della RAM resta, e non si rifa' a ogni aggiornamento (21-36 s): coreboot lo
# rifa' quando cambia la sua versione, la revisione di FSP-M dello slot con
# il byte basso (il numero di build) al posto di processore e
# Hyper-Threading (patch 0173). Non la cambiano le UPD di FSP-M che mette
# coreboot (soc/intel/cannonlake/romstage/fsp_params.c, romstage.c della
# board): una release che le cambia alza fsp_memory_soc_version() (i bit
# 3:0, liberi), o rimette qui RW_MRC_CACHE. Dalla v1.4.0-rc4; le capsule
# rc1-rc3 scrivono anche RW_MRC_CACHE (tools/update.py)
BOARD_CAPSULE_REGIONS=(RW_SECTION_A RW_SECTION_B)
BOARD_GBE=boards/m920x/blobs/gbe.bin
BOARD_VBIOS=""
BOARD_OPVK=""
# la ME resta intera (niente me_cleaner); lo schermo acceso anche con vboot
BOARD_CONFIG_WANT=(CONFIG_BOARD_LENOVO_M920X=y 'CONFIG_FMDFILE="m920x/m920x.fmd"'
	CONFIG_LENOVO_M920_VBOOT_MINIMAL_RO=y CONFIG_VBOOT_ALWAYS_ENABLE_DISPLAY=y)
