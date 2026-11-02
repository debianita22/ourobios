#!/usr/bin/env python3
# edk2-import.py - il payload EDK2 delle ROM, l'EDK2 di MrChromebox al commit
# dei defconfig con patches/edk2, come il tag stabile di TianoCore con
# patches/tianocore e il package edk2/OuroBiosPkg (docs/edk2-migration.md,
# fasi (b) e (c)): gli stessi sorgenti, file per file.
#
#   tools/edk2-import.py MRCHROMEBOX_GIT            scrive i file nel repository
#   tools/edk2-import.py --check MRCHROMEBOX_GIT    li confronta soltanto
#
# MRCHROMEBOX_GIT e' un clone del repository di MrChromebox, anche parziale
# (--filter=blob:none: i file arrivano dal suo remote), con nella storia il
# tag di TianoCore (EDK2_UPSTREAM_COMMIT di tools/build.sh) e il commit dei
# defconfig (--head, se no CONFIG_EDK2_TAG_OR_REV di configs/w541-mrc.defconfig):
# quello di tools/build.sh prepare va bene
# (work/coreboot/payloads/external/edk2/workspace/mrchromebox), le modifiche
# nella sua cartella non contano. R e' l'albero di quel commit con
# patches/edk2/series, fatto in un indice a parte:
#   - patches/tianocore/0001-...: i commit di MrChromebox dal tag al commit dei
#     defconfig, poi le patch di patches/edk2/series, ognuno ristretto ai file
#     che restano nell'albero di TianoCore (FUORI qui sotto), con una nota in
#     cima che dice da dove viene; quelli rimasti senza file saltati;
#   - edk2/OuroBiosPkg/<cartella>: le cartelle di UefiPayloadPkg che TianoCore
#     non ha (i moduli di MrChromebox e del progetto: il setup CFR, lo splash,
#     la password, le chiavi di Secure Boot, la schermata di aggiornamento...)
#     e FSDrivers, da R, con i percorsi del package nei loro file;
#   - edk2/OuroBiosPkg/OuroBiosPkg.dsc.patch e .fdf.patch: il .dsc e l'.fdf di
#     UefiPayloadPkg di R con i percorsi del package, come patch su quelli di
#     TianoCore (edk2_package di tools/build.sh li rifa' da li').
# Prima di scrivere controlla che il tag con la serie dia R in ogni file
# fuori dal package e dalla piattaforma. --check non scrive niente: il tag
# con patches/tianocore del repository deve dare R fuori da FUORI, il
# package e le due patch della piattaforma devono essere quelli di R; esce
# con 1 se no (una patch di patches/edk2 cambiata senza rifare l'import).
#
# Fuori dall'albero di TianoCore, e quindi da patches/tianocore:
#   - le cartelle del package (sopra);
#   - UefiPayloadPkg/NetworkDrivers: i driver di rete di Realtek e ASIX di
#     MrChromebox, binari, solo con NETWORK_PXE_BOOT (0ec988f, "drop" in
#     docs/edk2-migration.md); iPXE e' a parte, lo copia li' il Makefile di
#     coreboot, come CSMWrap in UefiPayloadPkg/LegacyBoot;
#   - LvglPkg e .gitmodules: LvglPkg e' un package a se', clonato da
#     tools/build.sh al commit del submodule di R (LVGLPKG_COMMIT) con
#     patches/lvglpkg;
#   - il .dsc e l'.fdf di UefiPayloadPkg: la piattaforma del package.
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

O = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "OuroBiosPkg"
PLATFORM = ("UefiPayloadPkg/UefiPayloadPkg.dsc", "UefiPayloadPkg/UefiPayloadPkg.fdf")
DROPPED = ("UefiPayloadPkg/NetworkDrivers",)
SEPARATE = ("LvglPkg", ".gitmodules")
TOP_DIRS = ("FSDrivers",)
# Il package: il .dec (senza GUID ne' PCD: i moduli usano quelli di
# UefiPayloadPkg.dec, che ha i suoi in patches/tianocore)
DEC = """## @file
# OuroBiosPkg: the modules and the platform of the payload of ouroBIOS that
# TianoCore's tree does not have, built against it (docs/edk2-migration.md
# of ouroBIOS, steps (b) and (c)). The modules keep the GUIDs, PCDs and
# library classes of UefiPayloadPkg.dec, which patches/tianocore extends.
#
# SPDX-License-Identifier: BSD-2-Clause-Patent
#
##

[Defines]
  DEC_SPECIFICATION              = 0x00010005
  PACKAGE_NAME                   = OuroBiosPkg
  PACKAGE_GUID                   = 2201540D-F8BE-4411-A3BE-5549BE0F5B19
  PACKAGE_VERSION                = 0.1
"""
DSC_NOTE = """# OuroBiosPkg: the platform of the payload of ouroBIOS. tools/build.sh of
# ouroBIOS makes it from UefiPayloadPkg.dsc of the edk2 tree it builds
# with and OuroBiosPkg.dsc.patch, which tools/edk2-import.py makes from
# the .dsc of MrChromebox's tree with the patches of ouroBIOS: the same
# settings, the modules of the package in OuroBiosPkg.
#
"""
FDF_NOTE = """# OuroBiosPkg: the flash device of the payload of ouroBIOS, made as its
# .dsc (OuroBiosPkg.dsc).
#
"""
DSC_DEFINES = (
    (r"(  PLATFORM_NAME +=) UefiPayloadPkg", r"\1 OuroBiosPkg"),
    (r"(  PLATFORM_GUID +=) F71608AB-D63D-4491-B744-A99998C8CD96", r"\1 AB7906A6-F812-40C8-ABF4-25E075FF67C3"),
    (r"(  FLASH_DEFINITION +=) UefiPayloadPkg/UefiPayloadPkg\.fdf", r"\1 OuroBiosPkg/OuroBiosPkg.fdf"),
)


class Error(Exception):
    pass


