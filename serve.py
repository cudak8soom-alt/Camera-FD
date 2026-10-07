"""Face inbox: FTP server for Dahua Face Detection picture uploads (Windows).

  Camera: Face Detection -> Snapshot -> FTP -> this PC (FTP_DIR).  No local face model.

Run:   python serve.py
Stop:  Ctrl+C / Ctrl+Break, or  powershell -ExecutionPolicy Bypass -File stop.ps1
Debug: FTP_DEBUG=1 in .env -> full FTP dialogue (<- command / -> reply) in console + log.
"""

from __future__ import annotations

import atexit
import ipaddress
import logging
import logging.handlers
import os
import re
import signal
import socket
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.filesystems import AbstractedFS
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from camera_config import apply_camera_config

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PID_FILE = ROOT / "serve.pid"
STOP_FILE = ROOT / "serve.stop"          # created by stop.ps1 -> graceful shutdown
PICTURE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
BAD_CHARS = str.maketrans({c: "_" for c in '<>:"|?*\\'})
# Dahua: 001_20261007123325_[M][0@0][1].jpg
#   -> face_2026-10-07_12-33-25_closeup.jpg
_DAHUA_PIC = re.compile(
    r"^(?P<ch>\d+)_(?P<ts>\d{14})_\[(?P<tag>[^\]]*)\]\[(?P<pos>[^\]]*)\]\[(?P<kind>\d+)\]$",
    re.IGNORECASE,
)
# [0] = wider scene snap, [1] = face close-up crop
_KIND_LABEL = {"0": "scene", "1": "closeup"}

log = logging.getLogger("faces")


def env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def friendly_picture_path(path: Path) -> Path | None:
    """Map Dahua face filenames to a readable name in the same folder."""
    m = _DAHUA_PIC.match(path.stem)
    if not m:
        return None
    ts = m.group("ts")
    stamp = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}_{ts[8:10]}-{ts[10:12]}-{ts[12:14]}"
    label = _KIND_LABEL.get(m.group("kind"), f"part{m.group('kind')}")
    dest = path.with_name(f"face_{stamp}_{label}{path.suffix.lower()}")
    if dest == path:
        return None
    if not dest.exists():
        return dest
    n = 2
    while True:
        alt = path.with_name(f"face_{stamp}_{label}_{n}{path.suffix.lower()}")
        if not alt.exists():
            return alt
        n += 1


def rename_picture(path: Path) -> Path:
    """Rename a received picture in place; return final path (original if skipped)."""
    dest = friendly_picture_path(path)
    if dest is None:
        return path
    try:
        path.rename(dest)
        return dest
    except OSError as exc:
        log.warning("rename failed %s -> %s: %s", path.name, dest.name, exc)
        return path


