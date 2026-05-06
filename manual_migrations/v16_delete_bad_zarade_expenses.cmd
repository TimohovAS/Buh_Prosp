@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running one-time DB cleanup v16: delete bad Zarade salary expenses...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Create venv first:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\delete_bad_zarade_expenses.py
if errorlevel 1 (
  echo [ERROR] DB cleanup v16 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB cleanup v16 completed successfully.
echo.
exit /b 0
