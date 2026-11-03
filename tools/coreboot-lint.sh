#!/bin/bash
# coreboot-lint.sh - lo stile di coreboot sulla serie di patches/, come lo
# chiede Gerrit: i lint stabili di coreboot (util/lint/lint lint-stable, gli
# stessi di Jenkins) sull'albero con la serie applicata, e checkpatch.pl, con
# la configurazione dell'albero (.checkpatch.conf), su ogni patch della serie
# che ha per autore quello del progetto (le altre sono backport e tengono lo
# stile di upstream).
#
#   tools/coreboot-lint.sh [ALBERO]     ALBERO: coreboot con la serie
#                                       applicata (default work/coreboot,
#                                       quello di tools/build.sh prepare)
#
# Ferma: un lint stabile che non passa, o un ERROR di checkpatch, salvo
# "Missing Signed-off-by" (lo aggiunge l'autore quando manda la patch
# upstream) e quelli di patches/checkpatch-known.txt. I WARNING si contano
# per tipo e si scrivono, senza fermare.
set -u

O="$(cd "$(dirname "$0")/.." && pwd)"
T="${1:-${O}/work/coreboot}"
AUTHOR="Domenico D'Arrigo <d.darrigo@outlook.it>"
KNOWN="${O}/patches/checkpatch-known.txt"
# le annotazioni di GitHub Actions, solo li'
gh() {
	if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "$*"; fi
}

[ -f "${T}/util/lint/checkpatch.pl" ] || { echo "coreboot-lint.sh: ${T} non e' un albero di coreboot" >&2; exit 2; }

fail=0
echo "==> lint-stable di coreboot in ${T}"
if ! (cd "${T}" && util/lint/lint lint-stable); then
	gh "::error title=coreboot lint-stable::un lint stabile non passa sull'albero con la serie (vedi il log)"
	fail=1
fi

echo "==> checkpatch.pl sulle patch del progetto"
known() {
	# "<file della patch> <TIPO>" in patches/checkpatch-known.txt
	[ -f "${KNOWN}" ] && sed -e 's/#.*//' -e 's/[[:space:]]*$//' "${KNOWN}" | grep -qxF "$1 $2"
}
n=0 own=0 errs=0 tmp="$(mktemp)"
declare -A warn=()
while read -r p; do
	n=$((n + 1))
	f="${O}/patches/${p}"
	[ "$(sed -n 's/^From: //p' "${f}" | head -1)" = "${AUTHOR}" ] || continue
	own=$((own + 1))
	(cd "${T}" && perl util/lint/checkpatch.pl --terse --show-types "${f}") > "${tmp}" 2>&1
	while IFS= read -r line; do
		# <file>:<riga>: <ERROR|WARNING|CHECK>:<TIPO>: <messaggio>
		[[ "${line}" =~ :([0-9]+):\ (ERROR|WARNING|CHECK):([A-Z0-9_]+):\ (.*)$ ]] || continue
		ln="${BASH_REMATCH[1]}" kind="${BASH_REMATCH[2]}" type="${BASH_REMATCH[3]}" msg="${BASH_REMATCH[4]}"
		if [ "${kind}" = ERROR ]; then
			[ "${type}" = MISSING_SIGN_OFF ] && continue
			known "${p}" "${type}" && continue
			echo "  ERROR ${p}:${ln}: ${type}: ${msg}"
			gh "::error file=patches/${p},line=${ln},title=checkpatch ${type}::${msg}"
			errs=$((errs + 1))
		else
			warn[${type}]=$(( ${warn[${type}]:-0} + 1 ))
		fi
	done < "${tmp}"
done < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "${O}/patches/series" | sed '/^$/d')
rm -f "${tmp}"
echo "  ${own} patch del progetto su ${n}, ${errs} errori nuovi"
for t in "${!warn[@]}"; do echo "  WARNING ${t}: ${warn[${t}]}"; done | sort
[ "${errs}" = 0 ] || fail=1
exit "${fail}"
