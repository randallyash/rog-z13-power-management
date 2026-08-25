# What’s new in z13-power

This is the drop that makes the Z13 Power on Linux feel like **Godmode**, not
like a tray icon with extra steps.

On **Omarchy**, power lives where your hand already goes: the stock
battery widget. Click it. Charge, live watts, Max / Perf / Mid / Silent /
Low, Automatic, Lock. No second bolt. No Armory Crate. No Windows.

On **CachyOS / KDE / anything else**, you still get the full Settings
window — fan graph, live lighting, charge presets, live temp/fan/TDP —
plus the Armory side button and a real in-game overlay. You do not need
Omarchy. You do not need KDE.

Same hardware story as before: the Armory Crate button finally does
something, profiles change **inside** a gamescope game, the tray sits
quiet instead of poking the chip twelve times a minute, and the charge
cap survives reboot.

This is for every **2025 GZ302** on Linux.

---

## Omarchy — the battery widget *is* z13-power

Install no longer leaves a stray bolt next to the battery. 
`z13-power-omarchy-setup` (from `install.sh` when `~/.config/omarchy`
exists) copies two **user** plugins and replaces **only the power slot**:

- **`z13.power`** — the Omarchy battery flyout, plus our pills: Max,
  Perf, Mid, Silent, Low, Automatic, Lock, and Charge to 100%.
- **`z13.battery`** — low-battery warnings; skips Omarchy’s
  `powerprofiles-set` so plug/unplug is ours.

Stock `/usr/share/omarchy` is never edited. `omarchy update` does not
delete the user plugins. `omarchy refresh shell` can put `omarchy.power`
back; re-run `z13-power-omarchy-setup`. KDE and Cachy without Omarchy
never load this. They keep the bolt tray.

### The bar

Default: live **battery glyph** (fill + charging) with the **profile
glyph** beside it — same size, same color, same optical slot language as
Bluetooth and Wi-Fi. No corner badge.

Right-click: **percent + profile**. The battery shape drops (the number
already is charge). Right-click again to go back.

### Charge to 100%

The flyout toggle **Charge to 100%** is a one-shot. Your saved cap
stays 80% (or 60, or whatever you set). This plug-in is allowed to go
all the way to full. When the pack hits ~100% — or when you unplug —
the cap snaps back. Next charge stops at 80 again. Settings still
owns the lasting limit; the toggle does not rewrite it.

### Live TDP

The flyout TDP row is **draw / cap**: `15W / 52W`. Live SoC watts from
amdgpu PPT, polled only while the panel is open. The 52W is the profile
limit we actually set (Mid, Perf, Max…).

### Toasts that belong on Omarchy

Flyout clicks do not pop a notification — the pills already moved. Plug
in, unplug, or hit the low-battery latch and you get a compact Omarchy
card (`omarchy-notification-send`): mode glyph, `Performance · AC`.
Setup failures still notify. KDE still uses `notify-send` on every
switch, because the bolt *is* the UI there.

### Settings and Diagnose actually launch

Those two flyout buttons now look in `~/.local/bin`, then `/usr/bin`,
then PATH. From-source and packaged installs both work. Pills still
talk through `command.json` so they never depend on PATH.

---

## Settings — the G-Helper window

Open Settings from the flyout, the bolt, or `z13-power settings`. Every
page shares a live strip: **Temp · Fan · TDP** (`11W / 52W`), plus the
big profile watts in the header.

### Fan curve is a graph

Eight firmware points on a real chart. Drag the dots. X is °C, Y is
fan %. A dashed line is live APU temp. Above 75 W PL1, a yellow floor
sits at 50% (the firmware rule). Fetch / Apply / Reset still there.
No more eight PWM spinboxes.

### Lighting is live

Effect, color, speed, brightness, device — they apply as you click.
There is no Apply button. **Turn off** stays.

