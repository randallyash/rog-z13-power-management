#!/usr/bin/env python3
"""In-tree hardware control for the 2025 ROG Flow Z13 (GZ302).

This is the control path z13-power used to shell out to dahui/z13ctl for.
An upstream z13ctl release can change its TDP limits, its daemon, or its
install path and take both apps with it. Profiles, PPT, fan curves, charge
cap, lighting, Curve Optimizer, and the Armoury button are implemented here
and do not execute /usr/bin/z13ctl.

Lighting packets follow the Aura HID layout documented for this machine
(report 0x5d, keyboard zone 0, lightbar zone 1). Curve Optimizer uses the
Strix Halo MP1 command 0x4C through ryzen_smu, the same mailbox ryzenadj uses.
PPT uses MP1 stapm 0x14, fast 0x15, and slow 0x16, in milliwatts. asus-armoury
floors PL1 at 28 W; the SMU is what the package actually follows.
"""
from __future__ import annotations

import array
import fcntl
import glob
import os
import select
import struct
import subprocess
import threading
import time
from types import SimpleNamespace

from z13_power_io import sys_read, sys_write

VERSION = "1.2.0"

WMI_PPT = "/sys/devices/platform/asus-nb-wmi"
ARMOURY = "/sys/class/firmware-attributes/asus-armoury/attributes"
PROFILE_GLOB = "/sys/class/platform-profile/*/profile"
CHARGE_PATH = "/sys/class/power_supply/BAT0/charge_control_end_threshold"
SMU = "/sys/kernel/ryzen_smu_drv"
CO_STATE = os.path.expanduser("~/.local/state/z13-power/co")

# PL1 above this needs --force and a fan floor before the write.
TDP_SAFE = 75
TDP_ABS_MIN = 5
TDP_ABS_MAX = 93
HIGH_TDP_MIN_PWM = 127
HIGH_TDP_CURVE = (
    (30, 127), (40, 127), (50, 140), (60, 165),
    (65, 190), (70, 215), (75, 235), (80, 255),
)

# MP1 mailbox: set all-core Curve Optimizer. Encoding is 0x100000 - abs(mV).
SMU_CO_ALL = 0x4C
# RyzenAdj Strix Halo PPT. arg0 is milliwatts.
SMU_STAPM = 0x14
SMU_FAST = 0x15
SMU_SLOW = 0x16
SMU_OK = 0x01
# A 5 W request is stored, then the package keeps drawing about this much.
SMU_PACKAGE_FLOOR_W = 10

KB_VID, KB_PID = "0b05", "1a30"
BAR_VID, BAR_PID = "0b05", "18c6"
MODES = {
    "static": 0x00, "breathe": 0x01, "cycle": 0x02,
    "rainbow": 0x03, "strobe": 0x0A,
}
SPEEDS = {"slow": 0xE1, "normal": 0xEB, "fast": 0xF5}
BRIGHTNESS = {"off": 0, "low": 1, "medium": 2, "med": 2, "high": 3}
EV_KEY = 0x01
KEY_PROG3 = 202
HIDIOCGRDESCSIZE = 0x80044801
HIDIOCGRDESC = 0x90044802

_quiesced = False


def result(code: int, out: str = "", err: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=code, stdout=out, stderr=err if err.endswith("\n") or not err else err + "\n")


