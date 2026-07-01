@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Repairing duplicate pending cash withdrawals...
echo [ProspEl] Working dir: %CD%
echo.
echo Recommended first run:
echo   manual_migrations\repair_duplicate_pending_cash_withdrawals.cmd --dry-run
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\repair_duplicate_pending_cash_withdrawals.py %*
if errorlevel 1 (
  echo [ERROR] Duplicate pending cash withdrawal repair failed.
  exit /b 1
)

echo.
echo [ProspEl] Duplicate pending cash withdrawal repair completed successfully.
echo.
exit /b 0