**Follow Omarchy theme** (Omarchy only — the button does not exist on
KDE) paints the keyboard and lightbar with the current accent. Change
theme, lights follow, until you pick a swatch.

### Charge limit: 60 / 80 / 100

Three pills above the slider, G-Helper style. Tap **80%** if you leave
it plugged in. **100%** charges to full. The slider is still there for
75%. Saved and re-applied at login — ACPI on this tablet forgets the
cap across reboot.

---

## Armory, in a game, with Automatic

The in-game overlay (Armory side button inside nested gamescope) now
has **Auto** next to the TDP.

- Auto on — follows the charger, same as the desktop flyout
- Tap a pill — pin that profile (manual)
- Tap Auto again — back to Automatic without leaving the game

Esc, click outside the card, or Armory again to close.

---

## Diagnose does not yell at you

`power-profiles-daemon` is **normal** on Omarchy and KDE. Diagnose no
longer calls it a warning. If the hardware, groups, udev, daemon, and
undervolt module are good, you get **All checks passed.** Each Diagnose
click re-runs; it does not replay a stale report.

---

## Armory Crate button


## Armory Crate button

The side button on the tablet (KEY_PROG3) used to open Armory Crate on
Windows and **do nothing** on Linux. Press it now:

- **On the desktop** — full settings open. Press again to close. The
  window stays on top, including over a fullscreen game that is *not*
  running inside gamescope.
- **In a gamescope game** — a slim in-game profile picker: Max, Perf,
  Mid, Silent, Low, plus **Auto**. Click a profile, or tap Auto to
  follow the charger again. Esc, click outside the card, or Armory
  again to close. You never leave the game.

Same path z13gui used: the `z13ctl` daemon already watches the key and
emits `gui-toggle`. Do not bind that key in your compositor — the daemon
already grabbed it.

---

## Gamescope — in-game overlay

Steam, Lutris, Heroic, or a terminal `gamescope -- ./game`: if gamescope
is the focused window, Armory puts a real overlay **inside** that nested
session. Proton or native, one title or fifty — the game does not matter.
Lootbound was only the test case.

| Your desktop | Overlay when gamescope is focused |
|---|---|
| **Hyprland** (Omarchy, Cachy Hyprland, …) | yes |
| **KDE Plasma Wayland** (CachyOS KDE, most “just install KDE” boxes) | yes |
| **X11** (Plasma X11, i3, Xfce, Cinnamon, …) | yes |

The picker is a Steam-style overlay (`STEAM_OVERLAY` + `STEAM_INPUT_FOCUS`)
so gamescope actually gives it the mouse. A HUD-style tag
(`GAMESCOPE_EXTERNAL_OVERLAY`, what MangoHud uses) **paints** on top and
sends every click to the game — we do not use that. The window is a
fullscreen transparent root with the card centered, so the compositor does
not stretch a small panel across 1080p.

Full settings are **not** opened on gamescope’s Xwayland: talking to
libX11 from inside that Qt process SIGSEGV’d. Desktop settings stay on
your host compositor. The tray **Settings…** item always opens the full
window, even if a game is running in the background.

Not this (and not a bug): **gamescope as the whole login session**
(SteamOS / Bazzite *gaming mode*, `gamescope-session`). There the
compositor *is* gamescope — there is no desktop window named gamescope
to detect. Fullscreen gamescope **on** Hyprland or Plasma is the normal
case and **is** supported.

GNOME Wayland and Sway/niri are not wired yet. Two gamescope windows at
once still pick the first nested display.

---

## Bugfix — tray stuck on Silent while the fans changed

Unlocked Silent, then unplug → chip went **Balanced**, plug → **Performance**
(popup + fans). The bolt and Omarchy flyout stayed **Silent (manual)**.

Three stacked bugs:

1. We waited for a **second** AC udev event (or 30 s) before turning
   Automatic back on. Unplug is one event. `power-profiles-daemon`
   switched firmware immediately; we never left Silent.
