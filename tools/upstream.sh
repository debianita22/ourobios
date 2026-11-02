#!/bin/bash
# upstream.sh - coreboot o EDK2 si sono mossi dal pin? Lo lancia
# .github/workflows/upstream.yml ogni settimana. Solo avvisi: un issue per
# ciascuno, aggiornato a ogni giro e chiuso quando non c'e' piu' niente da
# fare. I pin si spostano a mano.
#
#   tools/upstream.sh coreboot [--dry-run]
#   tools/upstream.sh edk2 [--dry-run]
#   tools/upstream.sh mirror [--dry-run]
#   tools/upstream.sh dbx [--dry-run]
#   tools/upstream.sh tianocore [--dry-run]
#
# coreboot  la serie di patches/ applica ancora su main? Qualche patch e' gia'
#           entrata upstream (stesso Subject)? C'e' un tag di release dopo il
#           pin? Se si', issue "coreboot: ...".
# edk2      il ramo uefipayload_AAMM piu' recente di MrChromebox e' andato
#           oltre il commit pinnato nei defconfig? Se si', issue "EDK2: ...".
# mirror    i commit di EDK2 e LvglPkg di configs/edk2-pins.txt hanno il loro
#           tag pin-<12 cifre> nei fork del progetto (EDK2_MIRROR e
#           LVGLPKG_MIRROR di tools/build.sh)? Se no, issue "Mirror: ...".
# dbx       la dbx che il payload scrive al primo avvio (EnrollDefaultKeys,
#           keys/ del commit di EDK2 dei defconfig) ha le liste di hash
#           dell'ultima release firmata di microsoft/secureboot_objects? Se
#           no, issue "DBX: ...".
# tianocore c'e' un tag edk2-stableAAAAMM di TianoCore dopo EDK2_UPSTREAM_TAG
#           di tools/build.sh (il passaggio a TianoCore, docs/edk2-migration.md)?
#           Se si', issue "TianoCore: ...", che dice se le patch del package
#           (edk2/OuroBiosPkg/*.patch) applicano ancora ai file di
#           UefiPayloadPkg di quel tag.
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
# I tag pin-* del mirror $1, "nome commit" per riga: di un tag annotato il
# commit a cui punta (la riga ^{} di ls-remote). Niente se il mirror non c'e'
# (GitHub: 404); se c'e' e non risponde, il controllo si ferma senza issue,
# come per un errore di rete
mirror_tags() {
	local out
	if out="$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags "$1" 'refs/tags/pin-*' 2>/dev/null)"; then
		awk '{ r = $2; sub("^refs/tags/", "", r)
		       if (r ~ /\^\{\}$/) { sub(/\^\{\}$/, "", r); peeled[r] = $1 } else { direct[r] = $1 } }
		     END { for (r in direct) print r, ((r in peeled) ? peeled[r] : direct[r]) }' <<< "${out}"
	elif gh api "repos/${1#https://github.com/}" --silent 2>/dev/null; then
		die "${1}: git ls-remote non risponde"
	fi
}

