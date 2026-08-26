#!/usr/bin/env python3
#
# Shared paths and helpers for z13-power-service and z13-power-settings.
# Loaded from beside the script, /usr/share/z13-power-management, or
# ~/.local/bin — same lookup as z13_power_theme.py.

import configparser
import os
import shutil
import subprocess
import sys

CONFIG_PATH = os.path.expanduser("~/.config/z13-power/service.conf")
LIGHTING_PATH = os.path.expanduser("~/.config/z13-power/lighting.conf")
BATTERY_PATH = os.path.expanduser("~/.config/z13-power/battery.conf")
TWEAKS_PATH = os.path.expanduser("~/.config/z13-power/tweaks.conf")
CHARGE_LIMIT_PATH = "/sys/class/power_supply/BAT0/charge_control_end_threshold"
STATE_DIR = os.path.expanduser("~/.local/state/z13-power")
STATUS_PATH = os.path.join(STATE_DIR, "status.json")
# Capacity at which a fill-to-100 one-shot is done (some packs never report 100).
FILL_DONE_CAPACITY = 99

_ac_online_path = None
_bat_capacity_path = None


def theme_mod():
    """Load z13_power_theme from beside this file or the share dir."""
    here = os.path.dirname(os.path.realpath(__file__))
    for path in (here, "/usr/share/z13-power-management",
                 os.path.expanduser("~/.local/bin")):
        if os.path.isfile(os.path.join(path, "z13_power_theme.py")):
            if path not in sys.path:
                sys.path.insert(0, path)
            break
    import z13_power_theme
    return z13_power_theme


