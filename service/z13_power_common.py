#!/usr/bin/env python3
#
# Shared paths and helpers for z13-power-service and z13-power-settings.
# Loaded from beside the script, /usr/share/z13-power-management, or
# ~/.local/bin — same lookup as z13_power_theme.py.

import array
import configparser
import fcntl
import glob
import io
import os
import sys

from z13_power_io import (
    IoError,
    Z13CTL_TIMEOUT,
    bounded_text,
    run_helper,
    sys_read,
    sys_write,
    write_user_file,
    read_user_file,
)

CONFIG_PATH = os.path.expanduser("~/.config/z13-power/service.conf")
LIGHTING_PATH = os.path.expanduser("~/.config/z13-power/lighting.conf")
BATTERY_PATH = os.path.expanduser("~/.config/z13-power/battery.conf")
TWEAKS_PATH = os.path.expanduser("~/.config/z13-power/tweaks.conf")
CUSTOM_TDP_MIN = 5
CUSTOM_TDP_MAX = 93
CUSTOM_TDP_DEFAULT = 75
CHARGE_LIMIT_PATH = "/sys/class/power_supply/BAT0/charge_control_end_threshold"
STATE_DIR = os.path.expanduser("~/.local/state/z13-power")
STATUS_PATH = os.path.join(STATE_DIR, "status.json")
# Capacity at which a fill-to-100 one-shot is done (some packs never report 100).
FILL_DONE_CAPACITY = 99

_ac_online_path = None
_bat_capacity_path = None


# Flow Z13 dock keyboard (GZ302EA-Keyboard).
_TABLET_KBD_VID = "0b05"
_TABLET_KBD_PID = "1a30"
# Linux input.h: EV_SW, SW_TABLET_MODE
_EV_SW = 0x05
_SW_TABLET_MODE = 0x01


def _ioc_read(typ, nr, size):
    return (2 << 30) | (size << 16) | (ord(typ) << 8) | nr


def _is_gz302():
    try:
        with open("/sys/class/dmi/id/product_name", encoding="utf-8") as fh:
            name = fh.read()
    except OSError:
        return False
    return "GZ302" in name or "Flow Z13" in name


def external_display_connected():
    """True when an external DRM sink is connected (HDMI / USB-C DP). eDP ignored."""
    try:
        names = os.listdir("/sys/class/drm")
    except OSError:
        return False
    for name in names:
        lower = name.lower()
        if "edp" in lower or "writeback" in lower:
            continue
        if not any(tag in lower for tag in ("hdmi", "dp-", "displayport", "dvi")):
            continue
        path = os.path.join("/sys/class/drm", name, "status")
        try:
            with open(path, encoding="ascii") as fh:
                if fh.read().strip() == "connected":
                    return True
        except OSError:
            continue
    return False


def usb_dock_keyboard_present():
    """True if the ASUS GZ302 dock keyboard (0b05:1a30) is enumerated."""
    try:
        names = os.listdir("/sys/bus/usb/devices")
    except OSError:
        return False
    for name in names:
        base = os.path.join("/sys/bus/usb/devices", name)
        try:
            with open(os.path.join(base, "idVendor"), encoding="ascii") as fh:
                vid = fh.read().strip()
            with open(os.path.join(base, "idProduct"), encoding="ascii") as fh:
                pid = fh.read().strip()
        except OSError:
            continue
        if vid == _TABLET_KBD_VID and pid == _TABLET_KBD_PID:
            return True
    return False


def _sw_tablet_mode():
    """SW_TABLET_MODE on Asus WMI (True tablet, False laptop, None unknown)."""
    eviocgname = _ioc_read("E", 0x06, 256)
    eviocgbit0 = _ioc_read("E", 0x20, 8)
    eviocgbitsw = _ioc_read("E", 0x20 + _EV_SW, 16)
    eviocgsw = _ioc_read("E", 0x1b, 16)
    found = None
    for path in glob.glob("/dev/input/event*"):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            namebuf = array.array("B", [0] * 256)
            try:
                fcntl.ioctl(fd, eviocgname, namebuf)
            except OSError:
                continue
            name = bytes(namebuf).split(b"\x00", 1)[0].decode("utf-8", "replace")
            evbits = array.array("B", [0] * 8)
            try:
                fcntl.ioctl(fd, eviocgbit0, evbits)
            except OSError:
                continue
            if not (evbits[0] & (1 << _EV_SW)):
                continue
            swbits = array.array("B", [0] * 16)
            try:
                fcntl.ioctl(fd, eviocgbitsw, swbits)
            except OSError:
                continue
            byte, bit = divmod(_SW_TABLET_MODE, 8)
            if byte >= len(swbits) or not (swbits[byte] & (1 << bit)):
                continue
            swstate = array.array("B", [0] * 16)
            try:
                fcntl.ioctl(fd, eviocgsw, swstate)
            except OSError:
                continue
            val = bool(swstate[byte] & (1 << bit))
            # Prefer the Asus WMI switch when several devices exist.
            if "asus" in name.lower() or "wmi" in name.lower():
                return val
            found = val
        finally:
            os.close(fd)
    return found


