#!/bin/bash
# edk2-patchcheck.sh - lo stile del codice di EDK II sulle patch di
# patches/edk2 dell'autore del progetto, con BaseTools/Scripts/PatchCheck.py
# dell'albero di TianoCore (fine riga CRLF, niente tab ne' spazi in fondo,
# intestazioni dei file...), come lo controlla la CI di TianoCore.
#
#   tools/edk2-patchcheck.sh [EDK2]     EDK2: un albero di TianoCore (default
#                                       quello di tools/build.sh prepare)
#
# Conta solo il codice ("The code passed all checks."): il messaggio non
# passa mai, perche' il Signed-off-by lo aggiunge l'autore quando manda la
# patch upstream. patches/lvglpkg resta fuori: LvglPkg ha le sue regole (fine
# riga LF).
set -u

O="$(cd "$(dirname "$0")/.." && pwd)"
E="${1:-${O}/work/coreboot/payloads/external/edk2/workspace/tianocore}"
AUTHOR="Domenico D'Arrigo <d.darrigo@outlook.it>"
PC="${E}/BaseTools/Scripts/PatchCheck.py"
gh() {
	if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "$*"; fi
}

[ -f "${PC}" ] || { echo "edk2-patchcheck.sh: ${PC} non c'e'" >&2; exit 2; }

n=0 own=0 bad=0 out="$(mktemp)"
while read -r p; do
	n=$((n + 1))
	f="${O}/patches/edk2/${p}"
	[ "$(sed -n 's/^From: //p' "${f}" | head -1)" = "${AUTHOR}" ] || continue
	own=$((own + 1))
	python3 "${PC}" "${f}" > "${out}" 2>&1
	if ! grep -q "^The code passed all checks\.$" "${out}"; then
		echo "  ${p}: il codice non passa PatchCheck.py"
		sed -n '/^Code format is not valid:/,$p' "${out}" | head -20 | sed 's/^/    /'
		gh "::error file=patches/edk2/${p},title=PatchCheck.py::il codice della patch non passa PatchCheck.py di EDK II (vedi il log)"
		bad=$((bad + 1))
	fi
done < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "${O}/patches/edk2/series" | sed '/^$/d')
rm -f "${out}"
echo "  ${own} patch del progetto su ${n} in patches/edk2, ${bad} con il codice fuori stile"
[ "${bad}" = 0 ]
