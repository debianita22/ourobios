# i915 "DPLL 1 not locked" on the M920x: the measurements

What was measured on the M920x of the port on 2026-11-03 and 11-04, with
ci-244, v1.6.0-rc1 and rc2 (Linux 7.0.14, i915 of the kernel, a monitor
on HDMI-A-2 at 1360x768, 38 GB of RAM), and how. The conclusion is in
[docs/roadmap.md](../../../roadmap.md#the-dpll-of-i915-at-boot-on-the-m920x):
the error is i915's own 5 ms wait for the lock of DPLL 1 in
`skl_ddi_pll_enable()`, which it re-enables at boot and at every blank of
the output, and the failure follows the activity of the system; nothing
in the firmware changes it. This file keeps the numbers.

## Where the error comes from

- At boot i915 cannot keep the state it inherits from libgfxinit (a
  fastset): with `drm.debug=0x1e` the compare of the two states lists
  `pipe_bpp` (36 wanted, 24 found), `port_clock` (127125 wanted, 84750
  found), `dpll_hw_state` and `infoframes.gcp`, so it does a full
  modeset, disables DPLL 1 and enables it again with its own dividers.
  The AVI and SPD infoframes are not compared in a fastset check.
- i915 picks 12 bits per colour from the monitor's EDID: port clock
  127.125 MHz, DCO 8898.75 MHz on the 9000 MHz central frequency,
  divider 14 (`cfgcr1 0x80c80172`, `cfgcr2 0x131`, `ctrl1 0x21`).
  libgfxinit runs 8 bits: 84.75 MHz, DCO 8475 MHz on 8400, divider 20
  (`cfgcr1 0x80200161`, `cfgcr2 0x5a7`).
- The same enable happens at every blank and unblank of the output from
  fbcon (`echo 4 > /sys/class/graphics/fb0/blank`, then `0`), which is
  how it was measured; the display works after the error every time.
- libgfxinit waits 10 ms for the same lock bit (`Default_Timeout_MS` of
  `hw-gfx-gma-registers.ads`), i915 5 ms; the error appeared once under
  MrChromebox's firmware on this machine too (2026-09-03), and Intel's CI
  saw it on Coffee Lake in 2018 (freedesktop bug 107345).

## Boots

| Firmware | Boots with a display | With the error |
|---|---|---|
| ci-140 to ci-205 | 0 (no monitor connected: *Cannot find any crtc or sizes*) | 0 |
| ci-208, ci-209, ci-211 | 11 | 3 |
| v1.5.0 | 4 | 0 |
| ci-244 | 9 | 3 |

## Cycles of the output from fbcon

Each row is a batch of blank/unblank cycles, 0.8 s apart, with the count
of new `DPLL 1 not locked` lines in `dmesg`. "Off 2 s" keeps the output
off for 2 s before the enable, "off 0 s" enables it right after the
disable. "Busy" is four `sh -c 'while :; do :; done'` loops on the four
cores.

| Condition | Failures |
|---|---|
| ci-244, 40 min after boot, 12 bpc, off 2 s | 5 of 20 |
| same, off 0 s | 15 of 20 |
| after one modeset asked from userspace (max bpc 8 then 12), 12 bpc, off 0 s | 2 of 40, 0 of 40, 0 of 40, 1 of 40 |
| same, off 2 s | 0 of 20, 0 of 20 |
| max bpc 8 (84.75 MHz), off 0 s and off 2 s | 0 of 80 |
| rc1 right after boot, before any userspace modeset, off 0 s | 2 of 40 |
| same, off 2 s | 0 of 20 |
| rc1 after the max bpc round trip, off 0 s | 1 of 40 |
| alternating max bpc 8 and 12 at each cycle | 0 of 40 |
| idle, 12 bpc, off 0 s (several batches) | 1 of 40, 4 of 30, 2 of 30, 0 of 30 |
| busy (4 shell loops), 12 bpc | 11 of 30, 13 of 40, 12 of 30, 17 of 30, 10 of 30, 20 of 30 |
| busy at 800 MHz (`max_perf_pct=8`) | 7 of 30 |
| busy with turbo off | 11 of 30 |
| one `yes` only | 0 of 30 |
| four `dd if=/dev/zero of=/dev/null bs=64M` | 2 of 30 |
| a process reading the display registers 20000 times a second, 12 bpc | 30 of 30 |
| same, 8 bpc | 6 of 30 |
| `enable_sagv=0`: idle, busy, busy | 2 of 30, 10 of 30, 20 of 30 |
| `enable_dc=0`: busy, idle, busy | 17 of 30, 1 of 30, 12 of 30 |

The state of i915 right after boot and after the userspace modeset
(`i915_cdclk_info`, `i915_shared_dplls_info`, `i915_display_info`,
`i915_power_domain_info`) is the same but for the DC counters: CDCLK
337.5 MHz as libgfxinit sets it, DPLL 1 on pipe A, DC6 entered while
the output is off.

## The lock itself

A poll of `LCPLL2_CTL` (0x46014, bit 31) and `DPLL_STATUS` (0x6C060, bit
8) through `resource0` of `0000:00:02.0` (`iomem=relaxed`), pinned to one
core with `chrt -f 50` while the load ran on the others: when the lock
comes in time it comes within 1 ms of the enable; in the two failures
caught, the lock bit rose 144 ms and 720 ms after the enable. A poll at
20 kHz raises the failure rate by itself (see the table), one at 2 kHz
does not.

## How to repeat

```sh
# cycles: N of them, G seconds off; count the new errors
cyc() { b=$(dmesg | grep -c "DPLL.*not locked"); for i in $(seq $1); do
  echo 4 > /sys/class/graphics/fb0/blank; sleep $2; echo 0 > /sys/class/graphics/fb0/blank; sleep 0.8; done
  echo "$1 cycles, off $2 s: $(( $(dmesg | grep -c 'DPLL.*not locked') - b )) errors"; }
cyc 30 0; cyc 20 2
# the load on all cores for 40 s, then the cycles
for i in 1 2 3 4; do timeout 40 sh -c 'while :; do :; done' & done; sleep 1; cyc 30 0; wait
```

The "max bpc" property of the connector was set through the DRM ioctls
without libdrm (`DRM_IOCTL_MODE_OBJ_GETPROPERTIES`, `_GETPROPERTY`,
`_OBJ_SETPROPERTY` on the connector, 127 here), then a blank and unblank
to apply it; i915's `port_clock` in `i915_display_info` shows which clock
runs. `/sys/kernel/debug/dri/0000:00:02.0/` has the state files.
