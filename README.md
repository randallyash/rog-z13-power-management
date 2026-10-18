# ROG Flow Z13 — Power Management

> **[What’s new →](CHANGELOG.md)** Armory Crate button · **gamescope in-game
> overlay** · tray follows plug/unplug (bugfix) · Tweaks undervolt · silicon
> lottery · charge cap that survives reboot · **~99% less idle work**.

Power, lighting, and thermals for the **2025 ASUS ROG Flow Z13 (GZ302)** —
one service, no Armory Crate, no Windows. Power limits are written directly
to the Ryzen SMU (stapm, slow, and fast). **`z13ctl` is not a dependency**,
and an AUR update of `z13ctl-bin` cannot change these limits. Replaces the
z13gui overlay drawer. Works on Omarchy, Hyprland, KDE Plasma, and anything
with a system tray.

## Features

<table>
<tr>
<td width="50%" valign="top">

**Power**
- Plug in → Performance. Unplug → Balanced. Low battery → Quiet.
- Four recipes plus **Custom** (10–80 W slider). Quiet is a real **20 W** lock. Low holds **10 W**.
- Lock a manual pick across plug/unplug. Low battery still forces Quiet, then restores it.
- Handheld tablet (keyboard off or tablet hinge, no TV) → Quiet. Keyboard-off to a TV keeps high power.
- Charge limit 40–100%, re-applied at login. One-shot *charge to 100%* for this plug-in only.

</td>
<td width="50%" valign="top">

**Control**
- Omarchy: lives in the **battery slot** — live watts, temp, profile pills, Automatic, Lock.
- Everywhere else: a tinted tray bolt. Left-click cycles; right-click opens the menu.
- The **Armory Crate** side button opens settings on the desktop.
- Nested **gamescope** (Steam, Lutris, Heroic) gets an in-game profile picker.
- CLI: `z13-power custom` · `performance` · `balanced` · `silent` · `lowpower`. `max` is custom 80.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**Tuning**
- Keyboard and lightbar: effect, colors, speed, brightness — restored at login.
- 8-point fan curve, or reset to firmware auto.
- Curve Optimizer undervolt, 0 to −40 mV, with a silicon-lottery suggestion.
- Panel overdrive, boot sound, live APU temp / fan / TDP.

</td>
<td width="50%" valign="top">

**Desktop**
- No KDE Run Script hooks. No PowerDevil profile wars. No `z13ctl` daemon.
- Follows the live Omarchy theme when one is present.
- **Diagnose** reports hardware, permissions, daemon, and modules — with the fix.
- Notifications on every switch, including changes from the overlay or the CLI.

</td>
</tr>
</table>

## Profiles

| Mode | When | TDP (W) | Undervolt |
|------|------|---------|-----------|
| `performance` | **AC** | 75 / 92 / 93 | reset |
| `balanced` | **Battery** | 52 / 71 / 70 | reset |
| `silent` | **Low battery** | 20 / 20 / 20 | −20 mV |
| `custom` | manual | 10–80 slider | reset |
| `lowpower` | manual | 10 | −25 mV |

asus-armoury still refuses PL1 below 28 W. That attribute is not what the
chip follows. This tree writes the requested watts to the SMU after the
armoury update. On this GZ302 the package holds that limit down to **10 W**
and no further. Quiet stays 20 W. A request under 10 W is stored and the
chip sits near 10 W.

`z13-power status` prints the live state. `z13-power settings` opens the window
(RGB, fan, battery, Tweaks, telemetry).

<details>
<summary>Tray, settings, and overlay — in detail</summary>

`z13-power-service` (system tray):
- **Tray icon + menu** — left-click cycles profiles, right-click opens the
  menu; five modes + Automatic, current one marked. ROG-style icon tinted by
  the active profile (colours follow the Omarchy theme when one is present).
  On SNI trays (Omarchy, waybar, …) the service leaves `IconName` empty so
  the host renders that pixmap instead of a theme icon. The Qt menu and
  settings window read `~/.local/state/omarchy/current/theme` and restyle
  themselves; the SNI item re-registers when the bar restarts so the icon
  does not vanish. On Omarchy the tray host can open a panel-style flyout
  (hero, stats, profile pills) from `contrib/omarchy/z13.power/Z13PowerPanel.qml`.