def read_tablet():
    """True for handheld tablet posture that should latch Quiet.

    Hinge SW_TABLET_MODE or a missing dock keyboard is a tablet *pose*.
    An external display (TV / USB-C dock) means it is a living-room
    machine and must keep high power — keyboard-off-to-the-TV is not Quiet.
    Other machines return False. ioctl-only for SW_TABLET_MODE so the
    compositor still gets rotation events.
    """
    if not _is_gz302():
        return False
    sw = _sw_tablet_mode()
    kbd = usb_dock_keyboard_present()
    posed = (sw is True) or (not kbd)
    if not posed:
        return False
    if external_display_connected():
        return False
    return True


def clamp_custom_tdp(watts):
    try:
        n = int(watts)
    except (TypeError, ValueError):
        return CUSTOM_TDP_DEFAULT
    return max(CUSTOM_TDP_MIN, min(CUSTOM_TDP_MAX, n))


def load_tweaks_conf():
    """Return the [tweaks] dict (undervolt, custom_tdp, …)."""
    out = {}
    text = bounded_text(read_user_file([".config", "z13-power"], "tweaks.conf"))
    if text is None:
        return out
    cfg = configparser.ConfigParser()
    try:
        cfg.read_string(text)
    except (configparser.Error, ValueError):
        return out
    if not cfg.has_section("tweaks"):
        return out
    for key in cfg.options("tweaks"):
        out[key] = cfg.get("tweaks", key).strip()
    return out


def save_tweaks_conf(updates):
    """Merge keys into tweaks.conf without dropping the others."""
    cur = load_tweaks_conf()
    cur.update(updates)
    cfg = configparser.ConfigParser()
    cfg.add_section("tweaks")
    for key, val in cur.items():
        if val is None or val == "":
            continue
        cfg.set("tweaks", key, str(val))
    buf = io.StringIO()
    cfg.write(buf)
    try:
        write_user_file([".config", "z13-power"], "tweaks.conf",
                        buf.getvalue().encode("utf-8"))
    except (IoError, OSError):
        return


def load_custom_tdp():
    raw = load_tweaks_conf().get("custom_tdp")
    if raw is None or raw == "":
        return CUSTOM_TDP_DEFAULT
    return clamp_custom_tdp(raw)


def save_custom_tdp(watts):
    watts = clamp_custom_tdp(watts)
    if load_custom_tdp() == watts:
        return watts
    save_tweaks_conf({"custom_tdp": str(watts)})
    return watts


def custom_mode_def(watts):
    """Recipe for the Custom pill: PL1=PL2=PL3=watts, 5–93."""
    w = clamp_custom_tdp(watts)
    if w <= 5:
        return {
            "profile": "quiet", "tdp": "5", "tdp_force": "false",
            "fancurve": "reset", "undervolt": "reset",
        }
    if w < 75:
        return {
            "profile": "balanced", "tdp": f"{w} {w} {w}",
            "tdp_force": "false", "fancurve": "reset", "undervolt": "reset",
        }
    md = {
        "profile": "performance",
        "tdp": str(w) if w > 75 else f"{w} {w} {w}",
        "tdp_force": "true" if w > 75 else "false",
        "undervolt": "reset",
    }
    if w <= 75:
        md["fancurve"] = "reset"
    return md


def runtime_dir():
    """Directory that holds a complete z13-power runtime (settings + common)."""
    here = os.path.dirname(os.path.realpath(__file__))
    for path in (here, "/usr/share/z13-power-management",
                 os.path.expanduser("~/.local/bin")):
        if (os.access(os.path.join(path, "z13-power-settings"), os.X_OK)
                and os.path.isfile(os.path.join(path, "z13_power_common.py"))):
            return path
    return None


