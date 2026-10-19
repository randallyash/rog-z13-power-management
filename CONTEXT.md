# rog-z13-power-management — CONTEXT.md

Project knowledge for the ROG Flow Z13 power automation repo. Agents read this
when working in this repo. Human-facing docs live in README.md (Forgejo page).

## Purpose

Automate power control on a 2025 ASUS ROG Flow Z13 (GZ302) and replace the
z13gui overlay drawer. Three components:
- `z13-power` — CLI modes. Hardware goes through `z13_power_hw.py` (SMU + sysfs). `/usr/bin/z13ctl` is not executed.
- `z13-power-service` — PyQt6 system tray app + power profile watcher that OWNS
  all profile switching (login, AC/battery transitions, low battery, notifications)
- `z13-power-settings` — standalone PyQt6 settings window (launched from the tray
  menu / `z13-power settings`): RGB lighting, fan curve editor, battery charge
  limit, panel overdrive, boot sound, live telemetry. Replaces z13gui.

KDE PowerDevil Run Script hooks are intentionally NOT used — the runtime is
plain Qt + the built-in controller + systemd, so it works on any desktop (KDE Plasma, and
Hyprland/Omarchy, whose bar already ships an SNI tray + notification daemon).
Only the optional display/DPMS config (`powerdevilrc`, `z13-power-config`) is
Plasma-specific. TDP / undervolt defaults are silicon-lottery values from
the original unit — other GZ302s may need milder Quiet / Low undervolt.
Packaged as `z13-power-git` in the pkgbuilds repo. License: GPL-3.0-or-later.

## Layout

- `scripts/z13-power` — mode CLI (applies profiles SILENTLY; no notifications)
- `service/z13-power-service` — tray + watcher (PyQt6): the only notifier
- `service/z13-power-settings` — settings window (PyQt6): z13gui replacement
- `service/z13_power_hw.py` — SMU PPT, profile, fans, lighting, Curve Optimizer
- `service/z13_power_common.py` — shared paths, battery.conf / charge cap. `z13ctl()` calls the in-tree controller.
- `service/z13_power_io.py` — bounded conf/status I/O and helper processes
  (prefer /usr/bin, PATH fallback; no marketplace digest pin)
- `service/z13-power-overlay` — slim in-game profile picker for nested gamescope
- `service/z13-power-service.service` — systemd user unit (graphical-session.target)
- `contrib/z13-power-config` — deploys display-only powerdevilrc (KDE Plasma only;
  no-ops elsewhere)
- `kde/powerdevilrc` — display/DPMS-only template (no RunScript hooks; KDE only)
- `install.sh` — from-source installer (fallback; package is preferred); deploys
  powerdevilrc only when running KDE Plasma (detected via XDG_CURRENT_DESKTOP).
  Copies the *whole* runtime (CLI, service, settings, overlay, common, io,
  theme). Never copies only `z13-power` into `/usr/share`.
- `LICENSE` — GPL-3.0-or-later

## Mode → hardware mapping

| Mode | What the controller applies |
|------|----------------|
| balanced | profile balanced; tdp 52/71/70; fancurve reset; undervolt reset |
| performance | profile performance; tdp 75/92/93; fancurve reset; undervolt reset |
| custom | TDP 10–80 from tweaks.conf `custom_tdp` (default 75); `--force` above 75 W |
| max | alias for custom 80 (armoury PL1 max) |
| silent | profile balanced; SMU 28/28/28; fancurve reset; undervolt -20 |
| lowpower | profile balanced; SMU 15 W; fancurve reset; undervolt -25 |
| status | prints profile/tdp/fancurve/undervolt |
| settings | opens `z13-power-settings` (lighting/fan/battery/power) |

TDP arg order: `--pl1 PL1 --pl2 PL2 --pl3 PL3`. The SMU stapm and slow limits
are PL1; fast is max(PL2, PL3). UV and the below-floor TDP path need `ryzen_smu`.

## Power limits (SMU, not z13ctl)

