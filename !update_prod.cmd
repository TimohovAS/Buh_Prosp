@echo off
setlocal
cd /d "%~dp0"

echo.
echo [ProspEl] Production update started...
echo [ProspEl] Working dir: %CD%
echo.

:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo =======================================================
    echo [ERROR] Administrator privileges required!
    echo Please right-click update_prod.cmd and select "Run as administrator"
    echo so that Windows Services can be restarted automatically.
    echo =======================================================
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] git not found in PATH.
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Create venv first:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

if not exist "frontend\package.json" (
  echo [ERROR] frontend\package.json not found.
  exit /b 1
)

if exist "backup_db.ps1" (
  echo [ProspEl] Creating DB backup...
  powershell -NoProfile -ExecutionPolicy Bypass -File ".\backup_db.ps1"
  if errorlevel 1 (
    echo [WARN] Backup step failed, continue anyway.
  )
) else (
  echo [WARN] backup_db.ps1 not found, skipping backup.
)

echo [ProspEl] Pulling latest code from GitHub...
for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set "GIT_BRANCH=%%i"
if "%GIT_BRANCH%"=="" (
  echo [ERROR] Failed to detect current git branch.
  exit /b 1
)
if /I "%GIT_BRANCH%"=="HEAD" (
  echo [ERROR] Detached HEAD detected. Please checkout a branch before update.
  exit /b 1
)
echo [ProspEl] Current branch: %GIT_BRANCH%
git pull --ff-only origin %GIT_BRANCH%
if errorlevel 1 (
  echo [ERROR] git pull failed.
  exit /b 1
)

echo [ProspEl] Installing backend dependencies...
.\venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Backend dependency install failed.
  exit /b 1
)

echo [ProspEl] Running DB migrations...
.\venv\Scripts\python.exe backend\scripts\migrate_v3_drop_project_contract_id.py
if errorlevel 1 (
  echo [ERROR] DB migration failed.
  exit /b 1
)
.\venv\Scripts\python.exe backend\scripts\migrate_v4_erp.py
if errorlevel 1 (
  echo [ERROR] DB migration failed.
  exit /b 1
)
.\venv\Scripts\python.exe backend\scripts\migrate_v5_expense_contracts.py
if errorlevel 1 (
  echo [ERROR] DB migration failed.
  exit /b 1
)

echo [ProspEl] Installing frontend dependencies...
call npm --prefix ".\frontend" install
if errorlevel 1 (
  echo [ERROR] Frontend dependency install failed.
  exit /b 1
)

echo [ProspEl] Building frontend...
call npm --prefix ".\frontend" run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  exit /b 1
)

echo [ProspEl] Restarting services...
net stop ProspEl-Web >nul 2>&1
net stop ProspEl-Backend >nul 2>&1

net start ProspEl-Backend
if errorlevel 1 (
  echo [ERROR] Failed to start ProspEl-Backend service.
  exit /b 1
)

timeout /t 2 /nobreak >nul

net start ProspEl-Web
if errorlevel 1 (
  echo [ERROR] Failed to start ProspEl-Web service.
  exit /b 1
)

echo [ProspEl] Health checks...
powershell -NoProfile -Command "$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/prospel' -TimeoutSec 10; Write-Host ('Backend: ' + $r.StatusCode)"
if errorlevel 1 (
  echo [ERROR] Backend health check failed.
  exit /b 1
)

powershell -NoProfile -Command "$ok=$false; try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1/' -TimeoutSec 6; Write-Host ('Web (80): ' + $r.StatusCode); $ok=$true } catch {}; if (-not $ok) { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 10; Write-Host ('Web (5173): ' + $r.StatusCode) }"
if errorlevel 1 (
  echo [ERROR] Web health check failed.
  exit /b 1
)

echo.
echo [ProspEl] Update completed successfully.
echo [ProspEl] URL: http://192.168.10.20/
echo.
exit /b 0
