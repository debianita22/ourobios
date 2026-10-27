#!/usr/bin/env bash
# q35-cfr-rom.sh - la ROM coreboot per QEMU q35 delle schermate del setup
# (tools/qemu-setup-shots.py): il payload EDK2 di una build del W541, come
# nella prova di fumo (tools/build.sh smoke), e la CFR da un file CBFS
# cfr.bin (patches/test/q35-cfr-file.patch), che qemu-setup-shots.py --cfr
# mette nella sua copia della ROM. Va rifatta solo quando cambia il payload:
# il menu cambia con il cfr.bin (tools/cfr-dump.sh).
#
#   tools/q35-cfr-rom.sh [-r LxA] WORKTREE BUILD
#
# WORKTREE e' un albero coreboot (un worktree, non quello delle ROM del
# W541) con patches/test/q35-cfr-file.patch e vboot in 3rdparty/vboot; la
# build va in WORKTREE/build-q35-cfr (coreboot.rom, make.log; con -r
# un'altra risoluzione, in build-q35-cfr-LxA). BUILD e' la
# build del W541 di cui si prendono UEFIPAYLOAD.fd (copiato in build-q35-cfr,
# che non cambia se BUILD si rifa' durante la build) e GUID, LSV e
# versione dell'ESRT, come sul W541: senza, FmpDxe del payload si ferma.
# -r: la risoluzione di coreboot (default 1920x1080, quella delle schermate).
# Serve la toolchain dell'host di coreboot (CONFIG_ANY_TOOLCHAIN) nel PATH.
set -euo pipefail

die() {
	echo "q35-cfr-rom: $*" >&2
	exit 1
}

res=1920x1080
while getopts r:h opt; do
	case "${opt}" in
		r) res="${OPTARG}" ;;
		*) echo "uso: $0 [-r LxA] WORKTREE BUILD" >&2; exit 2 ;;
	esac
done
shift $((OPTIND - 1))
[ $# = 2 ] || { echo "uso: $0 [-r LxA] WORKTREE BUILD" >&2; exit 2; }
wt="$(cd "$1" && pwd)" || die "$1: non trovato"
build="$(cd "$2" && pwd)" || die "$2: non trovata"

[ -f "${wt}/src/mainboard/emulation/qemu-q35/cfr.c" ] \
	|| die "${wt}: manca patches/test/q35-cfr-file.patch (git -C ${wt} apply ...)"
[ -f "${build}/UEFIPAYLOAD.fd" ] || die "${build}: manca UEFIPAYLOAD.fd (prima la build del W541)"
cfg() { sed -n "s/^CONFIG_$1=\(.*\)$/\1/p" "${build}/.config"; }
guid="$(cfg DRIVERS_EFI_MAIN_FW_GUID)"
lsv="$(cfg DRIVERS_EFI_MAIN_FW_LSV)"
ver="$(cfg DRIVERS_EFI_MAIN_FW_VERSION)"
lv="$(cfg LOCALVERSION | tr -d '"')"
[ -n "${guid}" ] && [ -n "${lsv}" ] && [ -n "${ver}" ] || die "${build}/.config: niente GUID, LSV o versione dell'ESRT"
x="${res%x*}"
y="${res#*x}"

# KERNELVERSION come le build del W541: la versione di coreboot del loro build.h
kv="$(sed -n 's/^#define COREBOOT_VERSION "\(.*\)"$/\1/p' "${build}/build.h" 2>/dev/null)"
[ -n "${kv}" ] || kv="$(git -C "${wt}" describe --always 2>/dev/null || echo unknown)"

b="build-q35-cfr"
[ "${res}" = 1920x1080 ] || b+="-${res}"
o="${wt}/${b}"
rm -rf "${o:?}"
mkdir -p "${o}"
cp "${build}/UEFIPAYLOAD.fd" "${o}/UEFIPAYLOAD.fd"
{
	echo "CONFIG_VENDOR_EMULATION=y"
	echo "CONFIG_BOARD_EMULATION_QEMU_X86_Q35=y"
	echo "CONFIG_CPU_QEMU_X86_TSEG_SMM=y"
	echo "CONFIG_SMMSTORE=y"
	echo "CONFIG_PAYLOAD_ELF=y"
	echo "CONFIG_PAYLOAD_FILE=\"${o}/UEFIPAYLOAD.fd\""
	echo "CONFIG_GENERIC_LINEAR_FRAMEBUFFER=y"
	echo "CONFIG_DRIVERS_EMULATION_QEMU_XRES=${x}"
	echo "CONFIG_DRIVERS_EMULATION_QEMU_YRES=${y}"
	echo "CONFIG_DRIVERS_EFI_FW_INFO=y"
	echo "CONFIG_DRIVERS_EFI_MAIN_FW_GUID=${guid}"
	echo "CONFIG_DRIVERS_EFI_MAIN_FW_LSV=${lsv}"
	echo "CONFIG_DRIVERS_EFI_MAIN_FW_VERSION=${ver}"
	echo "CONFIG_LOCALVERSION=\"${lv}-q35\""
	echo "CONFIG_DRIVERS_OPTION_CFR=y"
	echo "CONFIG_ANY_TOOLCHAIN=y"
} > "${o}/defconfig"
mk() {
	make -C "${wt}" obj="${b}" DOTCONFIG="${b}/.config" \
		UPDATED_SUBMODULES=1 KERNELVERSION="${kv}" "$@"
}
mk defconfig KBUILD_DEFCONFIG="${b}/defconfig" > "${o}/defconfig.log" 2>&1 \
	|| { cat "${o}/defconfig.log"; die "make defconfig fallito"; }
while IFS= read -r line; do
	grep -qxF -- "${line}" "${o}/.config" || die "il .config non ha ${line} (dipendenze?)"
done < "${o}/defconfig"
if ! mk -j"$(nproc)" > "${o}/make.log" 2>&1; then
	grep -n -i -B2 -A6 'error' "${o}/make.log" | tail -n 40 || true
	die "build fallita (${o}/make.log)"
fi
echo "q35-cfr-rom: ${o}/coreboot.rom (payload di ${build}, ${res})"