asus-armoury (BIOS 314) still stores only **PL1 28–80 W**, **PL2 32–92 W**,
**PL3 45–93 W**. `z13ctl` 1.4.x refuses anything outside that and is not used.
`z13_power_hw.py` writes the requested watts to the Strix Halo MP1 mailbox
(stapm `0x14`, fast `0x15`, slow `0x16`, milliwatts) after the armoury update.
On this GZ302 the package holds that down to **10 W**. Quiet is 28 W. Low is
15 W: 10 W held under load, then locked the machine when the screensaver
blanked the panel. A 5 W request is stored and the chip stays near 10 W.

- apply_mode does **not** clamp recipes up to the armoury floor.
- The upstream `z13ctl` user daemon is masked so it cannot put the old limits back.
- `CUSTOM_TDP_MIN/MAX` are 10/80.

Lighting settings live in `~/.config/z13-power/lighting.conf` (`[lighting]`
section — device/mode/color1/color2/speed/brightness). Charge cap lives in
`~/.config/z13-power/battery.conf` (`[battery] charge_limit`). The settings
window writes both; the service re-applies them at startup (ACPI charge limit
does not survive reboot on this unit). Tweaks undervolt (Curve Optimizer,
0 to -40 mV) lives in `~/.config/z13-power/tweaks.conf` and overrides the
per-mode `undervolt=` recipe after every profile apply. Kept separate from the
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

State: `automatic` (default), `manual_mode`, `locked`. Automatic off,
the manual mode, and lock are restored from `status.json` on login so a
reboot does not silently re-enable Automatic. Unlocked manual still
clears on a live AC/battery change.
- **Executor**: the service calls `z13_power_hw.invoke` per mode (the
  in-tree controller). It does not shell out to `/usr/bin/z13ctl` or to
  the `z13-power` CLI. `z13-power` remains the manual CLI.
- **Apply order**: `profile --set` is skipped when `/sys/firmware/acpi/platform_profile`
  already matches. A redundant write still restores stock PPT (performance = 70W)
  and drops custom fan curves, so MAX then races `--force` and stays at 70W.
  After a *real* profile switch that needs `--force`, wait until fans are in
  auto, then TDP once. A failed TDP is a failed apply (do not advertise Max).
- **Automatic**: applies `on_ac` / `on_battery` / `on_low_battery` from config
  on login (only if Automatic was still on), on udev power_supply events
  (30s safety poll fallback), and after an unlocked manual pick is cleared.
- **Manual pick**: applies immediately; unless **locked**, it clears on the
  next power-source change → back to Automatic. Locked picks survive changes.
- **Low battery** (capacity <= `low_battery`): latches the configured
  `on_low_battery` profile EVEN over a locked/manual pick; restores the locked
  pick when back above the threshold.
- **Tablet Quiet** (GZ302): Asus WMI `SW_TABLET_MODE` or missing USB dock
  keyboard `0b05:1a30` is a tablet *pose*. If an external DRM sink is
  connected (HDMI / USB-C DP, not eDP), it is a TV/monitor dock and we
  do **not** latch Quiet. Handheld pose → `on_tablet` (default silent).
  Leave pose → Automatic. Manual pick while latched sticks until posture
  changes. `tablet_quiet=false` disables. ioctl EVIOCGSW only — do not
  read evdev (would steal rotation).
- **Mode definitions**: `~/.config/z13-power/service.conf` `[modes.<name>]`
  sections — `profile`, `tdp` ("A" or "A B C" → `--set A [--pl2 B --pl3 C]`),
  `tdp_force` (adds `--force`), `fancurve` (`reset`/`auto` → `--reset`,
  else passed to `--set` as the 8-point string), `undervolt` (`reset` → `--reset`,
  else `--set <v>`, skipped without ryzen_smu). DEFAULT_MODES are the fallback.
- **Power-source change**: one AC0 udev event, confirmed with a second
  sysfs read 80ms later on a QTimer (do not sleep on the Qt thread).
  Unlocked manual → Automatic, then on_ac / on_battery.
