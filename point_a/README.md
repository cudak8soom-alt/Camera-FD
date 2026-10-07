# Point A — customer PC (camera side)

**Everything for the camera site is in this folder.**

```text
Camera  →  this PC (serve.py)  →  output/faces_camera/
                                      ↓
                                 sync_to_b.py  →  Point B (us)
```

---

## One-time setup

### 1. Install Python

Python 3.10+ from [python.org](https://www.python.org/downloads/)  
Tick **Add Python to PATH**.

### 2. Open VPN

Install the VPN we sent you. Leave it **Connected**.

### 3. Settings file

```powershell
cd D:\FD\point_a
copy .env.example .env
notepad .env
```

Fill in:

| Section | What to set |
|---------|-------------|
| Camera | `DAHUA_HOST`, passwords (we give you these) |
| Send to us | `SITE_ID`, `POINT_B_URL`, `SYNC_TOKEN` (we give you these) |

### 4. Install + firewall (once)

```powershell
cd D:\FD\point_a
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Administrator PowerShell (once):

```powershell
cd D:\FD\point_a
powershell -ExecutionPolicy Bypass -File .\setup_firewall.ps1
```

---

## Every day — leave **two** windows open

**Window 1 — receive from camera**

```powershell
cd D:\FD\point_a
powershell -ExecutionPolicy Bypass -File .\run_camera.ps1
```

Good sign: lines with `PICTURE`

**Window 2 — send to us**

```powershell
cd D:\FD\point_a
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Good sign: lines with `Sent OK`

---

## What’s in this folder

| File | What it does |
|------|----------------|
| `serve.py` | Main camera inbox (FTP) |
| `camera_config.py` | Keeps camera Face Detection settings correct |
| `run_camera.ps1` | Starts the camera inbox |
| `sync_to_b.py` | Sends new pictures to Point B |
| `run.ps1` | Starts the sync |
| `.env` | Your settings (passwords + Point B address) |
| `output/faces_camera/` | Pictures saved on this PC |
| `setup_firewall.ps1` | One-time Windows firewall (Admin) |
| `stop.ps1` | Stop the FTP inbox if needed |

---

## Problems?

| Message | Try |
|---------|-----|
| Point B not reachable | Turn VPN on; ask us if Point B is running |
| No PICTURE lines | Is `run_camera.ps1` still open? Camera on same LAN? |
| `.env` placeholders | Edit `.env` — replace `100.x.x.x` and `paste_token_here` |
