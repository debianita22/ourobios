# Report for i915: "DPLL 1 not locked" on Coffee Lake with HDMI

The text for the drm/i915 issue tracker
(https://gitlab.freedesktop.org/drm/i915/kernel/-/issues), from the
measurements in
[docs/tests/v1.6.0/m920x-fsp/dpll.md](../tests/v1.6.0/m920x-fsp/dpll.md).
Not sent yet: the owner of the repository files it.

---

**Title**: CFL: "DPLL 1 not locked" from skl_ddi_pll_enable() under CPU
load, HDMI, 12 bpc

**System**: Lenovo ThinkCentre M920x Tiny, Core i3-8100 (Coffee Lake-S
GT2, 8086:3e91), Q370 (Cannon Point-H), coreboot with libgfxinit and an
EDK II payload (the error was also seen once with another coreboot
build). One monitor on HDMI (DDI C), 1360x768@60, EDID 12 bpc capable.
Linux 7.0.14 (Proxmox kernel), i915 of the kernel, DMC kbl 1.4.

**What happens**: `i915 0000:00:02.0: [drm] *ERROR* DPLL 1 not locked`
at about one boot in three, and at any modeset that enables DPLL 1
again, e.g. a blank/unblank of fbcon. The display works every time.

**Where**: `skl_ddi_pll_enable()` waits 5 ms for `DPLL_LOCK(1)` in
`DPLL_STATUS` (`intel_de_wait_for_set_ms(..., 5)`). i915 programs
port clock 127125 kHz (12 bpc), `ctrl1 0x21`, `cfgcr1 0x80c80172`,
`cfgcr2 0x131` (DCO 8898.75 MHz, central 9000 MHz, divider 14).

**Measurements** (blank/unblank of fb0, 0.8 s apart, count of the error
in dmesg):

| Condition | Failures |
|---|---|
| idle, 12 bpc | 0-4 of 30 per batch |
| four cores busy (`while :; do :; done`), 12 bpc | 7-20 of 30 |
| same at 800 MHz (`max_perf_pct=8`) or turbo off | 7 and 11 of 30 |
| one core busy | 0 of 30 |
| a process reading MMIO of the GPU at 20 kHz | 30 of 30 (12 bpc), 6 of 30 (8 bpc) |
| max bpc 8 (84750 kHz, divider 20, central 8400) | 0 of 120 idle |
| `enable_sagv=0`, `enable_dc=0` | unchanged |

When the lock comes in time it comes within 1 ms of the enable; in two
failures caught by a register poll pinned to one core, `DPLL_LOCK(1)`
rose 144 ms and 720 ms after the enable bit. The state i915 inherits
from the firmware makes no difference (the same before and after a
userspace modeset); the CDCLK is 337.5 MHz.

**Related**: freedesktop bug 107345 (CFL, CI, 2018), where the 5 ms of
Broadwell was found to be reused for gen9 without a spec value and a
longer timeout was proposed (series 66025), not merged.

**Question**: would a retry of the enable (disable, wait, enable) or a
longer wait for the lock be acceptable for gen9 when the PLL is in HDMI
mode? The lock does come, late, and the display then works.
