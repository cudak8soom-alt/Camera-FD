"""Point B: HTTP inbox that receives face pictures from Point A over VPN.

Run:   python receive_server.py
Health: GET /health
Upload: POST /upload  (multipart: file + relative_path; header X-Sync-Token)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

PICTURE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
SITE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

log = logging.getLogger("point_b")
app = Flask(__name__)


def receive_dir() -> Path:
    folder = Path(os.getenv("RECEIVE_DIR", "received"))
    if not folder.is_absolute():
        folder = ROOT / folder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def sync_token() -> str:
    return os.getenv("SYNC_TOKEN", "").strip()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def authorized() -> bool:
    expected = sync_token()
    if not expected:
        return False
    got = (request.headers.get("X-Sync-Token") or "").strip()
    return got == expected


def safe_site(site_id: str) -> str | None:
    site_id = (site_id or "").strip() or "default"
    if not SITE_RE.match(site_id):
        return None
    return site_id


def safe_rel_path(rel: str) -> Path | None:
    """Reject absolute paths, drive letters, and .. traversal."""
    rel = (rel or "").replace("\\", "/").strip().lstrip("/")
    if not rel or rel.startswith("..") or "/../" in f"/{rel}/":
        return None
    parts = Path(rel).parts
    if any(p in ("..", "") or p.endswith(":") for p in parts):
        return None
    path = Path(*parts)
    if path.suffix.lower() not in PICTURE_EXT:
        return None
    return path


@app.get("/health")
def health():
    return jsonify(ok=True, role="point_b", receive_dir=str(receive_dir()))


@app.post("/upload")
def upload():
    if not sync_token():
        return jsonify(ok=False, error="SYNC_TOKEN not set on server"), 503
    if not authorized():
        return jsonify(ok=False, error="unauthorized"), 401

    site = safe_site(request.form.get("site_id", request.headers.get("X-Site-Id", "")))
    if site is None:
        return jsonify(ok=False, error="invalid site_id"), 400

    rel = safe_rel_path(request.form.get("relative_path", ""))
    if rel is None:
        return jsonify(ok=False, error="invalid relative_path"), 400

    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(ok=False, error="missing file"), 400

    dest = receive_dir() / site / rel
    try:
        dest.resolve().relative_to(receive_dir().resolve())
    except ValueError:
        return jsonify(ok=False, error="path escapes receive dir"), 400

    dest.parent.mkdir(parents=True, exist_ok=True)
    file.save(dest)
    size = dest.stat().st_size
    log.info("RECEIVED site=%s %s (%d bytes) from %s",
             site, dest.relative_to(receive_dir()), size, request.remote_addr)
    return jsonify(ok=True, site_id=site, path=str(rel).replace("\\", "/"), bytes=size)


def main() -> None:
    setup_logging()
    token = sync_token()
    if not token:
        raise SystemExit("Set SYNC_TOKEN in point_b/.env")

    host = os.getenv("BIND", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("PORT", "8787"))
    folder = receive_dir()
    log.info("Point B receive server %s:%d -> %s", host, port, folder)
    log.info("Auth: X-Sync-Token | health: GET /health | upload: POST /upload")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