2. `status.json` was replaced as a new file, so the flyout’s file watch
   died and froze on the old pick.
3. An 8 s firmware poll treated **our own** profile write as “set
   externally,” flipped Automatic off, and painted Silent over a live
   Performance chip.

**Fixed.** Confirm AC0 in the same call. Write status in place. Tray
shows the mode we actually applied. While Automatic or Lock is on, we
keep that recipe. Flyout reloads while it is open.

Lock Silent if you want Silent to survive unplug.

`z13-power diagnose` warns if **power-profiles-daemon** or **z13ctl
autoswitch** is also switching on plug/unplug. Plug/unplug confirm is a
timer, not a sleep on the tray thread.

---

## The headline numbers

The tray does **zero** `z13ctl` while nothing is changing. Plug/unplug is
udev. Firmware profile is one sysfs read every 8 seconds.

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

---

## Tweaks → CPU undervolt

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
cannot read fused VID/FIT from userspace). Example unit: **77 / 100**
(best 98 · weakest 54) → start around **−15 mV**. Yours will differ.

### One command to get undervolt working

```bash
z13-power setup-undervolt
```

Detects **this kernel** (`pkgbase` → `linux-cachyos-bore-headers`,
`linux-zen-headers`, …), installs `ryzen_smu-dkms-git` (amkillam fork for
Strix Halo), drops udev rules + modules-load, `modprobe`s, and restarts
`z13ctl`. **No prebuilt `.ko` in this repo** — DKMS rebuilds on every
kernel update.

`./install.sh` runs that step for from-source installs. The packaged
CLI looks in `/usr/share/z13-power-management/contrib/ryzen-smu/` (our
directory), not `/usr/share/contrib/`.

---

## Charge cap that survives reboot

ACPI on the GZ302 **forgets** `charge_control_end_threshold` across reboot.
**Set charge limit** writes `~/.config/z13-power/battery.conf`; the tray
re-applies it at login, same as lighting. (PR #7; later drops made the
re-apply a sysfs write and skip it when the live cap already matches.)

## Automatic stays how you left it

Reboot no longer silently turns Automatic back on. Manual mode + lock come
back from `status.json` before the tray rewrites it. (PR #6.)

---

## Compatibility

| | |
|--|--|
| **Hardware** | 2025 ASUS ROG Flow Z13 **GZ302** (Strix Halo) |
| **Distro** | Arch / CachyOS — any kernel with matching `-headers` |
| **Desktop** | KDE Plasma (X11 + Wayland), Hyprland / Omarchy, X11 WMs with EWMH, any SNI tray + `notify-send` |
| **Gamescope overlay** | Nested gamescope on Hyprland, Plasma Wayland, or X11. Steam / Lutris / Heroic / `gamescope --` |
| **Theme** | Follows the live Omarchy theme when one is present (flyout + settings + tray bolt) |
| **Undervolt** | Optional. Needs `ryzen_smu` for the running kernel. Without it, profiles / TDP / fans / lighting / charge cap / Armory still work |
| **Kernels** | CachyOS (default, bore, LTS), linux-zen, linux-lts, stock `linux` — `setup-undervolt` picks the headers for **whatever `uname -r` is** |
| **Not required** | KDE, PowerDevil Run Script hooks, z13gui, a baked kernel module, Omarchy |

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

**Leftover duplicates that this tree also cuts:**

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

The Omarchy flyout watches `status.json` (and reloads while open).

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
| [#8](https://forgejo.fifthdread.com/Fifthdread/rog-z13-power-management/pulls/8) | Tweaks undervolt, silicon lottery, skip-if-same apply path |
| main | Armory + gamescope overlay; **tray follows plug/unplug** (bolt/flyout were stuck on Silent) |

---

*z13-power — GPL-3.0-or-later. Built on [z13ctl](https://github.com/dahui/z13ctl).*