def quiesce_upstream() -> None:
    """Stop the upstream z13ctl user daemon so it cannot overwrite our writes.

    Socket activation would start it again on the next client, so the units
    are disabled too. Missing units are ignored.
    """
    global _quiesced
    if _quiesced:
        return
    _quiesced = True
    try:
        # Global enablement lives in /etc/systemd/user, so a user disable
        # does not stick. Masking this user stops the daemon from starting
        # on the next login and writing PPT back.
        subprocess.run(
            ["systemctl", "--user", "mask", "--now",
             "z13ctl.service", "z13ctl.socket"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _read_int(path: str):
    raw = sys_read(path)
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def _write_int(path: str, value: int) -> bool:
    return sys_write(path, str(int(value)) + "\n")


def _profile_path() -> str | None:
    matches = sorted(glob.glob(PROFILE_GLOB))
    return matches[0] if matches else None


def firmware_profile() -> str | None:
    path = _profile_path()
    if not path:
        return None
    raw = sys_read(path)
    return raw.strip() if raw else None


def _hwmon(name: str) -> str | None:
    try:
        entries = os.listdir("/sys/class/hwmon")
    except OSError:
        return None
    for entry in entries:
        base = os.path.join("/sys/class/hwmon", entry)
        if sys_read(os.path.join(base, "name")) == name:
            return base
    return None


def _armoury_range(attr: str):
    lo = _read_int(os.path.join(ARMOURY, attr, "min_value"))
    hi = _read_int(os.path.join(ARMOURY, attr, "max_value"))
    if lo is None or hi is None or lo > hi:
        return None
    return lo, hi


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def read_pl() -> tuple[int | None, int | None, int | None]:
    return (
        _read_int(os.path.join(WMI_PPT, "ppt_pl1_spl")),
        _read_int(os.path.join(WMI_PPT, "ppt_pl2_sppt")),
        _read_int(os.path.join(WMI_PPT, "ppt_fppt")),
    )


def write_tdp(pl1: int, pl2: int, pl3: int, *, force: bool) -> SimpleNamespace:
    if not (TDP_ABS_MIN <= pl1 <= TDP_ABS_MAX):
        return result(1, err=f"PL1 {pl1}W out of range {TDP_ABS_MIN}–{TDP_ABS_MAX}")
    for label, val in (("PL2", pl2), ("PL3", pl3)):
        if not (TDP_ABS_MIN <= val <= TDP_ABS_MAX):
            return result(1, err=f"{label} {val}W out of range {TDP_ABS_MIN}–{TDP_ABS_MAX}")
    if pl1 > TDP_SAFE and not force:
        return result(1, err=f"PL1 {pl1}W is above {TDP_SAFE}W; pass --force")
    quiesce_upstream()
    notes = []
    if pl1 > TDP_SAFE:
        if not _write_curve(HIGH_TDP_CURVE, enable=1):
            return result(1, err="refusing high TDP without the fan floor")
        notes.append(f"fan floor {HIGH_TDP_MIN_PWM} PWM")
    wmi = {
        "ppt_pl1_spl": pl1,
        "ppt_pl2_sppt": pl2,
        "ppt_fppt": pl3,
        "ppt_apu_sppt": pl2,
        "ppt_platform_sppt": pl2,
    }
    wmi_ok = True
    for name, val in wmi.items():
        path = os.path.join(WMI_PPT, name)
        if _read_int(path) is None and not os.path.exists(path):
            continue
        if not _write_int(path, val):
            wmi_ok = False
    armoury_map = {
        "ppt_pl1_spl": pl1,
        "ppt_pl2_sppt": pl2,
        "ppt_pl3_fppt": pl3,
    }
    armoury_ok = False
    for name, val in armoury_map.items():
        span = _armoury_range(name)
        path = os.path.join(ARMOURY, name, "current_value")
        if span is None:
            continue
        applied = _clamp(val, span[0], span[1])
        if applied != val:
            notes.append(f"armoury {name} clamped to {applied}W")
        current = _read_int(path)
        if current == applied:
            armoury_ok = True
            continue
        if _write_int(path, applied):
            armoury_ok = True
    if not wmi_ok and not armoury_ok:
        return result(1, err="PPT write failed")
    notes.extend(_smu_ppt(pl1, pl2, pl3))
    text = f"TDP {pl1}/{pl2}/{pl3}W"
    if notes:
        text += " (" + "; ".join(notes) + ")"
    return result(0, out=text + "\n")


def _curve_base() -> str | None:
    return _hwmon("asus_custom_fan_curve")


def _read_curve():
    base = _curve_base()
    if not base:
        return [], ""
    enable = sys_read(os.path.join(base, "pwm1_enable")) or ""
    mode = {"0": "full", "1": "custom", "2": "auto"}.get(enable.strip(), "")
    points = []
    for i in range(1, 9):
        temp = _read_int(os.path.join(base, f"pwm1_auto_point{i}_temp"))
        pwm = _read_int(os.path.join(base, f"pwm1_auto_point{i}_pwm"))
        if temp is None or pwm is None:
            return [], mode
        points.append((temp, pwm))
    return points, mode


def _write_curve(points, *, enable: int) -> bool:
    if len(points) != 8:
        return False
    base = _curve_base()
    if not base:
        return False
    for idx in (1, 2):
        for i, (temp, pwm) in enumerate(points, start=1):
            if not _write_int(os.path.join(base, f"pwm{idx}_auto_point{i}_temp"), temp):
                return False
            if not _write_int(os.path.join(base, f"pwm{idx}_auto_point{i}_pwm"), pwm):
                return False
        if not _write_int(os.path.join(base, f"pwm{idx}_enable"), enable):
            return False
    return True


def _parse_curve(text: str):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) != 8:
        raise ValueError("fan curve needs 8 temp:speed points")
    points = []
    for part in parts:
        temp_s, _, speed_s = part.partition(":")
        temp = int(temp_s)
        if speed_s.endswith("%"):
            pwm = int(round(int(speed_s[:-1]) * 255 / 100))
        else:
            pwm = int(speed_s)
        if not (0 <= temp <= 120) or not (0 <= pwm <= 255):
            raise ValueError(f"bad fan point {part}")
        points.append((temp, pwm))
    for prev, nxt in zip(points, points[1:]):
        if nxt[0] <= prev[0] or nxt[1] < prev[1]:
            raise ValueError("fan curve must rise in temp and not fall in speed")
    return points


def _floor_at(temp: int) -> int:
    floor = HIGH_TDP_CURVE
    if temp <= floor[0][0]:
        return floor[0][1]
    for i in range(1, len(floor)):
        lo_t, lo_p = floor[i - 1]
        hi_t, hi_p = floor[i]
        if temp > hi_t:
            continue
        if hi_t == lo_t:
            return hi_p
        span = (temp - lo_t) / (hi_t - lo_t)
        return int(round(lo_p + (hi_p - lo_p) * span))
    return floor[-1][1]


def cmd_profile(argv: list[str]) -> SimpleNamespace:
    if argv[:1] == ["--get"] or not argv:
        name = firmware_profile()
        if not name:
            return result(1, err="platform profile unreadable")
        return result(0, out=name + "\n")
    if argv[:1] == ["--set"] and len(argv) == 2:
        want = argv[1]
        if want not in ("quiet", "balanced", "performance"):
            return result(1, err=f"unknown firmware profile {want}")
        path = _profile_path()
        if not path:
            return result(1, err="platform profile missing")
        if firmware_profile() == want:
            return result(0, out=want + "\n")
        quiesce_upstream()
        if not sys_write(path, want + "\n"):
            return result(1, err="platform profile write failed")
        return result(0, out=want + "\n")
    return result(1, err="usage: profile --get | --set quiet|balanced|performance")


def cmd_tdp(argv: list[str]) -> SimpleNamespace:
    if argv[:1] == ["--get"] or not argv:
        pl1, pl2, pl3 = read_pl()
        if pl1 is None:
            return result(1, err="PPT unreadable")
        lines = [
            "TDP Power Limits (watts):",
            f"  PL1 (SPL):          {pl1}",
            f"  PL2 (sPPT):         {pl2 if pl2 is not None else pl1}",
            f"  PL3 (fPPT):         {pl3 if pl3 is not None else pl1}",
        ]
        return result(0, out="\n".join(lines) + "\n")
    if "--set" not in argv:
        return result(1, err="usage: tdp --get | --set WATTS [--pl2 W --pl3 W] [--force]")
    force = "--force" in argv
    try:
        set_at = argv.index("--set")
        pl1 = int(argv[set_at + 1])
    except (ValueError, IndexError):
        return result(1, err="tdp --set needs a watt value")
    pl2, pl3 = pl1, pl1

    def _opt(flag: str, current: int) -> int:
        if flag not in argv:
            return current
        try:
            return int(argv[argv.index(flag) + 1])
        except (ValueError, IndexError):
            raise ValueError(flag)

    try:
        pl2 = _opt("--pl2", pl2)
        pl3 = _opt("--pl3", pl3)
        if "--pl1" in argv:
            pl1 = _opt("--pl1", pl1)
    except ValueError as exc:
        return result(1, err=f"bad {exc.args[0]}")
    return write_tdp(pl1, pl2, pl3, force=force)


def cmd_fancurve(argv: list[str]) -> SimpleNamespace:
    if argv[:1] == ["--get"] or not argv:
        points, mode = _read_curve()
        if len(points) != 8:
            return result(1, err="fan curve unreadable")
        rpm = _read_int(os.path.join(_hwmon("asus") or "", "fan1_input"))
        lines = [f"Fans: {rpm if rpm is not None else 0} RPM, mode: {mode or 'unknown'}"]
        for temp, pwm in points:
            lines.append(f"{temp}°C: {pwm}/255")
        return result(0, out="\n".join(lines) + "\n")
    if argv[:1] == ["--reset"]:
        pl1, _, _ = read_pl()
        if pl1 is not None and pl1 > TDP_SAFE:
            return result(1, err="fan reset refused while PL1 is above 75W")
        quiesce_upstream()
        base = _curve_base()
        if not base:
            return result(1, err="fan curve device missing")
        ok = _write_int(os.path.join(base, "pwm1_enable"), 2) and _write_int(
            os.path.join(base, "pwm2_enable"), 2)
        return result(0, out="fans auto\n") if ok else result(1, err="fan reset failed")
    if argv[:1] == ["--set"] and len(argv) == 2:
        try:
            points = _parse_curve(argv[1])
        except ValueError as exc:
            return result(1, err=str(exc))
        pl1, _, _ = read_pl()
        if pl1 is not None and pl1 > TDP_SAFE:
            points = [(t, max(p, _floor_at(t))) for t, p in points]
        quiesce_upstream()
        if not _write_curve(points, enable=1):
            return result(1, err="fan curve write failed")
        return result(0, out="fan curve set\n")
    return result(1, err="usage: fancurve --get | --reset | --set temp:pwm,...")


_smu_lock = threading.Lock()
_ppt_gen = 0
_ppt_retry: threading.Thread | None = None
# The EC applies an armoury write to the SMU a moment after sysfs returns.
SMU_PPT_RETRY_S = 2.0


def _smu_ppt(pl1: int, pl2: int, pl3: int) -> list[str]:
    """Write the limits the APU follows.

    Sustained power tracks the slow limit, so stapm is set to the same
    watts. Fast is the boost cap. An armoury write can land on the SMU
    after this returns; a retry puts the requested watts back.
    """
    global _ppt_gen, _ppt_retry
    if not _smu_available():
        return ["ryzen_smu missing"]
    fast = max(pl2, pl3)
    targets = (
        (SMU_STAPM, pl1, "stapm"),
        (SMU_SLOW, pl1, "slow"),
        (SMU_FAST, fast, "fast"),
    )
    failed = []
    for cmd, watts, name in targets:
        code = _smu_command(cmd, watts * 1000)
        if code != SMU_OK:
            failed.append(f"{name} {code:#x}" if code is not None else f"{name} no response")
    with _smu_lock:
        _ppt_gen += 1
        gen = _ppt_gen

    def again() -> None:
        time.sleep(SMU_PPT_RETRY_S)
        with _smu_lock:
            if gen != _ppt_gen:
                return
            for cmd, watts, _name in targets:
                _smu_mailbox(cmd, watts * 1000)

    _ppt_retry = threading.Thread(target=again, daemon=True)
    _ppt_retry.start()
    if failed:
        return ["SMU PPT rejected " + ", ".join(failed)]
    note = f"SMU stapm/slow {pl1}W, fast {fast}W"
    if pl1 < SMU_PACKAGE_FLOOR_W:
        note += f"; package still draws about {SMU_PACKAGE_FLOOR_W}W"
    return [note]


def wait_smu_ppt() -> None:
    """Block until a one-shot CLI's SMU retry has run."""
    thread = _ppt_retry
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=SMU_PPT_RETRY_S + 1.0)


