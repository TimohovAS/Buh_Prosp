@echo off
cd /d "%~dp0\frontend"

echo.
echo Starting ProspEl frontend...
echo.
echo After start: open http://localhost:5173/
echo.
npm run dev
pause
