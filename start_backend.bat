@echo off
cd /d "%~dp0"

echo Stopping any process on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Killing PID %%a
    taskkill /PID %%a /F 2>nul
    timeout /t 2 /nobreak >nul
)

echo.
echo Starting ProspEl backend...
echo.
echo After start: open http://localhost:8000/api/prospel
echo If you see {"app":"ProspEl","status":"ok"} - backend is correct.
echo.
venv\Scripts\python.exe run.py
pause