def git(repo, *args, env=None, binary=False, check=True):
    r = subprocess.run(["git", "-C", repo] + list(args), env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if check and r.returncode != 0:
        raise Error("git %s: %s" % (" ".join(args[:3]), r.stderr.decode(errors="replace").strip()))
    return r.stdout if binary else r.stdout.decode()


def series(d):
    out = []
    for line in open(os.path.join(O, "patches", d, "series")):
        line = re.sub(r"#.*", "", line).strip()
        if line:
            out.append(line)
    return out


def setting(path, pattern):
    for line in open(os.path.join(O, path)):
        m = re.match(pattern, line)
        if m:
            return m.group(1)
    raise Error("%s: %s non trovato" % (path, pattern))


class Index:
    """Un indice di git a parte nel clone: un albero fatto applicando delle
    patch, senza toccare la cartella del clone."""

    def __init__(self, repo, tmp, name, tree):
        self.repo = repo
        self.env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index-" + name))
        git(repo, "read-tree", tree, env=self.env)

    def apply(self, patch, what):
        r = subprocess.run(["git", "-C", self.repo, "apply", "--cached", "--whitespace=nowarn", patch],
                           env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise Error("%s non applica: %s" % (what, r.stderr.decode(errors="replace").strip()[:400]))

    def tree(self):
        return git(self.repo, "write-tree", env=self.env).strip()


def entries(repo, tree):
    """path -> (mode, sha) dell'albero, i submodule compresi."""
    out = {}
    for line in git(repo, "ls-tree", "-r", "--full-tree", tree).splitlines():
        meta, path = line.split("\t", 1)
        mode, _, sha = meta.split()
        out[path] = (mode, sha)
    return out


def dirs_of(paths):
    d = set()
    for p in paths:
        while "/" in p:
            p = p.rsplit("/", 1)[0]
            d.add(p)
    return d


def under(path, dirs):
    return any(path == d or path.startswith(d + "/") for d in dirs)


def package_dirs(base, r):
    """Le cartelle nuove di R sotto UefiPayloadPkg, le piu' esterne (quelle
    il cui genitore c'e' nel tag), meno DROPPED; e quelle in cima (TOP_DIRS).
    Non quelle di UefiPayloadPkg/Include: i moduli ne prendono gli header
    per le [Includes] di UefiPayloadPkg.dec, restano li'."""
    old = dirs_of(base)
    new = set()
    for p in r:
        if p in base or not p.startswith("UefiPayloadPkg/") or p.startswith("UefiPayloadPkg/Include/"):
            continue
        parts = p.split("/")
        for i in range(2, len(parts)):
            d = "/".join(parts[:i])
            if d not in old:
                new.add(d)
                break
    keep = sorted(d for d in new if not under(d, DROPPED))
    for d in TOP_DIRS:
        if any(p.startswith(d + "/") for p in r) and d not in old:
            keep.append(d)
    return keep


def pkg_path(path):
    """Il percorso nel package di un file di una cartella del package."""
    if path.startswith("UefiPayloadPkg/"):
        return path[len("UefiPayloadPkg/"):]
    return path


def rewrite(text, dirs):
    """I percorsi delle cartelle del package nei file di testo: UefiPayloadPkg/X
    e FSDrivers/ (all'inizio di un percorso) in OuroBiosPkg/X."""
    for d in sorted(dirs, key=len, reverse=True):
        if d.startswith("UefiPayloadPkg/"):
            text = re.sub(r"(?<![\w/])" + re.escape(d) + r"(?=[/\s|]|$)",
                          PKG + "/" + pkg_path(d), text, flags=re.M)
        else:
            text = re.sub(r"(?<![\w/])" + re.escape(d) + r"/", PKG + "/" + d + "/", text)
    return text


def crlf(text):
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def platform_file(text, dirs, what):
    """Il .dsc o l'.fdf di R come file del package."""
    text = rewrite(text, dirs)
    if what == "dsc":
        for a, b in DSC_DEFINES:
            text, k = re.subn(a, b, text, count=1, flags=re.M)
            if k != 1:
                raise Error("UefiPayloadPkg.dsc di R: %s non trovato" % a)
    first, rest = text.split("\r\n", 1)
    if first != "## @file":
        raise Error("UefiPayloadPkg.%s di R: non comincia con ## @file" % what)
    return first + "\r\n" + crlf(DSC_NOTE if what == "dsc" else FDF_NOTE) + rest


def unified(tmp, name, old, new):
    """La patch di old in new, con a/NAME e b/NAME (git apply -p1 nella
    cartella del file)."""
    d = tempfile.mkdtemp(dir=tmp)
    for side, data in (("a", old), ("b", new)):
        os.makedirs(os.path.join(d, side))
        with open(os.path.join(d, side, name), "wb") as f:
            f.write(data)
    r = subprocess.run(["git", "diff", "--no-index", "--no-color", "--no-prefix", "-U3",
                        "a/" + name, "b/" + name], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode not in (0, 1):
        raise Error("git diff --no-index: %s" % r.stderr.decode(errors="replace").strip())
    out = r.stdout
    # solo ---, +++ e le parti: la patch e' di un file che tools/build.sh
    # copia dall'albero, non di un file di git
    return out[out.index(b"\n--- ") + 1:]


def note_after_headers(mail, note):
    """La nota in cima al messaggio di una mail di format-patch, dopo le
    intestazioni."""
    i = mail.index(b"\nSubject: ")
    j = mail.index(b"\n\n", i)
    return mail[:j + 2] + note + b"\n\n" + mail[j + 2:]


def restrict_mail(data, out):
    """Una mail di patches/edk2 senza i blocchi dei file di out(path): None se
    non resta niente, se no (mail, i file tolti)."""
    m = re.search(rb"\ndiff --git ", data)
    head, body = data[:m.start() + 1], data[m.start() + 1:]
    sig = b""
    m2 = re.search(rb"\n-- \n[0-9.]+\n*$", body)
    if m2:
        body, sig = body[:m2.start() + 1], body[m2.start() + 1:]
    keep, dropped = [], []
    for b in re.split(rb"(?=^diff --git )", body, flags=re.M):
        if not b.strip():
            continue
        path = re.match(rb"diff --git a/(\S+) ", b).group(1).decode()
        if out(path):
            dropped.append(path)
        else:
            keep.append(b)
    if not keep:
        return None
    if dropped:
        # la statistica dei file non e' piu' quella
        head = re.sub(rb"\n---\n.*\Z", b"\n---\n", head, flags=re.S)
    return head + b"".join(keep) + sig, dropped


def make_series(mrc, tmp, base, head, excl, out):
    """patches/tianocore in out: torna [(nome, origine)]."""
    pathspec = ["--", "."] + [":(exclude)%s" % p for p in excl]
    made = []
    n = 0
    for c in git(mrc, "rev-list", "--reverse", "--topo-order", "%s..%s" % (base, head)).split():
        if not git(mrc, "diff-tree", "--no-commit-id", "--name-only", "-r", c, *pathspec).split():
            continue
        all_files = git(mrc, "diff-tree", "--no-commit-id", "--name-only", "-r", c).split()
        n += 1
        path = git(mrc, "format-patch", "-1", "-N", "--zero-commit", "--no-signature", "--no-renames",
                   "--full-index", "--start-number", str(n), "-o", out, c, *pathspec).strip()
        note = ("[ouroBIOS: commit %s of MrChromebox's edk2%s]" % (
            c[:12], where_left([f for f in all_files if under(f, excl) or f in excl], excl))).encode()
        with open(path, "rb") as f:
            data = f.read()
        with open(path, "wb") as f:
            f.write(note_after_headers(data, wrap(note)))
        made.append((os.path.basename(path), "MrChromebox %s" % c[:12]))
    for name in series("edk2"):
        with open(os.path.join(O, "patches", "edk2", name), "rb") as f:
            data = f.read()
        r = restrict_mail(data, lambda p: under(p, excl) or p in excl)
        if r is None:
            continue
        data, dropped = r
        n += 1
        note = ("[ouroBIOS: patches/edk2/%s%s]" % (name[:4], where_left(dropped, excl))).encode()
        data = note_after_headers(data, wrap(note))
        out_name = "%04d-%s" % (n, name.split("-", 1)[1])
        with open(os.path.join(out, out_name), "wb") as f:
            f.write(data)
        made.append((out_name, "patches/edk2/%s" % name[:4]))
    with open(os.path.join(out, "series"), "w") as f:
        f.write("# TianoCore EDK II (EDK2_UPSTREAM_TAG of tools/build.sh) as the payload of\n"
                "# the ROMs: tools/edk2-import.py makes the series, patches/README.md says\n"
                "# what it is. Each patch says where it comes from in its first line.\n")
        for name, _ in made:
            f.write(name + "\n")
    return made


def where_left(paths, excl):
    """Dove sono i file di una patch che patches/tianocore non ha."""
    if not paths:
        return ", as it is"
    pkg = [p for p in paths if not under(p, DROPPED) and not under(p, SEPARATE)]
    parts = []
    if pkg:
        parts.append("%d in edk2/OuroBiosPkg" % len(pkg))
    if any(under(p, SEPARATE) for p in paths):
        parts.append("LvglPkg on its own")
    if any(under(p, DROPPED) for p in paths):
        parts.append("the network drivers of Realtek and ASIX left out")
    return (", without the files that TianoCore's tree does not have (tools/edk2-import.py): %s"
            % ", ".join(parts))


def wrap(text, width=72):
    words, lines, cur = text.split(b" "), [], b""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = cur + b" " + w if cur else w
    lines.append(cur)
    return b"\n".join(lines)


def package_files(mrc, r_entries, dirs):
    """path del package -> (mode, contenuto) da R."""
    out = {}
    for path, (mode, sha) in r_entries.items():
        if not under(path, dirs):
            continue
        if mode == "160000":
            raise Error("%s: un submodule in una cartella del package" % path)
        data = git(mrc, "cat-file", "blob", sha, binary=True)
        if b"\0" not in data:
            data = rewrite(data.decode("utf-8", errors="surrogateescape"), dirs).encode(
                "utf-8", errors="surrogateescape")
        out[pkg_path(path)] = (mode, data)
    out[PKG + ".dec"] = ("100644", crlf(DEC).encode())
    return out


def compare_trees(mrc, a, b, excl, what):
    diff = git(mrc, "diff-tree", "-r", "--name-status", a, b, "--", ".",
               *[":(exclude)%s" % p for p in excl]).strip()
    if diff:
        raise Error("%s: diverso da R in %d file, fuori dal package e dalla piattaforma:\n%s" % (
            what, len(diff.splitlines()), "\n".join(diff.splitlines()[:20])))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mrc", help="clone del repository di MrChromebox")
    ap.add_argument("--check", action="store_true", help="confronta soltanto, non scrive")
    ap.add_argument("--head", help="il commit di MrChromebox (CONFIG_EDK2_TAG_OR_REV)")
    args = ap.parse_args()
    mrc = os.path.abspath(args.mrc)
    base = setting("tools/build.sh", r'^EDK2_UPSTREAM_COMMIT="([0-9a-f]{40})"$')
    head = args.head or setting("configs/w541-mrc.defconfig", r'^CONFIG_EDK2_TAG_OR_REV="([0-9a-f]{40})"$')
    for c in (base, head):
        git(mrc, "cat-file", "-e", c + "^{commit}")
    if git(mrc, "merge-base", base, head).strip() != base:
        raise Error("%s non e' un antenato di %s" % (base[:12], head[:12]))
    tmp = tempfile.mkdtemp(prefix="edk2-import-")
    try:
        # R: il commit dei defconfig con patches/edk2
        idx = Index(mrc, tmp, "r", head)
        for name in series("edk2"):
            idx.apply(os.path.join(O, "patches", "edk2", name), "patches/edk2/" + name)
        r_tree = idx.tree()
        base_entries, r_entries = entries(mrc, base), entries(mrc, r_tree)
        # LvglPkg, un package a se': il commit di tools/build.sh deve essere
        # quello del submodule di R
        lvgl = setting("tools/build.sh", r'^LVGLPKG_COMMIT="([0-9a-f]{40})"$')
        if r_entries.get("LvglPkg", ("", ""))[1] != lvgl:
            raise Error("LVGLPKG_COMMIT di tools/build.sh e' %s, il submodule LvglPkg di %s e' %s" % (
                lvgl[:12], head[:12], r_entries.get("LvglPkg", ("", "nessuno"))[1][:12]))
        dirs = package_dirs(base_entries, r_entries)
        excl = sorted(set(dirs) | set(DROPPED) | set(SEPARATE) | set(PLATFORM))
        print("R %s (%s + %d patch di patches/edk2): %d file, package: %s" % (
            r_tree[:12], head[:12], len(series("edk2")), len(r_entries), " ".join(pkg_path(d) for d in dirs)))
        pkg = package_files(mrc, r_entries, dirs)
        plat = {}
        for p in PLATFORM:
            ext = p.rsplit(".", 1)[1]
            old = git(mrc, "cat-file", "blob", base_entries[p][1], binary=True)
            new = platform_file(git(mrc, "cat-file", "blob", r_entries[p][1], binary=True).decode(),
                                dirs, ext).encode()
            plat[ext] = (old, new)

        if args.check:
            idx = Index(mrc, tmp, "t", base)
            names = series("tianocore")
            for name in names:
                idx.apply(os.path.join(O, "patches", "tianocore", name), "patches/tianocore/" + name)
            compare_trees(mrc, r_tree, idx.tree(), excl, "il tag con patches/tianocore")
            print("  ok  %s con le %d patch di patches/tianocore e' R fuori dal package e dalla piattaforma"
                  % (base[:12], len(names)))
            print("  ok  LvglPkg %s, il submodule di R" % lvgl[:12])
            have = {}
            root = os.path.join(O, "edk2", PKG)
            for d, _, files in os.walk(root):
                for f in files:
                    full = os.path.join(d, f)
                    rel = os.path.relpath(full, root)
                    if rel in ("OuroBiosPkg.dsc.patch", "OuroBiosPkg.fdf.patch"):
                        continue
                    with open(full, "rb") as fh:
                        have[rel] = fh.read()
            bad = sorted(p for p in set(have) | set(pkg) if have.get(p) != pkg.get(p, (None, None))[1])
            if bad:
                raise Error("edk2/%s: %d file diversi da R: %s" % (PKG, len(bad), " ".join(bad[:10])))
            print("  ok  edk2/%s: i %d file del package sono quelli di R" % (PKG, len(pkg)))
            for ext, (old, new) in plat.items():
                d = tempfile.mkdtemp(dir=tmp)
                f = os.path.join(d, "%s.%s" % (PKG, ext))
                with open(f, "wb") as fh:
                    fh.write(old)
                r = subprocess.run(["git", "apply", "-p1", os.path.join(root, "%s.%s.patch" % (PKG, ext))],
                                   cwd=d, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if r.returncode != 0:
                    raise Error("%s.%s.patch non applica a UefiPayloadPkg.%s del tag: %s" % (
                        PKG, ext, ext, r.stderr.decode(errors="replace").strip()))
                with open(f, "rb") as fh:
                    if fh.read() != new:
                        raise Error("%s.%s.patch: il .%s che da' non e' quello di R" % (PKG, ext, ext))
                print("  ok  %s.%s.patch da' il .%s di R" % (PKG, ext, ext))
            return 0

        out = os.path.join(tmp, "tianocore")
        os.makedirs(out)
        made = make_series(mrc, tmp, base, head, excl, out)
        idx = Index(mrc, tmp, "n", base)
        for name, _ in made:
            idx.apply(os.path.join(out, name), name)
        compare_trees(mrc, r_tree, idx.tree(), excl, "il tag con la serie nuova")
        print("  ok  %s con le %d patch nuove e' R fuori dal package e dalla piattaforma" % (base[:12], len(made)))

        dst = os.path.join(O, "patches", "tianocore")
        shutil.rmtree(dst)
        shutil.copytree(out, dst)
        root = os.path.join(O, "edk2", PKG)
        shutil.rmtree(root)
        os.makedirs(root)
        for rel, (mode, data) in sorted(pkg.items()):
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(data)
            os.chmod(full, 0o755 if mode == "100755" else 0o644)
        for ext, (old, new) in plat.items():
            with open(os.path.join(root, "%s.%s.patch" % (PKG, ext)), "wb") as f:
                f.write(unified(tmp, "%s.%s" % (PKG, ext), old, new))
        mrc_n = sum(1 for _, o in made if o.startswith("MrChromebox"))
        print("  patches/tianocore: %d patch, %d di MrChromebox e %d di patches/edk2" % (
            len(made), mrc_n, len(made) - mrc_n))
        print("  edk2/%s: %d file, %s.dsc.patch, %s.fdf.patch" % (PKG, len(pkg), PKG, PKG))
        for name, origin in made:
            print("    %s  %s" % (name, origin))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Error as e:
        print("edk2-import: %s" % e, file=sys.stderr)
        sys.exit(1)