- **External profile poll**: 8s read of `/sys/firmware/acpi/platform_profile`
  (no subprocess). If it matches the last applied mode, only `last_fw_profile`
  is updated. If Automatic or Lock is on, force-apply the full recipe
  (TDP included — a same-name skip would leave stock PPT after a DE
  profile write). Unlocked manual: map firmware → mode so the tray
  matches the chip. Tray/flyout always show `_last_applied`. `status.json`
  is truncated in place so QML FileView keeps its inotify watch. TDP-only
  changes do not notify.
- **Config** is parsed on mtime change (file watcher); the settings window's
  Profiles tab edits the `[service]` values (AC/battery/low-battery modes +
  threshold) and its "Open config file…" button opens the raw file
  ($VISUAL/$EDITOR or xdg-open). Template written on first run with extensive
  comments (PL1/PL2/PL3 semantics + 75W/force rule, fan-curve point format +
  profile-change gotcha, CO safety range, ryzen_smu requirement).
- **Polling is slim**: idle path is sysfs + udev. Power events are udev-driven
  (zero idle cost) + a 30s safety `evaluate_power` that reuses the cached
  config parse. `z13ctl` runs only when a mode actually changes (profile/TDP/
  fan/UV writes skip if the target already matches). Tweaks.conf is mtime-
  cached; the last CO is remembered so start() + apply_mode do not double-
  hit the SMU. Startup diagnose is deferred 20s and is PATH/sysfs only (no
  `z13ctl`). Settings tabs are built on first view; Tweaks/Fan/Battery/
  Telemetry reads go through sysfs (k10temp, asus fans, panel_od, boot_sound,
  ppt_pl1_spl, charge_control_end_threshold) and fall back to z13ctl.
- **Diagnose**: `z13-power diagnose` checks the built-in controller, the
  users group, udev rules, sysfs writability, that the upstream z13ctl
  daemon is not running, hardware status, ryzen_smu, and notify-send.
  Exit 0/1. Tray menu has **Diagnose…**
  (QMessageBox) and the service runs it 20s after startup, notifying only on FAIL.
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
  fontconfig monospace family. Applied as Fusion + QSS to the diagnose
  dialog and a frameless ThemedMenu (gtk3 would otherwise draw Adwaita).
  The settings window uses the same tokens as the tray flyout (hero,
  sidebar nav, section headers, bordered pills, toggle rows) instead of
  a stock QTabWidget. Live-reloads on theme-set. Launchers prefer
  `~/.local/bin/z13-power-settings` so a from-source install wins over
  the packaged `/usr/bin` copy.
- **Panel IPC**: `~/.local/state/z13-power/status.json` (mode, automatic,
  locked, ac, capacity, tdp, profile, charge_limit, fill_once) written from
  `update_tray`. `command.json` (`op=mode|automatic|lock|fill`) is consumed
  by a directory watcher. `z13-power` CLI forwards mode/automatic/lock/fill
  to that file when the service is active.
  `contrib/omarchy/z13.power/Z13PowerPanel.qml` is the Omarchy flyout that
  uses it.
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

- If `z13ctl` is installed, its `autoswitch` must stay OFF and its user
  daemon must stay masked. Either one races this service.
- **No per-state power profiles from the desktop's own power manager** — on KDE
  that's System Settings → Power Management (writes `platform_profile`); on
  Omarchy/Hyprland it's the bar's **Power panel** (switches profiles and
  remembers separate AC/battery choices). Both would fight the service — keep
  the service as the single switcher.
- TDP, fan curve, and undervolt persistence is the tray service. It
  writes the Ryzen SMU directly. The upstream `z13ctl` user daemon is
  masked and is not required. The service watches the Armory Crate side
  button (`Asus WMI hotkeys`, KEY_PROG3) itself and toggles settings or
  the gamescope overlay. Do not also bind that key in the compositor.
