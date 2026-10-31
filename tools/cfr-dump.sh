#!/usr/bin/env bash
# cfr-dump.sh - il menu di setup (CFR) di una build coreboot di una board del
# progetto (W541, M920x), costruito sull'host: il record lb_cfr esattamente
# come il ramstage lo mette nella tabella di coreboot, per darlo al payload
# senza la macchina (tools/qemu-setup-shots.py: in QEMU q35, con
# patches/test/q35-cfr-file.patch).
#
#   tools/cfr-dump.sh [-o FILE] [-q] [-x NOME]... ALBERO BUILD
#   tools/cfr-dump.sh -c FILE
#
# ALBERO e' l'albero coreboot (i sorgenti: si legge e basta), BUILD una sua
# build configurata (build-nri, build-mrc, build-m920x-fsp): config.h, build.h, il
# static.c del devicetree e, se c'e', l'elenco dei cfr.o del ramstage, cioe'
# quali sorgenti CFR la build compila. Nella BUILD non si scrive niente.
#
# Il codice del menu si compila come per il ramstage (header di coreboot,
# config.h della build, -m32 se l'host lo sa linkare) con tools/cfr-dump/
# stubs.c, che include il cfr.c della mainboard e sostituisce le funzioni che
# leggono l'hardware (CPU, cbmem, VPD, EC) con valori finti; quelle dell'H8
# che leggono il devicetree prendono i valori dal static.c. Poi:
#   1. stubs.c scrive il record (mb_cfr_setup_menu(), come il ramstage) in
#      FILE (default: cfr.bin);
#   2. lo script lo rilegge per conto suo: dimensioni, tag e allineamento di
#      ogni record, CRC32, stringhe, ID e dipendenze, e stampa l'albero;
#   3. confronta l'albero letto dal blob con quello delle strutture in
#      memoria (sm_root[] e le form generiche, con i ctor): devono essere
#      uguali, oggetto per oggetto;
#   4. ogni opzione in una scheda sola: nessun nome di opzione due volte
#      nel menu, e nel menu ogni opzione che i sorgenti compilati
#      dichiarano (.opt_name, dopo il preprocessore con il config.h della
#      build: anche quelle degli header, che il compilatore non segnala),
#      tranne quelle di -x NOME (anche con * e ?, ripetibile), che la
#      board lascia fuori apposta.
#   5. il record non supera i 28 KiB: la tabella di coreboot ne ha 32 in
#      tutto (COREBOOT_TABLE_SIZE in src/arch/x86/include/arch/cbconfig.h)
#      e write_tables() non si ferma se non ci sta, scrive oltre la sua
#      voce di CBMEM e lo dice solo dopo; gli altri record ne prendono
#      circa 1,6 (M920x) e le stringhe dei callback crescono sulla macchina.
# Esce con 1 se il blob non e' valido o non corrisponde, un'opzione manca
# o e' ripetuta o il record e' troppo grande, con gli avvisi
# (dipendenze senza oggetto, form visibili vuote, piu' di otto categorie...)
# sullo stderr. -q non stampa l'albero. -c controlla e stampa soltanto un
# record gia' fatto (anche estratto da una ROM: cbfstool ... extract -n
# cfr.bin), senza il confronto con i sorgenti.
#
# Gli ID degli oggetti vengono dai puntatori, come nel ramstage: con -m32
# hanno la stessa forma (0xffffcafe........), ma non gli stessi valori.
set -euo pipefail

usage() {
	echo "uso: $0 [-o FILE] [-q] [-x NOME]... ALBERO BUILD | -c FILE" >&2
	exit 2
}

die() {
	echo "cfr-dump: $*" >&2
	exit 1
}

out=cfr.bin
quiet=0
check=""
exclude=()
while getopts o:qc:x:h opt; do
	case "${opt}" in
		o) out="${OPTARG}" ;;
		q) quiet=1 ;;
		c) check="${OPTARG}" ;;
		x) exclude+=("${OPTARG}") ;;
		*) usage ;;
	esac
