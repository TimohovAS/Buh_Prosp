@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running DB migration v19: counterparty loans...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v19_counterparty_loans.py %*
if errorlevel 1 (
  echo [ERROR] DB migration v19 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB migration v19 completed successfully.
echo.
exit /b 0