- Nested gamescope: if the focused *host* window is gamescope, spawn
  `z13-power-overlay` on the nested Xwayland (`QT_QPA_PLATFORM=xcb`,
  `Z13_GAMESCOPE=1`). Tag with `xprop` in a child process: `STEAM_OVERLAY`
  + `STEAM_INPUT_FOCUS` only (not `GAMESCOPE_EXTERNAL_OVERLAY` — that is
  paint-only / mangoapp, and setting both composites the window twice).
  Window is fullscreen transparent with a centered card so Steam overlay
  scaling does not stretch a 720×196 panel. Never ctypes/libX11 from the
  Qt process — that SIGSEGV'd settings in `XFlush`. Full settings stay on
  the host compositor.
- gamescope-focused detection: Hyprland `hyprctl activewindow` if it
  answers; else KWin on Plasma Wayland (`kdotool` or a one-shot KWin
  script via D-Bus); else X11 EWMH `_NET_ACTIVE_WINDOW` / `WM_CLASS`.
  First compositor that answers wins so Xwayland leftovers cannot steal
  the decision. Not gamescope-session / Deck gaming mode (no host window).
- Notifications are the service's job — don't re-add notify() to z13-power or
  you get double popups.

## Device specifics

- USB VID:PID `0b05:18c6` (keyboard/RGB HID) and `0b05:1a30` (folio).
- `ryzen_smu` kernel module required for undervolt. Module: `ryzen_smu_drv`.
  AUR `ryzen_smu-dkms-git` (amkillam fork).
- Sysfs perms: `users` group membership, plus udev rules
  (`99-z13ctl.rules` or `99-z13-power.rules`).

## SMU/EC wedge (P-state limit latch) — 2026-10-11

Firmware-level failure mode hit on the original unit. Full write-up with all
measurements: `diagnostics/2026-10-11-smu-wedge.md`.

- **Symptom**: everything slow; all cores pinned at exactly 2.0 GHz (or 604 MHz
  idle), package power ~7 W against a 52–75 W budget, GPU parked at 726 MHz,
  fans 0 RPM, temps 36–47 °C. A 10^6-iteration python loop takes 3.3–4.2 s
  (healthy: ~0.07 s).
- **Cause**: the EC/SMU latches the P-state limit to the slowest state —
  `MSR 0xC001_0061` bits[2:0] = 2 (wedged) vs 1 (healthy). Read-only to the
  OS (writes GP-fault). Every sysfs value looks correct while the SMU refuses
  to ramp.
- **Survives**: suspend/resume cycles, AC plug/unplug, every profile/PPT write
  (z13ctl, WMI, armoury, CO), asusd stopped, EPP/governor/boost toggles,
  `amd_pstate` live re-init, kexec (same kernel AND LTS kernel), and a full
  S5 reboot. **Only an EC power loss clears it.**
- **Recovery**: poweroff → unplug charger → hold power button 40–60 s → boot.
  ~2 min, no data loss. Verified working 2026-10-11. A full S5 reboot does
  **NOT** clear it; kexec (same or different kernel) does not either.
- **BIOS 314 flashed 2026-10-11** (was 311, 08/2025). No hard-wedge recurrence
  on 314 yet — the watcher is the tripwire. (The 2026-10-12 watcher alarms were
  false positives from GPU load, see Detection below.) If a hard wedge recurs
  on 314, that is new firmware-level evidence worth reporting to ASUS/kernel.
