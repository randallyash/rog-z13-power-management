# ROG Flow Z13 — Power Management

Automated power profile switching for the **2025 ASUS ROG Flow Z13 (GZ302)**.
Plug in → performance mode. Unplug → balanced. Low battery → silent.
Undervolt and TDP power limits ride along automatically.

Built on [z13ctl](https://github.com/dahui/z13ctl). A single **system tray
service** (`z13-power-service`) owns all profile switching: it applies the right
profile at login, on power-source changes, and on low battery, gives you a tray
menu to switch profiles manually, and pops a KDE notification on every switch.
A **settings window** (`z13-power-settings`) covers the rest of what the z13gui
overlay drawer used to do — RGB lighting, fan curves, battery charge limit,
panel overdrive, boot sound, live telemetry.
No KDE "Run Script" hooks, no PowerDevil configuration, no autoswitch config —
works on any desktop.

## What it does

One command, six modes (`z13-power <mode>`) plus a settings window, and a tray app:

| Mode | Profile | TDP (W) | Undervolt | Used for |
|------|---------|---------|-----------|----------|
| `max` | performance | 93 forced | reset | manual |
| `performance` | performance | 75 / 75 / 93 / 93 | reset | **AC** |
| `balanced` | balanced | 52 / 71 / 70 | reset | **Battery** |
| `silent` | quiet | 20 / 40 / 40 | -20 mV | **Low battery** |
| `lowpower` | quiet | 5 | -25 mV | manual |
| `status` | — | shows current state | — | manual |
| `settings` | — | opens the settings window | — | manual |

`z13-power-service` (system tray):
- **Tray icon + menu** — left-click cycles profiles, right-click opens the
  menu; five modes + Automatic, current one marked. ROG-style icon tinted by
  the active profile.
- **Automatic** (default) — applies `on_ac` / `on_battery` / `on_low_battery`
  from config on login and power changes
- **Manual picks** apply immediately; unless **Lock profile** is checked, they
  clear on the next plug/unplug and return to Automatic
- **Lock profile** — a manual pick survives power changes (low battery still
  forces the safety profile, then restores your locked pick)
- **Configure…** — opens `~/.config/z13-power/service.conf`: every z13ctl call
  it makes (profile, TDP limits, fan curve, undervolt) is defined there,
  per mode, fully commented
- **Notifications** — KDE popup on every switch, and when a profile is changed
  from outside the service (overlay, terminal, Armoury Crate button)
- **Diagnose…** — runs `z13-power diagnose` (hardware, permissions, daemon,
  modules) and shows the report with fixes; also checked at service startup
  (only notifies if something is wrong)

`z13-power-settings` (settings window, replaces the z13gui drawer):
- **Lighting** — keyboard + lightbar zones, effect (static / breathe / cycle /
  rainbow / strobe / off), two colors (presets or an HSL picker), speed,
  brightness. Selections persist in `lighting.conf` and are re-applied at login.
- **Fan curve** — fetch the live 8-point curve, edit temp/speed pairs, apply or
  reset to firmware auto (75 W PL1 safety rules enforced).
- **Battery** — charge limit slider (40–100%), shows the current limit.
- **Power** — panel overdrive and boot sound toggles.
- **Telemetry** — live APU temperature, fan RPM, profile, TDP, power source.
Opened from the tray menu (**Settings…**) or with `z13-power settings` (the
Meta+B panel button).
The low-battery tier is the reason this project exists — z13ctl's own autoswitch
only supports AC/battery.

## Requirements

- **2025 ASUS ROG Flow Z13 (GZ302)** — these are laptop-specific values
- Arch Linux / CachyOS with KDE Plasma 6
- AUR: [`z13ctl-bin`](https://github.com/dahui/z13ctl) (required)
- `python-pyqt6`, `python-pyudev`, `libnotify` (required — tray service + notifications)
- `ryzen_smu` kernel module (optional — needed only for undervolt; without it
  `z13-power` warns and skips the undervolt step)
- AUR conflicts: if you already run a `z13ctl` variant (e.g. `z13ctl-plus-bin`),
  pacman will offer to swap it for `z13ctl-bin` — that's expected and safe.
  `z13gui-bin` is no longer needed: remove it with `paru -Rns z13gui-bin`.

## Install

**Recommended — packaged (scripts land in `/usr/bin`):**

First add Fifthdread's package repo to paru — one command (adds + syncs):

```bash
curl -fsSL https://5d.fyi/addrepo | bash
```

Prefer not to run a script? Add the repo by hand, then sync:

```bash
mkdir -p ~/.config/paru && printf '[fifthdread]\nUrl = https://forgejo.fifthdread.com/Fifthdread/pkgbuilds.git\nGenerateSrcinfo\nSkipReview\n' >> ~/.config/paru/paru.conf
paru -Sy --pkgbuilds
```

**The sync step is required** — without it `paru -S` won't know about
`z13-power-git`. Then install:

```bash
paru -S z13-power-git
```

Dependencies are pulled automatically by paru (`z13ctl-bin`, `python-pyqt6`,
`python-pyudev`, `libnotify`), and the install hook **enables + starts the tray
service** for you — no extra commands. Installed as root (no paru)? It
auto-starts at your next login via a user preset.

**Or from source:**

```bash
git clone ssh://git@forgejo.fifthdread.com:223/Fifthdread/rog-z13-power-management.git
cd rog-z13-power-management
./install.sh
```

Either path:
1. Checks dependencies (`z13ctl`, `ryzen_smu`, `users` group)
2. Installs `z13-power` + `z13-power-service` (to `/usr/bin` or `~/.local/bin`)
3. Runs `sudo z13ctl setup` (udev rules + sysfs permission service) if needed
4. Enables the `z13ctl` daemon + socket and the `z13-power-service` tray app
5. Deploys the PowerDevil display settings (backing up yours)

Then **log out and back in** (for group changes), and verify:

```bash
z13-power diagnose
z13-power status
```

`z13-power diagnose` checks hardware, permissions, the daemon, and modules,
and tells you exactly what to fix if anything's wrong (on a fresh machine
that's usually: `sudo z13ctl setup`, then re-login for the `users` group).

A tray icon should appear — click it to switch profiles manually.

## Configuration

`~/.config/z13-power/service.conf` (created on first run with full inline
documentation; `Configure…` in the tray menu opens it). The `[service]` section
maps power states to modes; each `[modes.<name>]` section defines exactly what
`z13ctl` commands run for that profile:

```ini
[service]
low_battery = 15
on_ac = performance
on_battery = balanced
on_low_battery = silent

[modes.performance]
profile = performance
tdp = 75 93 93        # PL1 PL2 PL3 watts (one number = all equal)
tdp_force = false     # allow PL1 > 75 (hardware max 93)
fancurve = reset      # reset | "40:30%,50:40%,..." (8-point curve)
undervolt = reset     # reset | -1..-40 (Curve Optimizer mV)
```

Values are validated (bad ones fall back to defaults) and reloaded
automatically every ~30s — no service restart needed.

## Caveats

- **Undervolt is silicon lottery.** `-20`/`-25` mV worked on one unit; if the
  bud's Z13 is unstable (crashes under load), raise or remove the undervolt
  lines in the `silent` / `lowpower` modes of `scripts/z13-power`.
- **Don't use z13ctl's built-in autoswitch.** `z13ctl autoswitch` and the tray
  service would both fire on power changes and race each other. Leave autoswitch
  off: `z13ctl autoswitch --clear`
- **Don't set KDE's own per-state power profiles** (System Settings → Power
  Management → "Performance"). KDE would write `platform_profile` directly and
  fight the service.
- The `max` / `lowpower` modes are manual (tray menu or terminal) — they are not
  wired into any power state.
- Requires the z13ctl **daemon** running for TDP/fancurve/undervolt persistence.
  Check with `systemctl --user status z13ctl`.

## Project layout

```
├── install.sh              # from-source installer (deps, units, config deploy)
├── scripts/
│   └── z13-power           # the mode CLI: 6 modes + settings in one script
├── service/
│   ├── z13-power-service   # tray icon + power profile watcher (PyQt6)
│   ├── z13-power-settings  # settings window: RGB, fan curve, battery, power
│   └── z13-power-service.service   # systemd user unit
├── contrib/
│   └── z13-power-config    # packaged helper: deploys KDE display settings
├── kde/
│   └── powerdevilrc        # display/DPMS-only PowerDevil template
├── LICENSE                 # GPL-3.0-or-later
└── CONTEXT.md              # agent knowledge (local, not for the Forgejo page)
```

## Credits

- [z13ctl](https://github.com/dahui/z13ctl) — system control for the Z13
- This project replaces the [z13gui](https://github.com/dahui/z13gui) overlay
  drawer: profiles, RGB lighting, fan curves, battery limit, panel overdrive,
  boot sound, telemetry — all in the system tray + settings window.
