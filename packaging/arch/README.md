# Arch package (`z13-power-git`)

From a clone of this GitHub repo:

```bash
cd packaging/arch/z13-power-git
makepkg -si
```

`makepkg` clones `main` from GitHub, then installs. Pacman pulls
`python-pyqt6`, `python-pyudev`, `libnotify`, and `python-dbus-next`.
`z13ctl-bin` is not a dependency. Power limits are written to the Ryzen
SMU by `z13_power_hw.py`. Quiet (20 W), Low (10 W), and undervolt also
need `ryzen_smu-dkms-git`. The install hook enables and starts the tray
service.