def lan_ip(camera_host: str) -> str:
    """Source IP of the NIC that routes to the camera (UDP connect sends nothing)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((camera_host, 80))
        return s.getsockname()[0]


def parse_ports(text: str) -> range:
    lo, _, hi = text.strip().partition("-")
    return range(int(lo), int(hi or lo) + 1)


class WinSafeFS(AbstractedFS):
    """Camera names with chars Windows can't store (e.g. ':' in times) -> '_'.
    Without this the STOR fails with 550 and no picture lands."""

    def ftp2fs(self, ftppath):
        return super().ftp2fs(ftppath.translate(BAD_CHARS))


class FaceFTPHandler(FTPHandler):
    abstracted_fs = WinSafeFS
    folder: Path = ROOT
    allow: list = []                       # ip_network objects; empty = allow all
    pictures = 0
    # commands passed to log_cmd() (CWD/SIZE misses are normal camera probing -> not listed)
    log_cmds_list = ["MKD", "XMKD", "STOR", "APPE", "STOU", "DELE", "RNFR", "RNTO", "RMD"]

    def _rel(self, file: str) -> str:
        try:
            return str(Path(file).relative_to(self.folder))
        except ValueError:
            return str(file)

    def handle(self) -> None:
        if self.allow:
            try:
                ok = any(ipaddress.ip_address(self.remote_ip) in n for n in self.allow)
            except ValueError:
                ok = False
            if not ok:
                log.warning("REJECT %s (not in FTP_ALLOW)", self.remote_ip)
                self.respond("421 Not allowed.")
                self.close_when_done()
                return
        super().handle()

    def on_connect(self) -> None:
        log.info("CONNECT %s:%s", self.remote_ip, self.remote_port)

    def on_disconnect(self) -> None:
        log.info("DISCONNECT %s:%s", self.remote_ip, self.remote_port)

    def on_login(self, username: str) -> None:
        log.info("LOGIN ok user=%s from %s", username, self.remote_ip)

    def on_login_failed(self, username: str, password: str) -> None:
        log.warning("LOGIN FAILED user=%r from %s (camera FTP user/password != .env)",
                    username, self.remote_ip)

    def log_cmd(self, cmd, arg, respcode, respstr) -> None:
        if getattr(self, "_log_debug", False):
            return                          # DEBUG mode already logs the full dialogue
        if respcode >= 400:
            if cmd in ("MKD", "XMKD") and "exist" in str(respstr).lower():
                return                      # camera re-creating an existing folder: fine
            log.warning("%s %s -> %s %s  (from %s)", cmd, self._rel(arg), respcode,
                        respstr, self.remote_ip)
        elif cmd in ("MKD", "XMKD", "DELE", "RNTO", "RMD"):
            log.info("%s %s -> %s", cmd, self._rel(arg), respcode)

    def on_file_received(self, file: str) -> None:
        path = Path(file)
        if path.suffix.lower() in PICTURE_EXT:
            path = rename_picture(path)
            size = path.stat().st_size if path.is_file() else 0
            FaceFTPHandler.pictures += 1
            log.info("PICTURE #%d %s (%d bytes) from %s",
                     FaceFTPHandler.pictures, self._rel(str(path)), size, self.remote_ip)
        else:
            size = path.stat().st_size if path.is_file() else 0
            log.info("file %s (%d bytes) from %s", self._rel(file), size, self.remote_ip)

    def on_incomplete_file_received(self, file: str) -> None:
        log.warning("INCOMPLETE %s from %s -> data channel broke (firewall / passive ports); "
                    "partial file removed", self._rel(file), self.remote_ip)
        try:
            os.remove(file)
        except OSError:
            pass


class QuietPyftpdlib(logging.Filter):
    """Drop pyftpdlib lines that duplicate ours; keep its timeouts/errors/partial transfers."""

    DUP = ("FTP session opened", "FTP session closed", "logged in.", "failed login.")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(d in msg for d in self.DUP):
            return False
        return not ("STOR " in msg and " completed=1 " in msg)   # PICTURE line covers it


def setup_logging() -> Path:
    log_file = Path(os.getenv("LOG_FILE", "logs/ftp.log"))
    if not log_file.is_absolute():
        log_file = ROOT / log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    to_file = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname).1s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[console, to_file], force=True)
    lib = logging.getLogger("pyftpdlib")
    if env_on("FTP_DEBUG"):
        lib.setLevel(logging.DEBUG)
    else:
        lib.setLevel(logging.INFO)
        lib.addFilter(QuietPyftpdlib())
    return log_file


def setup_console() -> None:
    """Windows: re-enable Ctrl+C if the parent process disabled it, and turn off
    QuickEdit (a click in the console pauses output -> logging blocks -> server hangs)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetConsoleCtrlHandler(None, False)
        k32.GetStdHandle.restype = wintypes.HANDLE
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = k32.GetStdHandle(-10)                      # STD_INPUT_HANDLE
        mode = wintypes.DWORD()
        if handle and k32.GetConsoleMode(handle, ctypes.byref(mode)):
            original = mode.value
            k32.SetConsoleMode(handle, (original | 0x0080) & ~0x0040)    # +EXTENDED, -QUICK_EDIT
            atexit.register(k32.SetConsoleMode, handle, original)
    except Exception:  # noqa: BLE001 - console tweaks must never block startup
        pass


def install_signals() -> None:
    def _interrupt(signum, frame):  # noqa: ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, signal.default_int_handler)
    for name in ("SIGBREAK", "SIGTERM"):   # SIGBREAK = Ctrl+Break / console close (Windows)
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, _interrupt)