def _encode_co(offset: int) -> int:
    if offset >= 0:
        return 0x100000
    return 0x100000 - (-offset)


def _smu_available() -> bool:
    return os.path.exists(os.path.join(SMU, "mp1_smu_cmd"))


def _smu_mailbox(cmd: int, arg0: int) -> int | None:
    """Send one MP1 command. Caller holds _smu_lock."""
    args = struct.pack("<6I", arg0, 0, 0, 0, 0, 0)
    try:
        with open(os.path.join(SMU, "smu_args"), "wb", buffering=0) as fh:
            fh.write(args)
        cmd_path = os.path.join(SMU, "mp1_smu_cmd")
        with open(cmd_path, "wb", buffering=0) as fh:
            fh.write(struct.pack("<I", cmd))
        with open(cmd_path, "rb", buffering=0) as fh:
            raw = fh.read(4)
    except OSError:
        return None
    if len(raw) < 4:
        return None
    return struct.unpack("<I", raw)[0]


def _smu_command(cmd: int, arg0: int) -> int | None:
    if not _smu_available():
        return None
    with _smu_lock:
        return _smu_mailbox(cmd, arg0)


def _remember_co(offset: int) -> None:
    try:
        os.makedirs(os.path.dirname(CO_STATE), mode=0o700, exist_ok=True)
        with open(CO_STATE, "w", encoding="ascii") as fh:
            fh.write(str(int(offset)) + "\n")
    except OSError:
        pass


