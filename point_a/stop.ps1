# Kills whatever is listening on the FTP port (default 21).
#   powershell -ExecutionPolicy Bypass -File .\stop.ps1
param([int]$Port = 21)

$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conns) { Write-Host "Nothing listening on port $Port."; exit 0 }

foreach ($pid_ in ($conns.OwningProcess | Sort-Object -Unique)) {
    $p = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
    Write-Host "Killing PID $pid_ ($($p.ProcessName))"
    Stop-Process -Id $pid_ -Force
}
