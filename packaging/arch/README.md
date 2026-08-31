# Arch package (`z13-power-git`)

Build from this checkout after cloning the GitHub repo:

```bash
cd packaging/arch/z13-power-git
makepkg -si
```

`makepkg` clones `main` from GitHub, so the GitHub remote must already exist.
Dependencies (`z13ctl-bin`, PyQt6, pyudev, libnotify, python-dbus-next) are
pulled by pacman. The install hook enables and starts the tray service.

The PKGBUILD is the same layout as Fifthdread's `pkgbuilds` repo, with the
source URL pointed at this GitHub copy.