def _remembered_co() -> int | None:
    try:
        with open(CO_STATE, encoding="ascii") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _set_co(offset: int) -> SimpleNamespace:
    if offset > 0:
        offset = -offset
    if not (-40 <= offset <= 0):
        return result(1, err="undervolt must be 0 to -40")
    if not _smu_available():
        return result(1, err="ryzen_smu is not loaded")
    quiesce_upstream()
    code = _smu_command(SMU_CO_ALL, _encode_co(offset))
    if code != SMU_OK:
        return result(1, err=f"SMU CO command failed ({code})")
    _remember_co(offset)
    return result(0, out=f"{offset}\n")


def cmd_undervolt(argv: list[str]) -> SimpleNamespace:
    if argv[:1] == ["--get"] or not argv:
        if not _smu_available():
            return result(1, err="ryzen_smu is not loaded")
        remembered = _remembered_co()
        shown = 0 if remembered is None else remembered
        return result(0, out=f"{shown}\n")
    if argv[:1] == ["--reset"]:
        return _set_co(0)
    if argv[:1] == ["--set"] and len(argv) == 2:
        try:
            return _set_co(int(argv[1]))
        except ValueError:
            return result(1, err="undervolt --set needs an integer")
    return result(1, err="usage: undervolt --get | --set N | --reset")


