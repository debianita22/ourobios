#!/usr/bin/env python3
# qemu-setup-shots.py - le schermate del setup del W541 (il payload EDK2 con
# LvglPkg, il menu dalla CFR) in QEMU q35, senza il W541: la ROM di
# tools/q35-cfr-rom.sh, con il record CFR della build del W541 (tools/
# cfr-dump.sh) nel file CBFS cfr.bin (patches/test/q35-cfr-file.patch).
#
#   python3 tools/qemu-setup-shots.py [--cfr FILE] [--out DIR] [--cbfstool PATH]
#                                     [--timeout S] [--rtc DATA] [--vga-mb N]
#                                     [--debug] ROM
#
# Con --cfr il record va in una copia della ROM (cbfstool add, o lo
# sostituisce); senza, la ROM deve averlo gia'. Poi, in DIR (default:
# setup-shots/):
#   00-front.png        la pagina principale, aperta con Esc durante l'avvio;
#   NN-<categoria>.png  ogni categoria della CFR (le form visibili di primo
#                       livello, al massimo otto, come le mostra il payload),
#                       nell'ordine: il riquadro della pagina principale con
#                       le frecce (seguendo l'anello del fuoco, 0x4DA3FF),
#                       Invio, la schermata, Esc;
#   NN-<categoria>-K.png  la stessa pagina scorsa verso il basso, se e' piu'
#                       alta dello schermo: Giu' su ogni voce fino a tornare
#                       alla prima; una schermata ogni ~2/3 di schermo di
#                       scorrimento e una in fondo;
#   serial-setup.log    la seriale (coreboot e payload), qemu-setup.log.
# Si ferma con un errore su un'eccezione del payload ("Exception Type" sulla
# seriale), un riavvio (QEMU esce: -no-reboot), un secondo avvio di coreboot
# o un tasto che non fa quello che deve, con lo schermo in error.png; e
# controlla che coreboot abbia preso il cfr.bin e che la tabella di coreboot
# ci stia (32 KiB).
#
# --rtc: data e ora di partenza dell'RTC (default: oggi alle 10:30, la
# palette del giorno della carta da parati, che segue l'ora), o "host".
# --debug salva in DIR/debug lo schermo dopo ogni tasto. Riusa Smoke, ppm e
# Fail di tools/qemu-smoke.py; solo la libreria standard di Python,
# qemu-system-x86_64 e cbfstool (accanto alla ROM, o nel PATH).
import argparse
import datetime
import importlib.util
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib


