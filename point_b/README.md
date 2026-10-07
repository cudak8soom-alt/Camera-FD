# Point B — your collection PC

Receives face pictures from every Point A site over VPN.

## Setup (once)

```powershell
cd D:\FD\point_b
copy .env.example .env
notepad .env
```

Set `SYNC_TOKEN` (same value you give each Point A).

```powershell
powershell -ExecutionPolicy Bypass -File .\run_receive.ps1
```

Pictures land in `received/<SITE_ID>/`.

Keep VPN connected. Leave this running while Point A sites upload.