def cmd_battery(argv: list[str]) -> SimpleNamespace:
    if argv[:1] == ["--get"] or not argv:
        val = _read_int(CHARGE_PATH)
        if val is None:
            return result(1, err="charge limit unreadable")
        return result(0, out=f"{val}\n")
    if argv[:1] == ["--set"] and len(argv) == 2:
        try:
            limit = int(argv[1])
        except ValueError:
            return result(1, err="batterylimit --set needs an integer")
        if not (40 <= limit <= 100):
            return result(1, err="charge limit must be 40–100")
        quiesce_upstream()
        if not _write_int(CHARGE_PATH, limit):
            return result(1, err="charge limit write failed")
        return result(0, out=f"{limit}\n")
    return result(1, err="usage: batterylimit --get | --set 40-100")


def _armoury_flag(attr: str, argv: list[str], label: str) -> SimpleNamespace:
    path = os.path.join(ARMOURY, attr, "current_value")
    if argv[:1] == ["--get"] or not argv:
        val = _read_int(path)
        if val is None:
            return result(1, err=f"{label} unreadable")
        return result(0, out=f"{val}\n")
    if argv[:1] == ["--set"] and len(argv) == 2 and argv[1] in ("0", "1"):
        quiesce_upstream()
        if not sys_write(path, argv[1] + "\n"):
            return result(1, err=f"{label} write failed")
        return result(0, out=argv[1] + "\n")
    return result(1, err=f"usage: {label} --get | --set 0|1")