def _smoke():
    sys.dont_write_bytecode = True          # niente __pycache__ in tools/
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qemu-smoke.py")
    spec = importlib.util.spec_from_file_location("qemu_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


smoke = _smoke()
Fail = smoke.Fail

FOCUS_RING = b"\x4d\xa3\xff"        # THEME_COLOR_TILE_FOCUS di LvglTheme.h
MAX_CATEGORIES = 8                  # CfrSetupMenuDxe (patch edk2/0002)
NOISE = 600                         # pixel diversi da ignorare: il cursore che lampeggia


def cfr_categories(path):
    """I nomi delle form di primo livello visibili di un record lb_cfr, e
    per ciascuna quante opzioni visibili ha (per limitare i Giu')."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 16:
        raise Fail("%s: non e' un record CFR" % path)
    tag, size = struct.unpack_from("<II", data)
    if tag != 0x47 or size != len(data):
        raise Fail("%s: non e' un record CFR (tag 0x%x, %d byte su %d)" % (path, tag, size, len(data)))

    def visible(off, end):
        """Le opzioni visibili nella form a off (ricorsivo)."""
        n, p = 0, off + 28
        _, vsize = struct.unpack_from("<II", data, p)
        p += vsize                                  # ui_name
        while p < end:
            t, s, _, _, flags = struct.unpack_from("<IIQQI", data, p)
            if t == 12:                             # dep_values
                p += s
                continue
            if not flags & 4:
                n += visible(p, p + s) if t == 1 else 1
            p += s
        return n

    out, p = [], 16
    while p < size:
        t, s, _, _, flags = struct.unpack_from("<IIQQI", data, p)
        if t != 1:
            raise Fail("%s: tag %d nella radice" % (path, t))
        _, _, nlen = struct.unpack_from("<III", data, p + 28)
        name = data[p + 40:p + 40 + nlen - 1].decode("ascii", "replace")
        if not flags & 4:
            out.append((name, visible(p, p + s)))
        p += s
    return out[:MAX_CATEGORIES]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "form"


def write_png(path, w, h, rgb):
    """Un PNG RGB a 8 bit, righe senza filtro."""
    stride = 3 * w
    raw = b"".join(b"\0" + rgb[y * stride:(y + 1) * stride] for y in range(h))

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


class Frame:
    """Uno screendump intero. Nei confronti non contano la barra dei menu
    in alto (l'orologio) e fino a NOISE pixel diversi (il cursore che
    lampeggia in un campo numerico che ha il fuoco)."""

    def __init__(self, w, h, rgb):
        self.w, self.h, self.rgb = w, h, rgb
        self.top = max(32, h * 4 // 100)
        self.stride = 3 * w

    def diff(self, other, limit=NOISE):
        """I pixel diversi da other sotto la barra; smette di contare oltre
        limit."""
        if other is None or (self.w, self.h) != (other.w, other.h):
            return limit + 1
        a, b, s = self.rgb, other.rgb, self.stride
        if a[self.top * s:] == b[self.top * s:]:
            return 0
        n = 0
        for y in range(self.top, self.h):
            ra, rb = a[y * s:(y + 1) * s], b[y * s:(y + 1) * s]
            if ra == rb:
                continue
            for x in range(0, s, 3):
                if ra[x] != rb[x] or ra[x + 1] != rb[x + 1] or ra[x + 2] != rb[x + 2]:
                    n += 1
            if n > limit:
                break
        return n

    def same(self, other):
        return self.diff(other) <= NOISE

    def rows_changed(self, other):
        """La frazione delle righe (sotto la barra) diverse da other."""
        if other is None or (self.w, self.h) != (other.w, other.h):
            return 1.0
        s, n = self.stride, 0
        for y in range(self.top, self.h):
            if self.rgb[y * s:(y + 1) * s] != other.rgb[y * s:(y + 1) * s]:
                n += 1
        return n / (self.h - self.top)

    def ring(self):
        """Il centro dell'anello del fuoco dei riquadri della pagina
        principale, o None."""
        xs, ys = [], []
        i = self.rgb.find(FOCUS_RING, self.top * self.stride)
        while i >= 0 and len(xs) < 100000:
            if i % 3 == 0:
                xs.append(i // 3 % self.w)
                ys.append(i // 3 // self.w)
            i = self.rgb.find(FOCUS_RING, i + 1)
        if len(xs) < 20:
            return None
        return ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2)

    def vshift(self, before):
        """Di quanti pixel il contenuto e' salito rispetto a before (lo
        scorrimento verso il basso), dalle righe di testo di una fascia
        dentro le schede: non il titolo della finestra, la carta da parati
        ai lati, la barra di scorrimento e la colonna di aiuto a destra, che
        non scorrono; None se non si capisce."""
        x0, x1 = self.w * 15 // 100, self.w * 60 // 100
        y0, y1 = max(self.top, self.h * 12 // 100), self.h * 88 // 100

        def rows(frame):
            sig = {}
            for y in range(y0, y1):
                r = frame.rgb[y * frame.stride + 3 * x0:y * frame.stride + 3 * x1]
                if r != r[:3] * (x1 - x0):
                    sig.setdefault(r, []).append(y)
            return {r: ys for r, ys in sig.items() if len(ys) <= 2}
        a, b = rows(before), rows(self)
        votes = {}
        for r, ys in b.items():
            for ya in a.get(r, ()):
                for yb in ys:
                    votes[ya - yb] = votes.get(ya - yb, 0) + 1
        if not votes:
            return None
        shift, n = max(votes.items(), key=lambda kv: kv[1])
        return shift if n >= 8 else None


class Shots:
    def __init__(self, rom, out, timeout, rtc, vga_mb, debug=False):
        self.out, self.timeout = out, timeout
        self.sm = smoke.Smoke(rom, out, timeout, vga_mb)
        self.rtc = rtc
        self.ppm = os.path.join(self.sm.tmp, "f.ppm")
        self.saved = []
        self.debug = os.path.join(out, "debug") if debug else None
        self.ndebug = 0
        if self.debug:
            os.makedirs(self.debug, exist_ok=True)

    def grab(self):
        self.sm.alive()
        exc = self.sm.exception()
        if exc:
            raise Fail("eccezione del payload: %s" % exc)
        self.sm.qmp.cmd("screendump", filename=self.ppm)
        return Frame(*smoke.ppm(self.ppm))

    def save(self, name, frame):
        path = os.path.join(self.out, name + ".png")
        write_png(path, frame.w, frame.h, frame.rgb)
        self.saved.append(name + ".png")

    def settle(self, what, before=None, grace=None, timeout=None):
        """Aspetta che lo schermo si fermi: tre screendump uguali a 0.4 s
        (barra dei menu esclusa). Con before, diverso da before; se resta
        uguale per grace secondi, va bene anche cosi' (un tasto senza
        effetto)."""
        start = time.monotonic()
        end = start + (timeout or self.timeout)
        time.sleep(0.3)
        last, same = None, 0
        while time.monotonic() < end:
            f = self.grab()
            same = same + 1 if f.same(last) else 0
            last = f
            if same >= 2:
                if before is None or not f.same(before):
                    return f
                if grace is not None and time.monotonic() - start > grace:
                    return f
            time.sleep(0.4)
        raise Fail("dopo %d s: %s" % (time.monotonic() - start, what))

    def key(self, name, what, before, grace=None):
        self.sm.key(name)
        f = self.settle(what, before, grace)
        if self.debug:
            # --debug: ogni schermata dopo un tasto, per capire una navigazione
            self.ndebug += 1
            write_png(os.path.join(self.debug, "%03d-%s.png" % (self.ndebug, name)), f.w, f.h, f.rgb)
        return f

    def run(self, categories):
        sm, log = self.sm, []
        t0 = time.monotonic()

        def note(msg):
            log.append("%4.0f s  %s" % (time.monotonic() - t0, msg))
            print(log[-1], flush=True)

        extra = [] if self.rtc == "host" else ["-rtc", "base=" + self.rtc]
        sm.boot("setup", extra)
        sm.wait("coreboot non e' arrivato al payload (\"Jumping to boot code\" nella seriale)",
                lambda: (sm.alive(), "Jumping to boot code" in sm.serial_text())[1], self.timeout)
        serial = sm.serial_text()
        m = re.search(r"CFR: setup menu from cfr\.bin, (\d+) bytes", serial)
        if not m:
            raise Fail("coreboot non ha preso il cfr.bin (manca \"CFR: setup menu from cfr.bin\" nella seriale: "
                       "la ROM ha patches/test/q35-cfr-file.patch e il file?)")
        if "coreboot table didn't fit" in serial:
            raise Fail("la tabella di coreboot non ci sta con la CFR (\"coreboot table didn't fit\")")
        tb = re.search(r"coreboot table: (\d+) bytes", serial)
        note("coreboot -> payload, CFR di %s byte, tabella di coreboot di %s byte su 32768"
             % (m.group(1), tb.group(1) if tb else "?"))

        # il setup: Esc durante l'avvio (BOOT_MANAGER_ESCAPE), finche' la
        # pagina principale non e' ferma, come tools/qemu-smoke.py
        sm.wait("il payload non ha disegnato niente", lambda: (sm.key("esc"), sm.shot().colors() >= 2)[1],
                self.timeout)
        home = sm.stable("il setup non si e' fermato su una pagina", self.timeout, keys=("esc",))
        if home.colors() <= 8:
            raise Fail("lo schermo si e' fermato con %d colori: non e' il setup grafico" % home.colors())
        front = self.settle("la pagina principale non si ferma")
        self.save("00-front", front)
        start = front.ring()
        if start is None:
            raise Fail("nessun riquadro con il fuoco nella pagina principale (anello 0x4DA3FF)")
        note("pagina principale %dx%d, fuoco in %s" % (front.w, front.h, start))

        # Al primo riquadro. Le frecce seguono l'ordine di lettura dei
        # riquadri: Sinistra dal primo va all'ultimo (Reboot, in basso), e
        # Destra dall'ultimo al primo. Se Sinistra fa scendere l'anello il
        # fuoco era sul primo (di solito: la prima voce della pagina); se no,
        # Destra finche' l'anello non sale, cioe' dall'ultimo al primo
        pos, cur, f = [], start, front
        f = self.key("left", "Sinistra non sposta il fuoco", f, grace=4)
        ring = f.ring()
        if ring is not None and ring[1] > cur[1] + 10:
            f = self.key("right", "Destra non sposta il fuoco", f, grace=4)
            ring = f.ring()
            if ring is None or abs(ring[0] - cur[0]) > 10 or abs(ring[1] - cur[1]) > 10:
                raise Fail("Sinistra e Destra non tornano al riquadro di partenza (%s, %s)" % (cur, ring))
        else:
            cur = ring or cur
            for _ in range(24):
                f = self.key("right", "Destra non sposta il fuoco", f, grace=4)
                ring = f.ring()
                if ring is None:
                    raise Fail("Destra: nessun riquadro con il fuoco")
                if ring[1] < cur[1] - 10:
                    cur = ring
                    break
                cur = ring
            else:
                raise Fail("Destra non porta mai al primo riquadro (in alto)")

        n = 0
        for i, (name, count) in enumerate(categories):
            if i > 0:
                f = self.key("right", "Destra non sposta il fuoco", f, grace=4)
                ring = f.ring()
                if ring is None or not (ring[1] > cur[1] + 10 or (abs(ring[1] - cur[1]) <= 10 and ring[0] > cur[0])):
                    raise Fail("Destra non porta al riquadro dopo (%s -> %s): meno riquadri delle %d categorie?"
                               % (cur, ring, len(categories)))
                cur = ring
            pos.append(cur)
            here = f
            page = self.key("ret", "Invio non apre la pagina di %s" % name, here)
            if page.rows_changed(here) < 0.3:
                raise Fail("Invio su %s non ha aperto una pagina (%.0f%% delle righe cambiate)"
                           % (name, 100 * page.rows_changed(here)))
            n += 1
            base = "%02d-%s" % (n, slug(name))
            self.save(base, page)
            extra = self.scroll(base, page, count)
            note("%s: %s.png%s" % (name, base, "".join(", %s.png" % e for e in extra)))
            f = self.key("esc", "Esc non torna alla pagina principale da %s" % name, page)
            if f.rows_changed(here) > 0.4:
                raise Fail("dopo Esc da %s lo schermo non e' la pagina principale (%.0f%% delle righe diverse)"
                           % (name, 100 * f.rows_changed(here)))
            ring = f.ring()
            if ring is None or abs(ring[0] - cur[0]) > 10 or abs(ring[1] - cur[1]) > 10:
                # il fuoco non e' tornato sul riquadro: di nuovo dal primo
                note("dopo Esc il fuoco e' in %s, non in %s: di nuovo dal primo riquadro" % (ring, cur))
                for _ in range(20):
                    if ring is not None and abs(ring[0] - pos[0][0]) <= 10 and abs(ring[1] - pos[0][1]) <= 10:
                        break
                    f = self.key("right", "Destra non sposta il fuoco", f, grace=4)
                    ring = f.ring()
                else:
                    raise Fail("dopo Esc il fuoco non torna al primo riquadro")
                for j in range(1, i + 1):
                    f = self.key("right", "Destra non sposta il fuoco", f, grace=4)
                    ring = f.ring()
                    if ring is None or abs(ring[0] - pos[j][0]) > 10 or abs(ring[1] - pos[j][1]) > 10:
                        raise Fail("il riquadro %d non e' piu' dov'era" % j)
                cur = ring

        sm.alive()
        serial = sm.serial_text()
        boots = serial.count("bootblock starting")
        if boots > 1:
            raise Fail("coreboot e' partito %d volte (un riavvio)" % boots)
        note("QEMU vivo, un solo avvio, %d schermate" % len(self.saved))
        cfr = [x.strip() for x in serial[serial.find("Jumping to boot code"):].splitlines() if "CFR" in x]
        return log, cfr

    def scroll(self, base, first, count):
        """Le schermate della pagina scorsa: Giu' su ogni voce finche' il
        fuoco non torna alla prima (lo schermo torna quello di first), e una
        schermata ogni ~2/3 di altezza di scorrimento, piu' quella piu' in
        basso. Le voci sono al massimo count + 8 (le opzioni visibili della
        categoria, piu' i pulsanti che il payload aggiunge)."""
        view = first.h * 3 // 4
        prev, off, saved_off, k = first, 0, 0, 2
        deepest = (0, None)
        names, top = [], False
        for _ in range(count + 8):
            f = self.key("down", "Giu' non sposta il fuoco in %s" % base, prev, grace=4)
            if f.same(first) or f.same(prev):
                top = True                  # di nuovo la prima voce, o una voce sola
                break
            dy = f.vshift(prev)
            off += dy or 0
            if off > deepest[0]:
                deepest = (off, f)
            if off - saved_off >= view * 2 // 3:
                self.save("%s-%d" % (base, k), f)
                names.append("%s-%d" % (base, k))
                saved_off, k = off, k + 1
                deepest = (0, None)
            prev = f
        if deepest[1] is not None and deepest[0] > saved_off:
            self.save("%s-%d" % (base, k), deepest[1])
            names.append("%s-%d" % (base, k))
        # di nuovo in cima: se il giro non e' tornato alla prima voce, Su
        # finche' lo schermo non e' quello di first
        f = prev
        for _ in range(0 if top else count + 8):
            f = self.key("up", "Su non sposta il fuoco in %s" % base, f, grace=4)
            if f.same(first):
                break
        return names

    def close(self):
        self.sm.close()


def inject(rom, cfr, cbfstool, tmp):
    """Una copia della ROM con cfr.bin al posto di quello che c'era."""
    copy = os.path.join(tmp, "coreboot.rom")
    shutil.copyfile(rom, copy)
    files = subprocess.run([cbfstool, copy, "print", "-r", "COREBOOT"], capture_output=True, text=True)
    if files.returncode:
        raise Fail("cbfstool print: %s" % files.stderr.strip())
    if re.search(r"^cfr\.bin\s", files.stdout, re.M):
        subprocess.run([cbfstool, copy, "remove", "-r", "COREBOOT", "-n", "cfr.bin"], check=True,
                       capture_output=True)
    r = subprocess.run([cbfstool, copy, "add", "-r", "COREBOOT", "-f", cfr, "-n", "cfr.bin", "-t", "raw"],
                       capture_output=True, text=True)
    if r.returncode:
        raise Fail("cbfstool add: %s" % r.stderr.strip())
    return copy


def extract(rom, cbfstool, tmp):
    out = os.path.join(tmp, "cfr.bin")
    r = subprocess.run([cbfstool, rom, "extract", "-r", "COREBOOT", "-n", "cfr.bin", "-f", out],
                       capture_output=True, text=True)
    if r.returncode:
        raise Fail("la ROM non ha un cfr.bin: --cfr FILE (tools/cfr-dump.sh)")
    return out


def main():
    ap = argparse.ArgumentParser(description="Schermate del setup del W541 (CFR) in QEMU q35")
    ap.add_argument("rom", help="ROM coreboot per q35 (tools/q35-cfr-rom.sh)")
    ap.add_argument("--cfr", help="il record CFR da mettere nella ROM (tools/cfr-dump.sh)")
    ap.add_argument("--out", default="setup-shots", help="dove salvare schermate e seriale (default: setup-shots/)")
    ap.add_argument("--cbfstool", help="cbfstool (default: accanto alla ROM, poi nel PATH)")
    ap.add_argument("--timeout", type=float, default=180, help="secondi per ogni passo (default 180)")
    ap.add_argument("--rtc", default=datetime.date.today().isoformat() + "T10:30:00",
                    help="data e ora dell'RTC, AAAA-MM-GGTHH:MM:SS o host (default: oggi alle 10:30)")
    ap.add_argument("--vga-mb", type=int, default=16, help="MiB della VGA di QEMU (default 16)")
    ap.add_argument("--debug", action="store_true", help="salva in DIR/debug lo schermo dopo ogni tasto")
    args = ap.parse_args()
    if not shutil.which("qemu-system-x86_64"):
        sys.exit("serve qemu-system-x86_64 (Debian/Ubuntu: apt install qemu-system-x86)")
    cbfstool = args.cbfstool or os.path.join(os.path.dirname(os.path.abspath(args.rom)), "cbfstool")
    if not os.access(cbfstool, os.X_OK):
        cbfstool = shutil.which("cbfstool")
    if not cbfstool:
        sys.exit("serve cbfstool: --cbfstool, o quello della build di coreboot accanto alla ROM")
    os.makedirs(args.out, exist_ok=True)
    for old in os.listdir(args.out):
        if re.match(r"(\d\d-.*|error)\.png$", old):
            os.remove(os.path.join(args.out, old))
    shutil.rmtree(os.path.join(args.out, "debug"), ignore_errors=True)
    tmp = tempfile.mkdtemp(prefix="setup-shots-")
    shots = None
    try:
        rom = inject(args.rom, args.cfr, cbfstool, tmp) if args.cfr else args.rom
        categories = cfr_categories(args.cfr or extract(rom, cbfstool, tmp))
        if not categories:
            raise Fail("la CFR non ha categorie visibili")
        print("categorie: %s" % ", ".join(n for n, _ in categories), flush=True)
        shots = Shots(rom, args.out, args.timeout, args.rtc, args.vga_mb, args.debug)
        log, cfr_lines = shots.run(categories)
    except Fail as e:
        if shots is not None and shots.sm.proc is not None and shots.sm.proc.poll() is None:
            try:
                f = shots.grab()
                shots.save("error", f)
            except Fail:
                pass
        print("setup-shots: FALLITO: %s (schermate e seriale in %s)" % (e, args.out))
        return 1
    finally:
        if shots is not None:
            shots.close()
        shutil.rmtree(tmp, ignore_errors=True)
    if cfr_lines:
        print("righe CFR del payload sulla seriale:")
        for x in cfr_lines:
            print("  " + x)
    print("setup-shots: %d schermate in %s" % (len(shots.saved), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
