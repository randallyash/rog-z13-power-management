#!/bin/bash
#
# install.sh — ROG Flow Z13 power management setup
#
# Installs the z13-power profile manager, the z13-power-service tray/watcher
# (which owns all power profile switching) and the z13-power-settings window
# (lighting, fan curve, battery, power). Hardware control ships in
# service/z13_power_hw.py and writes the Ryzen SMU directly. z13ctl is not
# required; its user daemon is masked if it is installed.
# On KDE Plasma it also deploys the PowerDevil display settings; other
# desktops (Hyprland, etc.) manage display/DPMS themselves and are skipped.
#
# Requirements:
#   - 2025 ASUS ROG Flow Z13 (GZ302)
#   - Arch Linux / CachyOS (KDE Plasma 6, Hyprland, etc.)
#   - ryzen_smu kernel module (required for SMU power limits and undervolt)
#   - The rog-z13-trackpad-fix project for the touchpad DWT fix (optional)
#   - Non-KDE Wayland: a system tray host (SNI) + notification daemon for the
#     tray icon and popups (Omarchy/Hyprland setups usually have both)
#
# Usage:  ./install.sh
# Some steps prompt for sudo (udev rules and the share directory).

set -euo pipefail

INFO()  { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
OK()    { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
WARN()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
ERR()   { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; exit 1; }

# ── 0. Sanity checks ──────────────────────────────────────────────────────────
[[ -n "${HOME:-}" ]] || ERR "Cannot determine HOME (are you root? run as your user)."
[[ -e /proc/driver/version || -r /sys/class/power_supply ]] || ERR "This must run on the Z13 itself (no sysfs access)."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/service/z13_power_hw.py" ]]; then
  ERR "service/z13_power_hw.py is missing — this tree is incomplete."
fi
OK "built-in hardware controller: service/z13_power_hw.py"


# Optional: ryzen_smu (needed for undervolt; z13-power skips it gracefully).
if ! grep -qw ryzen_smu_drv /proc/modules 2>/dev/null; then
  WARN "ryzen_smu kernel module not loaded — TDP below the armoury floor and undervolt will not apply."
  WARN "Install/load it: e.g. paru -S ryzen_smu-dkms-git"
fi

# Optional: 'users' group membership (udev rules grant device access to this group).
if ! id -nG | tr ' ' '\n' | grep -qw users; then
  WARN "You are not in the 'users' group. Device nodes are often group-writable for it."
  WARN "  Run: sudo usermod -aG users \"$USER\"   then log out and back in."
fi

# ── 1. Install the profile manager + tray service ─────────────────────────────
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

install_runtime() {
  local dest="$1"
  mkdir -p "$dest"
  install -m755 "$SCRIPT_DIR/scripts/z13-power" "$dest/z13-power"
  install -m755 "$SCRIPT_DIR/service/z13-power-service" "$dest/z13-power-service"
  install -m755 "$SCRIPT_DIR/service/z13-power-settings" "$dest/z13-power-settings"
  install -m755 "$SCRIPT_DIR/service/z13-power-overlay" "$dest/z13-power-overlay"
  install -m644 "$SCRIPT_DIR/service/z13_power_theme.py" "$dest/z13_power_theme.py"
  install -m644 "$SCRIPT_DIR/service/z13_power_common.py" "$dest/z13_power_common.py"
  install -m644 "$SCRIPT_DIR/service/z13_power_io.py" "$dest/z13_power_io.py"
  install -m644 "$SCRIPT_DIR/service/z13_power_hw.py" "$dest/z13_power_hw.py"
}

install_runtime "$BIN_DIR"
OK "Installed z13-power runtime to $BIN_DIR"
# Never copy only the CLI into a packaged prefix — that split is how
# Settings lost lottery (flyout opens /usr/share, tray ran ~/.local).
SHARE=/usr/share/z13-power-management
if [[ -d "$SHARE" ]]; then
  if [[ -w "$SHARE" ]]; then
    install_runtime "$SHARE"
    OK "Replaced packaged runtime at $SHARE (same files as $BIN_DIR)"
  else
    WARN "Packaged runtime at $SHARE is not writable; PATH prefers /usr/bin."
    WARN "To unify onto one tree: sudo install -d $SHARE && sudo $0"
  fi
fi

if ! python3 -c "import PyQt6, pyudev" >/dev/null 2>&1; then
  WARN "z13-power-service needs python-pyqt6 + pyudev — install: paru -S python-pyqt6 python-pyudev"
fi
if ! command -v notify-send >/dev/null 2>&1; then
  WARN "z13-power-service notifications need notify-send (libnotify)"
fi

UNIT_DIR="$HOME/.config/systemd/user"
if [[ -w "${SHARE:-/usr/share/z13-power-management}" ]]; then
  # Packaged unit ExecStart=/usr/bin/z13-power-service — do not shadow it.
  rm -f "$UNIT_DIR/z13-power-service.service"
  rm -f "$UNIT_DIR/z13-power-service.service.d/override.conf"
  systemctl --user daemon-reload
  systemctl --user enable --now z13-power-service.service 2>/dev/null || \
    WARN "Could not enable z13-power-service — start it with: systemctl --user start z13-power-service"
  OK "Enabled packaged z13-power-service (/usr/bin, not ~/.local)"
else
  mkdir -p "$UNIT_DIR"
  sed "s|/usr/bin/z13-power-service|$BIN_DIR/z13-power-service|" \
    "$SCRIPT_DIR/service/z13-power-service.service" > "$UNIT_DIR/z13-power-service.service"
  systemctl --user daemon-reload
  systemctl --user enable --now z13-power-service.service 2>/dev/null || \
    WARN "Could not enable z13-power-service — start it with: systemctl --user start z13-power-service"
  OK "Enabled z13-power-service (tray icon + power watcher) from $BIN_DIR"
fi

cp "$SCRIPT_DIR/scripts/z13-power-omarchy-setup" "$BIN_DIR/z13-power-omarchy-setup"
chmod +x "$BIN_DIR/z13-power-omarchy-setup"
if [[ -d "$HOME/.config/omarchy" ]]; then
  INFO "Omarchy detected — installing z13.power into the battery flyout (not your whole bar)"
  if python3 "$BIN_DIR/z13-power-omarchy-setup"; then
    OK "Omarchy power slot is z13.power (stock omarchy.power left disabled)"
  else
    WARN "Omarchy setup failed — bolt tray still works; re-run: z13-power-omarchy-setup"
  fi
fi

# ── 2. z13ctl device permissions (udev rules + perms service) ─────────────────
if [[ -f /etc/udev/rules.d/99-z13ctl.rules || -f /etc/udev/rules.d/99-z13-power.rules ]]; then
  OK "udev rules already present"
else
  WARN "No z13 udev rules found. Sysfs writes may need root until rules are installed."
fi

# Armoury firmware-attributes PPT — the APU obeys these, not only WMI ppt_*.
ARMOURY_PPT_RULE="$SCRIPT_DIR/contrib/udev/99-z13-power-armoury-ppt.rules"
if [[ -f "$ARMOURY_PPT_RULE" ]]; then
  sudo cp "$ARMOURY_PPT_RULE" /etc/udev/rules.d/99-z13-power-armoury-ppt.rules
  sudo udevadm control --reload-rules || true
  for a in ppt_pl1_spl ppt_pl2_sppt ppt_pl3_fppt; do
    f="/sys/class/firmware-attributes/asus-armoury/attributes/$a/current_value"
    [[ -e "$f" ]] || continue
    sudo chgrp users "$f" 2>/dev/null || true
    sudo chmod g+w "$f" 2>/dev/null || true
  done
  OK "Armoury PPT sysfs writable for users (Quiet/TDP actually take effect)"
fi

# ── 2b. ryzen_smu: headers for THIS kernel + DKMS module ──────────────────────
if [[ -x "$BIN_DIR/z13-power" ]]; then
  INFO "Setting up undervolt (kernel headers for $(uname -r) + ryzen_smu)..."
  "$BIN_DIR/z13-power" setup-undervolt || \
    WARN "setup-undervolt failed — Tweaks slider will save; re-run: z13-power setup-undervolt"
fi

# ── 3. Upstream z13ctl daemon fights these writes. Leave it off. ─────────────
systemctl --user mask --now z13ctl.socket z13ctl.service 2>/dev/null || true
OK "Upstream z13ctl user daemon masked (z13-power owns the hardware)"

# ── 4. Touchpad DWT fix (optional, from rog-z13-trackpad-fix) ────────────────
if [[ ! -f /etc/udev/rules.d/99-rog-z13-touchpad.rules ]]; then
  WARN "Touchpad DWT fix not installed. To enable 'Disable While Typing' on your"
  WARN "  desktop, install the companion project: git clone ssh://git@forgejo.fifthdread.com:223/Fifthdread/rog-z13-trackpad-fix.git"
  WARN "  then: sudo ./fix-rog-z13-trackpad.sh"
else
  OK "Touchpad DWT fix already present"
fi

# ── 5. Deploy PowerDevil display settings (KDE Plasma only) ───────────────────
DE="${XDG_CURRENT_DESKTOP:-} ${XDG_SESSION_DESKTOP:-}"
case "$DE" in
  *[Kk][Dd][Ee]*|*[Pp]lasma*)
    if [[ -d "$HOME/.config" ]]; then
      TARGET="$HOME/.config/powerdevilrc"
      if [[ -f "$TARGET" ]]; then
        cp "$TARGET" "$TARGET.bak.$(date +%Y%m%d%H%M%S)"
        OK "Backed up existing $TARGET"
      fi
      cp "$SCRIPT_DIR/kde/powerdevilrc" "$TARGET"
      OK "Deployed KDE PowerDevil display settings to $TARGET"
    else
      ERR "No ~/.config directory — this needs to run as your normal desktop user."
    fi
    ;;
  *)
    INFO "Not KDE Plasma ($DE) — skipping PowerDevil display settings."
    INFO "  Display/DPMS is handled by your desktop (e.g. hypridle on Hyprland)."
    ;;
esac

# ── 6. Manual step reminders ──────────────────────────────────────────────────
cat <<'EOF'

=== DONE ===

Remaining manual steps:
  1. If you're in the 'users' group (or were just added), log out and back in.
  2. The tray icon should be in the system tray — click it to switch profiles.
     Profile switching (AC -> performance, battery -> balanced, low -> silent)
     is handled automatically by z13-power-service.
   3. (Optional) The Meta+B panel button runs: z13-power settings
     to open the settings window (lighting, fan curve, battery, power). On
     non-KDE desktops, bind that command to a key/combo of your choice.
   4. Non-KDE Wayland (Hyprland/Omarchy): the tray icon needs an SNI-capable
     system tray and popups need a notification daemon — most setups (incl.
     Omarchy) ship both. Confirm the tray icon appears; if not, add a tray host.

To verify: run  z13-power status
EOF
