@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running one-time DB repair v17: incoming invoice settlement rows...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Create venv first:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\repair_incoming_invoice_settlements.py %*
if errorlevel 1 (
  echo [ERROR] DB repair v17 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB repair v17 completed successfully.
echo.
exit /b 0