check_mirror() {
	local em lm pins e l r got sub repo missing="" seen=" " n=0 et lt
	em="$(sed -n 's/^EDK2_MIRROR="\([^"]*\)".*/\1/p' "${O}/tools/build.sh")"
	lm="$(sed -n 's/^LVGLPKG_MIRROR="\([^"]*\)".*/\1/p' "${O}/tools/build.sh")"
	pins="${O}/configs/edk2-pins.txt"
	[ -n "${em}" ] && [ -n "${lm}" ] || die "EDK2_MIRROR o LVGLPKG_MIRROR non trovati in tools/build.sh"
	[ -f "${pins}" ] || die "configs/edk2-pins.txt non c'e'"
	et="$(mirror_tags "${em}")"
	lt="$(mirror_tags "${lm}")"
	while read -r e l r; do
		case "${e}" in ''|'#'*) continue ;; esac
		n=$((n + 1))
		got="$(awk -v t="pin-${e:0:12}" '$1 == t { print $2 }' <<< "${et}")"
		if [ "${got}" != "${e}" ]; then
			missing="${missing}- EDK2 \`${e:0:12}\` (${r}): tag \`pin-${e:0:12}\` ${got:+su \`${got:0:12}\`}${got:-assente} in ${em}
"
		fi
		# un commit di LvglPkg una volta sola, anche se piu' pin lo usano
		if [ "${seen#* "${l}" }" = "${seen}" ]; then
			seen="${seen}${l} "
			got="$(awk -v t="pin-${l:0:12}" '$1 == t { print $2 }' <<< "${lt}")"
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

# Le liste di hash della dbx di default, per id del blob git (stesso
# contenuto, stesso id: nessun file scaricato, solo gli alberi):
#   keys/dbx_microsoft_baseline.bin = PostSignedObjects/DBX/amd64/DBXUpdate.bin
#   keys/dbx_microsoft_update.bin   = PostSignedObjects/SignedByKEK2023/dbx_x64.efiauth2
# dell'ultimo tag vX.Y.Z-signed di Microsoft. Le voci SVN
# (SignedByKEK2023/dbx_SVN.efiauth2) restano fuori di proposito: revocano i
# boot manager di Windows piu' vecchi, Windows le scrive da se' dopo aver
# aggiornato il suo, e nei default rifiuterebbero i supporti di installazione
# con un boot manager di prima.
DBX_REPO="https://github.com/microsoft/secureboot_objects"
DBX_KEYS="UefiPayloadPkg/EnrollDefaultKeys/keys"
check_dbx() {
	local rev em tag g ms_up ms_base pay_up pay_base from
	rev="$(sed -n 's/^CONFIG_EDK2_TAG_OR_REV="\(.*\)"$/\1/p' "${O}/configs/w541-mrc.defconfig")"
	em="$(pin EDK2_MIRROR)"
	[ -n "${rev}" ] && [ -n "${em}" ] || die "CONFIG_EDK2_TAG_OR_REV o EDK2_MIRROR non trovati"
	tag="$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags "${DBX_REPO}" 'refs/tags/v*-signed' \
		| sed -n 's#.*refs/tags/\(v[0-9.]*-signed\)$#\1#p' | sort -V | tail -n 1)"
	[ -n "${tag}" ] || die "${DBX_REPO}: nessun tag vX.Y.Z-signed"
	g="${TMP}/dbx"
	git init -q "${g}"
	GIT_TERMINAL_PROMPT=0 git -C "${g}" fetch -q --depth 1 --filter=blob:none "${DBX_REPO}" "refs/tags/${tag}" \
		|| die "${DBX_REPO} ${tag}: fetch non riuscito"
	ms_base="$(git -C "${g}" rev-parse "FETCH_HEAD:PostSignedObjects/DBX/amd64/DBXUpdate.bin")"
	ms_up="$(git -C "${g}" rev-parse "FETCH_HEAD:PostSignedObjects/SignedByKEK2023/dbx_x64.efiauth2")"
	# il commit pinnato dal mirror del progetto (tag pin-<12 cifre>), se no
	# da MrChromebox per hash
	from="${em}"
	if ! GIT_TERMINAL_PROMPT=0 git -C "${g}" fetch -q --depth 1 --filter=blob:none "${em}" "refs/tags/pin-${rev:0:12}"; then
		from="https://github.com/mrchromebox/edk2"
		GIT_TERMINAL_PROMPT=0 git -C "${g}" fetch -q --depth 1 --filter=blob:none "${from}" "${rev}" \
			|| die "EDK2 ${rev:0:12}: ne' il tag pin- del mirror ne' il commit da MrChromebox"
	fi
	pay_base="$(git -C "${g}" rev-parse "FETCH_HEAD:${DBX_KEYS}/dbx_microsoft_baseline.bin")"
	pay_up="$(git -C "${g}" rev-parse "FETCH_HEAD:${DBX_KEYS}/dbx_microsoft_update.bin")"
	if [ "${pay_base}" = "${ms_base}" ] && [ "${pay_up}" = "${ms_up}" ]; then
		settle "DBX:" "DBX: il payload (EDK2 ${rev:0:12}) ha le liste di hash di Microsoft ${tag}"
		return 0
	fi
	local body
	body="$(cat <<EOF
La dbx che il payload scrive al primo avvio (\`EnrollDefaultKeys\`, \`${DBX_KEYS}\` di EDK2 \`${rev:0:12}\`, da ${from}) non e' quella dell'ultima release firmata di Microsoft, \`${tag}\`:

| File del payload | Blob | Di Microsoft (${tag}) | Blob |
|---|---|---|---|
| \`dbx_microsoft_baseline.bin\` | \`${pay_base:0:12}\` | \`PostSignedObjects/DBX/amd64/DBXUpdate.bin\` | \`${ms_base:0:12}\` |
| \`dbx_microsoft_update.bin\` | \`${pay_up:0:12}\` | \`PostSignedObjects/SignedByKEK2023/dbx_x64.efiauth2\` | \`${ms_up:0:12}\` |

Vale per le macchine che iscrivono le chiavi di default (primo avvio, reset delle chiavi): le altre ricevono la dbx da Windows Update o da \`fwupdmgr update\` (firmata da Microsoft con la KEK, che il PK di default accetta).

Per aggiornarla: una patch di \`patches/edk2\` con i file di \`keys/\` rifatti da \`UpdateMicrosoftDbx.py --release ${tag} --kek 2023 --arch x64\` (lo script e' in quella cartella, \`git format-patch --binary\`), o il pin di EDK2 spostato a un commit di MrChromebox che li ha. Le voci SVN (\`dbx_SVN.efiauth2\`) restano fuori di proposito: Windows le scrive da se' dopo aver aggiornato il suo boot manager.

Questo issue lo aggiorna e lo chiude \`upstream.yml\`.
EOF
)"
	report "DBX:" "DBX: le liste di hash di Microsoft ${tag} non sono quelle del payload" "${body}"
}

# Il tag stabile di TianoCore dopo quello di edk2-upstream, e le patch del
# package (edk2/OuroBiosPkg) sui file di UefiPayloadPkg di quel tag
check_tianocore() {
	local repo tag latest g p e no=() rows=""
	repo="$(pin EDK2_UPSTREAM_REPO)"
	tag="$(pin EDK2_UPSTREAM_TAG)"
	[ -n "${repo}" ] && [ -n "${tag}" ] || die "EDK2_UPSTREAM_REPO o EDK2_UPSTREAM_TAG non trovati in tools/build.sh"
	latest="$(GIT_TERMINAL_PROMPT=0 git ls-remote --tags "${repo}" 'refs/tags/edk2-stable*' \
		| sed -n 's#.*refs/tags/\(edk2-stable[0-9]\{6\}\)$#\1#p' | sort | tail -n 1)"
	[ -n "${latest}" ] || die "${repo}: nessun tag edk2-stableAAAAMM"
	if [ "${latest}" = "${tag}" ] || [ "$(printf '%s\n%s\n' "${tag}" "${latest}" | sort | tail -n 1)" = "${tag}" ]; then
		settle "TianoCore:" "TianoCore: ${tag} e' l'ultimo tag stabile"
		return 0
	fi
	g="${TMP}/tianocore"
	git init -q "${g}"
	GIT_TERMINAL_PROMPT=0 git -C "${g}" fetch -q --depth 1 --filter=blob:none "${repo}" "refs/tags/${latest}" \
		|| die "${repo} ${latest}: fetch non riuscito"
	for p in "${O}"/edk2/OuroBiosPkg/OuroBiosPkg.*.patch; do
		[ -e "${p}" ] || continue
		e="${p%.patch}"
		e="${e##*.}"
		mkdir -p "${TMP}/pkg"
		git -C "${g}" show "FETCH_HEAD:UefiPayloadPkg/UefiPayloadPkg.${e}" > "${TMP}/pkg/OuroBiosPkg.${e}" \
			|| die "${latest}: niente UefiPayloadPkg/UefiPayloadPkg.${e}"
		if (cd "${TMP}/pkg" && git apply --check -p1 "${p}" 2> "${TMP}/pkg/${e}.err"); then
			rows+="| \`${p##*/}\` | applica |"$'\n'
		else
			no+=("${p##*/}")
			rows+="| \`${p##*/}\` | non applica: $(head -n 1 "${TMP}/pkg/${e}.err" | tr '|' '/') |"$'\n'
		fi
	done
	local title body
	if [ ${#no[@]} -eq 0 ]; then
		title="TianoCore: ${latest} dopo ${tag}, le patch del package applicano"
	else
		title="TianoCore: ${latest} dopo ${tag}, ${#no[@]} patch del package da rifare"
	fi
	body="$(cat <<EOF
TianoCore ha \`${latest}\`; \`tools/build.sh edk2-upstream\` e il package \`edk2/OuroBiosPkg\` sono su \`${tag}\` (\`EDK2_UPSTREAM_TAG\`).

Le patch del package sui file di \`UefiPayloadPkg\` di \`${latest}\`:

| Patch | Esito |
|---|---|
${rows}
Per spostarsi (a mano): \`EDK2_UPSTREAM_TAG\` e \`EDK2_UPSTREAM_COMMIT\` in \`tools/build.sh\`, le patch rifatte se non applicano, le lacune di \`EDK2_UPSTREAM_GAPS\` riviste, poi push su un ramo \`ci-edk2/...\` (docs/edk2-migration.md).

Questo issue lo aggiorna e lo chiude \`upstream.yml\`.
EOF
)"
	report "TianoCore:" "${title}" "${body}"
}

case "${WHAT}" in
	coreboot)  check_coreboot ;;
	edk2)      check_edk2 ;;
	mirror)    check_mirror ;;
	dbx)       check_dbx ;;
	tianocore) check_tianocore ;;
	*) die "uso: upstream.sh coreboot|edk2|mirror|dbx|tianocore [--dry-run]" ;;
esac
