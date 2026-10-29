# shellcheck shell=bash
# La board di tools/build.sh, tools/verify-rom.sh e tools/ci-check.sh
# (--board w541, il default): ThinkPad W541. I suoi file stanno dove
# stavano prima delle altre board (configs/, blobs/): i nomi delle ROM,
# delle release e dei GUID non cambiano.

BOARD_NAME="ThinkPad W541"
# le varianti (RAM init), e il nome delle release: vX.Y.Z-<prefisso><variante>
BOARD_VARIANTS=(mrc nri)
BOARD_FLAVOUR_PREFIX=""
# la cartella dell'albero coreboot dove li cercano i defconfig
BOARD_TREE=w541
# il defconfig della variante $1
board_defconfig() { printf 'configs/w541-%s.defconfig' "$1"; }
# i file che vanno nella cartella dell'albero, "sorgente[:nome]"
BOARD_TREE_FILES=(blobs/ifd.bin blobs/gbe.bin blobs/me.bin blobs/mrc.bin
	blobs/vbios_10de_11fc_1.rom configs/w541.fmd)
# i checksum dei blob (sha256sum -c dalla loro cartella)
BOARD_SUMS=(blobs/SHA256SUMS)
# il flash: dimensione e chip, "nome offset dimensione" (i file
# <rom>-<nome>-chip.rom di dist/), e il chip che avvia da solo (RO e slot B)
BOARD_ROM_SIZE=$((12 << 20))
BOARD_CHIPS=("8mb 0 $((8 << 20))" "4mb $((8 << 20)) $((4 << 20))")
BOARD_BOOT_CHIP=4mb
# IFD, GbE e ME: i byte prima della regione BIOS, che una build non cambia
BOARD_INTEL_SIZE=$((0x500000))
# l'immagine con quei byte attesi (verify-rom.sh), costruita dagli stessi blob
BOARD_REFERENCE=legacy/coreboot-4.22/coreboot.rom
# l'interfaccia della parte RO gia' sulle macchine (docs/vboot.md)
BOARD_RO_INTERFACE=configs/ro-interface.txt
# il CPUID per cui ci deve essere il microcode
BOARD_CPUIDS=(306c3)
# le risoluzioni della prova di fumo (smoke): tutta a 1920x1080, il solo
# setup alle altre (il pannello 3K, con gfx_fb_limit)
BOARD_SMOKE_SIZES=(1920x1080 2880x1620)
# i file CBFS che ogni slot RW deve avere oltre a stage, payload, DSDT,
# VBT, microcode e config (verify-rom.sh): il VBIOS NVIDIA
BOARD_SLOT_FILES=(pci10de,11fc.rom)
# i blob che verify-rom.sh confronta con la ROM: GbE, VBIOS NVIDIA (nome
# CBFS:file) e la chiave Optimus nel DSDT
BOARD_GBE=blobs/gbe.bin
BOARD_VBIOS=pci10de,11fc.rom:blobs/vbios_10de_11fc_1.rom
BOARD_OPVK=blobs/opvk.inc
# le righe che il .config della ROM deve avere, oltre a quelle comuni
# (verify-rom.sh); le varianti mrc e nri le controlla verify-rom.sh
BOARD_CONFIG_WANT=(CONFIG_BOARD_LENOVO_THINKPAD_W541=y 'CONFIG_FMDFILE="w541/w541.fmd"'
	CONFIG_VGA_BIOS_DGPU=y CONFIG_USE_ME_CLEANER=y CONFIG_LENOVO_HASWELL_VBOOT_MINIMAL_RO=y)