def _flag(argv: list[str], name: str):
    if name not in argv:
        return None
    i = argv.index(name)
    if i + 1 >= len(argv):
        raise ValueError(name)
    return argv[i + 1]


def _hex_color(text: str) -> tuple[int, int, int]:
    text = text.removeprefix("#")
    if len(text) != 6:
        raise ValueError("color must be RRGGBB")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _packet(payload: bytes) -> bytes:
    buf = bytearray(64)
    buf[:len(payload)] = payload
    return bytes(buf)


def _aura_init() -> list[bytes]:
    return [
        _packet(bytes([0x5D, 0xB9])),
        _packet(b"\x5dASUS Tech.Inc."),
        _packet(bytes([0x5D, 0x05, 0x20, 0x31, 0x00, 0x1A])),
        _packet(bytes([0x5D, 0xC0, 0x03, 0x01])),
    ]


def _set_power(on: bool) -> bytes:
    if on:
        fields = (0xFF, 0x1F, 0xFF, 0xFF)
    else:
        fields = (0x00, 0x00, 0x00, 0x00)
    return _packet(bytes([0x5D, 0xBD, 0x01, *fields, 0xFF]))


def _set_brightness(level: int) -> bytes:
    level = max(0, min(3, level))
    return _packet(bytes([0x5D, 0xBA, 0xC5, 0xC4, level]))


def _set_mode(zone: int, mode: int, rgb, speed: int, rgb2) -> bytes:
    r, g, b = rgb
    r2, g2, b2 = rgb2
    if (r, g, b) == (0, 0, 0):
        flag = 0xFF
    elif mode == MODES["breathe"]:
        flag = 0x01
    else:
        flag = 0x00
    return _packet(bytes([
        0x5D, 0xB3, zone, mode, r, g, b, speed, 0x00, flag, r2, g2, b2,
    ]))


def _commit() -> list[bytes]:
    return [_packet(bytes([0x5D, 0xB5])), _packet(bytes([0x5D, 0xB4]))]


def _hid_supports_aura(fd: int) -> bool:
    size = array.array("I", [0])
    try:
        fcntl.ioctl(fd, HIDIOCGRDESCSIZE, size)
    except OSError:
        return False
    desc = array.array("B", [0] * (4 + 4096))
    struct.pack_into("<I", desc, 0, min(size[0], 4096))
    try:
        fcntl.ioctl(fd, HIDIOCGRDESC, desc)
    except OSError:
        return False
    raw = bytes(desc[4:4 + size[0]])
    return b"\x85\x5d" in raw


