"""Point A — send new face pictures to Point B.

Same folder as serve.py. Uses the same .env file.

  Window 1:  run_camera.ps1   (camera → this PC)
  Window 2:  run.ps1          (this PC → Point B)
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PICTURE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
PLACEHOLDERS = ("100.x.x.x", "paste_token_here", "change_me", "your_")

log = logging.getLogger("point_a")


def setup_logging() -> Path:
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "sync.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
            ),
        ],
    )
    return log_file


def source_dir() -> Path:
    raw = os.getenv("SOURCE_DIR", "").strip() or os.getenv("FTP_DIR", "output/faces_camera")
    folder = Path(raw)
    if not folder.is_absolute():
        folder = (ROOT / folder).resolve()
    return folder


def state_path() -> Path:
    return ROOT / "sync_state.json"


def load_state(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def already_sent(state: dict, rel: str, size: int, mtime_ns: int) -> bool:
    prev = state.get(rel)
    return bool(prev) and prev.get("size") == size and prev.get("mtime_ns") == mtime_ns


def iter_pictures(folder: Path):
    if not folder.is_dir():
        return
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in PICTURE_EXT:
            yield path


def looks_placeholder(value: str) -> bool:
    low = value.lower()
    return any(p in low for p in PLACEHOLDERS)


def upload_one(
    session: requests.Session,
    base_url: str,
    token: str,
    site_id: str,
    src: Path,
    rel: str,
) -> None:
    url = base_url.rstrip("/") + "/upload"
    with src.open("rb") as fh:
        resp = session.post(
            url,
            headers={"X-Sync-Token": token, "X-Site-Id": site_id},
            data={"site_id": site_id, "relative_path": rel},
            files={"file": (src.name, fh, "application/octet-stream")},
            timeout=120,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(str(body))


def sync_once(
    session: requests.Session,
    folder: Path,
    state: dict[str, dict],
    base_url: str,
    token: str,
    site_id: str,
) -> int:
    sent = 0
    for path in sorted(iter_pictures(folder), key=lambda p: str(p)):
        try:
            st = path.stat()
        except OSError:
            continue
        rel = path.relative_to(folder).as_posix()
        if already_sent(state, rel, st.st_size, st.st_mtime_ns):
            continue
        try:
            upload_one(session, base_url, token, site_id, path, rel)
        except Exception as exc:
            log.warning("Could not send %s — %s", rel, exc)
            continue
        state[rel] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "rel": rel}
        sent += 1
        log.info("Sent OK  %s", rel)
    return sent


def point_b_ok(session: requests.Session, base_url: str) -> bool:
    try:
        resp = session.get(base_url.rstrip("/") + "/health", timeout=10)
        return resp.status_code == 200 and resp.json().get("ok") is True
    except requests.RequestException:
        return False


def main() -> None:
    setup_logging()

    site_id = os.getenv("SITE_ID", "").strip()
    base_url = os.getenv("POINT_B_URL", "").strip()
    token = os.getenv("SYNC_TOKEN", "").strip()

    if not site_id or not base_url or not token:
        raise SystemExit(
            "Missing SITE_ID / POINT_B_URL / SYNC_TOKEN in .env\n"
            "Edit point_a\\.env (section 2), then run run.ps1 again."
        )
    if looks_placeholder(base_url) or looks_placeholder(token):
        raise SystemExit(
            "Your .env still has example Point B values.\n"
            "Replace POINT_B_URL and SYNC_TOKEN, save, try again."
        )

    folder = source_dir()
    state_file = state_path()
    state = load_state(state_file)
    folder.mkdir(parents=True, exist_ok=True)

    log.info("Site name : %s", site_id)
    log.info("Send to   : %s", base_url)
    log.info("Watching  : %s", folder)
    log.info("Leave this window open. Press Ctrl+C to stop.")
    log.info("-" * 50)

    session = requests.Session()
    wait_note_at = 0.0
    while True:
        if not point_b_ok(session, base_url):
            now = time.monotonic()
            if now >= wait_note_at:
                log.warning("Waiting for Point B… check VPN is Connected.")
                wait_note_at = now + 60.0
        else:
            sent = sync_once(session, folder, state, base_url, token, site_id)
            save_state(state_file, state)
            if sent:
                log.info("Sent %d new picture(s).", sent)
        time.sleep(15)


if __name__ == "__main__":
    main()
