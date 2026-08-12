# ROG Flow Z13 — Power Management

Automated power profile switching for the **2025 ASUS ROG Flow Z13 (GZ302)**.
Plug in → performance mode. Unplug → balanced. Low battery → silent.
Undervolt and TDP power limits ride along automatically.

Built on [z13ctl](https://github.com/dahui/z13ctl) and driven by **KDE Plasma's
PowerDevil** — no extra daemon, no autoswitch config, just a single `z13-power`
command hooked into the power states you already have in System Settings.

## What it does

One command, seven modes (`z13-power <mode>`):

| Mode | Profile | TDP (W) | Undervolt | Wired to |
|------|---------|---------|-----------|----------|
| `performance` | performance | 75 / 75 / 93 / 93 | reset | **AC** |
| `balanced` | balanced | 52 / 71 / 70 | reset | **Battery** |
| `silent` | quiet | 20 / 40 / 40 | -20 mV | **Low battery** |
| `max` | performance | 93 forced | reset | manual |
| `lowpower` | quiet | 5 | -25 mV | manual |
| `status` | — | shows current state | — | manual |
| `toggle` | — | toggles z13gui overlay drawer | — | manual / shortcut |

The three wired entries fire automatically on power-source changes via KDE
PowerDevil (the same screen where you set display idle timeouts). z13ctl's own
`autoswitch` can only do AC/battery — the **Low Battery tier is the reason this
project exists**.

## Requirements

- **2025 ASUS ROG Flow Z13 (GZ302)** — these are laptop-specific values
- Arch Linux / CachyOS with KDE Plasma 6
- AUR: [`z13ctl-bin`](https://github.com/dahui/z13ctl) (required)
- AUR: [`z13gui-bin`](https://github.com/dahui/z13gui) (optional — for `toggle`)
- `ryzen_smu` kernel module (optional — needed only for undervolt; without it
  `z13-power` warns and skips the undervolt step)
- [rog-z13-trackpad-fix](https://forgejo.fifthdread.com/Fifthdread/rog-z13-trackpad-fix) (optional — enables "Disable While Typing")

## Install

**Recommended — packaged (scripts land in `/usr/bin`):**

```bash
paru -S z13-power-git        # from Fifthdread's pkgbuild repo
z13-power-config             # deploy the KDE PowerDevil hooks
```

**Or from source:**

```bash
git clone ssh://git@forgejo.fifthdread.com:223/Fifthdread/rog-z13-power-management.git
cd rog-z13-power-management
./install.sh
```

Either path:
1. Checks dependencies (`z13ctl`, `z13gui`, `ryzen_smu`, `users` group)
2. Installs `z13-power` (to `/usr/bin` or `~/.local/bin`)
3. Runs `sudo z13ctl setup` (udev rules + sysfs permission service) if needed
4. Enables the `z13ctl` daemon + socket (and `z13gui` if present)
5. Deploys the PowerDevil config (backing up yours)
6. Reminds you of the manual steps below

Then **log out and back in**, and verify:

```bash
z13-power status
```

## Manual steps (KDE GUI)

1. **Log out / back in** after group changes (`users` group for device access).
2. **System Settings → Power Management** — the three "Run Script" actions
   (AC / Battery / Low Battery) should be present. If not, add them:
   - AC: `z13-power performance`
   - Battery: `z13-power balanced`
   - Low Battery: `z13-power silent`
3. **(Optional) Meta+B overlay toggle** — a shortcut or panel button running
   `z13-power toggle` (requires `z13gui-bin`).

## Caveats

- **Undervolt is silicon lottery.** `-20`/`-25` mV worked on one unit; if the
  bud's Z13 is unstable (crashes under load), raise or remove the undervolt
  lines in the `silent` / `lowpower` modes of `scripts/z13-power`.
- **Don't use z13ctl's built-in autoswitch.** `z13ctl autoswitch` and KDE
  PowerDevil would both fire on power changes and race each other. Pick one —
  this project uses PowerDevil, so leave autoswitch off:
  `z13ctl autoswitch --clear`
- **Don't set KDE's own per-state power profiles** (System Settings → Power
  Management → "Performance"). PowerDevil would then write `platform_profile`
  directly and fight `z13-power`.
- The `max` / `lowpower` modes are manual (run from a terminal or shortcut) —
  they are not wired into any power state.
- Requires the z13ctl **daemon** running for TDP/fancurve/undervolt persistence.
  Check with `systemctl --user status z13ctl`.

## Project layout

```
├── install.sh              # from-source installer (deps, units, config deploy)
├── scripts/
│   └── z13-power           # the whole thing: 7 modes in one script
├── contrib/
│   └── z13-power-config    # packaged helper: deploys KDE hooks from the package
├── kde/
│   └── powerdevilrc        # PowerDevil config template (%BIN% substituted)
├── LICENSE                 # GPL-3.0-or-later
└── CONTEXT.md              # agent knowledge (local, not for the Forgejo page)
```

## Credits

- [z13ctl](https://github.com/dahui/z13ctl) — system control for the Z13
- [z13gui](https://github.com/dahui/z13gui) — GTK4 overlay drawer
