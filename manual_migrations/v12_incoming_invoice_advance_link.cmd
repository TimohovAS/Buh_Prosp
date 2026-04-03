@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running one-time DB migration v12: incoming invoice advance-closing link...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Create venv first:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v12_incoming_invoice_advance_link.py
if errorlevel 1 (
  echo [ERROR] DB migration v12 failed.
  exit /b 1
)

echo.
echo [ProspEl] Migration v12 completed successfully.
echo.
exit /b 0
