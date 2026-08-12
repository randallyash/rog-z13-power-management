# ROG Flow Z13 — Power Management

Automated power profile switching for the **2025 ASUS ROG Flow Z13 (GZ302)**.
Plug in → performance mode. Unplug → balanced. Low battery → silent.
Undervolt and TDP power limits ride along automatically.

Built on [z13ctl](https://github.com/dahui/z13ctl) and driven by **KDE Plasma's
PowerDevil** — no extra daemon, no autoswitch config, just scripts hooked into
the power states you already have in System Settings.

## What it does

| Power state | Script | Profile | TDP (W) | Undervolt |
|-------------|--------|---------|---------|-----------|
| **AC** | `z13performance` | performance | 75 / 75 / 93 / 93 | reset |
| **Battery** | `z13balanced` | balanced | 52 / 71 / 70 | reset |
| **Low battery** | `z13silent` | quiet | 20 / 40 / 40 | -20 mV |
| *(manual)* | `z13max` | performance | 93 forced | reset |
| *(manual)* | `z13lowpower` | quiet | 5 | -25 mV |
| *(manual)* | `z13status` | — | shows current state | — |

The three AC/Battery/LowBattery entries fire automatically on power-source
changes via KDE PowerDevil (the same screen where you set display idle timeouts).

## Requirements

- **2025 ASUS ROG Flow Z13 (GZ302)** — these are laptop-specific values
- Arch Linux / CachyOS with KDE Plasma 6
- AUR: [`z13ctl-bin`](https://github.com/dahui/z13ctl) (required)
- AUR: [`z13gui-bin`](https://github.com/dahui/z13gui) (optional — overlay drawer)
- `ryzen_smu` kernel module (optional — needed only for undervolt)
- [rog-z13-trackpad-fix](https://forgejo.fifthdread.com/Fifthdread/rog-z13-trackpad-fix) (optional — enables "Disable While Typing")

## Install

```bash
git clone ssh://git@forgejo.fifthdread.com:223/Fifthdread/rog-z13-power-management.git
cd rog-z13-power-management
./install.sh
```

The installer:
1. Checks dependencies (`z13ctl`, `z13gui`, `ryzen_smu`, `users` group)
2. Copies the 7 scripts to `~/.local/bin`
3. Runs `sudo z13ctl setup` (udev rules + sysfs permission service) if needed
4. Enables the `z13ctl` daemon + socket (and `z13gui` if present)
5. Deploys `kde/powerdevilrc` to `~/.config/powerdevilrc` (backing up yours)
6. Reminds you of the manual steps below

Then **log out and back in**, and verify:

```bash
z13status
```

## Manual steps (KDE GUI)

1. **Log out / back in** after group changes (`users` group for device access).
2. **System Settings → Power Management** — the three "Run Script" actions
   (AC / Battery / Low Battery) should be present. If not, add them:
   - AC: `~/.local/bin/z13performance`
   - Battery: `~/.local/bin/z13balanced`
   - Low Battery: `~/.local/bin/z13silent`
3. **(Optional) Meta+B overlay toggle** — toggles the z13gui overlay drawer.
   Requires `z13gui-bin`. Add a panel button or global shortcut that runs
   `~/.local/bin/z13toggle.sh`.

## Caveats

- **Undervolt is silicon lottery.** `-20`/`-25` mV worked on one unit; if the
  bud's Z13 is unstable (crashes under load), raise or remove the undervolt
  lines in `scripts/z13silent` and `scripts/z13lowpower`.
- **Don't use z13ctl's built-in autoswitch.** `z13ctl autoswitch` and KDE
  PowerDevil would both fire on power changes and race each other. Pick one —
  this repo uses PowerDevil, so leave autoswitch off:
  `z13ctl autoswitch --clear`
- **Don't set KDE's own per-state power profiles** (System Settings → Power
  Management → "Performance"). PowerDevil would then write `platform_profile`
  directly and fight the scripts.
- The `z13max` / `z13lowpower` scripts are manual (run them from a terminal or
  shortcut) — they are not wired into any power state.
- Requires the z13ctl **daemon** running for TDP/fancurve/undervolt persistence.
  `install.sh` enables it; check with `systemctl --user status z13ctl`.

## Project layout

```
├── install.sh           # one-shot installer (deps, units, config deploy)
├── scripts/             # z13 profile scripts (installed to ~/.local/bin)
│   ├── z13balanced      #   balanced profile, 52/71/70 TDP
│   ├── z13performance   #   performance, 75/93/93 TDP
│   ├── z13max           #   performance, 93W forced
│   ├── z13silent        #   quiet, 20/40/40 TDP, -20mV
│   ├── z13lowpower      #   quiet, 5W TDP, -25mV
│   ├── z13status        #   current profile/TDP/fancurve/UV
│   └── z13toggle.sh     #   toggle z13gui overlay service (needs z13gui)
└── kde/
    └── powerdevilrc     # PowerDevil config template (%HOME% substituted)
```

## Credits

- [z13ctl](https://github.com/dahui/z13ctl) — system control for the Z13
- [z13gui](https://github.com/dahui/z13gui) — GTK4 overlay drawer
