# edk2/: the project's package for EDK II

`OuroBiosPkg` is the package of step (b) of the move to upstream
TianoCore EDK II ([docs/edk2-migration.md](../docs/edk2-migration.md#step-b-the-package-a-plan)):
the modules and the platform of ouroBIOS's payload, built against the
EDK II tree as it is, without patches to its packages.

| File | What it is |
|---|---|
| `OuroBiosPkg/OuroBiosPkg.dec` | the package |
| `OuroBiosPkg/OuroBiosPkg.dsc.patch` | the platform, as a patch on `UefiPayloadPkg/UefiPayloadPkg.dsc` of the tree it is built with |
| `OuroBiosPkg/OuroBiosPkg.fdf.patch` | the flash device, as a patch on `UefiPayloadPkg/UefiPayloadPkg.fdf` |

`tools/build.sh` copies the package to `WORK/edk2-packages`, applies each
`OuroBiosPkg.<ext>.patch` to `UefiPayloadPkg.<ext>` of the TianoCore tree
(`EDK2_UPSTREAM_TAG`) to make `OuroBiosPkg.<ext>`, and gives coreboot that
directory in `CONFIG_EDK2_PACKAGES_PATH` and the platform in
`CONFIG_EDK2_PLATFORM_DSC` (patch 0216): the edk2 build looks in it before
the tree. A platform kept as a patch says what it changes, and one that no
longer applies to a new stable tag stops the build there, where it has to
be looked at again.

For now the platform is UefiPayloadPkg's with its own name and GUID and
three settings: Secure Boot (`SECURE_BOOT_ENABLE`), a flash device of
12 MiB for a DEBUG build and 11 for a RELEASE one, as ouroBIOS's payload
(`edk2/0024`), and a Shell that does not wait 5 s for `startup.nsh`
(`PcdShellDefaultDelay`). No ROM of a board is built from it:
`tools/build.sh edk2-upstream` builds it into a q35 image and runs the
steps of `qemu-smoke.py --upstream` on it, with the gaps of the upstream
payload.

The files of `OuroBiosPkg` are CRLF, as those of EDK II (`.gitattributes`
keeps them so), and BSD-2-Clause-Patent, as the files they derive from.
