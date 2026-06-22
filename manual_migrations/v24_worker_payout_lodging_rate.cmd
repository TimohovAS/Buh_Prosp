@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running DB migration v24: worker payout lodging night rate...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v24_worker_payout_lodging_rate.py %*
if errorlevel 1 (
  echo [ERROR] DB migration v24 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB migration v24 completed successfully.
echo.
exit /b 0
