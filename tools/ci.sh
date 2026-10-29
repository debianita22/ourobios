#!/bin/bash
# ci.sh - i passi di build.yml attorno alla build: la versione, le note, i
# controlli e la pubblicazione delle release. La build vera e' tools/build.sh.
#
#   tools/ci.sh version              job setup: version, publish, prerelease
#                                    (in GITHUB_OUTPUT)
#   tools/ci.sh notes DIST FLAVOUR   le note della release di quella variante
#                                    (stdout, in inglese come il README)
#   tools/ci.sh check DIST           job release: i file di ogni release in
#                                    DIST, prima di pubblicarli
#   tools/ci.sh compare DIST REPRO   job compare: le ROM di DIST (job build) e
#                                    di REPRO (job repro, un altro runner)
#                                    uguali bit a bit; se no le regioni
#                                    diverse e i compilatori delle due
#   tools/ci.sh publish DIST         job release: una release per variante di
#                                    ogni board, con i file di DIST
#
# Le release: una per variante di ogni board (boards/<board>/board.sh), con
# il tag <versione>-<prefisso della board><variante>, il "flavour": mrc e nri
# del W541 (prefisso vuoto: i tag di sempre), m920x-fsp del M920x. Una board
# con BOARD_SINCE e' nelle release da quella versione (il M920x dalla
# v1.4.0, rc comprese).
#
# Regole (le stesse dei commenti di build.yml):
#   - versione vX.Y.Z o vX.Y.Z-qualcosa; con un trattino, o con la casella
#     prerelease, tutte le release della versione sono pre-release, senza
#     tutte release: dalla v1.3.9 la nri esce con la mrc (fino alla v1.3.8
#     sempre pre-release: upstream la RAM init nativa di Haswell e'
#     "[NOT COMPLETE]")
#   - solo la mrc puo' essere latest: i metadati del remote fwupd sono nella mrc
#   - una release che non e' pre-release solo da un commit del ramo principale
#   - "latest" solo alla mrc della versione piu' alta (sort -V)
#   - i metadati del remote fwupd (FWUPD_METADATA e la sua firma .jcat), con
#     i .cab di tutte le board, nella release mrc: il remote li scarica da
#     releases/latest/download/, cioe' dall'ultima mrc che non e' una
#     pre-release; fwupd offre a ogni macchina solo il .cab del suo GUID
#   - gli stessi metadati anche negli asset della release fissa TESTING_TAG,
#     se la versione e' la piu' alta pubblicata finora, rc comprese: e' il
#     remote testing (configs/fwupd/ourobios-testing.conf)
set -euo pipefail
O="$(cd "$(dirname "$0")/.." && pwd)"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\033[31m[x] %s\033[0m\n' "$*" >&2; exit 1; }
summ() { echo "$*" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"; }
# un'annotazione del job: si legge anche dall'API, senza scaricare il log
note() {
	local level="$1" title="$2" msg="$3"
	[ -n "${GITHUB_ACTIONS:-}" ] || return 0
	msg="${msg//'%'/'%25'}"; msg="${msg//$'\r'/}"; msg="${msg//$'\n'/'%0A'}"
	title="${title//'%'/'%25'}"; title="${title//:/'%3A'}"; title="${title//,/'%2C'}"
	echo "::${level} title=${title}::${msg}"
}
fail() { note error "$1" "$2"; die "$2"; }

# Le board (boards/<board>/board.sh), il W541 prima, e una variabile $2
# (array: i suoi elementi, uno per riga) o la funzione board_defconfig $2
# della board $1, come in tools/ci-check.sh
boards() {
	local f
	[ ! -f "${O}/boards/w541/board.sh" ] || echo w541
	for f in "${O}"/boards/*/board.sh; do
		[ -f "${f}" ] || continue
		f="${f%/board.sh}"
		[ "${f##*/}" = w541 ] || printf '%s\n' "${f##*/}"
	done | LC_ALL=C sort
}
board_get() {
	(
		# shellcheck source=/dev/null
		. "${O}/boards/$1/board.sh" || exit 1
		if [ "$2" = defconfig ]; then
			board_defconfig "$3"
		else
			eval "printf '%s\\n' \"\${${2}[@]}\""
		fi
	)
}
# I flavour (le release di una versione), con la loro board e variante
FLAVOURS=()
declare -A FL_BOARD=() FL_VARIANT=()
for b in $(boards); do
	p="$(board_get "${b}" BOARD_FLAVOUR_PREFIX)"
	for v in $(board_get "${b}" BOARD_VARIANTS); do
		FLAVOURS+=("${p}${v}")
		FL_BOARD["${p}${v}"]="${b}"
		FL_VARIANT["${p}${v}"]="${v}"
	done
done
unset b p v
[ ${#FLAVOURS[@]} -gt 0 ] || die "nessuna board in boards/*/board.sh"
# La board $1 e' nelle release della versione $2? BOARD_SINCE di board.sh: la
# prima versione con la board, sue rc comprese (lo stesso conto di
# tools/build.sh --board all); le versioni che non sono di release (ci-...)
# hanno ogni board
board_in_version() {
	local since
	since="$(board_get "$1" BOARD_SINCE)"
	[ -n "${since}" ] || return 0
	[[ "$2" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]] || return 0
	[ "$(printf '%s\n' "${since}" "${2%%-*}" | sort -V | sed -n 1p)" = "${since}" ]
}
# FLAVOURS: solo quelli delle board nelle release della versione $1
flavours_for() {
	local f keep=()
	for f in "${FLAVOURS[@]}"; do
		if board_in_version "${FL_BOARD[${f}]}" "$1"; then keep+=("${f}"); fi
	done
	[ ${#keep[@]} -gt 0 ] || die "nessuna board nelle release di $1"
	FLAVOURS=("${keep[@]}")
}
# Il nome dei file del flavour $1 nella versione VERSION, senza estensione:
# <board>-coreboot-<versione>-<variante>, come romname di tools/build.sh
fl_name() { printf '%s-coreboot-%s-%s' "${FL_BOARD[$1]}" "${VERSION}" "${FL_VARIANT[$1]}"; }
# I file della release del flavour $1, uno per riga: ROM, i chip della board,
# capsula, pacchetto fwupd, .config e layout
fl_files() {
	local n c
	n="$(fl_name "$1")"
	echo "${n}.rom"
	while read -r c _; do echo "${n}-${c}-chip.rom"; done < <(board_get "${FL_BOARD[$1]}" BOARD_CHIPS)
	printf '%s\n' "${n}.cap" "${n}.cab" "${n}.config" "${n}-layout.txt"
}
# I flavour in una riga, "mrc, nri e m920x-fsp", ognuno preceduto da $1
# (per esempio la versione e il trattino), per i riepiloghi
fl_list() {
	local i pre="${1:-}" out=""
	for i in "${!FLAVOURS[@]}"; do
		if [ "${i}" -eq 0 ]; then out="${pre}${FLAVOURS[i]}"
		elif [ "${i}" -eq $(( ${#FLAVOURS[@]} - 1 )) ]; then out+=" e ${pre}${FLAVOURS[i]}"
		else out+=", ${pre}${FLAVOURS[i]}"; fi
	done
	printf '%s' "${out}"
}
# i metadati del remote fwupd (tools/build.sh, configs/fwupd/ourobios.conf)
FWUPD_METADATA=ourobios.xml.gz
# la release fissa con i metadati del remote testing
# (configs/fwupd/ourobios-testing.conf): i suoi asset li riscrive ogni release
TESTING_TAG=testing
# La variante del flavour $1 per le note, e il titolo della sua release:
# la board e la variante
variant_title() {
	case "${FL_VARIANT[$1]}" in
		mrc) echo "MRC (Intel mrc.bin RAM init)" ;;
		nri) echo "NRI (native RAM init)" ;;
		fsp) echo "FSP (Intel FSP RAM init)" ;;
		*) echo "${FL_VARIANT[$1]}" ;;
	esac
}
title_of() { printf '%s, %s\n' "$(board_get "${FL_BOARD[$1]}" BOARD_NAME)" "$(variant_title "$1")"; }

# Un valore assegnato in tools/build.sh (COREBOOT_COMMIT, ...)
pin() { sed -n "s/^$1=\"\([^\"]*\)\".*/\1/p" "${O}/tools/build.sh"; }

# Il commit $1 e' nella storia del ramo principale di origin?
on_default_branch() {
	local c
	c="$(git -C "${O}" rev-parse --verify -q "$1^{commit}")" || return 1
	if [ "$(git -C "${O}" rev-parse --is-shallow-repository)" = true ]; then
		git -C "${O}" fetch -q --unshallow origin || return 1
	fi
	git -C "${O}" fetch -q --no-tags origin "+refs/heads/${DEFAULT_BRANCH}:refs/remotes/origin/${DEFAULT_BRANCH}" || return 1
	git -C "${O}" merge-base --is-ancestor "${c}" "refs/remotes/origin/${DEFAULT_BRANCH}"
}

# Il commit del tag $1 su origin, vuoto se non c'e' (il ^{} di un tag annotato)
tag_commit() {
	local out
	out="$(git -C "${O}" ls-remote --tags origin "refs/tags/$1" "refs/tags/$1^{}")" || return 1
	awk -v t="refs/tags/$1" '$2 == t "^{}" { p = $1 } $2 == t { l = $1 } END { print (p != "" ? p : l) }' <<< "${out}"
}

# Le release con il tag $1: righe "<id> <bozza true|false>". Le bozze le vede
# solo chi puo' scrivere (il job release).
release_ids() {
	REL_TAG="$1" gh api --paginate "repos/${GITHUB_REPOSITORY}/releases?per_page=100" \
		--jq '.[] | select(.tag_name == env.REL_TAG) | "\(.id) \(.draft)"'
}

# Il tag della release "latest", vuoto se non ce n'e'
latest_tag() {
	local out
	if out="$(gh api "repos/${GITHUB_REPOSITORY}/releases/latest" --jq .tag_name 2>&1)"; then
		printf '%s\n' "${out}"
	else
		case "${out}" in *"HTTP 404"*|*"Not Found"*) return 0 ;; esac
		echo "${out}" >&2
		return 1
	fi
}

# La sezione "## vX.Y.Z" di CHANGELOG.md, senza le righe vuote ai bordi; una
# release candidate prende quella della versione a cui porta
changes_of() {
	local v="${1%%-*}"
	[ -f "${O}/CHANGELOG.md" ] || return 0
	awk -v h="## ${v}" '$0 == h { on = 1; next } /^## / { on = 0 } on' "${O}/CHANGELOG.md" \
		| sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}'
}

# $1 e' una versione piu' alta di $2? sort -V, col trattino come ~ perche'
# v1.1.0-rc1 venga prima di v1.1.0. Il -mrc dei tag si toglie prima.
newer() {
	local a b
	a="$(printf '%s' "${1%-mrc}" | sed 's/-/~/g')"; b="$(printf '%s' "${2%-mrc}" | sed 's/-/~/g')"
	[ "${a}" != "${b}" ] && [ "$(printf '%s\n' "${a}" "${b}" | sort -V | tail -n 1)" = "${a}" ]
}

# vX.Y.Z o vX.Y.Z-rcN (N da 1), numeri fino a 255: la versione dell'ESRT e
# della capsula ne ha un byte ciascuno (fw_version di tools/build.sh, che per
# le altre da' 0 e niente capsula). Una rc non di v0.0.0
release_version_ok() {
	local x y z r
	[[ "$1" =~ ^v(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})(-rc([1-9][0-9]{0,2}))?$ ]] || return 1
	x=$((10#${BASH_REMATCH[1]})); y=$((10#${BASH_REMATCH[2]})); z=$((10#${BASH_REMATCH[3]}))
	r=$((10#${BASH_REMATCH[5]:-0}))
	[ "${x}" -le 255 ] && [ "${y}" -le 255 ] && [ "${z}" -le 255 ] && [ "${r}" -le 255 ] \
		&& { [ "${r}" -eq 0 ] || [ $(( x + y + z )) -gt 0 ]; }
}

# Job setup: versione, se si pubblica, se e' una pre-release
cmd_version() {
	: "${GITHUB_EVENT_NAME:?}" "${GITHUB_REF_NAME:?}" "${GITHUB_RUN_NUMBER:?}" "${GITHUB_REPOSITORY:?}" "${DEFAULT_BRANCH:?}"
	local version publish=false prerelease=false v t c rels
	if [ "${GITHUB_EVENT_NAME}" = push ] && [ "${GITHUB_REF_TYPE:-}" = tag ]; then
		version="${GITHUB_REF_NAME}"; publish=true
	elif [ "${GITHUB_EVENT_NAME}" = workflow_dispatch ] && [ -n "${IN_VERSION:-}" ]; then
		version="${IN_VERSION}"; publish=true
		prerelease="${IN_PRERELEASE:-false}"
	else
		version="ci-${GITHUB_RUN_NUMBER}-$(git -C "${O}" rev-parse --short=7 HEAD)"
	fi
	flavours_for "${version}"
	if [ "${publish}" = true ]; then
		release_version_ok "${version}" \
			|| fail "Versione" "versione '${version}': vX.Y.Z o vX.Y.Z-rcN, numeri fino a 255 (la versione dell'ESRT ne ha un byte ciascuno)"
		for v in "${FLAVOURS[@]}"; do
			case "${version}" in
				*-"${v}") fail "Versione" "${version}: la versione senza -${v}, i tag delle release ($(fl_list -)) li crea la release" ;;
			esac
		done
		case "${version}" in *-*) prerelease=true ;; esac
		if [ "${prerelease}" != true ]; then
			if [ "${GITHUB_EVENT_NAME}" = workflow_dispatch ] && [ "${GITHUB_REF_NAME}" != "${DEFAULT_BRANCH}" ]; then
				fail "Versione" "da ${GITHUB_REF_NAME} solo pre-release (casella prerelease o vX.Y.Z-rcN)"
			fi
			on_default_branch "${GITHUB_SHA:-HEAD}" \
				|| fail "Versione" "${version}: il commit non e' su ${DEFAULT_BRANCH}; da altri rami solo pre-release"
		fi
		[ -n "$(changes_of "${version}")" ] \
			|| fail "Versione" "CHANGELOG.md non ha la sezione ## ${version%%-*}: le note della release la riportano"
		for v in "${FLAVOURS[@]}"; do
			t="${version}-${v}"
			c="$(tag_commit "${t}")" || fail "Versione" "origin non risponde (git ls-remote)"
			if [ "${GITHUB_EVENT_NAME}" = workflow_dispatch ]; then
				[ -z "${c}" ] || fail "Versione" "il tag ${t} esiste gia': un'altra versione"
			elif [ -n "${c}" ] && [ "${c}" != "$(git -C "${O}" rev-parse "${GITHUB_SHA:-HEAD}^{commit}")" ]; then
				# un tag di prima su un altro commit: il job release si fermerebbe
				# dopo la build (cmd_publish); qui costa un minuto
				fail "Versione" "il tag ${t} e' su ${c:0:12}, non sul commit della build"
			fi
			rels="$(release_ids "${t}")" || fail "Versione" "elenco delle release illeggibile"
			if grep -q ' false$' <<< "${rels}"; then fail "Versione" "la release ${t} esiste gia'"; fi
		done
	fi
	{
		echo "version=${version}"
		echo "publish=${publish}"
		echo "prerelease=${prerelease}"
	} >> "${GITHUB_OUTPUT:-/dev/null}"
	summ "### ${version}"
	if [ "${publish}" != true ]; then
		summ "Build di prova: nessuna release, le ROM negli artifact del run."
	elif [ "${prerelease}" = true ]; then
		summ "Release $(fl_list "${version}-"), tutte pre-release."
	else
		summ "Release $(fl_list "${version}-"): latest la ${version}-mrc, se e' la versione piu' alta; le altre mai."
	fi
	echo "versione ${version}, release ${publish}, pre-release ${prerelease}"
}

# La sezione di CHANGELOG.md della versione, per le note (notes_*), con i
# link relativi del file assoluti nella pagina della release
notes_changes() {
	local changes
	changes="$(changes_of "${version}")"
	[ -n "${changes}" ] || return 0
	echo
	if [ "${version%%-*}" = "${version}" ]; then
		echo "**What's new in ${version}** ([CHANGELOG.md](https://github.com/${repo}/blob/main/CHANGELOG.md)):"
	else
		echo "**What's new in ${version%%-*}**, so far ([CHANGELOG.md](https://github.com/${repo}/blob/main/CHANGELOG.md)):"
	fi
	echo
	printf '%s\n' "${changes}" | sed -E "s#\]\(((docs|patches|tools|keys|configs|blobs|boards|assets)/[^)]*|[A-Za-z0-9_.-]+\.md(\#[^)]*)?)\)#](https://github.com/${repo}/blob/main/\1)#g"
}

# Le note del W541 (mrc e nri): le variabili di cmd_notes
notes_w541() {
	local chip8="${n}-8mb-chip.rom" chip4="${n}-4mb-chip.rom"
	echo "**ouroBIOS** ${version}, $(variant_title "${fl}") variant: coreboot and EDK II for the **Lenovo ThinkPad W541**, reborn by design."
	echo
	if [ "${v}" = mrc ]; then
		cat <<'EOF'
RAM is initialized by Intel's `mrc.bin`, the blob from the coreboot 24.08 image
that ran on this W541 before this project (`blobs/README.md`): the
conservative choice.
EOF
	else
		cat <<EOF
RAM is initialized by coreboot's own native code (NRI), with no \`mrc.bin\`.
Upstream coreboot still labels the Haswell native RAM init *[NOT COMPLETE]*:
what it does on the W541 and how it compares with \`mrc.bin\` are in
[docs/raminit.md](https://github.com/${repo}/blob/main/docs/raminit.md#on-the-w541).
If the laptop does not come up after flashing it (black screen, no boot),
recovery needs an external programmer: see [Recovery](https://github.com/${repo}/blob/main/docs/flashing.md#recovery).
EOF
	fi
	notes_changes
	if [ "${pre}" = yes ]; then
		echo
		echo "**Pre-release**: not yet confirmed on real hardware. Keep a backup of your flash and an external programmer at hand."
	elif [ "${v}" = mrc ]; then
		echo
		echo "**Tested on a W541**: the move from v1.0.x with flashrom, boot and resume from suspend, capsule updates with the A/B slots (a slot rewritten across the two chips, the switch, the result in the ESRT), the fallback to the other slot when the running one is spoiled ([docs/vboot.md](https://github.com/${repo}/blob/main/docs/vboot.md#how-it-is-tested)), and DMA translation with \`intel_iommu=on\` under load, also after a resume ([docs/flashing.md](https://github.com/${repo}/blob/main/docs/flashing.md#first-boot-and-settings))."
	fi
	cat <<EOF

| File | Use |
|---|---|
| \`${rom}\` | **complete 12 MiB flash image**: descriptor (IFD), GbE, Intel ME and coreboot |
| \`${chip4}\` | its last 4 MiB: the read-only part and slot B, enough to boot, for an external programmer on the 4 MiB chip |
| \`${chip8}\` | its first 8 MiB: descriptor, GbE and ME of the machine the blobs come from, for the 8 MiB chip |
| \`${cap}\` | **signed UEFI capsule**: updates from Linux a W541 that already runs v1.3.0 or later, with \`tools/update.py\` |
| \`${cab}\` | the same capsule as an **fwupd package** (\`fwupdmgr install\`, once the project certificate is in \`/etc/pki/fwupd\`) |
| \`${cfg}\` | the complete coreboot \`.config\` |
| \`${lay}\` | flash layout (FMAP) and CBFS contents |${meta_row}
| \`SHA256SUMS\` | checksums of the files above |

Flash layout (\`configs/w541.fmd\`): the first 5 MiB (IFD, GbE, ME) are
byte-identical to the coreboot 4.22 image in \`legacy/coreboot-4.22\`:
unlocked regions, ME reduced by \`me_cleaner -S\`, and the GbE region with the
MAC address of the machine these blobs come from. Then, still on the 8 MiB
chip, the regions coreboot writes at runtime (RAM training, UEFI variables,
VPD, event log, vboot's state), empty; then the two RW slots, A and B, each
signed, and at the top of the 4 MiB chip the read-only part, which verifies
a slot before it runs it
([docs/vboot.md](https://github.com/${repo}/blob/main/docs/vboot.md)). An
update from Linux writes only the BIOS region, as below: it keeps the
machine's own descriptor, ME and MAC address.

**Update with the capsule**, on a W541 that already runs v1.3.0 or later:
the firmware checks the signature, writes the slot that is not running in
about a minute and starts again on it; if the new slot does not verify or
does not boot, vboot goes back to the old one. Settings, boot entries,
Secure Boot keys, VPD and event log stay, and *BIOS Lock* and *Firmware
protection* can stay on
([docs/update.md](https://github.com/${repo}/blob/main/docs/update.md)).

\`\`\`sh
curl -LO https://raw.githubusercontent.com/${repo}/main/tools/update.py
sudo python3 update.py stage ${latest}       # or: sudo python3 update.py stage ${cap}
sudo systemctl reboot
\`\`\`

Or with fwupd ([docs/update.md](https://github.com/${repo}/blob/main/docs/update.md#fwupd)):
${fwupd_how}

**From v1.0.3 to v1.2.x**: v1.3.0 changed the flash map (vboot, two RW
slots), so an older firmware does not take its capsule. Write it once with
flashrom, every region except those written at runtime, which are where they
were since v1.0.3: settings, boot entries, Secure Boot keys, VPD and event
log stay. *BIOS Lock* must be off; flashrom 1.2 or later
([details](https://github.com/${repo}/blob/main/docs/flashing.md#from-v12x-to-v130)).

\`\`\`sh
sha256sum -c SHA256SUMS --ignore-missing
sudo modprobe -r spi_intel_platform spi_intel               # flashrom must not go through /dev/mtd0
sudo flashrom -p internal -r backup-\$(date +%F).rom        # 12582912 bytes, keep it off the laptop
sudo flashrom -p internal --fmap-file ${rom} \\
  -i RW_MRC_CACHE -i RW_UNUSED -i RW_NVRAM -i RECOVERY_MRC_CACHE \\
  -i RW_SECTION_A -i RW_SECTION_B -i WP_RO -w ${rom}
\`\`\`

**Update with flashrom**, from older versions or other firmware, on a W541
that already runs coreboot with an unlocked flash: only the BIOS region is
written (details, VPD and recovery in
[docs/flashing.md](https://github.com/${repo}/blob/main/docs/flashing.md)).
From v1.3.0 on the laptop, turn off *Firmware protection* (setup menu,
*Security*) first.

\`\`\`sh
sha256sum -c SHA256SUMS --ignore-missing
sudo modprobe -r spi_intel_platform spi_intel               # flashrom must not go through /dev/mtd0
sudo flashrom -p internal -r backup-\$(date +%F).rom        # whole 12 MiB, keep it off the laptop
ls -l backup-*.rom                                        # 12582912 bytes (8388608: it went through /dev/mtd0)
sudo flashrom -p internal --ifd -i bios -w ${rom}
\`\`\`

**External programmer** (recovery): \`${chip4}\` on the 4 MiB chip boots
(read-only part and slot B); leave the 8 MiB chip as it is. \`${chip8}\` would give the laptop
the descriptor, ME and MAC address of another machine: see
[docs/flashing.md](https://github.com/${repo}/blob/main/docs/flashing.md#external-programmer).

If flashrom says "Opened /dev/mtd0" and finds an 8192 kB "Opaque flash chip",
the kernel owns the SPI controller: run \`sudo modprobe -r spi_intel_platform
spi_intel\` first ([details](https://github.com/${repo}/blob/main/docs/flashing.md#before-you-start)).
If flashrom cannot map the flash, boot once with \`iomem=relaxed\` on the
kernel command line. Flashing resets the UEFI settings and boot entries: the
firmware then boots \`\\EFI\\BOOT\\BOOTX64.EFI\` from each disk, so install your
boot loader at that path too (Debian: \`sudo grub-install --removable\`), or
pick it once with *Boot From File* in the boot manager (Esc at power-on).

The NVIDIA GPU is **off by default**, as in upstream coreboot: turn it on in
the setup menu (Esc at power-on), *Hardware* → *NVIDIA discrete GPU*.

**Suspend to RAM (S3)**: the images up to v1.0.6 did not resume: coreboot's
cache-as-RAM setup lost one line of the region on Haswell, and \`mrc.bin\` hung
on it while restoring the memory. Patch 0043 (from v1.0.7) fills the region as
before. If a resume still stops, the event log has its last POST code:
[diagnosing a hang](https://github.com/${repo}/blob/main/docs/flashing.md#diagnosing-a-hang);
suspend-to-idle (\`mem_sleep_default=s2idle\`) works meanwhile.

**Serial number and machine type (VPD)**: from v1.0.9 the firmware reports
the serial number, machine type model and UUID of the laptop as the Lenovo
firmware did, from the \`RO_VPD\` flash region, which these images leave
empty. Write it once with \`tools/vpd.py\`; a capsule update leaves it alone,
flashrom rewrites it, so copy it into the image first (\`tools/vpd.py copy\`,
[how](https://github.com/${repo}/blob/main/docs/flashing.md#serial-number-and-machine-type-vpd)).
*BIOS Lock* (setup menu, *Security*) must be off to flash with flashrom, and
*Firmware protection* too to write the whole BIOS region.

Inside: coreboot \`${cbdesc}\` ([${cb:0:12}](https://github.com/coreboot/coreboot/commit/${cb}))
with [${npatch} patches](https://github.com/${repo}/tree/${sha}/patches), EDK2 payload
(MrChromebox [\`${edk2:0:12}\`](https://github.com/mrchromebox/edk2/commit/${edk2})
with [${nedk2} patches](https://github.com/${repo}/blob/${sha}/patches/README.md#edk2-and-lvglpkg)
to EDK2 and LvglPkg: the setup menu laid out like System Preferences on a
wallpaper that follows the hour of the day, the TrackPoint and the touchpad
moving the cursor by their speed),
iPXE [\`${ipxe:0:12}\`](https://github.com/ipxe/ipxe/commit/${ipxe}) with its Intel
driver for network boot, [CSMWrap](https://github.com/CSMWrap/CSMWrap)
[\`${csm:0:12}\`](https://github.com/CSMWrap/CSMWrap/commit/${csm}) with the CSM of
SeaBIOS for legacy boot, libgfxinit for the Intel GPU, the NVIDIA Quadro
K2100M VBIOS exposed to the OS through ACPI \`_ROM\` and the Optimus key the
Windows NVIDIA driver asks for, CPU microcode from coreboot's intel-microcode.
coreboot is built with its cross toolchain, the payload, iPXE and CSMWrap
with the GCC and binutils of the build machine (GitHub's Ubuntu 24.04
runner): \`${lay}\` names them. Licenses: coreboot GPL-2.0, EDK2
BSD-2-Clause-Patent, iPXE GPL-2.0-or-later, CSMWrap LGPL-2.1, SeaBIOS
LGPL-3.0; the sources are at the commits above.
EOF

}

# Le note del M920x (fsp): le variabili di cmd_notes
notes_m920x() {
	local chip16="${n}-16mb-chip.rom" chip8="${n}-8mb-chip.rom"
	echo "**ouroBIOS** ${version}, $(variant_title "${fl}") variant: coreboot and EDK II for the **Lenovo ThinkCentre M920x Tiny**, reborn by design."
	echo
	cat <<EOF
RAM is initialized by Intel's FSP-M for Coffee Lake, as in every coreboot
build for this machine. The rest is what the W541 releases have: the same
EDK II payload and setup, a setup menu of its own in the same layout, vboot
with two signed RW slots, signed UEFI capsules and fwupd. What is specific
to the M920x, what was tried on one and how to go back are in
[docs/m920x.md](https://github.com/${repo}/blob/main/docs/m920x.md).
EOF
	notes_changes
	if [ "${pre}" = yes ]; then
		echo
		echo "**Pre-release**: not yet confirmed on real hardware. Keep a backup of your flash and an external programmer at hand."
	fi
	cat <<EOF

| File | Use |
|---|---|
| \`${rom}\` | **complete 24 MiB flash image**: descriptor (IFD), GbE, Intel ME and coreboot |
| \`${chip8}\` | its last 8 MiB: the read-only part and slot B, enough to boot, for an external programmer on the 8 MiB chip (BIOS2) |
| \`${chip16}\` | its first 16 MiB: descriptor, GbE and ME of the machine the blobs come from, for the 16 MiB chip (BIOS1) |
| \`${cap}\` | **signed UEFI capsule**: updates from Linux an M920x that already runs ouroBIOS, with \`tools/update.py\` |
| \`${cab}\` | the same capsule as an **fwupd package** (\`fwupdmgr install\`, once the project certificate is in \`/etc/pki/fwupd\`) |
| \`${cfg}\` | the complete coreboot \`.config\` |
| \`${lay}\` | flash layout (FMAP) and CBFS contents |
| \`SHA256SUMS\` | checksums of the files above |

Flash layout (\`boards/m920x/flash.fmd\`): the first 12 MiB (IFD, GbE, ME)
come from the coreboot image that ran on the M920x these blobs come from:
unlocked regions, the whole Intel CSME 12 firmware (no \`me_cleaner\`), and
the GbE region with that machine's MAC address. Then, still on the 16 MiB
chip, the regions coreboot writes at runtime (memory training, UEFI
variables, VPD, event log, vboot's state), empty; then the two RW slots, A
across the two chips and B on the 8 MiB one, each signed, and at the top of
the 8 MiB chip the read-only part, which verifies a slot before it runs it
([docs/vboot.md](https://github.com/${repo}/blob/main/docs/vboot.md)). An
update from Linux writes only the BIOS region, as below: it keeps the
machine's own descriptor, ME and MAC address.

**Update with the capsule**, on an M920x that already runs ouroBIOS: the
firmware checks the signature, writes the slot that is not running and
starts again on it; if the new slot does not verify or does not boot, vboot
goes back to the old one. Settings, boot entries, Secure Boot keys, VPD and
event log stay, and *BIOS Lock* and *Firmware protection* can stay on
([docs/update.md](https://github.com/${repo}/blob/main/docs/update.md)).

\`\`\`sh
curl -LO https://raw.githubusercontent.com/${repo}/main/tools/update.py
sudo python3 update.py stage ${latest}       # or: sudo python3 update.py stage ${cap}
sudo systemctl reboot
\`\`\`

Or with fwupd ([docs/update.md](https://github.com/${repo}/blob/main/docs/update.md#fwupd)):
${fwupd_how}

**First install**, on an M920x that already runs coreboot with an unlocked
flash, as the image these blobs come from: only the BIOS region is written.
From the Lenovo firmware the flash is locked: the first time, an external
programmer ([docs/m920x.md](https://github.com/${repo}/blob/main/docs/m920x.md#first-install)).
From an ouroBIOS release, turn off *Firmware protection* (setup menu,
*Security*) first.

\`\`\`sh
sha256sum -c SHA256SUMS --ignore-missing
sudo modprobe -r spi_intel_platform spi_intel               # flashrom must not go through /dev/mtd0
sudo flashrom -p internal -r backup-\$(date +%F).rom        # whole 24 MiB, keep it off the machine
ls -l backup-*.rom                                        # 25165824 bytes
sudo flashrom -p internal --ifd -i bios -w ${rom}
\`\`\`

**External programmer** (recovery): \`${chip8}\` on the 8 MiB chip (BIOS2)
boots (read-only part and slot B); leave the 16 MiB chip (BIOS1) as it is.
\`${chip16}\` would give the machine the descriptor, ME and MAC address of
another machine: see [docs/m920x.md](https://github.com/${repo}/blob/main/docs/m920x.md#recovery).

If flashrom says "Opened /dev/mtd0", the kernel owns the SPI controller: run
\`sudo modprobe -r spi_intel_platform spi_intel\` first. If flashrom cannot
map the flash, boot once with \`iomem=relaxed\` on the kernel command line.
Flashing resets the UEFI settings and boot entries: the firmware then boots
\`\\EFI\\BOOT\\BOOTX64.EFI\` from each disk, so install your boot loader at that
path too (Debian: \`sudo grub-install --removable\`), or pick it once with
*Boot From File* in the boot manager (Esc at power-on).

**Intel ME**: the whole CSME 12 firmware stays; the setup menu turns it off
or back on (*Security*, *Management Engine*). Do not update it with
Lenovo's tools, which expect the Lenovo firmware
([docs/m920x.md](https://github.com/${repo}/blob/main/docs/m920x.md#intel-me)).

**Serial number and machine type (VPD)**: as on the W541, the firmware
reports the serial number, machine type model and UUID of the machine from
the \`RO_VPD\` flash region, which these images leave empty: write it once
with \`tools/vpd.py\`
([how](https://github.com/${repo}/blob/main/docs/m920x.md#serial-number-and-machine-type-vpd)).

Inside: coreboot \`${cbdesc}\` ([${cb:0:12}](https://github.com/coreboot/coreboot/commit/${cb}))
with [${npatch} patches](https://github.com/${repo}/tree/${sha}/patches), EDK2 payload
(MrChromebox [\`${edk2:0:12}\`](https://github.com/mrchromebox/edk2/commit/${edk2})
with [${nedk2} patches](https://github.com/${repo}/blob/${sha}/patches/README.md#edk2-and-lvglpkg)
to EDK2 and LvglPkg), iPXE [\`${ipxe:0:12}\`](https://github.com/ipxe/ipxe/commit/${ipxe})
with its Intel driver for network boot, [CSMWrap](https://github.com/CSMWrap/CSMWrap)
[\`${csm:0:12}\`](https://github.com/CSMWrap/CSMWrap/commit/${csm}) with the CSM of
SeaBIOS for legacy boot, Intel's FSP 2.0 for Coffee Lake (FSP-M and FSP-S,
from coreboot's \`3rdparty/fsp\` at the commit that coreboot pins),
libgfxinit for the Intel GPU, CPU microcode from coreboot's intel-microcode.
coreboot is built with its cross toolchain, the payload, iPXE and CSMWrap
with the GCC and binutils of the build machine (GitHub's Ubuntu 24.04
runner): \`${lay}\` names them. Licenses: coreboot GPL-2.0, EDK2
BSD-2-Clause-Patent, iPXE GPL-2.0-or-later, CSMWrap LGPL-2.1, SeaBIOS
LGPL-3.0, Intel FSP under Intel's license (\`3rdparty/fsp/FSP_License.pdf\`);
the sources are at the commits above.
EOF
}

# Le note della release del flavour $2 (mrc, nri, m920x-fsp), dai file di $1:
# l'inizio comune, il corpo della board (notes_<board>), i cambi dall'ultima
# release dello stesso flavour
cmd_notes() {
	local d="${1:?cartella con le ROM}" fl="${2:?flavour}" board v n f version rom cap cab cfg lay repo sha cb cbdesc ipxe csm edk2 npatch nedk2 pre=no machine=laptop
	: "${VERSION:?}"
	[ -n "${FL_BOARD[${fl}]:-}" ] || die "flavour '${fl}': uno di ${FLAVOURS[*]}"
	flavours_for "${VERSION}"
	[[ " ${FLAVOURS[*]} " == *" ${fl} "* ]] || die "flavour ${fl}: non nelle release di ${VERSION} (${FLAVOURS[*]})"
	board="${FL_BOARD[${fl}]}"
	v="${FL_VARIANT[${fl}]}"
	declare -F "notes_${board}" > /dev/null || die "${fl}: nessuna funzione notes_${board} in tools/ci.sh"
	case "${board}" in m920x) machine=PC ;; esac
	repo="${GITHUB_REPOSITORY:-debianita22/ourobios}"
	sha="${GITHUB_SHA:-$(git -C "${O}" rev-parse HEAD)}"
	version="${VERSION}"
	n="$(fl_name "${fl}")"
	rom="${n}.rom"
	cap="${n}.cap"
	cab="${n}.cab"
	cfg="${n}.config"
	lay="${n}-layout.txt"
	while read -r f; do [ -f "${d}/${f}" ] || die "${d}/${f} non c'e'"; done < <(fl_files "${fl}")
	cb="$(pin COREBOOT_COMMIT)"
	cbdesc="$(pin COREBOOT_DESCRIBE)"
	ipxe="$(pin IPXE_COMMIT)"
	csm="$(pin CSMWRAP_COMMIT)"
	[ -n "${ipxe}" ] && [ -n "${csm}" ] || die "tools/build.sh: IPXE_COMMIT o CSMWRAP_COMMIT non trovati"
	edk2="$(sed -n 's/^CONFIG_EDK2_TAG_OR_REV="\(.*\)"$/\1/p' "${O}/$(board_get "${board}" defconfig "${v}")")"
	[ -n "${edk2}" ] || die "${fl}: CONFIG_EDK2_TAG_OR_REV non nel defconfig"
	npatch="$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "${O}/patches/series" | wc -l)"
	nedk2="$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "${O}/patches/edk2/series" "${O}/patches/lvglpkg/series" | wc -l)"
	case "${version}" in *-*) pre=yes ;; esac
	if [ "${PRERELEASE:-false}" = true ]; then pre=yes; fi
	# --latest salta le pre-release: per queste ci vuole anche --pre
	local latest="--latest"
	if [ "${pre}" = yes ]; then latest="--latest --pre"; fi
	# i remote fwupd: quello del progetto con i metadati dell'ultima release
	# mrc (latest), con le altre della stessa versione, mai una candidate;
	# quello testing (TESTING_TAG) anche con le candidate. Ogni candidate ha
	# la sua versione, sotto quella della release a cui porta
	local fwupd_how meta_row=""
	if [ "${version%%-*}" = "${version}" ] && [ "${PRERELEASE:-false}" != true ]; then
		fwupd_how="with the project remote and certificate installed ([docs/update.md](https://github.com/debianita22/ourobios/blob/main/docs/update.md#the-fwupd-remote)), \`fwupdmgr refresh\` then \`fwupdmgr update\` (or GNOME Software, KDE Discover) offers this release as long as it is the latest, also to a ${machine} on one of its release candidates, each of which has a version of its own, below the release's; or \`sudo fwupdmgr install ${cab}\`. Then reboot."
	else
		fwupd_how="the project remote (\`configs/fwupd/ourobios.conf\`) offers releases only; the testing remote (\`configs/fwupd/ourobios-testing.conf\`, off until \`sudo fwupdmgr enable-remote ourobios-testing\`) offers the release candidates too, each with a version of its own ([docs/update.md](https://github.com/debianita22/ourobios/blob/main/docs/update.md#the-fwupd-remote)). With the project certificate in \`/etc/pki/fwupd\` (once: \`sudo install -m 644 keys/capsule-signing.pem /etc/pki/fwupd/ourobios.pem\` from a clone, then restart fwupd), \`fwupdmgr refresh\` then \`fwupdmgr update\` with the testing remote on, or \`sudo fwupdmgr install ${cab}\`; then reboot. Without the certificate it stops at *Firmware version formats were different*."
	fi
	if [ "${fl}" = mrc ]; then
		meta_row=$'\n'"| \`${FWUPD_METADATA}\`, \`${FWUPD_METADATA}.jcat\` | the signed metadata of the project's **fwupd remote**: the \`.cab\` of every board and variant of this release |"
	fi

	"notes_${board}"

	# i cambi dall'ultima release di questo flavour (pubblicata, antenata di
	# questo commit); serve la storia (checkout con fetch-depth 0). Il tag
	# intero: -nri del W541 non e' -t440p-nri
	local prev="" t
	if [ -n "${GH_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
		for t in $(gh api "repos/${repo}/releases?per_page=100" \
				--jq ".[] | select(.draft | not) | .tag_name | select(test(\"^v[0-9]+\\\\.[0-9]+\\\\.[0-9]+(-rc[0-9]+)?-${fl}\$\"))" 2>/dev/null); do
			[ "${t}" != "${version}-${fl}" ] || continue
			if git -C "${O}" merge-base --is-ancestor "${t}" "${sha}" 2>/dev/null; then
				prev="${t}"
				break
			fi
		done
	fi
	if [ -n "${prev}" ]; then
		echo
		echo "Changes since ${prev}:"
		git -C "${O}" log --no-merges --format='- %s' "${prev}..${sha}"
	fi
	cat <<EOF

Built by GitHub Actions from [\`${sha:0:12}\`](https://github.com/${repo}/commit/${sha}).
EOF
}

# Job release: una release per flavour, bozze prima e pubblicate insieme
# alla fine
cmd_publish() {
	local d="${1:?cartella con le ROM}" sha v t tag rels id draft cur latest=false pre
	: "${VERSION:?}" "${GITHUB_REPOSITORY:?}" "${GITHUB_SHA:?}" "${DEFAULT_BRANCH:?}"
	flavours_for "${VERSION}"
	sha="$(git -C "${O}" rev-parse --verify -q "${GITHUB_SHA}^{commit}")" || fail "Pubblica" "commit ${GITHUB_SHA} non trovato"
	pre="${PRERELEASE:-false}"
	case "${VERSION}" in *-*) pre=true ;; esac
	if [ "${pre}" != true ] && ! on_default_branch "${sha}"; then
		fail "Pubblica" "${sha:0:12} non e' su ${DEFAULT_BRANCH}: da qui solo pre-release"
	fi
	# "latest" solo alla mrc piu' alta, mai a una pre-release
	if [ "${pre}" != true ]; then
		cur="$(latest_tag)" || fail "Pubblica" "la release latest non si legge"
		if [ -z "${cur}" ] || newer "${VERSION}" "${cur}"; then latest=true; fi
	fi
	# Rieseguito dopo che le release sono uscite da questo commit (per
	# esempio quando l'aggiornamento del remote testing si era fermato su
	# un errore di rete): resta publish_testing, che ripete solo cio' che
	# manca. Solo alcune pubblicate, o da un altro commit: ci si ferma qui
	# sotto.
	local pub=0
	for v in "${FLAVOURS[@]}"; do
		t="${VERSION}-${v}"
		tag="$(tag_commit "${t}")" || fail "Pubblica" "origin non risponde (git ls-remote)"
		rels="$(release_ids "${t}")" || fail "Pubblica" "elenco delle release illeggibile"
		if [ "${tag}" = "${sha}" ] && grep -q ' false$' <<< "${rels}"; then pub=$((pub + 1)); fi
	done
	if [ "${pub}" -eq "${#FLAVOURS[@]}" ]; then
		echo "  ${VERSION}: $(fl_list) gia' pubblicate da ${sha:0:12}, resta il remote testing"
		summ "${VERSION}: $(fl_list) gia' pubblicate da ${sha:0:12}."
		publish_testing "${d}" "${sha}"
		return 0
	fi
	for v in "${FLAVOURS[@]}"; do
		t="${VERSION}-${v}"
		say "${t}"
		# il tag, se c'e' gia', deve essere sul commit della build
		tag="$(tag_commit "${t}")" || fail "Pubblica" "origin non risponde (git ls-remote)"
		if [ -n "${tag}" ] && [ "${tag}" != "${sha}" ]; then
			fail "Pubblica" "il tag ${t} e' su ${tag:0:12}, la build su ${sha:0:12}"
		fi
		# una release pubblicata ferma tutto; le bozze sono di un tentativo
		# fallito: via
		rels="$(release_ids "${t}")" || fail "Pubblica" "elenco delle release illeggibile"
		while read -r id draft; do
			[ -n "${id}" ] || continue
			[ "${draft}" = true ] || fail "Pubblica" "la release ${t} e' gia' pubblicata"
			echo "  bozza ${id} di un tentativo precedente: la cancello"
			gh api -X DELETE "repos/${GITHUB_REPOSITORY}/releases/${id}" > /dev/null
		done <<< "${rels}"
		# i file del flavour e un SHA256SUMS solo loro
		rm -rf "${d}/release-${v}"
		mkdir -p "${d}/release-${v}"
		local f up=()
		mapfile -t up < <(fl_files "${v}")
		# i metadati del remote fwupd, con tutti i flavour: solo nella mrc
		if [ "${v}" = mrc ]; then up+=("${FWUPD_METADATA}" "${FWUPD_METADATA}.jcat"); fi
		for f in "${up[@]}"; do
			[ -f "${d}/${f}" ] || fail "Pubblica" "${f} non c'e' negli artifact"
			cp "${d}/${f}" "${d}/release-${v}/"
		done
		(cd "${d}/release-${v}" && sha256sum -- "${up[@]}" > SHA256SUMS)
		cmd_notes "${d}" "${v}" > "${d}/release-${v}/NOTES.md"
		local flags=()
		if [ "${pre}" = true ]; then flags+=(--prerelease); fi
		gh release create "${t}" --repo "${GITHUB_REPOSITORY}" --draft --target "${sha}" \
			--title "ouroBIOS ${VERSION} - $(title_of "${v}")" \
			--notes-file "${d}/release-${v}/NOTES.md" "${flags[@]}"
		(cd "${d}/release-${v}" && gh release upload "${t}" --repo "${GITHUB_REPOSITORY}" --clobber \
			"${up[@]}" SHA256SUMS)
	done
	# pubblicate insieme: mai solo alcune visibili per un errore a meta'
	for v in "${FLAVOURS[@]}"; do
		t="${VERSION}-${v}"
		if [ "${v}" = mrc ]; then
			gh release edit "${t}" --repo "${GITHUB_REPOSITORY}" --draft=false --latest="${latest}"
		else
			gh release edit "${t}" --repo "${GITHUB_REPOSITORY}" --draft=false --latest=false
		fi
		summ "### Pubblicata: https://github.com/${GITHUB_REPOSITORY}/releases/tag/${t}"
		note notice "Release" "${t} pubblicata"
	done
	if [ "${pre}" = true ]; then
		echo "  $(fl_list) pre-release"
	elif [ "${latest}" = true ]; then
		echo "  ${VERSION}-mrc latest, le altre release"
	else
		echo "  ${VERSION}-mrc non latest (resta ${cur}), le altre release"
	fi
	publish_testing "${d}" "${sha}"
}

# Le note della release TESTING_TAG: non e' una release, dice che versione
# tiene (la riga "version:" la rilegge publish_testing)
testing_notes() {
	local repo="${GITHUB_REPOSITORY}" links="" v
	for v in "${FLAVOURS[@]}"; do
		links+="${links:+, }[${VERSION}-${v}](https://github.com/${repo}/releases/tag/${VERSION}-${v})"
	done
	cat <<EOF
Not a release: the assets of this entry are the signed metadata of the
project's fwupd **testing** remote, the \`.cab\` of every board and variant
of the latest release, release candidates included ([docs/update.md](https://github.com/${repo}/blob/main/docs/update.md#the-fwupd-remote)).
Every release replaces them; the tag stays where this entry was first made.

Now: **ouroBIOS ${VERSION}** (${links}).

\`\`\`sh
sudo install -m 644 configs/fwupd/ourobios-testing.conf /etc/fwupd/remotes.d/
sudo fwupdmgr enable-remote ourobios-testing
\`\`\`

<!-- version: ${VERSION} -->
EOF
}

# I metadati di questa versione negli asset della release TESTING_TAG, se
# e' piu' alta di quella che c'e' (rc comprese: v1.3.7-rc1 dopo v1.3.6, non
# dopo v1.3.7). La release si crea la prima volta, poi si riscrivono solo
# gli asset e le note: niente notifica di una nuova release a ogni giro.
publish_testing() {
	local d="$1" sha="$2" out cur
	say "remote testing (${TESTING_TAG})"
	if out="$(gh api "repos/${GITHUB_REPOSITORY}/releases/tags/${TESTING_TAG}" --jq .body 2>&1)"; then
		cur="$(grep -o '<!-- version: v[0-9A-Za-z.-]* -->' <<< "${out}" | sed 's/<!-- version: \(.*\) -->/\1/' | head -n 1)"
		if [ -n "${cur}" ] && ! newer "${VERSION}" "${cur}"; then
			echo "  resta ${cur}: ${VERSION} non e' piu' alta"
			summ "Remote testing: resta ${cur}."
			return 0
		fi
	else
		case "${out}" in
			*"HTTP 404"*|*"Not Found"*)
				echo "  la release ${TESTING_TAG} non c'e': la creo"
				testing_notes > "${d}/TESTING.md"
				gh release create "${TESTING_TAG}" --repo "${GITHUB_REPOSITORY}" --prerelease --target "${sha}" \
					--title "fwupd remote: testing" --notes-file "${d}/TESTING.md" \
					|| fail "Pubblica" "la release ${TESTING_TAG} non si crea"
				;;
			*) fail "Pubblica" "la release ${TESTING_TAG} non si legge: ${out}" ;;
		esac
	fi
	(cd "${d}" && gh release upload "${TESTING_TAG}" --repo "${GITHUB_REPOSITORY}" --clobber \
		"${FWUPD_METADATA}" "${FWUPD_METADATA}.jcat") || fail "Pubblica" "asset di ${TESTING_TAG} non caricati"
	testing_notes > "${d}/TESTING.md"
	gh release edit "${TESTING_TAG}" --repo "${GITHUB_REPOSITORY}" --prerelease --latest=false \
		--notes-file "${d}/TESTING.md" || fail "Pubblica" "note di ${TESTING_TAG} non aggiornate"
	echo "  ${TESTING_TAG}: ${VERSION}${cur:+ (era ${cur})}"
	summ "Remote testing: ${VERSION}${cur:+ (era ${cur})}."
}

# Job release: i file di ogni release in DIST, quelli che si pubblicano
# (tools/verify-rom.sh li ha gia' controllati nel job build, qui sui file
# scaricati): ci sono tutti con i loro checksum; i byte prima della regione
# BIOS (IFD, GbE, ME) sono quelli di BOARD_REFERENCE della board; capsula e
# pacchetto fwupd firmati dalla chiave di keys/ e con la ROM della release;
# i metadati del remote fwupd firmati, con i .cab di tutti i flavour e
# nient'altro
cmd_check() {
	local d="${1:?cartella con le ROM}" v b n f ref size want have cabs=()
	: "${VERSION:?}"
	flavours_for "${VERSION}"
	[ -f "${d}/SHA256SUMS" ] || fail "Controlli" "${d}/SHA256SUMS non c'e'"
	(cd "${d}" && sha256sum -c --quiet SHA256SUMS) || fail "Controlli" "i file di ${d} non sono quelli di SHA256SUMS"
	for v in "${FLAVOURS[@]}"; do
		b="${FL_BOARD[${v}]}"
		n="$(fl_name "${v}")"
		while read -r f; do
			[ -s "${d}/${f}" ] || fail "Controlli" "${VERSION}-${v}: manca ${f}"
			grep -q "[ *]${f}\$" "${d}/SHA256SUMS" || fail "Controlli" "${VERSION}-${v}: ${f} non e' in SHA256SUMS"
		done < <(fl_files "${v}")
		size="$(board_get "${b}" BOARD_INTEL_SIZE)"
		ref="${O}/$(board_get "${b}" BOARD_REFERENCE)"
		[ -f "${ref}" ] || fail "Controlli" "${b}: ${ref#"${O}/"} non c'e'"
		case "${ref}" in
			*.sha256)
				want="$(cut -d' ' -f1 "${ref}")"
				have="$(head -c "${size}" "${d}/${n}.rom" | sha256sum | cut -d' ' -f1)"
				[ "${have}" = "${want}" ] \
					|| fail "Controlli" "${n}.rom: i primi $((size >> 20)) MiB (IFD, GbE, ME) non hanno lo SHA-256 di ${ref#"${O}/"}"
				;;
			*)
				cmp -n "${size}" "${d}/${n}.rom" "${ref}" \
					|| fail "Controlli" "${n}.rom: i primi $((size >> 20)) MiB (IFD, GbE, ME) diversi da ${ref#"${O}/"}"
				;;
		esac
		# la capsula: la ROM di questa release, firmata dalla chiave di keys/
		python3 "${O}/tools/update.py" info --cert "${O}/keys/capsule-signing.pem" \
			--rom "${d}/${n}.rom" "${d}/${n}.cap" \
			|| fail "Controlli" "${n}.cap non passa tools/update.py info"
		# il pacchetto fwupd: quella capsula, metainfo e firma jcat
		python3 "${O}/tools/update.py" info --cert "${O}/keys/capsule-signing.pem" \
			--same-as "${d}/${n}.cap" "${d}/${n}.cab" \
			|| fail "Controlli" "${n}.cab non passa tools/update.py info"
		cabs+=("${d}/${n}.cab")
		echo "  ok  ${VERSION}-${v}: $(fl_files "${v}" | wc -l) file, IFD/GbE/ME, capsula e .cab"
	done
	python3 "${O}/tools/fwupd-cab.py" check-metadata --cert "${O}/keys/capsule-signing.pem" \
		"${d}/${FWUPD_METADATA}" "${cabs[@]}" \
		|| fail "Controlli" "${FWUPD_METADATA}: non firmato da keys/ o non con i .cab di $(fl_list "${VERSION}-")"
	echo "  ok  ${FWUPD_METADATA}: i .cab di $(fl_list "${VERSION}-")"
	summ "Controlli: $(fl_list "${VERSION}-"), ${FWUPD_METADATA}."
}

# Le ROM del job build (DIST) e quelle del job repro (REPRO, un runner che
# ha costruito tutto da capo: coreboot, EDK2, iPXE, CSMWrap) uguali bit a
# bit, con i loro .config. Se no, le regioni della mappa che differiscono
# (tools/update.py) e i compilatori delle due build, dai file del layout: due
# runner con immagini di versioni diverse (gcc, binutils) danno payload diversi
cmd_compare() {
	: "${VERSION:?}"
	flavours_for "${VERSION}"
	local a="$1" b="$2" v f n bad=0
	for v in "${FLAVOURS[@]}"; do
		n="$(fl_name "${v}")"
		for f in "${n}.rom" "${n}.config" "${n}-layout.txt"; do
			[ -f "${a}/${f}" ] || fail "Build riproducibile" "manca ${a}/${f} (job build)"
			[ -f "${b}/${f}" ] || fail "Build riproducibile" "manca ${b}/${f} (job repro)"
		done
		if ! cmp -s "${a}/${n}.config" "${b}/${n}.config"; then
			bad=1
			echo "  NO  ${v}: i .config delle due build sono diversi"
			diff "${a}/${n}.config" "${b}/${n}.config" || true
		fi
		if cmp -s "${a}/${n}.rom" "${b}/${n}.rom"; then
			echo "  ok  ${v}: la ROM del job repro e' uguale a quella del job build ($(sha256sum "${a}/${n}.rom" | cut -c1-16)...)"
			continue
		fi
		bad=1
		echo "  NO  ${v}: la ROM del job repro e' diversa da quella del job build"
		python3 - "${O}/tools" "${a}/${n}.rom" "${b}/${n}.rom" <<-'EOF' || echo "      (regioni non confrontate)"
			import sys
			sys.path.insert(0, sys.argv[1])
			import update
			a = open(sys.argv[2], "rb").read()
			b = open(sys.argv[3], "rb").read()
			if len(a) != len(b):
			    print("      %d e %d byte" % (len(a), len(b)))
			areas = update.fmap_areas(a) or {}
			for name, (off, size) in sorted(areas.items(), key=lambda i: i[1]):
			    if a[off:off + size] != b[off:off + size]:
			        print("      regione %s diversa" % name)
		EOF
		diff <(grep '^toolchain: ' "${a}/${n}-layout.txt") <(grep '^toolchain: ' "${b}/${n}-layout.txt") > /dev/null \
			|| { echo "      compilatori diversi:"; grep '^toolchain: ' "${a}/${n}-layout.txt" "${b}/${n}-layout.txt"; }
	done
	[ "${bad}" = 0 ] || fail "Build riproducibile" "le ROM del job repro non sono uguali a quelle del job build (regioni e compilatori nel log)"
	summ "Build riproducibile: le ROM del job repro, costruite da capo su un altro runner, uguali a quelle del job build."
}

case "${1:-}" in
	version) cmd_version ;;
	notes)   shift; cmd_notes "$@" ;;
	check)   shift; cmd_check "$@" ;;
	compare) shift; cmd_compare "$@" ;;
	publish) shift; cmd_publish "$@" ;;
	*) die "uso: ci.sh version | notes DIST FLAVOUR | check DIST | compare DIST REPRO | publish DIST (flavour: ${FLAVOURS[*]})" ;;
esac
