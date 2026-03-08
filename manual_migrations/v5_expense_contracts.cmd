@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running one-time DB migration v5: expense contracts...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Create venv first:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v5_expense_contracts.py
if errorlevel 1 (
  echo [ERROR] DB migration v5 failed.
  exit /b 1
)

echo.
echo [ProspEl] Migration v5 completed successfully.
echo.
exit /b 0