def z13ctl(args, timeout=30):
    """Run a z13ctl command; return the CompletedProcess or None."""
    try:
        return subprocess.run(["z13ctl", *args], capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def z13ctl_ok(args, timeout=30):
    r = z13ctl(args, timeout=timeout)
    return r is not None and r.returncode == 0


# GZ302E asus-armoury firmware-attributes range (BIOS). WMI ppt_* can be
# written lower, but the APU follows these. Quiet cannot go below PL1 28.
ARMOURY_PPT = {
    "ppt_pl1_spl": (28, 80),
    "ppt_pl2_sppt": (32, 92),
    "ppt_pl3_fppt": (45, 93),
}
ARMOURY_PPT_DIR = (
    "/sys/class/firmware-attributes/asus-armoury/attributes")
WMI_PPT_DIR = "/sys/devices/platform/asus-nb-wmi"
WMI_PPT_ATTRS = (
    "ppt_pl1_spl", "ppt_pl2_sppt", "ppt_fppt",
    "ppt_apu_sppt", "ppt_platform_sppt",
)


def write_wmi_ppt(pl1, pl2=None, pl3=None):
    """Lock asus-nb-wmi PPT, including APU/platform sPPT (no boost)."""
    try:
        pl1 = int(pl1)
    except (TypeError, ValueError):
        return False
    if pl2 is None:
        pl2 = pl1
    if pl3 is None:
        pl3 = pl1
    mapping = {
        "ppt_pl1_spl": pl1,
        "ppt_pl2_sppt": int(pl2),
        "ppt_fppt": int(pl3),
        "ppt_apu_sppt": int(pl2),
        "ppt_platform_sppt": int(pl2),
    }
    ok = True
    for name, val in mapping.items():
        path = os.path.join(WMI_PPT_DIR, name)
        try:
            with open(path, "w") as fh:
                fh.write(str(int(val)))
        except OSError:
            ok = False
    return ok


def read_wmi_pl1():
    try:
        with open(os.path.join(WMI_PPT_DIR, "ppt_pl1_spl")) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def write_armoury_ppt(pl1, pl2=None, pl3=None):
    """Write the PPT the SMU actually uses. Clamp to BIOS min/max.

    Raw sysfs is not enough: asusd caches Armoury defaults (60/75/86) and
    restores them. `asusctl armoury set` updates that cache. Fan curves stay
    BIOS auto — user curves on this GZ302 floor around 3400 RPM.
    """
    try:
        pl1 = int(pl1)
    except (TypeError, ValueError):
        return
    if pl2 is None:
        pl2 = pl1
    if pl3 is None:
        pl3 = pl1
    vals = {
        "ppt_pl1_spl": pl1,
        "ppt_pl2_sppt": int(pl2),
        "ppt_pl3_fppt": int(pl3),
    }
    for name, val in vals.items():
        lo, hi = ARMOURY_PPT[name]
        val = max(lo, min(hi, val))
        path = os.path.join(ARMOURY_PPT_DIR, name, "current_value")
        try:
            with open(path, "w") as fh:
                fh.write(str(val))
        except OSError:
            pass
        if shutil.which("asusctl"):
            subprocess.run(
                ["asusctl", "armoury", "set", name, str(val)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5)



def _discover_power_paths():
    """Resolve AC/battery sysfs files once; retry if a path disappears."""
    global _ac_online_path, _bat_capacity_path
    _ac_online_path = None
    _bat_capacity_path = None
    try:
        names = os.listdir("/sys/class/power_supply")
    except OSError:
        return
    for d in names:
        base = os.path.join("/sys/class/power_supply", d)
        if not os.path.isdir(base):
            continue
        if _ac_online_path is None and (
                d in ("AC", "ACAD", "AC0") or d.startswith("ADP")):
            path = os.path.join(base, "online")
            if os.path.isfile(path):
                _ac_online_path = path
        elif _bat_capacity_path is None and d.startswith("BAT"):
            path = os.path.join(base, "capacity")
            if os.path.isfile(path):
                _bat_capacity_path = path
        if _ac_online_path and _bat_capacity_path:
            return


def read_power():
    """Return (ac_online: bool, capacity: int|None)."""
    global _ac_online_path, _bat_capacity_path
    if _ac_online_path is None and _bat_capacity_path is None:
        _discover_power_paths()
    ac = False
    capacity = None
    if _ac_online_path:
        try:
            with open(_ac_online_path) as f:
                ac = f.read().strip() == "1"
        except OSError:
            _discover_power_paths()
            if _ac_online_path:
                try:
                    with open(_ac_online_path) as f:
                        ac = f.read().strip() == "1"
                except OSError:
                    pass
    if _bat_capacity_path:
        try:
            with open(_bat_capacity_path) as f:
                capacity = int(f.read().strip())
        except (OSError, ValueError):
            _discover_power_paths()
            if _bat_capacity_path:
                try:
                    with open(_bat_capacity_path) as f:
                        capacity = int(f.read().strip())
                except (OSError, ValueError):
                    pass
    return ac, capacity


def load_battery_conf():
    """Return (saved charge_limit or None, fill_once bool)."""
    cfg = configparser.ConfigParser()
    cfg.read(BATTERY_PATH)
    limit = None
    fill_once = False
    if cfg.has_section("battery"):
        try:
            limit = int(cfg.get("battery", "charge_limit").strip())
            if not (40 <= limit <= 100):
                limit = None
        except (configparser.Error, ValueError):
            limit = None
        try:
            fill_once = cfg.getboolean("battery", "fill_once")
        except (configparser.Error, ValueError):
            fill_once = False
    return limit, fill_once


def save_battery_conf(*, limit=None, fill_once=None):
    """Update battery.conf keys without wiping the others.

    In-place write so QML FileView keeps its inotify watch (os.replace
    drops the inode and the flyout tip goes stale).
    """
    cfg = configparser.ConfigParser()
    cfg.read(BATTERY_PATH)
    if not cfg.has_section("battery"):
        cfg.add_section("battery")
    if limit is not None:
        cfg.set("battery", "charge_limit", str(int(limit)))
    if fill_once is not None:
        cfg.set("battery", "fill_once", "true" if fill_once else "false")
    os.makedirs(os.path.dirname(BATTERY_PATH), exist_ok=True)
    with open(BATTERY_PATH, "w") as f:
        cfg.write(f)


def load_charge_limit():
    limit, _ = load_battery_conf()
    return limit


def load_fill_once():
    return load_battery_conf()[1]


def save_charge_limit(val):
    save_battery_conf(limit=val)


def read_charge_threshold():
    try:
        with open(CHARGE_LIMIT_PATH) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def write_charge_threshold(limit):
    if limit is None:
        return False
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return False
    if not (40 <= limit <= 100):
        return False
    if read_charge_threshold() == limit:
        return True
    try:
        with open(CHARGE_LIMIT_PATH, "w") as f:
            f.write(str(limit))
        return True
    except OSError:
        r = z13ctl(["batterylimit", "--set", str(limit)])
        return r is not None and r.returncode == 0


def apply_saved_charge_limit():
    """Re-apply the charge cap; ACPI does not keep it across reboot.

    A live fill-to-100 one-shot lifts the hardware cap to 100 until the pack
    is full or the charger is pulled. The saved charge_limit is unchanged.
    """
    limit, fill_once = load_battery_conf()
    if fill_once:
        ac, capacity = read_power()
        if ac and (capacity is None or capacity < FILL_DONE_CAPACITY):
            write_charge_threshold(100)
            return
        save_battery_conf(fill_once=False)
    if limit is None:
        return
    write_charge_threshold(limit)