done
shift $((OPTIND - 1))
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${check}" ]; then
	[ $# = 0 ] && [ -f "${check}" ] || usage
	# solo il controllo e l'albero: lo stesso python qui sotto, senza elenco
	exec python3 -I - "${check}" - "${quiet}" - < <(sed -n '/^python3 -I - "${out}"/,/^PY$/{//!p}' "${here}/cfr-dump.sh")
fi
[ $# = 2 ] || usage

tree="$(cd "$1" 2> /dev/null && pwd)" || die "$1: albero non trovato"
build="$(cd "$2" 2> /dev/null && pwd)" || die "$2: build non trovata"
stubs="${here}/cfr-dump/stubs.c"
CC="${HOSTCC:-gcc}"

[ -f "${tree}/src/drivers/option/cfr.c" ] || die "${tree}: non e' un albero coreboot con CFR"
for f in config.h build.h; do
	[ -f "${build}/${f}" ] || die "${build}: manca ${f} (prima make ... olddefconfig, o una build)"
done
grep -q '^#define CONFIG_DRIVERS_OPTION_CFR 1$' "${build}/config.h" \
	|| die "${build}: CONFIG_DRIVERS_OPTION_CFR non e' attivo"
mbdir="$(sed -n 's/^#define CONFIG_MAINBOARD_DIR "\(.*\)"$/\1/p' "${build}/config.h")"
mbcfr="${tree}/src/mainboard/${mbdir}/cfr.c"
[ -f "${mbcfr}" ] || die "${mbcfr}: la mainboard non ha un cfr.c"

work="$(mktemp -d "${TMPDIR:-/tmp}/cfr-dump.XXXXXX")"
trap 'rm -rf "${work}"' EXIT

# I sorgenti CFR del ramstage: i suoi cfr.o (in coreboot le form stanno nei
# cfr.c). Senza oggetti, una build mai fatta: quelli di ogni board con CFR,
# piu' l'H8 se c'e'
mapfile -t srcs < <(
	if [ -d "${build}/ramstage" ]; then
		cd "${build}/ramstage" && find . -name cfr.o | sed 's|^\./||; s|\.o$|.c|' | sort
	fi
)
if [ "${#srcs[@]}" = 0 ]; then
	srcs=(console/cfr.c drivers/option/cfr.c "mainboard/${mbdir}/cfr.c")
	grep -q '^#define CONFIG_EC_LENOVO_H8 1$' "${build}/config.h" && srcs+=(ec/lenovo/h8/cfr.c)
	echo "cfr-dump: nessun cfr.o in ${build}/ramstage, sorgenti presunti: ${srcs[*]}" >&2
fi

# Le opzioni dell'H8 dal devicetree della build (default: quelle del W541)
h8=(-DCFR_DUMP_H8_THINKLIGHT=0 -DCFR_DUMP_H8_KB_BACKLIGHT=1 -DCFR_DUMP_H8_UWB=0 -DCFR_DUMP_H8_PM_BEEPS=0
	-DCFR_DUMP_H8_POWER_ON_AC=1 -DCFR_DUMP_H8_KBD_BEEP=1 -DCFR_DUMP_H8_UAO_BATTERY=1)
static_c="$(find "${build}/mainboard" -name static.c 2>/dev/null | head -n 1 || true)"
if [ -n "${static_c}" ]; then
	h8conf="$(sed -n '/struct ec_lenovo_h8_config ec_lenovo_h8_info_/,/^};/p' "${static_c}")"
	if [ -n "${h8conf}" ]; then
		h8=()
		for f in has_thinklight:THINKLIGHT has_keyboard_backlight:KB_BACKLIGHT has_uwb:UWB \
				has_power_management_beeps:PM_BEEPS has_power_on_ac_attach:POWER_ON_AC \
				has_keyboard_beep_option:KBD_BEEP uao_battery_in_config2:UAO_BATTERY; do
			v="$(sed -n "s/^\s*\.${f%%:*} = \(.*\),$/\1/p" <<< "${h8conf}")"
			h8+=("-DCFR_DUMP_H8_${f#*:}=${v:-0}")
		done
	fi
fi

# Come il ramstage: -m32 se l'host ha la libc a 32 bit, altrimenti a 64 bit
arch=(-m32 -D__ARCH_x86_32__)
if ! echo 'int main(void) { return 0; }' | "${CC}" -m32 -no-pie -x c - -o "${work}/m32" > /dev/null 2>&1; then
	arch=(-D__ARCH_x86_64__)
	echo "cfr-dump: ${CC} non linka a 32 bit (gcc-multilib), compilo a 64 bit" >&2
fi
std=gnu2x
"${CC}" -std=gnu23 -E -x c /dev/null > /dev/null 2>&1 && std=gnu23
cflags=("${arch[@]}" -std="${std}" -O1 -g -nostdinc -ffreestanding -fno-builtin -fno-common
	-fno-strict-aliasing -fno-stack-protector -fno-pie -Wall -Wno-unused-function -Wno-unused-variable
	-Wno-address-of-packed-member
	-D__COREBOOT__ -D__RAMSTAGE__ "-D__BUILD_DIR__=\"${build}\""
	-I"${tree}/src" -I"${tree}/src/include" -I"${tree}/src/commonlib/include"
	-I"${tree}/src/commonlib/bsd/include" -I"${build}" -I"${tree}/src/arch/x86/include"
	-I"${tree}/3rdparty/vboot/firmware/include" -I"${tree}/3rdparty"
	-include "${tree}/src/include/kconfig.h" -include "${tree}/src/include/rules.h"
	-include "${tree}/src/commonlib/bsd/include/commonlib/bsd/compiler.h")
# Gli header della board (<mainboard/...>), se ne ha: il suo Makefile.mk li
# aggiunge con CPPFLAGS_common, e il cfr.c del M920x usa mainboard/ec.h
[ -d "${tree}/src/mainboard/${mbdir}/include" ] && cflags+=(-I"${tree}/src/mainboard/${mbdir}/include")
# Con un SoC Intel (il M920x: cannonlake), i suoi header e quelli del codice
# comune e di FSP, dopo gli altri come nel Makefile di coreboot: il cfr.c
# della board usa i suoi enum (soc/soc_chip.h, intelblocks/)
for d in "${tree}"/src/soc/intel/*/include; do
	n="$(basename "$(dirname "${d}")")"
	if grep -Eq "^#define CONFIG_SOC_INTEL_${n^^}(_BASE)? 1$" "${build}/config.h"; then
		cflags+=(-I"${d}" -I"${tree}/src/soc/intel/common/block/include"
			-I"${tree}/src/soc/intel/common/basecode/include" -I"${tree}/src/soc/intel/common/pch/include")
	fi
done
fsp="$(sed -n 's/^#define CONFIG_FSP_HEADER_PATH "\(.*\)"$/\1/p' "${build}/config.h")"
if [ -n "${fsp}" ]; then
	cflags+=(-I"${tree}/${fsp}" -I"${tree}/src/drivers/intel/fsp2_0/include")
	# gli header di EDK2 della versione di FSP (UDK_*_BINDING), come li
	# aggiunge src/vendorcode/intel/Makefile.mk per l'architettura scelta
	mkarch=x86_32
	[ "${arch[0]}" = -m32 ] || mkarch=x86_64
	mapfile -t udk < <(awk -v tree="${tree}" -v a="CPPFLAGS_${mkarch}" '
		NR == FNR { if ($1 == "#define" && $3 == "1") set[$2] = 1; next }
		/^(else )?ifeq \(\$\(CONFIG_[A-Z0-9_]+\),y\)/ {
			match($0, /CONFIG_[A-Z0-9_]+/); on = (substr($0, RSTART, RLENGTH) in set); next
		}
		/^endif/ { on = 0; next }
		on && ($1 == "CPPFLAGS_common" || $1 == a) && $2 == "+=" {
			for (i = 3; i <= NF; i++) { f = $i; gsub(/\$\(src\)/, tree "/src", f); print f }
		}' "${build}/config.h" "${tree}/src/vendorcode/intel/Makefile.mk")
	cflags+=("${udk[@]}")
fi

objs=()
compile() {
	local src="$1" o
	o="${work}/$(echo "${src#"${tree}"/src/}" | tr / _).o"
	shift
	"${CC}" "${cflags[@]}" "$@" -c "${src}" -o "${o}" || die "${src}: non compila"
	# le opzioni che il sorgente dichiara, come il compilatore lo vede
	"${CC}" "${cflags[@]}" "$@" -E "${src}" 2> /dev/null \
		| grep -o '\.opt_name[[:space:]]*=[[:space:]]*"[^"]*"' \
		| sed 's/.*"\([^"]*\)"$/\1/' >> "${work}/declared" || true
	# le form generiche (__cfr_form, .rodata.cfr_forms nel ramstage) in una
	# sezione con un nome da C: il linker dell'host da' __start_ e __stop_
	objcopy --rename-section .rodata.cfr_forms=cfr_forms "${o}"
	objs+=("${o}")
}
for s in "${srcs[@]}"; do
	case "${s}" in
		"mainboard/${mbdir}/cfr.c") ;;		# in stubs.c
		drivers/option/cfr.c)
			compile "${tree}/src/${s}" -D_cfr_forms=__start_cfr_forms -D_ecfr_forms=__stop_cfr_forms ;;
		*) compile "${tree}/src/${s}" ;;
	esac
done
compile "${tree}/src/lib/crc_byte.c"
compile "${stubs}" "-DCFR_DUMP_MB_CFR=\"${mbcfr}\"" "${h8[@]}"
"${CC}" "${arch[0]}" -no-pie -o "${work}/cfr-dump-bin" "${objs[@]}" 2> "${work}/ld.log" \
	|| { cat "${work}/ld.log" >&2; die "link fallito (una funzione del menu da aggiungere a stubs.c?)"; }

"${work}/cfr-dump-bin" blob > "${work}/cfr.bin" 2> "${work}/blob.log" \
	|| { cat "${work}/blob.log" >&2; die "il menu non si costruisce"; }
grep -v '^CFR: Written' "${work}/blob.log" >&2 || true
"${work}/cfr-dump-bin" list > "${work}/list.ref" || die "l'elenco di riferimento non si costruisce"
cp "${work}/cfr.bin" "${out}"

sort -u -o "${work}/declared" "${work}/declared"
# (su una riga sola: -c ne prende il codice con sed, dalla riga dopo questa)
python3 -I - "${out}" "${work}/list.ref" "${quiet}" "${mbcfr#"${tree}"/}" "${work}/declared" "${exclude[@]}" <<'PY'
import collections
import difflib
import fnmatch
import struct
import sys

path, ref, quiet, mbcfr = sys.argv[1], sys.argv[2], sys.argv[3] == "1", sys.argv[4]
declared = sys.argv[5] if len(sys.argv) > 5 else "-"
exclude = sys.argv[6:]
data = open(path, "rb").read()
warnings = []


class Bad(Exception):
    pass


# CRC32 di coreboot (lib/crc_byte.c): polinomio 0x04C11DB7, MSB first,
# partenza 0 e nessuno XOR finale; quella del payload (CbCalculateCrc32) e' uguale
TABLE = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04C11DB7) if c & 0x80000000 else (c << 1)
    TABLE.append(c & 0xFFFFFFFF)


def crc32(buf):
    crc = 0
    for b in buf:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ TABLE[((crc >> 24) ^ b) & 0xFF]
    return crc


FORM, ENUM_VALUE, ENUM, NUMBER, BOOL, VARCHAR = 1, 2, 3, 4, 5, 6
OPT_NAME, UI_NAME, HELPTEXT, DEF_VALUE, COMMENT, DEP_VALUES = 7, 8, 9, 10, 11, 12
KIND = {FORM: "form", ENUM: "enum", NUMBER: "number", BOOL: "bool", VARCHAR: "varchar", COMMENT: "comment"}
FLAGS = ((1, "readonly"), (2, "inactive"), (4, "suppress"), (8, "volatile"), (16, "runtime"),
         (32, "lock_at_boot"))


def header(off, end, what):
    if off + 8 > end:
        raise Bad("0x%x: %s troncato" % (off, what))
    tag, size = struct.unpack_from("<II", data, off)
    if size < 8 or off + size > end or size % 4:
        raise Bad("0x%x: %s (tag %d) di %d byte, fuori dal genitore (fine 0x%x) o non allineato a 4"
                  % (off, what, tag, size, end))
    return tag, size


def varbin(off, end, tag):
    t, size = header(off, end, "varbinary")
    if t != tag:
        raise Bad("0x%x: tag %d, atteso %d" % (off, t, tag))
    dlen, = struct.unpack_from("<I", data, off + 8)
    if 12 + dlen > size or (12 + dlen + 3) & ~3 != size:
        raise Bad("0x%x: varbinary di %d byte con %d byte di dati" % (off, size, dlen))
    return data[off + 12:off + 12 + dlen], off + size


def string(off, end, tag):
    raw, nxt = varbin(off, end, tag)
    if not raw or raw[-1] != 0 or 0 in raw[:-1]:
        raise Bad("0x%x: stringa senza NUL finale o con un NUL in mezzo" % off)
    try:
        s = raw[:-1].decode("ascii")
    except UnicodeDecodeError:
        s = raw[:-1].decode("utf-8", "replace")
        warnings.append("stringa non ASCII a 0x%x: %r" % (off, s))
    return s, nxt


def peek(off, end):
    return struct.unpack_from("<I", data, off)[0] if off + 4 <= end else None


def option(off, end):
    tag, size = header(off, end, "opzione")
    if tag not in KIND:
        raise Bad("0x%x: tag %d dove va un'opzione o una form" % (off, tag))
    rend = off + size
    n = {"kind": KIND[tag], "off": off, "name": "-", "help": None, "depvals": None,
         "values": [], "children": []}
    n["id"], n["dep"], n["flags"] = struct.unpack_from("<QQI", data, off + 8)
    p = off + 28
    if tag in (ENUM, NUMBER, BOOL):
        (n["default"], n["min"], n["max"], n["step"], n["disp"]) = struct.unpack_from("<5I", data, p)
        p += 20
    if tag == VARCHAR:
        n["default"], p = string(p, rend, DEF_VALUE)
    if tag in (ENUM, NUMBER, BOOL, VARCHAR):
        n["name"], p = string(p, rend, OPT_NAME)
    n["ui"], p = string(p, rend, UI_NAME)
    if tag != FORM and peek(p, rend) == HELPTEXT:
        n["help"], p = string(p, rend, HELPTEXT)
    if peek(p, rend) == DEP_VALUES:
        raw, p = varbin(p, rend, DEP_VALUES)
        if len(raw) % 4:
            raise Bad("0x%x: dep_values di %d byte" % (p, len(raw)))
        n["depvals"] = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    while p < rend:
        if tag == ENUM:
            t, s = header(p, rend, "valore")
            if t != ENUM_VALUE:
                raise Bad("0x%x: tag %d nell'enum %s" % (p, t, n["name"]))
            value, = struct.unpack_from("<I", data, p + 8)
            name, q = string(p + 12, p + s, UI_NAME)
            if q != p + s:
                raise Bad("0x%x: valore di enum con %d byte in piu'" % (p, p + s - q))
            n["values"].append((name, value))
            p += s
        elif tag == FORM:
            child = option(p, rend)
            n["children"].append(child)
            p += child["size"]
        else:
            raise Bad("0x%x: tag %d in piu' nell'opzione %s" % (p, peek(p, rend), n["name"]))
    n["size"] = size
    return n


try:
    if len(data) < 16:
        raise Bad("%d byte: niente lb_cfr" % len(data))
    tag, size, version, checksum = struct.unpack_from("<4I", data)
    if tag != 0x47 or size != len(data) or version != 0:
        raise Bad("radice: tag 0x%x (atteso 0x47), %d byte (il file ne ha %d), versione %d"
                  % (tag, size, len(data), version))
    if crc32(data[16:]) != checksum:
        raise Bad("CRC32 0x%08x, nel record 0x%08x" % (crc32(data[16:]), checksum))
    forms, p = [], 16
    while p < size:
        if peek(p, size) != FORM:
            raise Bad("0x%x: tag %d nella radice, solo form" % (p, peek(p, size)))
        f = option(p, size)
        forms.append(f)
        p += f["size"]
except Bad as e:
    sys.exit("cfr-dump: %s: blob non valido: %s" % (path, e))


def walk(nodes, depth=0):
    for n in nodes:
        yield n, depth
        yield from walk(n["children"], depth + 1)


ids, names = {}, {}
for n, _ in walk(forms):
    if n["id"]:
        if n["id"] in ids:
            warnings.append("ID 0x%x ripetuto (%s e %s)" % (n["id"], ids[n["id"]]["name"], n["name"]))
        ids[n["id"]] = n
    if n["name"] != "-":
        if n["name"] in names and names[n["name"]]["kind"] != n["kind"]:
            warnings.append("opzione %s di due tipi (%s, %s)" % (n["name"], names[n["name"]]["kind"], n["kind"]))
        names[n["name"]] = n


def hidden(n):
    return bool(n["flags"] & 4)


def paths_of(nodes, name, trail=()):
    """I titoli delle form che portano a ogni opzione di nome name."""
    for n in nodes:
        if n["kind"] == "form":
            yield from paths_of(n["children"], name, trail + (n["ui"],))
        elif n["name"] == name:
            yield trail + (n["ui"],)


for n, _ in walk(forms):
    if n["dep"]:
        d = ids.get(n["dep"])
        if d is None or d["kind"] not in ("bool", "enum"):
            warnings.append("%s \"%s\": dipende dall'ID 0x%x, che non e' un bool o un enum del menu"
                            % (n["kind"], n["ui"], n["dep"]))
    if n["kind"] == "enum":
        if not n["values"]:
            warnings.append("enum %s senza valori" % n["name"])
        elif n["default"] not in [v for _, v in n["values"]]:
            warnings.append("enum %s: il default %d non e' tra i valori" % (n["name"], n["default"]))
    if n["kind"] == "number" and not n["min"] <= n["default"] <= n["max"]:
        warnings.append("number %s: default %d fuori da %d..%d" % (n["name"], n["default"], n["min"], n["max"]))
    if n["kind"] == "form" and not hidden(n) and not any(not hidden(c) for c in n["children"]):
        warnings.append("form \"%s\" visibile senza opzioni visibili: una pagina o una scheda vuota" % n["ui"])

categories = [f["ui"] for f in forms if not hidden(f)]
if len(categories) > 8:
    warnings.append("%d categorie: il payload (CfrSetupMenuDxe, patch edk2/0002) ne fa pagine solo per le "
                    "prime otto" % len(categories))


def flags(n):
    f = [name for bit, name in FLAGS if n["flags"] & bit]
    return " [%s]" % ",".join(f) if f else ""


def dep(n):
    if not n["dep"]:
        return ""
    d = ids.get(n["dep"])
    s = " dep=%s" % (d["name"] if d else "?0x%x" % n["dep"])
    if n["depvals"]:
        s += "[%s]" % ",".join(str(v) for v in n["depvals"])
    return s


if not quiet:
    print("%s: %d byte, CRC32 0x%08x, %d form di primo livello, %d opzioni"
          % (path, len(data), checksum, len(forms),
             sum(1 for n, _ in walk(forms) if n["kind"] not in ("form", "comment"))))
    for n, depth in walk(forms):
        line = "  " * depth + "%s %s \"%s\"" % (n["kind"], n["name"], n["ui"])
        if n["kind"] == "varchar":
            line += " = \"%s\"" % n["default"]
        elif n["kind"] in ("bool", "enum"):
            line += " = %d" % n["default"]
        elif n["kind"] == "number":
            fmt = "0x%x" if n["disp"] & 1 else "%d"
            line += (" = " + fmt + " (" + fmt + ".." + fmt + ", step %d)") % (
                n["default"], n["min"], n["max"], n["step"])
        line += dep(n) + flags(n)
        if n["values"]:
            line += " {%s}" % "|".join("%s=%d" % v for v in n["values"])
        print(line)
    print("categorie del setup (form visibili di primo livello): %s" % ", ".join(categories))

# L'elenco nello stesso formato di stubs.c (list): tipo, nome, etichetta,
# dipendenza, valori degli enum
listing = []
for n, depth in walk(forms):
    line = "  " * depth + "%s %s \"%s\"%s" % (n["kind"], n["name"], n["ui"], dep(n))
    if n["kind"] == "enum" and n["values"]:
        line += " {%s}" % "|".join("%s=%d" % v for v in n["values"])
    listing.append(line + "\n")
for w in warnings:
    print("cfr-dump: avviso: %s" % w, file=sys.stderr)

# Ogni opzione in una scheda sola: un nome di opzione una volta nel menu
# (due oggetti con lo stesso nome sono la stessa variabile, mostrata due
# volte), e ogni opzione dichiarata dai sorgenti compilati nel menu
errors = []
# Il margine nella tabella di coreboot (32 KiB, COREBOOT_TABLE_SIZE): vedi
# il punto 5 in cima
BUDGET = 28 << 10
if len(data) > BUDGET:
    errors.append("record di %d byte, oltre %d: con gli altri record la tabella di coreboot "
                  "(0x8000 byte) puo' non bastare, e write_tables() scrive oltre la voce di CBMEM"
                  % (len(data), BUDGET))
count = collections.Counter(n["name"] for n, _ in walk(forms) if n["name"] != "-")
for name, c in sorted(count.items()):
    if c > 1:
        where = ["/".join(p) for p in paths_of(forms, name)]
        errors.append("opzione %s in %d posti: %s" % (name, c, "; ".join(where)))
if declared != "-":
    for name in sorted(set(open(declared).read().split()) - set(count)):
        if not any(fnmatch.fnmatchcase(name, x) for x in exclude):
            errors.append("opzione %s dichiarata nei sorgenti ma in nessuna scheda del menu" % name)
for e in errors:
    print("cfr-dump: %s" % e, file=sys.stderr)
if errors:
    sys.exit("cfr-dump: %d errori nel menu" % len(errors))
if ref == "-":
    sys.exit(print("cfr-dump: %s valido (%d oggetti, %d byte)" % (path, len(listing), len(data))))
expected = open(ref).readlines()
if listing != expected:
    sys.stderr.writelines(difflib.unified_diff(expected, listing, "%s (sm_root[])" % mbcfr, path))
    sys.exit("cfr-dump: il blob non corrisponde alle strutture del menu (diff qui sopra)")
print("cfr-dump: %s valido, uguale a sm_root[] di %s e alle form generiche (%d oggetti, %d byte)"
      % (path, mbcfr, len(listing), len(data)))
PY
