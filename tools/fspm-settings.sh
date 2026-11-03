#!/bin/bash
# fspm-settings.sh - le impostazioni della memoria che coreboot passa a FSP-M
# (le UPD), da cui dipende il training salvato in RW_MRC_CACHE, sulle board
# che lo tengono da un aggiornamento all'altro (BOARD_FSPM_SETTINGS di
# board.sh: il M920x, la cui capsula non scrive RW_MRC_CACHE). La versione
# della cache cambia da sola con FSP-M, il processore e Hyper-Threading
# (patch 0173), non con quello che sceglie coreboot: un cambio dei file che
# mettono quelle UPD ferma la CI finche' qualcuno non lo ha guardato.
#
#   tools/fspm-settings.sh [ALBERO]           controlla (check.yml)
#   tools/fspm-settings.sh --update [ALBERO]  riscrive gli SHA-256 dei file,
#                                             dopo averli guardati
#
# ALBERO: coreboot con la serie applicata (default work/coreboot, quello di
# tools/build.sh prepare). Il file della board (boards/m920x/fspm-settings.txt)
# ha la versione delle impostazioni, che e' CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION
# di ogni defconfig della board (patch 0222, i bit 3:0 della versione della
# cache), e lo SHA-256 di ogni file. Quando un file cambia:
#   - se cambiano le UPD della memoria, o quello che le decide (devicetree),
#     si alza la versione nei defconfig e nel file, poi --update: il primo
#     avvio dopo l'aggiornamento rifa' il training;
#   - se no (altre UPD, commenti), basta --update.
set -euo pipefail

O="$(cd "$(dirname "$0")/.." && pwd)"
update=0
if [ "${1:-}" = --update ]; then update=1; shift; fi
T="${1:-${O}/work/coreboot}"
gh() {
	if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "$*"; fi
}
[ -d "${T}/src/drivers/intel/fsp2_0" ] || { echo "fspm-settings.sh: ${T} non e' un albero di coreboot" >&2; exit 2; }

fail=0
for b in "${O}"/boards/*/board.sh; do
	board="$(basename "$(dirname "${b}")")"
	# in una subshell, come board_get di tools/ci.sh
	# shellcheck source=/dev/null
	f="$(. "${b}"; printf '%s' "${BOARD_FSPM_SETTINGS:-}")"
	[ -n "${f}" ] || continue
	# shellcheck source=/dev/null
	mapfile -t defconfigs < <(. "${b}"; for v in "${BOARD_VARIANTS[@]}"; do board_defconfig "${v}"; echo; done)
	file="${O}/${f}"
	[ -f "${file}" ] || { echo "  ${board}: ${f} non c'e'"; fail=1; continue; }
	version="$(sed -n 's/^version \([0-9]\{1,2\}\)$/\1/p' "${file}")"
	[ -n "${version}" ] || { echo "  ${f}: nessuna riga version"; fail=1; continue; }
	for d in "${defconfigs[@]}"; do
		[ -n "${d}" ] || continue
		have="$(sed -n 's/^CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION=\([0-9]\{1,2\}\)$/\1/p' "${O}/${d}")"
		if [ "${have}" != "${version}" ]; then
			echo "  ${d}: CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION '${have}', ${f} dice ${version}"
			gh "::error file=${d},title=fspm-settings::CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION '${have}', ${f} dice ${version}"
			fail=1
		fi
	done
	changed=0 tmp="$(mktemp)"
	while IFS= read -r line; do
		if [[ "${line}" =~ ^sha256\ ([0-9a-f]{64})\ (.+)$ ]]; then
			want="${BASH_REMATCH[1]}" path="${BASH_REMATCH[2]}"
			if [ ! -f "${T}/${path}" ]; then
				echo "  ${board}: ${path} non c'e' nell'albero"
				gh "::error file=${f},title=fspm-settings::${path} non c'e' nell'albero con la serie"
				fail=1
				echo "${line}" >> "${tmp}"
				continue
			fi
			got="$(sha256sum "${T}/${path}" | cut -d' ' -f1)"
			if [ "${got}" != "${want}" ]; then
				changed=$((changed + 1))
				echo "  ${board}: ${path} cambiato"
			fi
			echo "sha256 ${got} ${path}" >> "${tmp}"
		else
			echo "${line}" >> "${tmp}"
		fi
	done < "${file}"
	if [ "${changed}" = 0 ]; then
		echo "  ok  ${board}: le impostazioni di FSP-M sono quelle guardate (versione ${version})"
	elif [ "${update}" = 1 ]; then
		cp "${tmp}" "${file}"
		echo "  ${board}: ${changed} file riscritti in ${f}, versione ${version}"
	else
		echo "  ${board}: ${changed} file delle UPD di FSP-M cambiati: se cambia la memoria, alzare"
		echo "      CONFIG_FSP_MEMORY_SETTINGS_SOC_VERSION nei defconfig e la riga version; poi"
		echo "      tools/fspm-settings.sh --update"
		gh "::error file=${f},title=fspm-settings::${changed} file delle UPD di FSP-M cambiati: la versione del training (${version}) va alzata se cambiano le impostazioni della memoria, poi tools/fspm-settings.sh --update"
		fail=1
	fi
	rm -f "${tmp}"
done
exit "${fail}"
