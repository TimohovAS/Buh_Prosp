@echo off
setlocal
cd /d "%~dp0"

echo.
echo [ProspEl] Service installation started...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Run:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

if not exist "frontend\package.json" (
  echo [ERROR] frontend\package.json not found.
  exit /b 1
)

set "NSSM=C:\Tools\nssm\win64\nssm.exe"
if not exist "%NSSM%" (
  where nssm >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] nssm.exe not found.
    echo [HINT] Put nssm at C:\Tools\nssm\win64\nssm.exe or add nssm to PATH.
    exit /b 1
  )
  for /f "delims=" %%i in ('where nssm') do (
    set "NSSM=%%i"
    goto :nssm_found
  )
)

:nssm_found
echo [ProspEl] NSSM: %NSSM%

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found in PATH.
  exit /b 1
)

set "NPM_CMD="
for /f "delims=" %%i in ('where npm.cmd 2^>nul') do (
  set "NPM_CMD=%%i"
  goto :npm_found
)
for /f "delims=" %%i in ('where npm') do (
  set "NPM_CMD=%%i"
  goto :npm_found
)

:npm_found
if "%NPM_CMD%"=="" (
  echo [ERROR] npm executable path not found.
  exit /b 1
)
echo [ProspEl] npm: %NPM_CMD%

if not exist "logs" mkdir logs

echo [ProspEl] Removing old services if exist...
sc.exe stop ProspEl-Web >nul 2>nul
sc.exe stop ProspEl-Backend >nul 2>nul
"%NSSM%" remove ProspEl-Web confirm >nul 2>nul
"%NSSM%" remove ProspEl-Backend confirm >nul 2>nul

echo [ProspEl] Installing ProspEl-Backend...
"%NSSM%" install ProspEl-Backend "%CD%\venv\Scripts\python.exe" "-m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
if errorlevel 1 (
  echo [ERROR] Failed to install ProspEl-Backend.
  exit /b 1
)
"%NSSM%" set ProspEl-Backend AppDirectory "%CD%"
"%NSSM%" set ProspEl-Backend Start SERVICE_AUTO_START
"%NSSM%" set ProspEl-Backend AppStdout "%CD%\logs\backend.out.log"
"%NSSM%" set ProspEl-Backend AppStderr "%CD%\logs\backend.err.log"
"%NSSM%" set ProspEl-Backend AppRotateFiles 1
"%NSSM%" set ProspEl-Backend AppRotateOnline 1

echo [ProspEl] Installing ProspEl-Web...
"%NSSM%" install ProspEl-Web "%NPM_CMD%" "run dev -- --host 0.0.0.0 --port 5173"
if errorlevel 1 (
  echo [ERROR] Failed to install ProspEl-Web.
  exit /b 1
)
"%NSSM%" set ProspEl-Web AppDirectory "%CD%\frontend"
"%NSSM%" set ProspEl-Web Start SERVICE_AUTO_START
"%NSSM%" set ProspEl-Web AppStdout "%CD%\logs\web.out.log"
"%NSSM%" set ProspEl-Web AppStderr "%CD%\logs\web.err.log"
"%NSSM%" set ProspEl-Web AppRotateFiles 1
"%NSSM%" set ProspEl-Web AppRotateOnline 1

echo [ProspEl] Starting services...
sc.exe start ProspEl-Backend
if errorlevel 1 (
  echo [ERROR] Failed to start ProspEl-Backend.
  exit /b 1
)
timeout /t 2 /nobreak >nul
sc.exe start ProspEl-Web
if errorlevel 1 (
  echo [ERROR] Failed to start ProspEl-Web.
  exit /b 1
)

echo [ProspEl] Health checks...
powershell -NoProfile -Command "$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/prospel' -TimeoutSec 10; Write-Host ('Backend: ' + $r.StatusCode)"
if errorlevel 1 (
  echo [ERROR] Backend health check failed.
  exit /b 1
)
powershell -NoProfile -Command "$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 10; Write-Host ('Web: ' + $r.StatusCode)"
if errorlevel 1 (
  echo [ERROR] Web health check failed.
  exit /b 1
)

echo.
echo [ProspEl] Services installed and running.
echo [ProspEl] URL: http://192.168.10.20:5173
echo.
exit /b 0
