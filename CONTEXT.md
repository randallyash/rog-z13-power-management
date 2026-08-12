# rog-z13-power-management — CONTEXT.md

Project knowledge for the ROG Flow Z13 power automation repo. Agents read this
when working in this repo. Human-facing docs live in README.md (Forgejo page).

## Purpose

Automate power profile switching on a 2025 ASUS ROG Flow Z13 (GZ302). Two
components:
- `z13-power` — CLI modes wrapping `z13ctl` (AUR `z13ctl-bin`, github dahui/z13ctl)
- `z13-power-service` — PyQt6 system tray app + power profile watcher that OWNS
  all profile switching (login, AC/battery transitions, low battery, notifications)

KDE PowerDevil Run Script hooks are intentionally NOT used. Hand-off repo for a
friend; values are the original owner's per-unit tuning. Packaged as
`z13-power-git` in the pkgbuilds repo. License: GPL-3.0-or-later.

## Layout

- `scripts/z13-power` — mode CLI (applies profiles SILENTLY; no notifications)
- `service/z13-power-service` — tray + watcher (PyQt6): the only notifier
- `service/z13-power-service.service` — systemd user unit (graphical-session.target)
- `contrib/z13-power-config` — deploys display-only powerdevilrc
- `kde/powerdevilrc` — display/DPMS-only template (no RunScript hooks)
- `install.sh` — from-source installer (fallback; package is preferred)
- `LICENSE` — GPL-3.0-or-later

## Mode → z13ctl mapping

| Mode | `z13ctl` calls |
|------|----------------|
| balanced | profile balanced; tdp 52/71/70; fancurve reset; undervolt reset |
| performance | profile performance; tdp 75/75/93/93; fancurve reset; undervolt reset |
| max | profile performance; tdp 93 --force; undervolt reset |
| silent | profile quiet; tdp 20/40/40; fancurve reset; undervolt -20 |
| lowpower | profile quiet; tdp 5; fancurve reset; undervolt -25 |
| status | prints profile/tdp/fancurve/undervolt |
| toggle | `systemctl --user` start/stop of `z13gui.service` |

TDP arg order: `--pl1 PL1 --pl2 PL2 --pl3 PL3`. UV steps skip gracefully when
`ryzen_smu` module is absent.

## Service behavior

Menu = 5 modes + **Automatic** (exclusive QActionGroup) + **Lock profile**
(checkbox, enabled only on a manual pick) + **Configure…** + Quit. Left/middle
click CYCLES to the next profile (Trigger); right-click = Plasma-native menu.
(Menu popups on Plasma Wayland are position-unreliable — that's why left-click
cycles instead of opening the menu; PyQt6 6.x also lacks QSystemTrayIcon.setMenu.)

State: `automatic` (default), `manual_mode`, `locked`.
- **Executor**: the service runs `z13ctl` DIRECTLY per mode — it no longer
  shells out to `z13-power` (removes both the config gap and double
  notifications from a stale z13-power). `z13-power` remains only as the
  manual CLI (its hardcoded presets match DEFAULT_MODES).
- **Automatic**: applies `on_ac` / `on_battery` / `on_low_battery` from config
  on login, on udev power_supply events (30s safety poll fallback), and after
  an unlocked manual pick is cleared.
- **Manual pick**: applies immediately; unless **locked**, it clears on the
  next power-source change → back to Automatic. Locked picks survive changes.
- **Low battery** (capacity <= `low_battery`): latches the configured
  `on_low_battery` profile EVEN over a locked/manual pick; restores the locked
  pick when back above the threshold.
- **Mode definitions**: `~/.config/z13-power/service.conf` `[modes.<name>]`
  sections — `profile`, `tdp` ("A" or "A B C" → `--set A [--pl2 B --pl3 C]`),
  `tdp_force` (adds `--force`), `fancurve` (`reset`/`auto` → `--reset`,
  else passed to `--set` as the 8-point string), `undervolt` (`reset` → `--reset`,
  else `--set <v>`, skipped without ryzen_smu). DEFAULT_MODES are the fallback.
- **3s profile poll**: `z13_sig()` = `z13ctl profile --get` label + TDP PL1.
  External changes (overlay/terminal/button) → notify + treated as an unlocked
  manual pick. Signature needed because `profile --get` returns the active
  custom-profile label (e.g. "custom") even when the platform profile changed.
