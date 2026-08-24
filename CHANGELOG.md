# What’s new in z13-power

The Z13 tray that used to poke hardware twelve times a minute now sits quiet,
remembers your charge cap and undervolt across reboot, and still looks like
Omarchy. This is the drop.

---

## The headline numbers

| | Then | Now |
|--|------|-----|
| **Idle `z13ctl` calls** | ~12 / min | **0 / min** |
| **Idle work** | ~81 ms / min | **~0.6 ms / min** |
| | | **~99% less · ~135× lighter** |
| **Same-profile click** | ~169 ms of TDP + fan + UV writes | **~0 ms** (already applied) |
| **Login, already on the right mode** | ~178 ms of duplicate writes | **~96 ms** (~46% less) |
| **Telemetry tab** | ~290 ms / min | **~25 ms / min** (~12×) |
| **Fan curve Fetch** | ~10.5 ms | **~0.15 ms** (~70×) |
| **Tweaks first paint** | ~6.0 ms | **~0.51 ms** (~12×) |

Times are median wall-clock on a GZ302 (CachyOS + `z13ctl` + `ryzen_smu`).
Your box will be in the same ballpark. Real profile changes still pay for
TDP / fan / UV — skip-if-same only fires when you are already there.

**The tray does zero `z13ctl` while nothing is changing.** Plug/unplug is
udev. Firmware profile is one sysfs read every 8 seconds.

---

## New features

### Tweaks → CPU undervolt

A G-Helper-style all-core **Curve Optimizer** slider, **0 to −40 mV**, on
the Tweaks page.

- Saved to `~/.config/z13-power/tweaks.conf`
- Re-applied at login and after every profile switch
- Overrides the per-mode recipe (`silent` −20 / `lowpower` −25) when you
  set one
- If `ryzen_smu` is missing, the slider still **saves** — it applies the
  moment the module is there

### Silicon lottery

Same page, same 50–99 scale for the overall score, **best core**, and
**weakest core** — plus a suggested starting undervolt.

This is AMD’s own preferred-core ranking (CPPC), not ASUS BIOS SP (we
cannot read fused VID/FIT from userspace). On this unit: **77 / 100**
(best 98 · weakest 54) → start around **−15 mV**.

### Charge cap that survives reboot

ACPI on the GZ302 **forgets** `charge_control_end_threshold` across reboot.
**Set charge limit** writes `~/.config/z13-power/battery.conf`; the tray
re-applies it at login, same as lighting. (Landed as PR #7; this drop
makes the re-apply a sysfs write and skips it when the live cap already
matches.)

### Automatic stays how you left it

Reboot no longer silently turns Automatic back on. Manual mode + lock come
back from `status.json` before the tray rewrites it. (PR #6.)

### One command to get undervolt working

```bash
z13-power setup-undervolt
```

Detects **this kernel** (`pkgbase` → `linux-cachyos-bore-headers`,
`linux-zen-headers`, …), installs `ryzen_smu-dkms-git` (amkillam fork for
Strix Halo), drops udev rules + modules-load, `modprobe`s, and restarts
`z13ctl`. **No prebuilt `.ko` in this repo** — DKMS rebuilds on every
kernel update.

`./install.sh` runs that step for from-source installs.

---

## Compatibility

| | |
|--|--|
| **Hardware** | 2025 ASUS ROG Flow Z13 **GZ302** (Strix Halo) |
| **Distro** | Arch / CachyOS — any kernel with matching `-headers` |
| **Desktop** | KDE Plasma, Hyprland / **Omarchy**, any SNI tray + `notify-send` |
| **Theme** | Follows the live Omarchy theme (flyout + settings + tray bolt) |
| **Undervolt** | Optional. Needs `ryzen_smu` for the running kernel. Without it, profiles / TDP / fans / lighting / charge cap still work |
| **Kernels** | CachyOS (default, bore, LTS), linux-zen, linux-lts, stock `linux` — `setup-undervolt` picks the headers for **whatever `uname -r` is** |
| **Not required** | KDE, PowerDevil Run Script hooks, z13gui, a baked kernel module |

Conflicts to leave off: `z13ctl autoswitch`, and the desktop’s own AC/battery
power profiles (KDE Power Management, Omarchy bar Power panel). This service
is the single switcher.

---

## Performance, in English

**Idle used to be the expensive part.** The tray spawned `z13ctl` about
twelve times a minute just to ask “what profile is the firmware on?”
That is gone (PR #5). Idle is sysfs + udev. Config is parsed only when
the file’s mtime changes. `status.json` is not rewritten if nothing
changed. The bolt pixmap is cached.

**This drop cuts the leftover duplicates:**

- Same TDP recipe already applied this process → skip `tdp --set` (~92 ms)
- Fans already auto and we did not rewrite the firmware profile → skip
  `fancurve --reset` (~73 ms)
- Curve Optimizer already at the Tweaks (or mode) value → skip the SMU
  write (~4 ms). Login used to apply UV twice; the second hit is a no-op
- Charge cap already matches `battery.conf` → skip the write
- 20 s startup diagnose is PATH/sysfs only (no `z13ctl status`). The
  **Diagnose** button is still the full report
- Fan / Battery / Tweaks / Profiles / Telemetry widgets are built the
  **first time you open that tab**
- Telemetry, fan-curve fetch, charge limit, panel overdrive, boot sound,
  and PL1 **read sysfs** (`k10temp`, asus fans, `ppt_pl1_spl`, `panel_od`,
  `boot_sound`, `charge_control_end_threshold`). `z13ctl` is the fallback

The Omarchy flyout was already cheap: `FileView` on `status.json`, no timer.

---

## Already on `main`

| PR | What you got |
|----|----------------|
| [#1](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/1) | Tinted bolt on Omarchy/waybar (`IconName` empty so `IconPixmap` wins) |
| [#2](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/2) | Omarchy-themed tray + panel flyout |
| [#3](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/3) | Max actually hits 93 W (no stock-70 W race) |
| [#5](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/5) | Settings restyled like the flyout, live theme, **~99% less idle work** |
| [#6](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/6) | Automatic-off survives reboot |
| [#7](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/7) | Charge cap persisted in `battery.conf` |

---

*z13-power — GPL-3.0-or-later. Built on [z13ctl](https://github.com/dahui/z13ctl).*
