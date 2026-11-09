# MrChromebox's EDK II commits marked *upstream*: where each one stands

The 22 commits of MrChromebox's branch that
[docs/edk2-migration.md](../edk2-migration.md) marks *upstream*: changes
to TianoCore's own packages that belong in TianoCore, not in ouroBIOS's
package. Looked at on 2026-11-09 against TianoCore's `master` at
`b9d8871d3` (2026-11-06, 628 commits after `edk2-stable202608`) and the
pull requests of [tianocore/edk2](https://github.com/tianocore/edk2/pulls).

None of them is in `master`. They are other people's work (MrChromebox,
Star Labs, 9elements, 3mdeb): each goes upstream from its author, or
with the author's `Signed-off-by` and authorship kept. ouroBIOS does not
send them in its own name. What the project can do is say which ones
are waiting, test them on its boards, and comment on the pull requests
with the results.

*Applies to master* is `git apply --check` of the project's
`patches/tianocore` patch for the commit (only TianoCore's files, without
the package's) on `master`: *yes*, *3-way* (applies with a merge), or
*no*.

| Commit | Author | Subject | Pull request | Applies to master |
|---|---|---|---|---|
| `565124c` | Sean Rhodes | MdeModulePkg: Add Logo position PCD and BGRT support | none found | 3-way |
| `4844b23` | Patrick Rudolph | MdeModulePkg: Be more verbose about SecureBoot and the reason why the boot failed | none found | 3-way |
| `fc55cf0` | Benjamin Doron | UefiPayloadPkg: Implement CFR support | [#12869](https://github.com/tianocore/edk2/pull/12869), "add coreboot CFR setup support" (Star Labs), closed by its author on 2026-10-15 after a review by Benjamin Doron, who asked for his own commit of the driver to be taken with his authorship | yes |
| `9b3274a` | Matt DeVillier | MdeModulePkg/SetupBrowserDxe: Sync ordered lists before action callback | [#13000](https://github.com/tianocore/edk2/pull/13000), open | yes |
| `ad284e9` | Matt DeVillier | MdeModulePkg/FileExplorerLib: Add "Up one level" navigation | [#13004](https://github.com/tianocore/edk2/pull/13004), open (the commit in MrChromebox's branch has no `Signed-off-by`) | yes |
| `240f748` | Matt DeVillier | UefiPayloadPkg/CfrSetupMenuDxe: Add support for LOCK_AT_BOOT CFR flag | none found; goes with `fc55cf0` | no: it changes `CfrSetupMenuGuid.h`, which `fc55cf0` adds |
| `6c7b28d` | Sean Rhodes | UefiPayloadPkg/Fmp: Keep capsule updates resilient through progress and reset | none found under this subject; Star Labs's capsule pull requests ([#12342](https://github.com/tianocore/edk2/pull/12342), [#12902](https://github.com/tianocore/edk2/pull/12902)) were closed unmerged | yes |
| `cc69856` | Sean Rhodes | MdeModulePkg/UefiPayloadPkg: Keep ESRT durable across hibernate and FMP sync | none found | yes |
| `0d39245` | Matt DeVillier | CryptoPkg/BaseCryptLib: Ignore foreign buffers in runtime free/realloc | none found | yes |
| `6128cce` | Michał Kopeć | UefiPayloadPkg/GraphicsOutputDxe: Allow for framebuffer at an offset from BAR | [#12231](https://github.com/tianocore/edk2/pull/12231) closed as stale, [#12852](https://github.com/tianocore/edk2/pull/12852) closed by its author (Star Labs) | yes |
| `4c76525` | Matt DeVillier | MdeModulePkg/Usb/Keyboard.c: remove Get/SetConfig calls | none found | yes |
| `42865d9` | Patrick Rudolph | MdeModulePkg: Improve USB error handling for faulting devices | [#12232](https://github.com/tianocore/edk2/pull/12232) closed as stale, [#12853](https://github.com/tianocore/edk2/pull/12853) closed by its author (Star Labs) | yes |
| `b8d0242` | Matt DeVillier | MdeModulePkg: UFS pass-through fix and boot enumeration filter | its UFS half is in `master` as `1d8f64df1` ([#12762](https://github.com/tianocore/edk2/pull/12762), merged 2026-09-29); the `BmBoot.c` half (a block device without a device path, UFS units other than LUN 0) has none | 3-way |
| `a79398a` | Matt DeVillier | PcRtcEntry: Don't assert if RTC init fails | none found | yes |
| `dde0798` | Matt DeVillier | FatPkg: Fix FAT32 mount on small 4K-sector ESP partitions | [#12761](https://github.com/tianocore/edk2/pull/12761), open | yes |
| `acf9505` | Sean Rhodes | MdeModulePkg/Usb: Warm reset downstream SuperSpeed ports | none found | yes |
| `252f6d2` | Patrick Rudolph | UefiPayloadPkg: Extend SmmStoreLib for 64-bit MMIO store | none found | yes |
| `1c39058` | Michał Żygowski | UefiPayloadPkg/Library/CbParseLib: Populate root bridges info from HOB | none found | 3-way |
| `40a1b7a` | Matt DeVillier | UefiPayloadPkg/PciPlatformDxe: Fix BAR restore leak and uninit CodeType | [#13015](https://github.com/tianocore/edk2/pull/13015), open | yes |
| `e27ef54` | Matt DeVillier | UefiPayloadPkg/ResetSystemLib: Select S5 sleep type from CPUID | none found | yes |
| `0453b7a` | Sean Rhodes | UefiPayloadPkg/ResetSystemLib: Use full CF9 sequence for cold reset | none found | 3-way |
| `94a2365` | Matt DeVillier | UefiPayloadPkg: Pass coreboot boot media params to DXE | none found | 3-way |

So: four are open in MrChromebox's own pull requests (`9b3274a`,
`ad284e9`, `dde0798`, `40a1b7a`); half of `b8d0242` is merged and comes
with the next stable tag; four were proposed by Star Labs and closed
without a merge (`fc55cf0`, `6128cce`, `42865d9`, and capsule work close
to `6c7b28d`); the other thirteen have not been proposed.

Another one, not *upstream* in the table: `6cf55e1`, the PCD that keeps
the payload off the MTRRs, which ouroBIOS carries. Star Labs proposed
it as [#12227](https://github.com/tianocore/edk2/pull/12227); the
maintainer of `MtrrLib` refused a switch inside the library ("please do
not add a backdoor in MtrrLib to skip MTRR programming; please change
the callers"), and the pull request was closed. Upstream wants the
callers, `CpuDxe` and `MpInitLib`, to leave the MTRRs alone when the
bootloader owns them.

## What ouroBIOS can add

- For the open pull requests (#13000, #13004, #12761, #13015): the
  result on the M920x and the W541, where each is in the payload of the
  ROMs since v1.6.0, as a comment on the pull request.
- When the tag moves past `1d8f64df1`, `tianocore/0029` keeps only the
  `BmBoot.c` half of `b8d0242` (`tools/edk2-import.py` makes it again).
- The rest waits for its authors. Asking MrChromebox, whose branch
  carries them all, which ones he means to send is the first step; the
  owner of the repository decides whether and how to ask.
