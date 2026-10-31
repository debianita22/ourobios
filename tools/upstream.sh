#!/bin/bash
# upstream.sh - coreboot o EDK2 si sono mossi dal pin? Lo lancia
# .github/workflows/upstream.yml ogni settimana. Solo avvisi: un issue per
# ciascuno, aggiornato a ogni giro e chiuso quando non c'e' piu' niente da
# fare. I pin si spostano a mano.
#
#   tools/upstream.sh coreboot [--dry-run]
#   tools/upstream.sh edk2 [--dry-run]
#   tools/upstream.sh mirror [--dry-run]
#
# coreboot  la serie di patches/ applica ancora su main? Qualche patch e' gia'
#           entrata upstream (stesso Subject)? C'e' un tag di release dopo il
#           pin? Se si', issue "coreboot: ...".
# edk2      il ramo uefipayload_AAMM piu' recente di MrChromebox e' andato
#           oltre il commit pinnato nei defconfig? Se si', issue "EDK2: ...".
# mirror    i commit di EDK2 e LvglPkg di configs/edk2-pins.txt hanno il loro
#           tag pin-<12 cifre> nei fork del progetto (EDK2_MIRROR e
#           LVGLPKG_MIRROR di tools/build.sh)? Se no, issue "Mirror: ...".
#
# Con --dry-run scrive soltanto cosa farebbe (niente issue).
set -euo pipefail
O="$(cd "$(dirname "$0")/.." && pwd)"
WHAT="${1:-}"
DRY=no
[ "${2:-}" = "--dry-run" ] && DRY=yes

