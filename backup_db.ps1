$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$dbPath = Join-Path $projectRoot "prospel.db"
$backupDir = Join-Path $projectRoot "backups"

if (-not (Test-Path $dbPath)) {
  Write-Error "Database file not found: $dbPath"
}

New-Item -Path $backupDir -ItemType Directory -Force | Out-Null

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupPath = Join-Path $backupDir ("prospel_" + $timestamp + ".db")
Copy-Item -Path $dbPath -Destination $backupPath -Force

# Keep last 14 backups
Get-ChildItem -Path $backupDir -Filter "prospel_*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 14 |
  Remove-Item -Force

Write-Host "Backup done: $backupPath"
