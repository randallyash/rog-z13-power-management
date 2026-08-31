# Arch package (`z13-power-git`)

From a clone of this GitHub repo:

```bash
paru -S z13ctl-bin
cd packaging/arch/z13-power-git
makepkg -si
```

`makepkg` clones `main` from GitHub, then installs. Pacman pulls
`python-pyqt6`, `python-pyudev`, `libnotify`, and `python-dbus-next`.
`z13ctl-bin` is AUR, so install it first (or have an AUR helper resolve it).
The install hook enables and starts the tray service.
