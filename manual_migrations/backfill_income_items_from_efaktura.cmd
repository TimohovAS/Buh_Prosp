@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Backfilling Income invoice items from outgoing eFaktura XML...
echo [ProspEl] Working dir: %CD%
echo.
echo Recommended first run:
echo   manual_migrations\backfill_income_items_from_efaktura.cmd --dry-run
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\backfill_income_items_from_efaktura.py %*
if errorlevel 1 (
  echo [ERROR] Income item backfill from eFaktura failed.
  exit /b 1
)

echo.
echo [ProspEl] Income item backfill from eFaktura completed successfully.
echo.
exit /b 0
