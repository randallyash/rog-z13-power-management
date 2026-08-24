# Omarchy integration

Same z13-power repo. KDE / Cachy without Omarchy never load this.

## Packaged plugins

- `z13.power` — Omarchy **battery** bar widget with our Max/Perf/Mid/Silent/Low
  pills, Automatic, and Lock (`embedInPowerPanel`). Replaces the `omarchy.power`
  **slot only** — not the rest of the bar.
- `z13.battery` — low-battery warnings; skips `omarchy-powerprofiles-set` when
  `status.json` exists so plug/unplug is ours.

`z13-power-omarchy-setup` (run from `install.sh` on Omarchy) copies those
into `~/.config/omarchy/plugins/` and points the existing power slot at
`z13.power`. Idempotent. Does **not** copy anyone’s clock/music/layout.

Stock `/usr/share/omarchy` is never edited. `omarchy update` does not
delete the user plugins. `omarchy refresh shell` can put `omarchy.power`
back; re-run `z13-power-omarchy-setup`.

The SNI bolt is Passive / hidden while `z13.power` (or `ramzal.power`) is
on the bar. Other desktops still show the bolt.

## Manual

```bash
z13-power-omarchy-setup
omarchy restart shell
```