note() { if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::$1 title=${WHAT}::$2"; fi; echo "$2"; }
die()  { note error "$*"; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pin() { sed -n "s/^$1=\"\([^\"]*\)\".*/\1/p" "${O}/tools/build.sh"; }

# L'issue aperto con il titolo che comincia per $1, se c'e'
open_issue() {
	W541_PREFIX="$1" gh issue list --state open --search "\"$1\" in:title" --json number,title \
		--jq '[.[] | select(.title | startswith(env.W541_PREFIX))][0].number // empty'
}

# Apre o aggiorna l'issue ($1 prefisso, $2 titolo, $3 testo)
report() {
	local num
	if [ "${DRY}" = yes ]; then
		note notice "$2 (prova: nessun issue)"
		printf '%s\n' "$3"
		return 0
	fi
	num="$(open_issue "$1")"
	if [ -n "${num}" ]; then
		gh issue edit "${num}" --title "$2" --body "$3" > /dev/null
		note notice "$2: issue #${num} aggiornato"
	else
		gh issue create --title "$2" --body "$3" > /dev/null
		note notice "$2: issue aperto"
	fi
}

# Chiude l'issue con prefisso $1, se c'e' ($2 il commento)
settle() {
	local num
	note notice "$2"
	[ "${DRY}" = no ] || return 0
	num="$(open_issue "$1")"
	if [ -n "${num}" ]; then gh issue close "${num}" --comment "$2" > /dev/null; fi
}

check_coreboot() {
	local repo commit desc base head tag newtag="" work="${TMP}" ahead when p sub stop="" merged=()
	repo="$(pin COREBOOT_REPO)"
	commit="$(pin COREBOOT_COMMIT)"
	desc="$(pin COREBOOT_DESCRIBE)"
	[ -n "${repo}" ] && [ -n "${commit}" ] && [ -n "${desc}" ] || die "pin di coreboot non trovato in tools/build.sh"
	base="${desc%%-*}"
	head="$(git ls-remote "${repo}" refs/heads/main | cut -f1)"
	[ -n "${head}" ] || die "main non trovato in ${repo}"
	# l'ultimo tag di release (YY.MM), se e' dopo quello del pin
	tag="$(git ls-remote --tags "${repo}" | sed -n 's|.*refs/tags/\([0-9][0-9]\.[0-9][0-9]\(\.[0-9]*\)\{0,1\}\)$|\1|p' | sort -V | tail -n 1)"
	if [ -n "${tag}" ] && [ "${tag}" != "${base}" ] && [ "$(printf '%s\n' "${tag}" "${base}" | sort -V | tail -n 1)" = "${tag}" ]; then
		newtag="${tag}"
	fi
	if [ "${head}" = "${commit}" ]; then
		settle "coreboot:" "coreboot main e' al commit pinnato (${commit:0:12})"
		return 0
	fi

	# main dalla data del pin: i soggetti per le patch gia' upstream e
	# l'albero su cui provare la serie
	when="$(gh api "repos/coreboot/coreboot/commits/${commit}" --jq .commit.committer.date)"
	git init -q "${work}/cb"
	git -C "${work}/cb" fetch -q --shallow-since="${when}" "${repo}" main
	git -C "${work}/cb" checkout -q --detach FETCH_HEAD
	ahead="$(git -C "${work}/cb" rev-list --count HEAD)"
	git -C "${work}/cb" log --format=%s HEAD > "${work}/subjects"

	export GIT_COMMITTER_NAME="ourobios" GIT_COMMITTER_EMAIL="ourobios@users.noreply.github.com"
	while read -r p; do
		# il Subject della mail, anche se va a capo, senza [PATCH]
		sub="$(sed -n '/^Subject: /{:a;N;/\n[^ ]/!ba;p;q}' "${O}/patches/${p}" | sed '$d' | tr -d '\n' \
			| sed 's/^Subject: \(\[PATCH[^]]*\] \)\{0,1\}//; s/^ *//')"
		if grep -qxF -- "${sub}" "${work}/subjects"; then merged+=("${p}: ${sub}"); fi
		if [ -z "${stop}" ] && ! git -C "${work}/cb" am -q "${O}/patches/${p}" > /dev/null 2>&1; then
			git -C "${work}/cb" am --abort > /dev/null 2>&1 || true
			stop="${p}"
		fi
	done < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "${O}/patches/series" | sed '/^$/d')

	if [ -z "${stop}" ] && [ ${#merged[@]} -eq 0 ] && [ -z "${newtag}" ]; then
		settle "coreboot:" "coreboot main (${head:0:12}, ~${ahead} commit dopo il pin): la serie applica, nessuna patch upstream, nessun tag nuovo"
		return 0
	fi
	local title="coreboot:" body
	[ -z "${newtag}" ] || title+=" release ${newtag},"
	[ -z "${stop}" ] || title+=" la serie si ferma a ${stop%%-*},"
	[ ${#merged[@]} -eq 0 ] || title+=" ${#merged[@]} patch upstream,"
	title="${title%,}"
	body="$(
		echo "coreboot \`main\` e' a \`${head:0:12}\`, circa ${ahead} commit dopo il pin \`${desc}\` (\`tools/build.sh\`)."
		echo
		if [ -n "${newtag}" ]; then echo "- **Release nuova**: \`${newtag}\` (il pin e' su \`${base}\`)."; fi
		if [ -n "${stop}" ]; then
			echo "- **La serie non applica su main**: si ferma a \`${stop}\` (le patch prima applicano)."
		else
			echo "- La serie di \`patches/series\` applica su main."
		fi
		if [ ${#merged[@]} -gt 0 ]; then
			echo "- **Gia' upstream** (stesso Subject su main), da togliere dalla serie:"
			printf '  - `%s`\n' "${merged[@]}"
		fi
		echo
		echo "Per spostare il pin (a mano):"
		echo "1. \`COREBOOT_COMMIT\` e \`COREBOOT_DESCRIBE\` (\`git describe --abbrev=12\`) in \`tools/build.sh\`;"
		echo "2. le patch ribasate e riesportate con \`git format-patch --zero-commit\`, \`patches/series\` aggiornato;"
		echo "3. \`tools/build.sh prepare config\`, poi push su un ramo \`ci-test/...\` per la build di prova;"
		echo "4. se e' verde, merge e una release (pre-release finche' non e' provata sul portatile)."
		echo
		echo "Questo issue lo aggiorna e lo chiude \`upstream.yml\`."
	)"
	report "coreboot:" "${title}" "${body}"
}

check_edk2() {
	local rev branch head cmp status ahead behind last
	rev="$(sed -n 's/^CONFIG_EDK2_TAG_OR_REV="\([0-9a-f]\{40\}\)"$/\1/p' "${O}/configs/w541-mrc.defconfig")"
	[ -n "${rev}" ] || die "CONFIG_EDK2_TAG_OR_REV (un commit) non trovato in configs/w541-mrc.defconfig"
	# i rami delle release di MrChromebox: uefipayload_AAMM (i vecchi AAAAMM,
	# _redux, _rwl_* e gli altri no)
	branch="$(git ls-remote --heads https://github.com/mrchromebox/edk2.git 'uefipayload_*' \
		| sed -n 's|.*refs/heads/\(uefipayload_[0-9]\{4\}\)$|\1|p' | sort -V | tail -n 1)"
	[ -n "${branch}" ] || die "nessun ramo uefipayload_* in mrchromebox/edk2"
	head="$(git ls-remote --heads https://github.com/mrchromebox/edk2.git "refs/heads/${branch}" | cut -f1)"
	if [ "${head}" = "${rev}" ]; then
		settle "EDK2:" "EDK2: ${branch} e' al commit pinnato (${rev:0:12})"
		return 0
	fi
	cmp="$(gh api "repos/mrchromebox/edk2/compare/${rev}...${head}" \
		--jq '"\(.status) \(.ahead_by) \(.behind_by)\n" + ([.commits[-15:] | reverse | .[] | "- `\(.sha[0:12])` \(.commit.message | split("\n")[0])"] | join("\n"))')"
	read -r status ahead behind <<< "$(head -n 1 <<< "${cmp}")"
	last="$(tail -n +2 <<< "${cmp}")"
	local title body
	if [ "${status}" = ahead ]; then
		title="EDK2: ${branch}, ${ahead} commit dopo il pin"
	else
		title="EDK2: ${branch} non contiene il pin (${status}, +${ahead}/-${behind})"
	fi
	body="$(cat <<EOF
MrChromebox \`${branch}\` e' a \`${head:0:12}\`; i defconfig sono pinnati a \`${rev:0:12}\` (\`CONFIG_EDK2_TAG_OR_REV\`).
Confronto: ${status}, ${ahead} commit avanti, ${behind} indietro.

Gli ultimi:
${last}

Per spostare il pin (a mano): \`CONFIG_EDK2_TAG_OR_REV\` in tutti e due i defconfig, poi push su un ramo \`ci-test/...\` per la build di prova; prima di una release, prova sul portatile (boot, menu di setup, variabili UEFI in SMMSTORE, S3).

Questo issue lo aggiorna e lo chiude \`upstream.yml\`.
EOF
)"
	report "EDK2:" "${title}" "${body}"
}

# I commit di EDK2 e di LvglPkg pinnati (configs/edk2-pins.txt) nei mirror
# del progetto (EDK2_MIRROR e LVGLPKG_MIRROR di tools/build.sh): per ognuno
# il tag pin-<12 cifre>, perche' MrChromebox riscrive i suoi rami e un commit
# tolto dal ramo non arriva piu' con un clone. Controlla anche che il
# submodule LvglPkg del commit di EDK2 sia quello della lista.
check_mirror() {
	local em lm pins e l r got sub repo missing="" seen=" " n=0
	em="$(sed -n 's/^EDK2_MIRROR="\([^"]*\)".*/\1/p' "${O}/tools/build.sh")"
	lm="$(sed -n 's/^LVGLPKG_MIRROR="\([^"]*\)".*/\1/p' "${O}/tools/build.sh")"
	pins="${O}/configs/edk2-pins.txt"
	[ -n "${em}" ] && [ -n "${lm}" ] || die "EDK2_MIRROR o LVGLPKG_MIRROR non trovati in tools/build.sh"
	[ -f "${pins}" ] || die "configs/edk2-pins.txt non c'e'"
	while read -r e l r; do
		case "${e}" in ''|'#'*) continue ;; esac
		n=$((n + 1))
		got="$(GIT_TERMINAL_PROMPT=0 git ls-remote "${em}" "refs/tags/pin-${e:0:12}" 2>/dev/null | cut -f1 || true)"
		if [ "${got}" != "${e}" ]; then
			missing="${missing}- EDK2 \`${e:0:12}\` (${r}): tag \`pin-${e:0:12}\` ${got:+su \`${got:0:12}\`}${got:-assente} in ${em}
"
		fi
		# un commit di LvglPkg una volta sola, anche se piu' pin lo usano
		if [ "${seen#* "${l}" }" = "${seen}" ]; then
			seen="${seen}${l} "
			got="$(GIT_TERMINAL_PROMPT=0 git ls-remote "${lm}" "refs/tags/pin-${l:0:12}" 2>/dev/null | cut -f1 || true)"
			if [ "${got}" != "${l}" ]; then
				missing="${missing}- LvglPkg \`${l:0:12}\`: tag \`pin-${l:0:12}\` ${got:+su \`${got:0:12}\`}${got:-assente} in ${lm}
"
			fi
		fi
		# il submodule del commit di EDK2, dal mirror o da MrChromebox (un 404
		# scrive il suo JSON su stdout: vale solo un commit intero)
		sub=""
		for repo in "${em#https://github.com/}" mrchromebox/edk2; do
			sub="$(gh api "repos/${repo}/contents/LvglPkg?ref=${e}" --jq .sha 2>/dev/null || true)"
			[[ "${sub}" =~ ^[0-9a-f]{40}$ ]] && break
			sub=""
		done
		if [ -n "${sub}" ] && [ "${sub}" != "${l}" ]; then
			missing="${missing}- EDK2 \`${e:0:12}\`: il submodule LvglPkg e' \`${sub:0:12}\`, non \`${l:0:12}\` come in configs/edk2-pins.txt
"
		fi
	done < "${pins}"
	if [ -z "${missing}" ]; then
		settle "Mirror:" "Mirror: i ${n} commit pinnati di EDK2 e LvglPkg hanno il loro tag"
		note notice "Mirror: ${n} commit pinnati, tutti con il tag pin-<12 cifre> nei mirror"
		return 0
	fi
	local body
	body="$(cat <<EOF
Nei mirror del progetto mancano dei tag dei commit pinnati (\`configs/edk2-pins.txt\`):

${missing}
Senza il tag, una build di quei commit dipende da MrChromebox: se il commit non e' piu' sul suo ramo, \`tools/build.sh\` lo trova solo finche' GitHub lo da' per hash.

Per aggiungerli (il fork, se non c'e': \`gh repo fork mrchromebox/edk2 --clone=false --default-branch-only\`, e lo stesso per \`MrChromebox/LvglPkg\`):

\`\`\`sh
git clone --bare --filter=blob:none https://github.com/mrchromebox/edk2 edk2.git
git -C edk2.git fetch origin <commit>
git -C edk2.git push ${em} <commit>:refs/tags/pin-<prime 12 cifre>
\`\`\`

e lo stesso con \`https://github.com/MrChromebox/LvglPkg\` e ${lm}.

Questo issue lo aggiorna e lo chiude \`upstream.yml\`.
EOF
)"
	report "Mirror:" "Mirror: tag mancanti per i commit pinnati di EDK2 o LvglPkg" "${body}"
}

case "${WHAT}" in
	coreboot) check_coreboot ;;
	edk2)     check_edk2 ;;
	mirror)   check_mirror ;;
	*) die "uso: upstream.sh coreboot|edk2|mirror [--dry-run]" ;;
esac