- **Detection**: `~/.local/bin/z13-wedge-watch` v3 (systemd user unit
  `z13-wedge-watch.service`, deployed on the original unit, versioned at
  `contrib/wedge-watch/`). v3 probes the wedge invariant: spin one core
  ~1.4 s, require boost past 2.2 GHz. **Busy gate (v3, 2026-10-12 lesson)**:
  a heavy iGPU load (wallfx, games) makes the SMU legitimately limit the CPU
  to P2 — `MSR 0xC001_0061` bits[2:0]=2 shows under budget pressure too, so a
  capped probe is only meaningful when the GPU is quiet and the package cool.
  While amdgpu power > 15 W or k10temp > 80 °C a probe is inconclusive: no
  fail counted, no alarm, no recovery clear, fails reset. A real wedge is
  still caught by two consecutive idle probes ~90 s after load drops.
  Hard-wedge signature: capped ~2.0 GHz with LOW package power (7 W), LOW
  temps (36-47 °C) and a QUIET GPU. Alarm needs 2 consecutive failed idle
  probes (~90 s apart). Log: `~/.local/state/z13-wedge-watch.log`
  (transitions + hourly heartbeat, 500 KB cap). Root-level signature:
  `MSR 0xC001_0061` bits[2:0] — 0x20/0x21 healthy *when idle/cool*; 0x22
  alone is NOT proof of wedge (legit P2 budget limiting shows the same).
  v1 lesson (do not regress): "max freq < 3 GHz while load > 2" false-alarms —
  on battery with EPP balance_power, load 2-3 legitimately parks clocks at
  2.7-2.9 GHz because no single core is pushed. v2 lesson: the probe-only
  invariant false-alarms under iGPU load (5 false alarms from wallfx on
  2026-10-12).
- **Implication for this repo**: NO software kick (including any post-resume
  hook we might add) can heal this failure mode — the wedge is below every
  interface z13power owns. Prevention/detection is the only software answer.
  Trigger unknown; correlated with long s2idle on battery and the 2026-10-10
  profile-flapping session.

## z13power findings from the wedge investigation (real bugs, fix later)

- **asusd rejects armoury PPT sets on battery**: `asusctl armoury set` fails
  with "profile tuning is disabled for current profile and power state" when
  on battery. z13power's `write_armoury_ppt` calls fail silently → asusd's
  cache drifts from the applied values (cache said 75, sysfs said 52) → asusd
  can restore stale defaults on its own events. Fix: surface the rejection,
  verify-after-write (read back `current_value`), and/or mask asusd.
- **PPD is masked by the installer** (correct, sole profile ownership), but
  powerdevil then writes EPP directly and flip-flops it (balance_power ↔
  performance) on every profile/platform change. Harmless to clocks but noisy;
  worth suppressing or documenting.
- **The Oct 10 `read_power` ucsi fallback patch works** — generic USB-C PD
  chargers keep EC mains (AC0) offline; the ucsi source-psy fallback aligned
  z13power with reality and stopped the performance↔balanced flapping.

## Packaging

- PRIMARY REPO (2026-10-10): `ssh://git@forgejo.fifthdread.com:223/Ramzal/rog-z13-power-management.git`
  - Ramzal develops here; this (Fifthdread) clone is a mirror. Push code to
    Ramzal first, then mirror to origin. Both accept pushes (verified).
  - The `z13-power-git` PKGBUILD in the pkgbuilds repo sources Ramzal's URL
    (repointed 2026-10-10).
- PKGBUILD `z13-power-git` in the `pkgbuilds` repo (paru custom source).
- depends: `python-pyqt6 python-pyudev libnotify python-dbus-next
  ryzen_smu-dkms-git`. `z13ctl-bin` is not a dependency. Undervolt needs a kernel module rebuilt for each
  kernel via DKMS — do not ship a prebuilt .ko. `ryzen_smu-dkms-git` is
  the amkillam fork (Strix Halo). Kernel `-headers` for the running kernel
  must be installed or DKMS cannot build. (z13gui-bin was dropped when the
  settings window replaced it.)
- package(): installs z13-power, z13-power-service, z13-power-settings,
  z13_power_hw.py, z13_power_theme.py, z13_power_common.py, contrib/ryzen-smu udev +
  modules-load, systemd user unit, z13-power-config, powerdevilrc, LICENSE.
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
original unit. Other GZ302s may need milder Quiet / Low undervolt (Tweaks
slider, or `undervolt=` in `scripts/z13-power` / `service.conf`). See README
caveats.

## Related projects

- `rog-z13-trackpad-fix` (Forgejo, same forge) — companion; enables touchpad DWT.
- `z13ctl` upstream: github.com/dahui — AUR `z13ctl-bin`. (z13gui is
  intentionally NOT installed — this project replaces it.)