def start_camera_keeper(ftp_host: str) -> None:
    """Re-apply Face Detection + FTP settings on start and while serve.py runs.

    Stopping the FTP server never changes the camera; UI tweaks / power blips can.
    Re-locking every CAMERA_KEEPALIVE_MINUTES (default 5) keeps uploads working.
    """
    minutes = float(os.getenv("CAMERA_KEEPALIVE_MINUTES", "5") or "0")

    def worker() -> None:
        # Do not bounce Scene.Type on start — clearing it stalls Face Detection
        # until a full AI restart; just lock the known-good values.
        apply_camera_config(ftp_host=ftp_host, bounce_scene=False)
        if minutes <= 0:
            return
        interval = max(60.0, minutes * 60.0)
        while True:
            time.sleep(interval)
            apply_camera_config(ftp_host=ftp_host, bounce_scene=False)

    threading.Thread(target=worker, name="camera-keeper", daemon=True).start()


def main() -> None:
    log_file = setup_logging()
    setup_console()
    install_signals()

    camera = os.getenv("DAHUA_HOST", "192.168.103.108")
    user = os.getenv("FTP_USER", "dahua")
    password = os.getenv("FTP_PASSWORD", "")
    port = int(os.getenv("FTP_PORT", "21"))
    pasv = parse_ports(os.getenv("FTP_PASV", "60000-60050"))
    folder = Path(os.getenv("FTP_DIR", "output/faces_camera"))
    if not folder.is_absolute():
        folder = ROOT / folder
    if not password:
        raise SystemExit("Set FTP_PASSWORD in .env")
    folder.mkdir(parents=True, exist_ok=True)

    bind = os.getenv("FTP_BIND", "").strip()
    if not bind:
        try:
            bind = lan_ip(camera)
        except OSError as exc:
            log.warning("No route to camera %s (%s) -> binding 0.0.0.0", camera, exc)
            bind = "0.0.0.0"
    shown = bind
    if bind == "0.0.0.0":
        try:
            shown = lan_ip(camera)
        except OSError:
            pass

    allow_text = os.getenv("FTP_ALLOW", "").strip()
    allow = [] if allow_text in ("", "*") else [
        ipaddress.ip_network(x.strip(), strict=False) for x in allow_text.split(",") if x.strip()]

    authorizer = DummyAuthorizer()
    # e=cd l=list r=read a=append d=delete f=rename m=mkdir w=store M=chmod T=mtime
    authorizer.add_user(user, password, str(folder), perm="elradfmwMT")

    handler = FaceFTPHandler
    handler.folder = folder
    handler.allow = allow
    handler.authorizer = authorizer
    handler.passive_ports = pasv
    handler.timeout = 300
    handler.banner = "Face inbox ready."

    try:
        server = FTPServer((bind, port), handler)
    except OSError as exc:
        raise SystemExit(
            f"Cannot bind {bind}:{port}: {exc}\n"
            f"Owner: Get-NetTCPConnection -LocalPort {port} -State Listen\n"
            "Old instance? powershell -ExecutionPolicy Bypass -File stop.ps1") from None
    server.max_cons = 64
    server.max_cons_per_ip = 16

    STOP_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    log.info("FTP inbox %s:%d user=%s -> %s", bind, port, user, folder)
    log.info("Camera FTP: server %s port %d | passive %d-%d | allow %s | pid %d",
             shown, port, pasv.start, pasv.stop - 1, allow_text or "any", os.getpid())
    log.info("Log %s | stop: Ctrl+C / Ctrl+Break / stop.ps1", log_file)
    log.info("Leave this running. Face pictures can take minutes; stopping early = 0 pictures.")

    # Lock camera Face Detection + snapshot->FTP every start (and periodically).
    start_camera_keeper(shown)

    reason = "error"
    ioloop = server.ioloop
    next_check = 0.0
    try:
        while True:
            ioloop.loop(0.5, blocking=False)    # select() wakes <= 0.5 s -> Ctrl+C is honored
            now = time.monotonic()
            if now >= next_check:
                next_check = now + 0.5
                if STOP_FILE.exists():
                    reason = "stop.ps1"
                    break
    except KeyboardInterrupt:
        reason = "interrupt"
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)       # don't interrupt the cleanup
        server.close_all()
        STOP_FILE.unlink(missing_ok=True)
        try:
            if PID_FILE.read_text().strip() == str(os.getpid()):
                PID_FILE.unlink()
        except OSError:
            pass
        log.info("FTP server stopped (%s). Pictures this run: %d", reason, FaceFTPHandler.pictures)


if __name__ == "__main__":
    main()