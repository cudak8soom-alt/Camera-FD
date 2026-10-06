# Face inbox (Dahua FTP)

Windows FTP inbox for Dahua Face Detection snapshot uploads. The camera detects faces and uploads pictures to this PC over FTP. There is no local face-recognition model — this project only receives and stores images.

## How it works

1. `serve.py` starts an FTP server on this PC.
2. On start (and every `CAMERA_KEEPALIVE_MINUTES`), it locks known-good Face Detection + FTP settings on the camera via HTTP Digest API.
3. Face snapshots land under `FTP_DIR` (default `output/faces_camera`).

The PC LAN IP used as the camera’s FTP server is **auto-detected** (NIC that routes to `DAHUA_HOST`) unless you set `FTP_BIND`.

## Requirements

- Windows PC on the same LAN as the camera
- Python 3.10+ recommended
- Camera reachable at `DAHUA_HOST` (web UI / CGI)
- Admin rights once, to open the firewall

## Setup

```powershell
cd D:\FD
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your camera login and an FTP password the camera will use.

Open the firewall (Administrator PowerShell, once per machine):

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_firewall.ps1
```

Optional — allow only the camera:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_firewall.ps1 -Camera 192.168.103.108
```

## Run

```powershell
python serve.py
```

Leave this window running. Face pictures can take a while after a person appears; stopping early means no uploads.

Stop options:

- `Ctrl+C` / `Ctrl+Break` in the console
- `powershell -ExecutionPolicy Bypass -File .\stop.ps1`

Manual camera lock (same settings as startup, without starting FTP):

```powershell
python fix_camera.py
```

## Configuration (`.env`)

Copy from `.env.example`. Main keys:

| Variable | Purpose |
|----------|---------|
| `DAHUA_HOST` | Camera IP |
| `DAHUA_USER` / `DAHUA_PASSWORD` | Camera web login (needed to push config) |
| `FTP_USER` / `FTP_PASSWORD` / `FTP_PORT` | FTP inbox credentials (written to camera NAS/FTP) |
| `FTP_DIR` | Local folder for uploads |
| `CAMERA_ROTATE` | Image rotation Face AI needs on this model (`1` = 90°) |
| `CAMERA_KEEPALIVE_MINUTES` | Re-apply camera settings while running (`0` = only on start) |

Optional:

| Variable | Purpose |
|----------|---------|
| `FTP_BIND` | Force FTP listen IP (default: auto-detect toward camera) |
| `FTP_PASV` | Passive port range (default `60000-60050`) |
| `FTP_ALLOW` | Comma-separated allowed client nets (`*` or empty = any) |
| `FTP_DEBUG` | `1` = full FTP dialogue in log |
| `LOG_FILE` | Log path (default `logs/ftp.log`) |

`.env` is gitignored — do not commit passwords.

## If this PC’s IP changes

With no `FTP_BIND` set: **no `.env` edits**. Restart `serve.py`. It re-detects the LAN IP and updates the camera’s `NAS[0].Address`.

If `serve.py` was already running when the IP changed, restart it — keepalive reuses the IP from startup.

Update `.env` only if you hardcoded `FTP_BIND`, or if the **camera** IP changed (`DAHUA_HOST`).

## Moving to another PC on the same network

1. Copy the project (include `.env` or create one from `.env.example`).
2. Install Python deps: `pip install -r requirements.txt`.
3. Run `setup_firewall.ps1` as Administrator on the **new** PC.
4. **Stop** `serve.py` on the old PC (only one inbox should own the camera).
5. Run `python serve.py` on the new PC.

Usually **no `.env` changes** if the camera IP and passwords are unchanged. The new PC’s IP is detected and pushed to the camera automatically. Pictures are stored on the new PC under `FTP_DIR`.

Change `DAHUA_HOST` only if the camera address differs on that network.

## Project layout

| Path | Role |
|------|------|
| `serve.py` | FTP inbox + camera keepalive |
| `camera_config.py` | Known-good Face Detection / FTP settings |
| `fix_camera.py` | Apply camera settings without starting FTP |
| `setup_firewall.ps1` | Inbound rules for FTP + passive ports |
| `stop.ps1` | Kill whatever is listening on the FTP port |
| `output/faces_camera/` | Received pictures |
| `logs/ftp.log` | Rotating log |

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `Cannot bind ...:21` | Something else on port 21 → `stop.ps1`, or change `FTP_PORT` |
| Login failed from camera | `FTP_USER` / `FTP_PASSWORD` in `.env` must match what the camera uses (serve.py writes them on lock) |
| Connects but incomplete files | Firewall / passive ports — re-run `setup_firewall.ps1` |
| No pictures | Leave `serve.py` running; confirm log shows `Camera locked` and `PICTURE` lines |
| Camera config skipped | Set `DAHUA_PASSWORD` in `.env` |
| Wrong FTP host after IP change | Restart `serve.py` |

Debug FTP dialogue:

```text
FTP_DEBUG=1
```

in `.env`, then restart `serve.py`.

## Notes

- Live view may look rotated 90° when `CAMERA_ROTATE=1` — required for Face Detection on the IPC-HDBW5241E-ZE used with this project.
- Do not change Face Detection / FTP settings in the camera UI while relying on this inbox; keepalive will overwrite them toward the known-good set.
- Stopping the FTP server does not clear camera settings; starting another PC’s `serve.py` will retarget FTP to that PC.
