@echo off
setlocal
cd /d "%~dp0"

echo [ProspEl] Starting backend and frontend in separate windows...

start "ProspEl Backend" cmd /k "%~dp0start_backend_server.bat"
start "ProspEl Frontend" cmd /k "%~dp0start_frontend_server.bat"

echo [ProspEl] Done. Client URL: http://192.168.10.20:5173
pause
