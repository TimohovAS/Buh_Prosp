@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Repairing bank -> expense matches...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\repair_bank_expense_matches.py
if errorlevel 1 (
  echo [ERROR] Bank/expense repair failed.
  exit /b 1
)

echo.
echo [ProspEl] Bank/expense repair completed successfully.
echo.
exit /b 0