def theme_mod():
    """Load z13_power_theme from beside this file, share dir, or ~/.local/bin."""
    here = os.path.dirname(os.path.realpath(__file__))
    for path in (here, "/usr/share/z13-power-management",
                 os.path.expanduser("~/.local/bin")):
        if os.path.isfile(os.path.join(path, "z13_power_theme.py")):
            if path not in sys.path:
                sys.path.insert(0, path)
            break
    import z13_power_theme
    return z13_power_theme


Z13CTL_BIN = "/usr/bin/z13ctl"


def z13ctl(args, timeout=Z13CTL_TIMEOUT):
    """Run a z13ctl command; return the CompletedProcess or None."""
    return run_helper(["z13ctl", *args], timeout=min(max(timeout, 0.1), Z13CTL_TIMEOUT))


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
        if not sys_write(path, str(int(val))):
            ok = False
    return ok


def read_wmi_pl1():
    raw = sys_read(os.path.join(WMI_PPT_DIR, "ppt_pl1_spl"))
    try:
        return int(raw) if raw is not None else None
    except ValueError:
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
        sys_write(path, str(val))
        run_helper(["asusctl", "armoury", "set", name, str(val)], timeout=5.0)



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


def _ucsi_pd_online():
    """True when a USB-C PD source port reports online.

    The ASUS EC keeps the mains indicator (AC0) offline for generic
    USB-C PD chargers - power flows but the platform never sees "mains".
    The ucsi source PSUs are the only signal that the machine is
    actually plugged in on such chargers.
    """
    try:
        names = os.listdir("/sys/class/power_supply")
    except OSError:
        return False
    for d in names:
        if not d.startswith("ucsi-source-psy"):
            continue
        raw = sys_read(os.path.join("/sys/class/power_supply", d, "online"))
        if raw == "1":
            return True
    return False


def read_power():
    """Return (ac_online: bool, capacity: int|None)."""
    global _ac_online_path, _bat_capacity_path
    if _ac_online_path is None and _bat_capacity_path is None:
        _discover_power_paths()
    ac = False
    capacity = None
    if _ac_online_path:
        raw = sys_read(_ac_online_path)
        if raw is None:
            _discover_power_paths()
            raw = sys_read(_ac_online_path) if _ac_online_path else None
        ac = raw == "1"
    if not ac:
        # Generic USB-C PD chargers: EC mains stays offline, ucsi tells the truth.
        ac = _ucsi_pd_online()
    if _bat_capacity_path:
        raw = sys_read(_bat_capacity_path)
        if raw is None:
            _discover_power_paths()
            raw = sys_read(_bat_capacity_path) if _bat_capacity_path else None
        try:
            capacity = int(raw) if raw is not None else None
        except ValueError:
            capacity = None
    return ac, capacity


def load_battery_conf():
    """Return (saved charge_limit or None, fill_once bool)."""
    text = bounded_text(read_user_file([".config", "z13-power"], "battery.conf"))
    if text is None:
        return None, False
    cfg = configparser.ConfigParser()
    try:
        cfg.read_string(text)
    except (configparser.Error, ValueError):
        return None, False
    limit = None
    fill_once = False
    if cfg.has_section("battery"):
        try:
            limit = int(cfg.get("battery", "charge_limit").strip()[:8])
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
    """Update battery.conf keys without wiping the others."""
    cur_limit, cur_fill = load_battery_conf()
    if limit is None:
        limit = cur_limit
    if fill_once is None:
        fill_once = cur_fill
    cfg = configparser.ConfigParser()
    cfg.add_section("battery")
    if limit is not None:
        cfg.set("battery", "charge_limit", str(int(limit)))
    cfg.set("battery", "fill_once", "true" if fill_once else "false")
    buf = io.StringIO()
    cfg.write(buf)
    body = buf.getvalue().encode("utf-8")
    try:
        write_user_file([".config", "z13-power"], "battery.conf", body)
    except (IoError, OSError):
        return


def load_charge_limit():
    limit, _ = load_battery_conf()
    return limit


def load_fill_once():
    return load_battery_conf()[1]


def save_charge_limit(val):
    save_battery_conf(limit=val)


def read_charge_threshold():
    raw = sys_read(CHARGE_LIMIT_PATH)
    try:
        return int(raw) if raw is not None else None
    except ValueError:
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
    if sys_write(CHARGE_LIMIT_PATH, str(limit)):
        return True
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
