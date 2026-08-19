# Omarchy tray panel

`Z13PowerPanel.qml` is the right-click flyout used on Omarchy: same shape as
the stock battery / network / display panels (hero, stats, POWER PROFILE
pills, Automatic switch, Lock toggle).

It is not a standalone plugin. Drop the file into an Omarchy tray plugin
(for example a clone of `omarchy.tray`) and, when the activated item is
`z13-power`, open a `PopupCard` containing this panel instead of the
dbusmenu list.

The panel talks to `z13-power-service` through:

- `~/.local/state/z13-power/status.json` — live mode / AC / TDP
- `~/.local/state/z13-power/command.json` — `{ "op": "mode"|"automatic"|"lock", ... }`

Nerd Font glyphs above U+FFFF must be built with `String.fromCodePoint`.
QML `\Uxxxxxxxx` escapes are not valid and render as literal `U000f04c5`.
