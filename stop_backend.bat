@echo off
echo Stopping all processes on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /PID %%a /F
    timeout /t 1 /nobreak >nul
)
echo Done. Run start_backend.bat to start fresh.
pause
