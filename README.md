# Face Detection — Point A / Point B

```text
Point A (customer)              Point B (you)
──────────────────              ─────────────
point_a/serve.py → faces
point_a/sync  ──── VPN ──────►  point_b/receive_server.py
                                → received/<SITE_ID>/
```

| Folder | Who | Guide |
|--------|-----|--------|
| [`point_a/`](point_a/) | Customer PC next to camera | [point_a/README.md](point_a/README.md) |
| [`point_b/`](point_b/) | Your collection PC | Run `run_receive.ps1` |

## Quick start

**Point B first**

```powershell
cd point_b
copy .env.example .env
notepad .env
powershell -ExecutionPolicy Bypass -File .\run_receive.ps1
```

**Point A (two windows)**

```powershell
cd point_a
copy .env.example .env
notepad .env
powershell -ExecutionPolicy Bypass -File .\run_camera.ps1
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

VPN (e.g. Tailscale) must be connected on both PCs.  
`POINT_B_URL` uses Point B’s VPN IP. Do not expose port 8787 publicly.
