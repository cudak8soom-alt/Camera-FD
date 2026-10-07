# Run once from an ADMIN PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup_firewall.ps1
# Optional: restrict to the camera only:  -Camera 192.168.103.108

param(
    [int]$FtpPort = 21,
    [string]$PassiveRange = "60000-60050",
    [string]$Camera = ""
)

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Run this in an Administrator PowerShell."; exit 1
}

$name = "Face inbox FTP"
Get-NetFirewallRule -DisplayName "$name*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule

$common = @{
    Direction = "Inbound"; Action = "Allow"; Protocol = "TCP"
    Profile   = "Any"   # a LAN marked "Public" would otherwise still block
}
if ($Camera) { $common.RemoteAddress = $Camera }

New-NetFirewallRule -DisplayName "$name (control $FtpPort)"    -LocalPort $FtpPort      @common | Out-Null
New-NetFirewallRule -DisplayName "$name (passive $PassiveRange)" -LocalPort $PassiveRange @common | Out-Null

Write-Host "Firewall rules added:" -ForegroundColor Green
Get-NetFirewallRule -DisplayName "$name*" | Format-Table DisplayName, Enabled, Direction, Action