- **Automatic** (default) — applies `on_ac` / `on_battery` / `on_low_battery`
  from config on login and power changes
- **Manual picks** apply immediately; unless **Lock profile** is checked, they
  clear on the next plug/unplug and return to Automatic
- **Lock profile** — a manual pick survives power changes (low battery still
  forces the safety profile, then restores your locked pick)
- **Notifications** — popup on every switch, and when a profile is changed
  from outside the service (overlay, terminal, Armory Crate button)
- **Diagnose…** — runs `z13-power diagnose` (hardware, permissions, daemon,
  modules) and shows the report with fixes; also checked at service startup
  (only notifies if something is wrong)
- **Armory Crate button** — the side button that did nothing on Linux
  (it opened Armory Crate on Windows) now toggles UI: press to open,
  press again to close. On the desktop that is full settings, stuck
  above a fullscreen game. **Inside nested gamescope** (Steam, Lutris,
  Heroic, `gamescope --`) it is a clickable in-game profile picker
  (Max / Perf / Mid / Quiet / Low) — Hyprland, Plasma Wayland, and
  X11. The service reads KEY_PROG3 from `Asus WMI hotkeys` itself.
  The full settings window is
  never opened on gamescope's Xwayland (that SIGSEGV'd).

`z13-power-settings` (settings window, replaces the z13gui drawer). On
Omarchy it follows the live theme — same hero / section-header / pill
language as the tray flyout — instead of a stock Qt tab dialog:
- **Lighting** — keyboard + lightbar zones, effect (static / breathe / cycle /
  rainbow / strobe / off), two colors (presets or an HSL picker), speed,
  brightness. Selections persist in `lighting.conf` and are re-applied at login.
- **Fan curve** — fetch the live 8-point curve, edit temp/speed pairs, apply or
  reset to firmware auto (75 W PL1 safety rules enforced).
- **Battery** — charge limit slider (40–100%). Saved in `battery.conf` and
  re-applied at login (the ACPI cap does not survive reboot).
- **Tweaks** — panel overdrive, boot sound, and a CPU undervolt slider
  (Curve Optimizer, 0 to -40 mV). Saved in `tweaks.conf` and re-applied
  at login and after every profile switch. A silicon-lottery score
  (50–99) sits next to it with a suggested starting undervolt; best and
  weakest cores use the same scale. Derived from AMD preferred-core
  rankings, not ASUS BIOS SP.
- **Profiles** — which mode runs on AC / battery / low battery and the
  low-battery threshold, written back to `service.conf`; "Open config file…"
  exposes the raw file for per-mode TDP / fan curve / undervolt tuning.
- **Telemetry** — live APU temperature, fan RPM, profile, TDP, power source.

Opened from the tray menu (**Settings…**) or with `z13-power settings` (the
Meta+B panel button). The low-battery tier is the reason this project exists —
z13ctl's own autoswitch only supports AC/battery.

</details>

## Requirements

- **2025 ASUS ROG Flow Z13 (GZ302)** — these are laptop-specific values
- Arch Linux / CachyOS (KDE Plasma 6, Hyprland, etc.)
- Hardware control ships in `service/z13_power_hw.py`. It talks to
  platform profile, asus-nb-wmi, asus-armoury, the fan curve, and the Ryzen
  SMU (`/sys/kernel/ryzen_smu_drv`). **`z13ctl-bin` is not required.** If it
  is installed, its user daemon is masked so it cannot write over these limits.
