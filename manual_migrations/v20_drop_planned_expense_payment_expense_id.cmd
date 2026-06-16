@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running DB migration v20: drop planned_expense_payments.expense_id...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v20_drop_planned_expense_payment_expense_id.py %*
if errorlevel 1 (
  echo [ERROR] DB migration v20 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB migration v20 completed successfully.
echo.
exit /b 0
