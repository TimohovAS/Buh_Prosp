@echo off
setlocal
cd /d "%~dp0"

echo [ProspEl] Starting backend on 127.0.0.1:8000 ...
echo [ProspEl] Health check URL: http://127.0.0.1:8000/api/prospel
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] Python venv is missing: venv\Scripts\python.exe
  echo [HINT] Run: python -m venv venv
  pause
  exit /b 1
)

venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