- `python-pyqt6`, `python-pyudev`, `libnotify` (required — tray service + notifications)
- `python-dbus-next` (required — non-KDE Wayland desktops serve the tray menu
  via an SNI/dbusmenu item; KDE/X11 don't use it)
- KDE Plasma is not required — the tray service is plain Qt and works on any
  desktop. See [Desktop environments](#desktop-environments) below.
- `ryzen_smu-dkms-git` (amkillam fork) — **required**. The SMU mailbox is
  how TDP under the armoury floor and the Tweaks undervolt are applied.
  It is a DKMS module (not baked into this repo) and must rebuild against
  your running kernel, so install the matching `-headers` package
  (e.g. `linux-cachyos-bore-headers`).
- `z13gui-bin` is no longer needed: remove it with `paru -Rns z13gui-bin`.
  An installed `z13ctl-bin` can stay for its udev rules; this app does not run it.

## Install

**Recommended — packaged (scripts land in `/usr/bin`):**

First add Fifthdread's package repo to paru — one command (adds + syncs):

```bash
curl -fsSL https://5d.fyi/addrepo | bash
```

Prefer not to run a script? Add the repo by hand, then sync:

```bash
mkdir -p ~/.config/paru && printf '[fifthdread]\nUrl = https://forgejo.fifthdread.com/Fifthdread/pkgbuilds.git\nSkipReview\n' >> ~/.config/paru/paru.conf
paru -Sy --pkgbuilds
```

**The sync step is required** — without it `paru -S` won't know about
`z13-power-git`. Then install (this is the packaged Arch path; do not
switch to the GitHub marketplace pin unless you want `/usr` digest
checks):

```bash
paru -S z13-power-git
```

Dependencies are pulled automatically by paru (`python-pyqt6`,
`python-pyudev`, `libnotify`, `ryzen_smu-dkms-git`). **`z13ctl-bin` is not
one of them.** The install hook enables and starts the tray service.
Installed as root (no paru)? It auto-starts at your next login via a user preset.

**Or from source:**

```bash
git clone ssh://git@forgejo.fifthdread.com:223/Fifthdread/rog-z13-power-management.git
cd rog-z13-power-management
./install.sh
```

Either path:
1. Checks the built-in controller, `ryzen_smu`, and the `users` group
2. Installs `z13-power`, `z13-power-service`, and `z13_power_hw.py`
3. Leaves existing udev rules in place (it does not run `z13ctl setup`)
4. Masks the `z13ctl` user daemon if that unit exists, and enables `z13-power-service`
5. Deploys the PowerDevil display settings (backing up yours)

Then **log out and back in** (for group changes), and verify:

```bash
z13-power diagnose
z13-power status
```

`z13-power diagnose` checks hardware, permissions, the controller, and
modules, and tells you exactly what to fix if anything's wrong (on a fresh
machine that's usually group membership, then a re-login).

Want the Tweaks undervolt slider live on **this** kernel?

```bash
z13-power setup-undervolt
```

That installs the matching `-headers` package plus `ryzen_smu-dkms-git`
(amkillam, rebuilds via DKMS — nothing prebuilt in this repo).

A tray icon should appear — click it to switch profiles manually.

## Desktop environments

The service, settings window, and CLI are plain Qt/Python — no KDE
APIs, no PowerDevil hooks, no autoswitch. Everything runs on any desktop:

- **KDE Plasma** — works out of the box. The installer also deploys a
  display/DPMS-only `powerdevilrc` (optional; `z13-power-config` does the same
  for packaged installs). Don't set KDE's own per-state power profiles — see
  [Caveats](#caveats).
- **Hyprland / Omarchy** — works out of the box too; Omarchy's bar already
  provides an SNI system tray and a notification daemon, so both the tray icon
  and `notify-send` popups appear with no extra software. On non-KDE Wayland
  desktops the service registers its own StatusNotifierItem + dbusmenu, so the
  tray menu (right-click) is rendered by the bar itself instead of Qt (Qt's
  tray backend can't pop a menu on Wayland). The SNI `IconName` is left empty
  on purpose: hosts prefer a theme name over `IconPixmap`, so advertising
  `preferences-system-power` made the tray show a fixed yellow power glyph
  instead of the profile-tinted bolt. If the SNI item ever fails to
  register, the service automatically falls back to the classic Qt tray icon
  (and notifies you) rather than losing the icon. Two things to check:
  - the service auto-starts at login — it hooks `graphical-session.target`
    (`systemctl --user is-active graphical-session.target`; Hyprland setups
    must import it via `systemctl --user import-environment` + start the
    target, which Omarchy does);
  - `z13-power-config` is a no-op outside KDE (display/DPMS is hypridle's
    job there).
  Other Wayland compositors need an SNI-capable tray (waybar, anyrun, …) and a
  notification daemon (swaync, mako, dunst, …) for the same features.

  Omarchy specifically: `install.sh` runs `z13-power-omarchy-setup`, which
  puts **`z13.power`** in the battery slot (Max / Perf / Mid / Quiet / Low,
  Automatic, Lock) and **`z13.battery`** for low-battery warnings. Stock
  `omarchy.power` is disabled, not edited. The SNI bolt goes Passive while
  that widget is on the bar. `omarchy update` does not remove the user
  plugins; `omarchy refresh shell` can restore the stock slot — re-run
  `z13-power-omarchy-setup`. The service still writes `status.json` /
  `command.json` so the panel never races the tray service.

## Configuration

`~/.config/z13-power/service.conf` (created on first run with full inline
documentation; the settings window's **Profiles** tab edits it, and its
"Open config file…" button opens the raw file). The `[service]` section
maps power states to modes; each `[modes.<name>]` section defines exactly what
the controller applies for that profile:

```ini
[service]
low_battery = 15
on_ac = performance
on_battery = balanced
on_low_battery = silent

[modes.performance]
profile = performance
tdp = 75 92 93        # PL1 PL2 PL3 watts (one number = all equal, empty = skip)
tdp_force = false     # allow PL1 > 75 (hardware max 80 on asus-armoury)
fancurve = reset      # reset | "40:30%,50:40%,..." (8-point curve)
undervolt = reset     # reset | -1..-40 (Curve Optimizer mV)
```

Values are validated (bad ones fall back to defaults) and reloaded
automatically every ~30s — no service restart needed. The watts you set are
written to the SMU. asus-armoury is updated too, and clamped to its own
28/32/45 W floor when the request is lower. The package follows the SMU.

## Caveats

- **asus-armoury cannot store PL1 below 28 W.** The SMU can. Quiet is 20 W
  and Low is 10 W because those are the sustained limits this APU holds.
  Below 10 W the limit register changes and the package climbs back to
  about 10 W.
- **Undervolt is silicon lottery.** Quiet (`-20` mV) and Low (`-25` mV) were
  stable on one GZ302. If yours crashes under load, ease off: pull the Tweaks
  slider toward 0, or change `undervolt=` in those modes (`scripts/z13-power`
  / `service.conf`) to something milder or `reset`.
- **Don't set per-state power profiles in your desktop's own power manager.**
  On KDE that's System Settings → Power Management → "Performance". On
  Omarchy, `z13-power-omarchy-setup` replaces the bar's Power slot with
  `z13.power` so that flyout talks to us instead of `powerprofiles-set`.
  Keep the service as the single profile switcher.
- The `custom` / `lowpower` modes are manual (tray menu or terminal) — they are not
  wired into any power state.
- The tray service reapplies TDP, fans, lighting, and undervolt. If `z13ctl`
  is installed, its user daemon is masked so it does not write over those.

## Project layout

```
├── CHANGELOG.md            # what's new — features, compatibility, numbers
├── install.sh              # from-source installer (deps, units, config deploy)
├── scripts/
│   ├── z13-power           # the mode CLI: 6 modes + settings + setup-undervolt
│   └── z13-power-omarchy-setup  # Omarchy: z13.power in the battery slot
├── service/
│   ├── z13-power-service   # tray icon + power profile watcher (PyQt6)
│   ├── z13-power-settings  # settings window: RGB, fan curve, battery, Tweaks
│   ├── z13_power_common.py # shared paths, battery.conf / charge cap
│   ├── z13_power_hw.py     # SMU, PPT, fans, lighting, Curve Optimizer
│   ├── z13_power_io.py     # bounded conf I/O and helper processes
│   └── z13-power-service.service   # systemd user unit
├── contrib/
│   ├── omarchy/            # z13.power + z13.battery user plugins
│   ├── ryzen-smu/          # udev + modules-load for Curve Optimizer
│   └── z13-power-config    # packaged helper: deploys KDE Plasma display settings
├── kde/
│   └── powerdevilrc        # display/DPMS-only PowerDevil template (KDE only)
├── LICENSE                 # GPL-3.0-or-later
└── CONTEXT.md              # agent knowledge (local, not for the Forgejo page)
```

## Credits

- [z13ctl](https://github.com/dahui/z13ctl) — the upstream tool this tree no longer executes
- This project replaces the [z13gui](https://github.com/dahui/z13gui) overlay
  drawer: profiles, RGB lighting, fan curves, battery limit, panel overdrive,
  boot sound, telemetry — all in the system tray + settings window.