def _hidraw_nodes():
    found = []
    try:
        names = os.listdir("/sys/class/hidraw")
    except OSError:
        return found
    for name in names:
        uevent = os.path.join("/sys/class/hidraw", name, "device", "uevent")
        try:
            with open(uevent, encoding="ascii", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        hid = ""
        for line in text.splitlines():
            if line.startswith("HID_ID="):
                hid = line.split("=", 1)[1].lower()
        if "00000b05" not in hid:
            continue
        role = None
        if "00001a30" in hid:
            role = "keyboard"
        elif "000018c6" in hid:
            role = "lightbar"
        if role is None:
            continue
        path = os.path.join("/dev", name)
        try:
            fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
        except OSError:
            continue
        try:
            if _hid_supports_aura(fd):
                found.append((role, path, fd))
                fd = -1
        finally:
            if fd >= 0:
                os.close(fd)
    return found


def _write_all(nodes, packets: list[bytes]) -> bool:
    ok = False
    for _role, _path, fd in nodes:
        try:
            for packet in packets:
                os.write(fd, packet)
            ok = True
        except OSError:
            continue
    return ok


def apply_lighting(*, mode: str, color: str, color2: str, speed: str,
                   brightness: str, device: str, power: bool) -> SimpleNamespace:
    if power and mode not in MODES:
        return result(1, err=f"unknown lighting mode {mode}")
    try:
        rgb = _hex_color(color) if power else (0, 0, 0)
        rgb2 = _hex_color(color2) if power else (0, 0, 0)
    except ValueError as exc:
        return result(1, err=str(exc))
    level = BRIGHTNESS.get(brightness.lower(), 3)
    speed_b = SPEEDS.get(speed.lower(), SPEEDS["normal"])
    nodes = _hidraw_nodes()
    if device in ("keyboard", "lightbar"):
        nodes = [n for n in nodes if n[0] == device]
    if not nodes:
        return result(1, err="Aura hidraw device not openable")
    quiesce_upstream()
    try:
        packets = _aura_init()
        packets.append(_set_power(power))
        packets.append(_set_brightness(0 if not power else level))
        if power:
            mode_b = MODES[mode]
            for zone in (0, 1):
                packets.append(_set_mode(zone, mode_b, rgb, speed_b, rgb2))
                packets.extend(_commit())
        if not _write_all(nodes, packets):
            return result(1, err="lighting write failed")
    finally:
        for _role, _path, fd in nodes:
            os.close(fd)
    return result(0, out=("off\n" if not power else f"{mode}\n"))


def cmd_apply(argv: list[str]) -> SimpleNamespace:
    try:
        mode = _flag(argv, "--mode") or "static"
        color = _flag(argv, "--color") or "FF0000"
        color2 = _flag(argv, "--color2") or "000000"
        speed = _flag(argv, "--speed") or "normal"
        brightness = _flag(argv, "--brightness") or "high"
        device = _flag(argv, "--device") or "all"
    except ValueError as exc:
        return result(1, err=f"missing value for {exc.args[0]}")
    return apply_lighting(
        mode=mode, color=color, color2=color2, speed=speed,
        brightness=brightness, device=device, power=True,
    )


def cmd_off(argv: list[str]) -> SimpleNamespace:
    try:
        device = _flag(argv, "--device") or "all"
    except ValueError as exc:
        return result(1, err=f"missing value for {exc.args[0]}")
    return apply_lighting(
        mode="static", color="000000", color2="000000", speed="normal",
        brightness="off", device=device, power=False,
    )


def cmd_status(_argv: list[str]) -> SimpleNamespace:
    profile = firmware_profile() or "unknown"
    pl1, pl2, pl3 = read_pl()
    _points, mode = _read_curve()
    asus = _hwmon("asus")
    rpm = _read_int(os.path.join(asus, "fan1_input")) if asus else None
    k10 = _hwmon("k10temp")
    temp = None
    if k10:
        raw = _read_int(os.path.join(k10, "temp1_input"))
        if raw is not None:
            temp = raw // 1000 if raw > 1000 else raw
    ac = sys_read("/sys/class/power_supply/AC0/online")
    cap = _read_int("/sys/class/power_supply/BAT0/capacity")
    limit = _read_int(CHARGE_PATH)
    lines = [
        f"APU:     {temp if temp is not None else '?'}°C",
        f"Fans:    {rpm if rpm is not None else 0} RPM, mode: {mode or 'unknown'}",
        f"Profile: {profile}",
        f"Power:   {'AC' if ac == '1' else 'battery'}",
        f"TDP:     {pl1 if pl1 is not None else '?'}W (PL1) / "
        f"{pl2 if pl2 is not None else '?'}W (PL2) / {pl3 if pl3 is not None else '?'}W (PL3)",
        f"Battery: {cap if cap is not None else '?'}% (limit: {limit if limit is not None else '?'}%)",
    ]
    return result(0, out="\n".join(lines) + "\n")


def cmd_autoswitch(argv: list[str]) -> SimpleNamespace:
    # z13-power owns plug and unplug. There is no second switcher to enable.
    if argv[:1] == ["--clear"] or argv[:1] == ["--get"] or not argv:
        return result(0, out="Autoswitch: disabled\n")
    return result(1, err="autoswitch is not used; z13-power owns AC and battery")


def invoke(argv: list[str]) -> SimpleNamespace:
    if not argv or argv[0] in ("-h", "--help", "help"):
        return result(0, out=(
            "z13-power-hw — built-in GZ302 control (no z13ctl)\n"
            "  profile | tdp | fancurve | undervolt | batterylimit |\n"
            "  paneloverdrive | bootsound | apply | off | status | autoswitch\n"
        ))
    if argv[0] in ("-v", "--version", "version"):
        return result(0, out=f"z13-power-hw {VERSION}\n")
    cmd, rest = argv[0], argv[1:]
    table = {
        "profile": cmd_profile,
        "tdp": cmd_tdp,
        "fancurve": cmd_fancurve,
        "undervolt": cmd_undervolt,
        "batterylimit": cmd_battery,
        "paneloverdrive": lambda a: _armoury_flag("panel_overdrive", a, "paneloverdrive"),
        "bootsound": lambda a: _armoury_flag("boot_sound", a, "bootsound"),
        "apply": cmd_apply,
        "off": cmd_off,
        "status": cmd_status,
        "autoswitch": cmd_autoswitch,
    }
    fn = table.get(cmd)
    if fn is None:
        return result(1, err=f"unknown command {cmd}")
    try:
        return fn(rest)
    except Exception as exc:
        return result(1, err=str(exc))


def open_armoury_button() -> int:
    """Shared read of the Asus WMI hotkeys node. Do not EVIOCGRAB it."""
    try:
        names = os.listdir("/sys/class/input")
    except OSError as exc:
        raise OSError("no input class") from exc
    for name in names:
        if not name.startswith("event"):
            continue
        npath = os.path.join("/sys/class/input", name, "device", "name")
        try:
            with open(npath, encoding="utf-8", errors="replace") as fh:
                label = fh.read().strip()
        except OSError:
            continue
        if label != "Asus WMI hotkeys":
            continue
        return os.open(os.path.join("/dev/input", name), os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    raise OSError("Asus WMI hotkeys not found")


def _pressed(data: bytes) -> bool:
    size = 24
    for off in range(0, len(data) - size + 1, size):
        _sec, _usec, ev_type, code, value = struct.unpack_from("llHHi", data, off)
        if ev_type == EV_KEY and code == KEY_PROG3 and value == 1:
            return True
    return False


def wait_armoury_press(should_stop) -> bool:
    """Block until KEY_PROG3 goes down. False when should_stop() is true."""
    while not should_stop():
        try:
            fd = open_armoury_button()
        except OSError:
            for _ in range(20):
                if should_stop():
                    return False
                time.sleep(0.1)
            continue
        try:
            while not should_stop():
                try:
                    ready, _, _ = select.select([fd], [], [], 1.0)
                except (OSError, ValueError):
                    break
                if not ready:
                    continue
                try:
                    data = os.read(fd, 24 * 32)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if data and _pressed(data):
                    return True
        finally:
            os.close(fd)
    return False


def main(argv: list[str] | None = None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    done = invoke(args)
    wait_smu_ppt()
    if done.stdout:
        sys.stdout.write(done.stdout)
    if done.stderr:
        sys.stderr.write(done.stderr)
    return int(done.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
