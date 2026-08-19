# rog-z13-power-management — CONTEXT.md

Project knowledge for the ROG Flow Z13 power automation repo. Agents read this
when working in this repo. Human-facing docs live in README.md (Forgejo page).

## Purpose

Automate power control on a 2025 ASUS ROG Flow Z13 (GZ302) and replace the
z13gui overlay drawer. Three components:
- `z13-power` — CLI modes wrapping `z13ctl` (AUR `z13ctl-bin`, github dahui/z13ctl)
- `z13-power-service` — PyQt6 system tray app + power profile watcher that OWNS
  all profile switching (login, AC/battery transitions, low battery, notifications)
- `z13-power-settings` — standalone PyQt6 settings window (launched from the tray
  menu / `z13-power settings`): RGB lighting, fan curve editor, battery charge
  limit, panel overdrive, boot sound, live telemetry. Replaces z13gui.

KDE PowerDevil Run Script hooks are intentionally NOT used — the runtime is
plain Qt + z13ctl + systemd, so it works on any desktop (KDE Plasma, and
Hyprland/Omarchy, whose bar already ships an SNI tray + notification daemon).
Only the optional display/DPMS config (`powerdevilrc`, `z13-power-config`) is
Plasma-specific. Hand-off repo for a friend; values are the original owner's
per-unit tuning. Packaged as `z13-power-git` in the pkgbuilds repo. License:
GPL-3.0-or-later.

## Layout

- `scripts/z13-power` — mode CLI (applies profiles SILENTLY; no notifications)
- `service/z13-power-service` — tray + watcher (PyQt6): the only notifier
- `service/z13-power-settings` — settings window (PyQt6): z13gui replacement
- `service/z13-power-service.service` — systemd user unit (graphical-session.target)
- `contrib/z13-power-config` — deploys display-only powerdevilrc (KDE Plasma only;
  no-ops elsewhere)
- `kde/powerdevilrc` — display/DPMS-only template (no RunScript hooks; KDE only)
- `install.sh` — from-source installer (fallback; package is preferred); deploys
  powerdevilrc only when running KDE Plasma (detected via XDG_CURRENT_DESKTOP)
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
| settings | opens `z13-power-settings` (lighting/fan/battery/power) |

TDP arg order: `--pl1 PL1 --pl2 PL2 --pl3 PL3`. UV steps skip gracefully when
`ryzen_smu` module is absent.

Lighting settings live in `~/.config/z13-power/lighting.conf` (`[lighting]`
section — device/mode/color1/color2/speed/brightness). The settings window
writes it; the service re-applies it at startup. Kept separate from the
heavily-commented service.conf so a ConfigParser rewrite can't clobber docs.
## Service behavior

Menu = 5 modes + **Automatic** (exclusive radio group) + **Lock profile**
(checkbox, enabled only on a manual pick) + **Diagnose…** + **Settings…**
(launches `z13-power-settings`) + **Quit**. Left/middle
click CYCLES to the next profile (Activate); right-click opens the menu.
- **KDE Plasma / X11**: classic Qt `QSystemTrayIcon` + `QMenu`. KDE's shell
  renders the menu natively; on X11, Qt's backend emits `activated(Context)`
  and the service pops the menu itself.
