@echo off
setlocal
cd /d "%~dp0\frontend"

echo [ProspEl] Starting frontend on 0.0.0.0:5173 ...
echo [ProspEl] Open from clients: http://192.168.10.20:5173
echo.

npm run dev -- --host 0.0.0.0 --port 5173
pause
