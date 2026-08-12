#!/bin/bash
#
# install.sh — ROG Flow Z13 power management setup
#
# Installs the z13-power profile manager, enables the z13ctl daemon stack,
# and deploys the KDE PowerDevil automation (AC/Battery/LowBattery -> modes).
#
# Requirements:
#   - 2025 ASUS ROG Flow Z13 (GZ302)
#   - Arch Linux / CachyOS with KDE Plasma 6
#   - AUR packages: z13ctl-bin (required), z13gui-bin (optional)
#   - ryzen_smu kernel module for undervolt support (optional)
#   - The rog-z13-trackpad-fix project for the touchpad DWT fix (optional)
#
# Usage:  ./install.sh
# Some steps prompt for sudo (z13ctl setup writes udev rules + system unit).

set -euo pipefail

INFO()  { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
OK()    { printf '\033[1;32m[ OK ]\033[0m %s\n' "$*"; }
WARN()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
ERR()   { printf '\033[1;31m[FAIL]\033[0m %s\n' "$*"; exit 1; }

# ── 0. Sanity checks ──────────────────────────────────────────────────────────
[[ -n "${HOME:-}" ]] || ERR "Cannot determine HOME (are you root? run as your user)."
[[ -e /proc/driver/version || -r /sys/class/power_supply ]] || ERR "This must run on the Z13 itself (no sysfs access)."

# z13ctl is a hard dependency.
if ! command -v z13ctl >/dev/null 2>&1; then
  ERR "z13ctl not found. Install it first: paru -S z13ctl-bin  (AUR, github.com/dahui/z13ctl)"
fi
OK "z13ctl found: $(z13ctl --version | head -1)"

# Optional: z13gui (overlay drawer). Needed only for the Meta+B toggle button.
GUI_INSTALLED=false
if systemctl --user list-unit-files z13gui.service >/dev/null 2>&1 && systemctl --user list-unit-files z13gui.service | grep -q z13gui; then
  GUI_INSTALLED=true
  OK "z13gui service unit present (optional overlay drawer)"
else
  WARN "z13gui not found. Optional: paru -S z13gui-bin  (needed only for the Meta+B overlay toggle)"
fi

# Optional: ryzen_smu (needed for undervolt; z13-power skips it gracefully).
if ! grep -qw ryzen_smu_drv /proc/modules 2>/dev/null; then
  WARN "ryzen_smu kernel module not loaded — undervolt modes will skip the UV step."
  WARN "Install/load it if you want undervolt: e.g. paru -S ryzen_smu-dkms-git"
fi

# Optional: 'users' group membership (z13ctl setup grants device access to this group).
if ! id -nG | tr ' ' '\n' | grep -qw users; then
  WARN "You are not in the 'users' group. z13ctl grants device access to that group."
  WARN "  Run: sudo usermod -aG users \"$USER\"   then log out and back in."
fi

# ── 1. Install the profile manager ─────────────────────────────────────────────
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/scripts/z13-power" "$BIN_DIR/z13-power"
chmod +x "$BIN_DIR/z13-power"
OK "Installed z13-power to $BIN_DIR"

# ── 2. z13ctl device permissions (udev rules + perms service) ─────────────────
if [[ ! -f /etc/udev/rules.d/99-z13ctl.rules ]]; then
  INFO "Running 'sudo z13ctl setup' to install udev rules + z13ctl-perms.service..."
  sudo z13ctl setup || WARN "z13ctl setup failed — you can re-run it later with: sudo z13ctl setup"
else
  OK "z13ctl udev rules already present"
fi

# ── 3. Enable the daemon stack ────────────────────────────────────────────────
systemctl --user enable --now z13ctl.socket z13ctl.service 2>/dev/null || \
  WARN "Could not enable z13ctl user units — are they installed (z13ctl setup)?"
if [[ "$GUI_INSTALLED" == true ]]; then
  systemctl --user enable --now z13gui.service 2>/dev/null || WARN "Could not enable z13gui.service"
fi

# ── 4. Touchpad DWT fix (optional, from rog-z13-trackpad-fix) ────────────────
if [[ ! -f /etc/udev/rules.d/99-rog-z13-touchpad.rules ]]; then
  WARN "Touchpad DWT fix not installed. To enable 'Disable While Typing' in KDE,"
  WARN "  install the companion project: git clone ssh://git@forgejo.fifthdread.com:223/Fifthdread/rog-z13-trackpad-fix.git"
  WARN "  then: sudo ./fix-rog-z13-trackpad.sh"
else
  OK "Touchpad DWT fix already present"
fi

# ── 5. Deploy KDE PowerDevil automation ───────────────────────────────────────
if [[ -d "$HOME/.config" ]]; then
  TARGET="$HOME/.config/powerdevilrc"
  if [[ -f "$TARGET" ]]; then
    cp "$TARGET" "$TARGET.bak.$(date +%Y%m%d%H%M%S)"
    OK "Backed up existing $TARGET"
  fi
  sed "s|%BIN%|$BIN_DIR|g" "$SCRIPT_DIR/kde/powerdevilrc" > "$TARGET"
  OK "Deployed KDE PowerDevil automation to $TARGET"
  INFO "  AC          -> z13-power performance"
  INFO "  Battery     -> z13-power balanced"
  INFO "  Low Battery -> z13-power silent"
else
  ERR "No ~/.config directory — this needs to run as your normal desktop user."
fi

# ── 6. Manual step reminders ──────────────────────────────────────────────────
cat <<'EOF'

=== DONE ===

Remaining manual steps (KDE GUI):
  1. If you're in the 'users' group (or were just added), log out and back in.
  2. System Settings -> Power Management -> verify the three "Run Script"
     actions under AC / Battery / Low Battery profiles.
  3. (Optional) For the Meta+B overlay toggle button: add a global shortcut
     or panel button that runs  ~/.local/bin/z13-power toggle  (requires z13gui).

To verify: run  ~/.local/bin/z13-power status
EOF
