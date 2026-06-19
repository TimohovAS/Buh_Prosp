@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running DB migration v23: worker weekly pay and trip pricing mode...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v23_worker_weekly_and_trip_mode.py %*
if errorlevel 1 (
  echo [ERROR] DB migration v23 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB migration v23 completed successfully.
echo.
exit /b 0
