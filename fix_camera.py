"""Manually re-apply Face Detection + FTP settings (same as serve.py startup).

  python fix_camera.py
"""

from __future__ import annotations

import sys

from camera_config import apply_camera_config


def main() -> int:
    print("Applying known-good camera Face Detection + FTP settings...")
    ok = apply_camera_config(bounce_scene=False)
    if not ok:
        print("Failed. Check DAHUA_HOST / DAHUA_USER / DAHUA_PASSWORD in .env")
        return 1
    print("OK. Start or keep running:  python serve.py")
    print("Live view may look rotated 90° (CAMERA_ROTATE) — required for face AI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
