#!/usr/bin/python3
"""Descriptor-relative user-state I/O and bounded helpers for z13-power.

Used by z13-power-settings and the modules it imports. Pathnames are not used
after the first trusted directory open: components are O_NOFOLLOW + fstat,
writes are O_EXCL tmp + fsync + rename + dir fsync, and children run from a
held /usr fd with a sanitized environment.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import pwd
import select
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

MAX_FILE_BYTES = 16 * 1024
MAX_LINES = 128
MAX_LINE_CHARS = 256
MAX_KEYS = 32
MAX_STR = 64
MAX_PROC_BYTES = 32 * 1024
MAX_ERR_BYTES = 8 * 1024
MAX_SYS_BYTES = 64
DEFAULT_TIMEOUT = 3.0
Z13CTL_TIMEOUT = 8.0
UNTRUSTED_WRITE = stat.S_IWGRP | stat.S_IWOTH

HELPERS = {
    "z13ctl": ("bin", "z13ctl"),
    "fc-match": ("bin", "fc-match"),
    "hyprctl": ("bin", "hyprctl"),
    "asusctl": ("bin", "asusctl"),
    "xdg-open": ("bin", "xdg-open"),
}
Z13CTL_SHA256 = "3e49f796e6eec2021ce4716f57c19f5f65f43f76408cb56a6454f88147f5f4d6"
Z13CTL_VERSION = "z13ctl version 1.3.2"
_held_fds: dict[str, int] = {}

ENV_KEEP = (
    "HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
    "LC_MESSAGES", "LC_TIME", "TZ", "TERM", "DISPLAY", "WAYLAND_DISPLAY",
    "XAUTHORITY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP",
    "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
    "DBUS_SESSION_BUS_ADDRESS", "HYPRLAND_INSTANCE_SIGNATURE",
    "QT_QPA_PLATFORM", "QT_QPA_PLATFORMTHEME", "QT_STYLE_OVERRIDE",
    "OMARCHY_PATH",
)


class Missing(Exception):
    pass


class IoError(Exception):
    pass


def trusted_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ENV_KEEP:
        val = os.environ.get(key)
        if val:
            env[key] = val
    env["PATH"] = "/usr/bin"
    env["IFS"] = " \t\n"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = "/usr/share/z13-power-management"
    env["Z13CTL"] = "/usr/bin/z13ctl"
    env["XDG_DATA_DIRS"] = os.environ.get("XDG_DATA_DIRS") or "/usr/share"
    env["XDG_CONFIG_DIRS"] = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    return env


def _check_dir(st: os.stat_result, *, owner: int | None) -> None:
    if not stat.S_ISDIR(st.st_mode):
        raise IoError("path component is not a directory")
    if owner is not None and st.st_uid != owner:
        raise IoError("directory owner mismatch")
    if st.st_mode & UNTRUSTED_WRITE:
        raise IoError("directory is group- or world-writable")


def _check_reg(st: os.stat_result, *, owner: int | None, executable: bool) -> None:
    if not stat.S_ISREG(st.st_mode):
        raise IoError("not a regular file")
    if owner is not None and st.st_uid != owner:
        raise IoError("file owner mismatch")
    if st.st_mode & UNTRUSTED_WRITE:
        raise IoError("file is group- or world-writable")
    if executable and st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) == 0:
        raise IoError("binary is not executable")


def open_anchor(path: str, *, owner: int | None) -> int:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise IoError(f"anchor is not a directory: {path}")
        if owner is not None and st.st_uid != owner:
            raise IoError(f"anchor not owned as required: {path}")
        if st.st_mode & UNTRUSTED_WRITE:
            raise IoError(f"anchor is group- or world-writable: {path}")
        return fd
    except BaseException:
        os.close(fd)
        raise


def trusted_home_fd() -> int:
    home = pwd.getpwuid(os.getuid()).pw_dir
    return open_anchor(home, owner=os.getuid())


def trusted_usr_fd() -> int:
    return open_anchor("/usr", owner=0)


def trusted_sys_fd() -> int:
    return open_anchor("/sys", owner=0)


def _legal_name(name: str) -> None:
    if name in ("", ".", "..") or "/" in name or "\x00" in name:
        raise IoError("illegal path component")


def openat_dir(parent_fd: int, name: str, *, owner: int | None, create: bool = False, mode: int = 0o700) -> int:
    _legal_name(name)
    if create:
        try:
            os.mkdir(name, mode, dir_fd=parent_fd)
        except FileExistsError:
            pass
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
    except FileNotFoundError:
        raise Missing(name)
    try:
        st = os.fstat(fd)
        _check_dir(st, owner=owner)
        if create and owner == os.getuid():
            os.fchmod(fd, mode)
        return fd
    except BaseException:
        os.close(fd)
        raise


def openat_file(parent_fd: int, name: str, flags: int, *, mode: int = 0) -> int:
    _legal_name(name)
    try:
        fd = os.open(
            name,
            flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            mode,
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        raise Missing(name)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise IoError("not a regular file")
        return fd
    except BaseException:
        os.close(fd)
        raise


def walk_dirs(anchor_fd: int, parts: list[str], *, owner: int | None, create: bool = False, mode: int = 0o700) -> int:
    fd = anchor_fd
    close_anchor = False
    try:
        for part in parts:
            nxt = openat_dir(fd, part, owner=owner, create=create, mode=mode)
            if fd is not anchor_fd or close_anchor:
                os.close(fd)
            fd = nxt
            close_anchor = True
        if fd is anchor_fd:
            raise IoError("walk_dirs requires at least one component")
        return fd
    except BaseException:
        if fd is not anchor_fd:
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def read_fd(fd: int, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            buf = os.read(fd, 4096)
        except BlockingIOError:
            break
        if not buf:
            break
        total += len(buf)
        if total > max_bytes:
            raise IoError("file too large")
        chunks.append(buf)
    return b"".join(chunks)


def read_under(anchor_fd: int, dirs: list[str], filename: str, max_bytes: int, *, owner: int | None) -> bytes:
    dirfd = walk_dirs(anchor_fd, dirs, owner=owner) if dirs else anchor_fd
    close_dir = dirs != []
    try:
        fd = openat_file(dirfd, filename, os.O_RDONLY)
        try:
            st = os.fstat(fd)
            if owner is not None and st.st_uid != owner:
                raise IoError("file owner mismatch")
            if st.st_mode & UNTRUSTED_WRITE:
                raise IoError("file is group- or world-writable")
            return read_fd(fd, max_bytes)
        finally:
            os.close(fd)
    finally:
        if close_dir:
            os.close(dirfd)


def atomic_replace(dirfd: int, name: str, data: bytes, *, owner: int) -> None:
    """Write data via O_EXCL tmp, fsync, rename, dir fsync. Dest unchanged on failure."""
    if len(data) > MAX_FILE_BYTES:
        raise IoError("payload too large")
    _legal_name(name)
    tmp_name = f".{name}.{os.getpid()}.{os.urandom(8).hex()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = None
    renamed = False
    try:
        fd = os.open(tmp_name, flags, 0o600, dir_fd=dirfd)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != owner:
            raise IoError("tmp is not a private regular file")
        view = memoryview(data)
        off = 0
        while off < len(view):
            n = os.write(fd, view[off:])
            if n <= 0:
                raise IoError("short write")
            off += n
        os.fsync(fd)
        os.rename(tmp_name, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        renamed = True
        os.fsync(dirfd)
    except BaseException:
        if fd is not None and not renamed:
            try:
                os.unlink(tmp_name, dir_fd=dirfd)
            except OSError:
                pass
        raise
    finally:
        if fd is not None:
            os.close(fd)


def _home_sub_dirfd(parts: list[str], *, create: bool, mode: int = 0o700) -> int:
    home = trusted_home_fd()
    try:
        return walk_dirs(home, parts, owner=os.getuid(), create=create, mode=mode)
    finally:
        os.close(home)


def read_user_file(dirs: list[str], name: str, max_bytes: int = MAX_FILE_BYTES) -> bytes | None:
    home = trusted_home_fd()
    try:
        try:
            return read_under(home, dirs, name, max_bytes, owner=os.getuid())
        except (Missing, IoError, OSError):
            return None
    finally:
        os.close(home)


def write_user_file(dirs: list[str], name: str, data: bytes, *, private_mode: int = 0o700) -> None:
    dirfd = _home_sub_dirfd(dirs, create=True, mode=private_mode)
    try:
        atomic_replace(dirfd, name, data, owner=os.getuid())
    finally:
        os.close(dirfd)


def bounded_text(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        return None
    if any(len(line) > MAX_LINE_CHARS for line in lines):
        return None
    return text


def parse_json_object(raw: bytes | None, allowed: dict[str, type | tuple]) -> dict:
    if raw is None or len(raw) > MAX_FILE_BYTES:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or len(data) > MAX_KEYS:
        return {}
    out: dict = {}
    for key, typ in allowed.items():
        if key not in data:
            continue
        val = data[key]
        if isinstance(typ, tuple):
            if not isinstance(val, typ):
                continue
        elif not isinstance(val, typ):
            continue
        if isinstance(val, str):
            out[key] = val[:MAX_STR]
        elif isinstance(val, bool):
            out[key] = val
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            if -1e6 <= float(val) <= 1e6:
                out[key] = val
        elif val is None:
            out[key] = None
    return out


def _open_same_dir_symlink(dirfd: int, name: str) -> int:
    target = os.readlink(name, dir_fd=dirfd)
    if target in ("", ".", "..") or "/" in target or "\x00" in target:
        raise IoError("symlink target not a same-directory name")
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise IoError("symlink target is not a regular file")
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_usr_file(rel: tuple[str, ...], *, allow_same_dir_symlink: bool = False) -> int:
    usr = trusted_usr_fd()
    try:
        *dirs, name = rel
        dirfd = usr
        close_dir = False
        if dirs:
            dirfd = walk_dirs(usr, list(dirs), owner=0)
            close_dir = True
        try:
            try:
                fd = openat_file(dirfd, name, os.O_RDONLY)
            except OSError as e:
                if not allow_same_dir_symlink or e.errno != errno.ELOOP:
                    raise
                fd = _open_same_dir_symlink(dirfd, name)
            _check_reg(os.fstat(fd), owner=0, executable=True)
            return fd
        finally:
            if close_dir:
                os.close(dirfd)
    finally:
        os.close(usr)


def sha256_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    total = 0
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        total += len(chunk)
        if total > 16 * 1024 * 1024:
            raise IoError("binary too large")
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _clear_cloexec(fd: int) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)
    os.set_inheritable(fd, True)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=0.2)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _bounded_collect(proc: subprocess.Popen, timeout: float, max_out: int, max_err: int) -> tuple[bytes, bytes, int]:
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    for fd in (out_fd, err_fd):
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    out = bytearray()
    err = bytearray()
    open_fds = {out_fd, err_fd}
    deadline = time.monotonic() + timeout
    overflow = False

    def read_one(fd: int) -> None:
        nonlocal overflow
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            return
        if chunk == b"":
            open_fds.discard(fd)
            return
        if fd == out_fd:
            out.extend(chunk)
            if len(out) > max_out:
                overflow = True
                _kill_group(proc)
        else:
            err.extend(chunk)
            if len(err) > max_err:
                overflow = True
                _kill_group(proc)

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or overflow:
            _kill_group(proc)
            raise IoError("timeout" if remaining <= 0 else "output overflow")
        rc = proc.poll()
        if not open_fds and rc is not None:
            return bytes(out), bytes(err), rc
        rlist = list(open_fds)
        if not rlist:
            try:
                proc.wait(timeout=min(remaining, 0.05))
            except subprocess.TimeoutExpired:
                continue
            return bytes(out), bytes(err), proc.returncode or 0
        ready, _, _ = select.select(rlist, [], [], min(remaining, 0.1))
        for fd in ready:
            read_one(fd)
        if rc is not None and not ready:
            for fd in list(open_fds):
                read_one(fd)
            if not open_fds:
                return bytes(out), bytes(err), rc


def _held_helper_fd(name: str) -> int | None:
    rel = HELPERS.get(name)
    if rel is None:
        return None
    fd = _held_fds.get(name)
    if fd is not None:
        try:
            _check_reg(os.fstat(fd), owner=0, executable=True)
            if name == "z13ctl" and sha256_fd(fd) != Z13CTL_SHA256:
                raise IoError("z13ctl digest changed on held fd")
            return fd
        except (IoError, OSError):
            try:
                os.close(fd)
            except OSError:
                pass
            _held_fds.pop(name, None)
    try:
        fd = open_usr_file(rel)
    except (Missing, IoError, OSError):
        return None
    try:
        _check_reg(os.fstat(fd), owner=0, executable=True)
        if name == "z13ctl":
            if sha256_fd(fd) != Z13CTL_SHA256:
                raise IoError("z13ctl digest mismatch")
            _clear_cloexec(fd)
            proc = subprocess.Popen(
                [f"/proc/self/fd/{fd}", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=trusted_env(),
                start_new_session=True,
                close_fds=True,
                pass_fds=(fd,),
            )
            try:
                out, _err, rc = _bounded_collect(proc, 2.0, 256, 256)
            except IoError:
                os.close(fd)
                return None
            identity = out.decode("utf-8", "replace").strip()
            if rc not in (0, None) or identity != Z13CTL_VERSION:
                os.close(fd)
                return None
        _held_fds[name] = fd
        return fd
    except (IoError, OSError):
        os.close(fd)
        return None


def run_helper(argv: list[str], *, timeout: float = DEFAULT_TIMEOUT) -> SimpleNamespace | None:
    if not argv:
        return None
    name = os.path.basename(argv[0])
    extra = argv[1:]
    fd = _held_helper_fd(name)
    if fd is None:
        return None
    _clear_cloexec(fd)
    proc_path = f"/proc/self/fd/{fd}"
    proc = subprocess.Popen(
        [proc_path, *extra],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=trusted_env(),
        start_new_session=True,
        close_fds=True,
        pass_fds=(fd,),
    )
    try:
        out, err, rc = _bounded_collect(proc, timeout, MAX_PROC_BYTES, MAX_ERR_BYTES)
    except IoError:
        return None
    finally:
        if proc.poll() is None:
            _kill_group(proc)
    return SimpleNamespace(
        stdout=out.decode("utf-8", "replace")[:MAX_PROC_BYTES],
        stderr=err.decode("utf-8", "replace")[:MAX_ERR_BYTES],
        returncode=rc or 0,
    )


def spawn_detached_usr(rel: tuple[str, ...], extra_argv: list[str]) -> bool:
    """Double-fork a /usr helper so the long-lived parent can reap immediately."""
    try:
        fd = open_usr_file(rel)
    except (Missing, IoError, OSError):
        return False
    try:
        _clear_cloexec(fd)
        proc_path = f"/proc/self/fd/{fd}"
        child_env = trusted_env()
        pid = os.fork()
        if pid == 0:
            try:
                os.setsid()
                pid2 = os.fork()
                if pid2 > 0:
                    os._exit(0)
                devnull = os.open("/dev/null", os.O_RDWR | os.O_CLOEXEC)
                os.dup2(devnull, 0)
                os.dup2(devnull, 1)
                os.dup2(devnull, 2)
                os.execve(proc_path, [proc_path, *extra_argv], child_env)
            except Exception:
                os._exit(127)
        os.waitpid(pid, 0)
        return True
    finally:
        os.close(fd)


def sys_listdir(parts: list[str]) -> list[str]:
    sysfd = trusted_sys_fd()
    sys_dev = os.fstat(sysfd).st_dev
    cur = sysfd
    try:
        for part in parts:
            try:
                nxt = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=cur,
                )
            except OSError:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=cur)
            if os.fstat(nxt).st_dev != sys_dev:
                os.close(nxt)
                return []
            if cur is not sysfd:
                os.close(cur)
            cur = nxt
        try:
            names = os.listdir(cur)
        except OSError:
            return []
        return [n for n in names[:64] if n not in (".", "..") and "/" not in n and "\x00" not in n]
    except (Missing, IoError, OSError):
        return []
    finally:
        if cur is not sysfd:
            try:
                os.close(cur)
            except OSError:
                pass
        os.close(sysfd)


def user_dir_exists(parts: list[str]) -> bool:
    try:
        fd = _home_sub_dirfd(parts, create=False)
    except (Missing, IoError, OSError):
        return False
    os.close(fd)
    return True


def sys_read(path: str, max_bytes: int = MAX_SYS_BYTES) -> str | None:
    if not path.startswith("/sys/") or ".." in path.split("/"):
        return None
    parts = [p for p in path.split("/")[2:] if p]
    if not parts:
        return None
    sysfd = trusted_sys_fd()
    sys_dev = os.fstat(sysfd).st_dev
    try:
        *dirs, name = parts
        dirfd = sysfd
        close_dir = False
        cur = sysfd
        try:
            for part in dirs:
                try:
                    nxt = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=cur,
                    )
                except OSError:
                    nxt = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                        dir_fd=cur,
                    )
                try:
                    if os.fstat(nxt).st_dev != sys_dev:
                        os.close(nxt)
                        return None
                except BaseException:
                    os.close(nxt)
                    raise
                if cur is not sysfd:
                    os.close(cur)
                cur = nxt
                close_dir = True
            dirfd = cur
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
            except OSError:
                fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dirfd)
            try:
                if os.fstat(fd).st_dev != sys_dev:
                    return None
                raw = read_fd(fd, max_bytes)
            finally:
                os.close(fd)
            return raw.decode("ascii", "ignore").strip()
        finally:
            if close_dir:
                os.close(dirfd)
    except (Missing, IoError, OSError):
        return None
    finally:
        os.close(sysfd)


def sys_write(path: str, value: str) -> bool:
    raw = str(value).encode("ascii", "ignore")
    if not path.startswith("/sys/") or ".." in path.split("/") or len(raw) > 32:
        return False
    parts = [p for p in path.split("/")[2:] if p]
    if not parts:
        return False
    sysfd = trusted_sys_fd()
    sys_dev = os.fstat(sysfd).st_dev
    try:
        *dirs, name = parts
        cur = sysfd
        close_dir = False
        try:
            for part in dirs:
                try:
                    nxt = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=cur,
                    )
                except OSError:
                    nxt = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                        dir_fd=cur,
                    )
                if os.fstat(nxt).st_dev != sys_dev:
                    os.close(nxt)
                    return False
                if cur is not sysfd:
                    os.close(cur)
                cur = nxt
                close_dir = True
            try:
                fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=cur)
            except OSError:
                fd = os.open(name, os.O_WRONLY | os.O_CLOEXEC, dir_fd=cur)
            try:
                if os.fstat(fd).st_dev != sys_dev:
                    return False
                os.write(fd, raw)
                return True
            finally:
                os.close(fd)
        finally:
            if close_dir:
                os.close(cur)
    except (Missing, IoError, OSError):
        return False
    finally:
        os.close(sysfd)


def selftest() -> None:
    """Atomic write leaves the destination unchanged when the tmp write fails."""
    import tempfile

    tmp = tempfile.mkdtemp(prefix="z13-io-")
    try:
        os.chmod(tmp, 0o700)
        dirfd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            atomic_replace(dirfd, "state.txt", b"one\n", owner=os.getuid())
            with open(os.path.join(tmp, "state.txt"), "rb") as fh:
                assert fh.read() == b"one\n"
            try:
                atomic_replace(dirfd, "state.txt", b"x" * (MAX_FILE_BYTES + 1), owner=os.getuid())
            except IoError:
                pass
            else:
                raise AssertionError("oversize write should fail")
            with open(os.path.join(tmp, "state.txt"), "rb") as fh:
                assert fh.read() == b"one\n", "destination mutated on failure"
            atomic_replace(dirfd, "state.txt", b"two\n", owner=os.getuid())
            with open(os.path.join(tmp, "state.txt"), "rb") as fh:
                assert fh.read() == b"two\n"
        finally:
            os.close(dirfd)
    finally:
        for name in os.listdir(tmp):
            os.unlink(os.path.join(tmp, name))
        os.rmdir(tmp)


if __name__ == "__main__":
    selftest()
    sys.stdout.write("z13_power_io selftest ok\n")