- **Other Wayland desktops (Hyprland/waybar)**: the service registers its OWN
  StatusNotifierItem + `com.canonical.dbusmenu` (`SniTray`), and the host
  renders the menu — the appindicator mechanism. QSystemTrayIcon can't do this:
  the SNI `ContextMenu()` call is swallowed by the platform theme
  (plasma-integration never emits `activated(Context)`), and a parentless
  `QMenu.popup()` can't display on Wayland (no surface for the xdg_popup in a
  windowless service). Live menu state (checked mode, Lock enable/state) is
  pushed via `ItemsPropertiesUpdated`. Needs `python-dbus-next`. The SniTray
  dbus thread must never silently take the icon away: it emits `registered`
  on success and `failed(reason)` on error, and the service falls back to the
  classic Qt tray (icon + cycling, no menu) after 15s or on failure.

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
- **Config** reloaded every 30s; the settings window's Profiles tab edits the
  `[service]` values (AC/battery/low-battery modes + threshold) and its
  "Open config file…" button opens the raw file ($VISUAL/$EDITOR or xdg-open).
  Template written on first run with extensive comments (PL1/PL2/PL3
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
  per mode from the live Omarchy theme when present (else neon fallbacks);
  tooltip shows mode + automatic/manual/locked. The SNI item must
  leave `IconName` empty so hosts (Omarchy/waybar) use `IconPixmap`. A
  non-empty theme name such as `preferences-system-power` wins over the
  pixmap and shows a fixed yellow glyph on every mode. The dbus thread
  re-registers with StatusNotifierWatcher on NameOwnerChanged so a bar
  refresh does not swallow the icon.
- **Omarchy theme**: `service/z13_power_theme.py` reads
  `~/.local/state/omarchy/current/theme/{colors,shell}.toml` and the
  fontconfig monospace family. Applied as Fusion + QSS to the settings
  window, diagnose dialog, and a frameless ThemedMenu (gtk3 would otherwise
  draw Adwaita). Live-reloads on theme-set.
- **Panel IPC**: `~/.local/state/z13-power/status.json` (mode, automatic,
  locked, ac, capacity, tdp, profile) written from `update_tray`.
  `command.json` (`op=mode|automatic|lock`) is consumed by a directory
  watcher. `z13-power` CLI forwards mode/automatic/lock to that file when
  the service is active. `contrib/omarchy/Z13PowerPanel.qml` is the Omarchy
  flyout that uses it.
- **Notifications**: `notify-send` on every switch + external change. Single
  notifier — `z13-power` itself is silent.
- Service PATH (systemd) does NOT include `~/.local/bin` — resolves z13-power
  from `/usr/bin` (packaged).

## Automation topology (original machine)

- **z13-power-service** (user unit, graphical-session) — owns all switching.
- **PowerDevil** `~/.config/powerdevilrc` — display/DPMS settings ONLY; the
  `[X][RunScript]` hooks were removed (commit-era; see git history).
- **Panel button** (Meta+B, `com.github.configurable_button` applet) → runs
  `z13-power settings` (opens the settings window). NOT shipped; containment
  IDs user-specific.
- **User systemd units**: `z13ctl.service` (daemon), `z13ctl.socket`,
  `z13-power-service.service`.
- **System**: `z13ctl-perms.service` + `/etc/udev/rules.d/99-z13ctl.rules`
  (generated by `sudo z13ctl setup`), plus `99-rog-z13-touchpad.rules`
 (rog-z13-trackpad-fix), plus `99-z13gui-gamepad.rules` (from a leftover
 z13gui install — safe to remove with z13gui).

## Conflict rules (the important gotchas)

- **z13ctl `autoswitch` must stay OFF** — it races the service on power changes.
- **No per-state power profiles from the desktop's own power manager** — on KDE
  that's System Settings → Power Management (writes `platform_profile`); on
  Omarchy/Hyprland it's the bar's **Power panel** (switches profiles and
  remembers separate AC/battery choices). Both would fight the service — keep
  the service as the single switcher.
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
  `ryzen_smu-dkms-git`. (z13gui-bin was dropped when the settings window
  replaced it; the pkgbuilds PKGBUILD now ships `z13-power-settings`.)
- package(): installs z13-power, z13-power-service, z13-power-settings,
  z13_power_theme.py + `/usr/lib/systemd/user/` unit, z13-power-config,
  powerdevilrc, LICENSE. Theme module must sit next to the scripts (same
  share dir or `~/.local/bin`) so they can import it.
- The packaged service's `.install` hook: enable+start on install;
  daemon-reload + restart on upgrade (new code deploys without re-login);
  stop+disable+cleanup on remove. Re-enters the user manager via
  `sudo -u $SUDO_USER` — a root-shell pacman run skips it (with a warning).
- NOTE: the PKGBUILD builds from the REMOTE source — `service/z13-power-settings`
  must exist in the pushed `main` branch or `makepkg` fails at `install:`.
  Push this repo before publishing pkgbuilds changes that touch package().
- MANDATORY: every code push to this repo must bump the pkgbuilds PKGBUILD
  `pkgver=` to `rev-count.commit`, regenerate + commit `.SRCINFO`
  (`makepkg --printsrcinfo > z13-power-git/.SRCINFO`), and push the pkgbuilds
  repo, in the same change (paru does not devel-detect pkgbuild-repo packages).

## Per-unit tuning caveat

Undervolt (-20/-25 mV) and TDP (5–93 W) are silicon-lottery values from the
original unit. The bud may need to adjust the `silent` / `lowpower` modes in
`scripts/z13-power`. See README caveats.

## Related projects

- `rog-z13-trackpad-fix` (Forgejo, same forge) — companion; enables touchpad DWT.
- `z13ctl` upstream: github.com/dahui — AUR `z13ctl-bin`. (z13gui is
  intentionally NOT installed — this project replaces it.)