- **Config** reloaded every 30s; `Configure…` opens it ($VISUAL/$EDITOR or
  xdg-open). Template written on first run with extensive comments (PL1/PL2/PL3
  semantics + 75W/force rule, fan-curve point format + profile-change gotcha,
  CO safety range, ryzen_smu requirement).
- **Polling is slim**: 5s poll = ONE `z13ctl profile --get` call (external
  change detection; TDP-only changes won't notify). Power events are udev-driven
  (zero idle cost) + a 30s safety `evaluate_power`. No other periodic work.
- **Diagnose**: `z13-power diagnose` subcommand checks hardware (DMI), z13ctl,
  users group, udev rules, sysfs writability, daemon, `z13ctl status`, ryzen_smu,
  notify-send — each with a fix; exit 0/1. Tray menu has **Diagnose…**
  (QMessageBox) and the service runs it at startup, notifying only on FAIL.
- **ryzen_smu detection**: module name in /proc/modules is `ryzen_smu` (not
  `ryzen_smu_drv`); check `/sys/kernel/ryzen_smu_drv` dir instead. This bug
  silently skipped undervolt on this machine until fixed.
- **Tray icon**: QPainter-drawn ROG-style dark tile + lightning bolt, color
  per mode (performance red, balanced cyan, silent green, max orange, lowpower
  amber); tooltip shows mode + automatic/manual/locked.
- **Notifications**: `notify-send` on every switch + external change. Single
  notifier — `z13-power` itself is silent.
- Service PATH (systemd) does NOT include `~/.local/bin` — resolves z13-power
  from `/usr/bin` (packaged).

## Automation topology (original machine)

- **z13-power-service** (user unit, graphical-session) — owns all switching.
- **PowerDevil** `~/.config/powerdevilrc` — display/DPMS settings ONLY; the
  `[X][RunScript]` hooks were removed (commit-era; see git history).
- **Panel button** (Meta+B, `com.github.configurable_button` applet) → runs
  `z13-power toggle` (z13gui overlay). NOT shipped; containment IDs user-specific.
- **User systemd units**: `z13ctl.service` (daemon), `z13ctl.socket`,
  `z13gui.service`, `z13-power-service.service`.
- **System**: `z13ctl-perms.service` + `/etc/udev/rules.d/99-z13ctl.rules`
  (generated by `sudo z13ctl setup`), plus `99-rog-z13-touchpad.rules`
  (rog-z13-trackpad-fix), `99-z13gui-gamepad.rules` (z13gui pkg).

## Conflict rules (the important gotchas)

- **z13ctl `autoswitch` must stay OFF** — it races the service on power changes.
- **KDE per-state power profiles must stay unset** — KDE would write
  `platform_profile` and fight the service.
- z13ctl daemon required for TDP/fancurve/undervolt persistence. Armoury Crate
  button watcher (daemon) is manual, not a conflict.
- Notifications are the service's job — don't re-add notify() to z13-power or
  you get double popups.

## Device specifics

- USB VID:PID `0b05:18c6` (keyboard/RGB HID) and `0b05:1a30` (folio).
- `ryzen_smu` kernel module required for undervolt. Module: `ryzen_smu_drv`.
  AUR `ryzen_smu-dkms-git` (amkillam fork).
- Sysfs perms: `users` group membership required (z13ctl setup + perms service).

## Packaging

- PKGBUILD `z13-power-git` in the `pkgbuilds` repo (paru custom source).
- depends: `z13ctl-bin python-pyqt6 python-pyudev libnotify`; optdepends:
  `z13gui-bin`, `ryzen_smu-dkms-git`.
- package(): installs z13-power, z13-power-service + `/usr/lib/systemd/user/`
  unit, z13-power-config, powerdevilrc, LICENSE.

## Per-unit tuning caveat

Undervolt (-20/-25 mV) and TDP (5–93 W) are silicon-lottery values from the
original unit. The bud may need to adjust the `silent` / `lowpower` modes in
`scripts/z13-power`. See README caveats.

## Related projects

- `rog-z13-trackpad-fix` (Forgejo, same forge) — companion; enables touchpad DWT.
- `z13ctl` / `z13gui` upstream: github.com/dahui — AUR `z13ctl-bin`, `z13gui-bin`.
