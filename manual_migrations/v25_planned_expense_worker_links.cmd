@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running DB migration v25: planned expense worker links...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v25_planned_expense_worker_links.py %*
if errorlevel 1 (
  echo [ERROR] DB migration v25 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB migration v25 completed successfully.
echo.
exit /b 0
