"""Known-good Dahua Face Detection + FTP settings for this project.

Applied automatically when serve.py starts, and again every CAMERA_KEEPALIVE_MINUTES
while it runs, so stopping/restarting the inbox (or tweaking the camera UI) does
not leave Face Detection / FTP broken.

Also: python fix_camera.py
"""

from __future__ import annotations

import logging
import os
import socket
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("faces")


def _cam_pass() -> str:
    return os.getenv("DAHUA_PASSWORD") or os.getenv("DAHUA_PASS") or ""


def lan_ip(camera_host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((camera_host, 80))
        return s.getsockname()[0]


def desired_pairs(ftp_host: str | None = None) -> dict[str, str]:
    """Settings that make Face Detection upload pictures to this PC's FTP."""
    rotate = os.getenv("CAMERA_ROTATE", "1").strip() or "1"
    host = ftp_host or os.getenv("FTP_BIND", "").strip()
    if not host or host == "0.0.0.0":
        try:
            host = lan_ip(os.getenv("DAHUA_HOST", "192.168.103.108"))
        except OSError:
            host = ""

    pairs: dict[str, str] = {
        # Face AI is rotation-sensitive on IPC-HDBW5241E-ZE
        "VideoInOptions[0].Rotate90": rotate,
        "VideoInOptions[0].NormalOptions.Rotate90": rotate,
        "VideoInOptions[0].NightOptions.Rotate90": rotate,
        "VideoAnalyseGlobal[0].Scene.Type": "FaceDetection",
        "VideoAnalyseGlobal[0].Scene.Depth": "Far",
        "VideoAnalyseGlobal[0].Scene.Detail.FaceAngleRight": "90",
        "VideoAnalyseGlobal[0].Scene.Detail.FaceAngleUp": "90",
        "VideoAnalyseGlobal[0].Scene.Detail.FaceRollRigth": "90",
        # Office mount: keep Far even if UI / rule toggles reset Depth to Near
        "VideoAnalyseModule[0][2].Sensitivity": "100",
        "VideoAnalyseModule[0][2].AntiDisturbance": "false",
        "VideoAnalyseModule[0][1].Sensitivity": "100",
        "VideoAnalyseModule[0][1].AntiDisturbance": "false",
        "VideoAnalyseRule[0][0].Enable": "false",  # HeatMap
        "VideoAnalyseRule[0][2].Enable": "false",  # NumberStat
        "VideoAnalyseRule[0][1].Enable": "true",
        "VideoAnalyseRule[0][1].EventHandler.SnapshotEnable": "true",
        "VideoAnalyseRule[0][1].EventHandler.SnapshotChannels[0]": "0",
        "VideoAnalyseRule[0][1].EventHandler.SnapshotTimes": "2",
        "VideoAnalyseRule[0][1].EventHandler.Delay": "0",
        "VideoAnalyseRule[0][1].EventHandler.MessageEnable": "true",
        "VideoAnalyseRule[0][1].EventHandler.LogEnable": "true",
        "VideoAnalyseRule[0][1].Config.MinQuality": "1",
        "VideoAnalyseRule[0][1].Config.SnapThreshold": "1",
        "VideoAnalyseRule[0][1].Config.MinDuration": "0",
        "VideoAnalyseRule[0][1].Config.SizeFilter.MinSize[0]": "8",
        "VideoAnalyseRule[0][1].Config.SizeFilter.MinSize[1]": "8",
        # Module-level size filter (was 60 after reboot and blocked faces)
        "VideoAnalyseModule[0][2].SizeFilter.MinSize[0]": "8",
        "VideoAnalyseModule[0][2].SizeFilter.MinSize[1]": "8",
        "VideoAnalyseModule[0][2].SnapShot": "true",
        "VideoAnalyseModule[0][1].SizeFilter.MinSize[0]": "8",
        "VideoAnalyseModule[0][1].SizeFilter.MinSize[1]": "8",
        "MotionDetect[0].Enable": "false",
        "MotionDetect[0].EventHandler.SnapshotEnable": "false",
        # Face pics on this firmware use Event + VideoDetect FTP paths
        "RecordStoragePoint[0].EventSnapShot.FTP": "true",
        "RecordStoragePoint[1].EventSnapShot.FTP": "true",
        "RecordStoragePoint[0].VideoDetectSnapShot.FTP": "true",
        "RecordStoragePoint[1].VideoDetectSnapShot.FTP": "true",
        "RecordStoragePoint[0].AlarmSnapShot.FTP": "true",
        "RecordStoragePoint[1].AlarmSnapShot.FTP": "true",
        "RecordStoragePoint[0].TimingSnapShot.FTP": "false",
        "RecordStoragePoint[1].TimingSnapShot.FTP": "false",
    }
    for day in range(8):
        pairs[f"Snap[0].TimeSection[{day}][0]"] = "393222 00:00:00-23:59:59"

    if host:
        pairs.update(
            {
                "NAS[0].Enable": "true",
                "NAS[0].Protocol": "FTP",
                "NAS[0].Address": host,
                "NAS[0].Port": os.getenv("FTP_PORT", "21"),
                "NAS[0].UserName": os.getenv("FTP_USER", "dahua"),
                "NAS[0].Directory": "/",
            }
        )
        ftp_password = os.getenv("FTP_PASSWORD", "")
        if ftp_password:
            pairs["NAS[0].Password"] = ftp_password

    return pairs


def _table_batches(pairs: dict[str, str]) -> list[dict[str, str]]:
    """Split by config table — one giant GET exceeds this camera's URL limit (Bad Request)."""
    buckets: dict[str, dict[str, str]] = {}
    for key, value in pairs.items():
        table = key.split("[", 1)[0] if "[" in key else key.split(".", 1)[0]
        buckets.setdefault(table, {})[key] = value
    # Stable order: AI / storage first, NAS last
    order = (
        "VideoInOptions",
        "VideoAnalyseGlobal",
        "VideoAnalyseRule",
        "MotionDetect",
        "RecordStoragePoint",
        "Snap",
        "NAS",
    )
    out: list[dict[str, str]] = []
    for name in order:
        if name in buckets:
            out.append(buckets.pop(name))
    out.extend(buckets.values())
    return out


def apply_camera_config(*, ftp_host: str | None = None, bounce_scene: bool = False) -> bool:
    """Push desired settings to the camera. Returns True if all batches OK."""
    host = os.getenv("DAHUA_HOST", "192.168.103.108")
    user = os.getenv("DAHUA_USER", "admin")
    password = _cam_pass()
    if not password:
        log.warning("Camera config skipped: set DAHUA_PASSWORD in .env")
        return False

    pairs = desired_pairs(ftp_host)
    session = requests.Session()
    session.auth = HTTPDigestAuth(user, password)
    base = f"http://{host}"

    def _set(batch: dict[str, str]) -> bool:
        query = "&".join(f"{k}={quote(str(v), safe=':-.')}" for k, v in batch.items())
        try:
            resp = session.get(
                f"{base}/cgi-bin/configManager.cgi?action=setConfig&{query}",
                timeout=20,
            )
        except requests.RequestException as exc:
            log.warning("Camera config failed: %s", exc)
            return False
        ok = resp.ok and resp.text.strip().upper().startswith("OK")
        if not ok:
            log.warning("Camera config rejected: %s", resp.text.strip()[:160])
        return ok

    failed = 0
    for batch in _table_batches(pairs):
        if not _set(batch):
            failed += 1

    # Depth sometimes snaps back to Near after rule/UI changes — pin Far last.
    if not _set({"VideoAnalyseGlobal[0].Scene.Depth": "Far"}):
        failed += 1

    if bounce_scene:
        _set({"VideoAnalyseGlobal[0].Scene.Type": ""})
        _set({"VideoAnalyseGlobal[0].Scene.Type": "FaceDetection"})

    if failed:
        log.warning("Camera lock incomplete (%d table batch(es) failed)", failed)
        return False

    log.info(
        "Camera locked: FaceDetection on, Rotate90=%s, snapshot->FTP, FTP server=%s",
        pairs.get("VideoInOptions[0].Rotate90"),
        pairs.get("NAS[0].Address", "?"),
    )
    return True
