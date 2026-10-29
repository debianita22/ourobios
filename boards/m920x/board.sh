# shellcheck shell=bash
# La board di tools/build.sh, tools/verify-rom.sh e tools/ci-check.sh
# (--board m920x): ThinkCentre M920x Tiny (docs/m920x.md).

BOARD_NAME="ThinkCentre M920x Tiny"
# una variante, la RAM init di FSP-M; le release: vX.Y.Z-m920x-fsp
BOARD_VARIANTS=(fsp)
BOARD_FLAVOUR_PREFIX="m920x-"
BOARD_TREE=m920x
board_defconfig() { printf 'boards/m920x/%s.defconfig' "$1"; }
BOARD_TREE_FILES=(boards/m920x/blobs/ifd.bin boards/m920x/blobs/gbe.bin
	boards/m920x/blobs/me.bin boards/m920x/flash.fmd:m920x.fmd)
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
BOARD_GBE=boards/m920x/blobs/gbe.bin
BOARD_VBIOS=""
BOARD_OPVK=""
# la ME resta intera (niente me_cleaner); lo schermo acceso anche con vboot
BOARD_CONFIG_WANT=(CONFIG_BOARD_LENOVO_M920X=y 'CONFIG_FMDFILE="m920x/m920x.fmd"'
	CONFIG_LENOVO_M920_VBOOT_MINIMAL_RO=y CONFIG_VBOOT_ALWAYS_ENABLE_DISPLAY=y)
