@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running one-time DB migration v3: drop project.contract_id...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  echo [HINT] Create venv first:
  echo        C:\Python314\python.exe -m venv venv
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v3_drop_project_contract_id.py
if errorlevel 1 (
  echo [ERROR] DB migration v3 failed.
  exit /b 1
)

echo.
echo [ProspEl] Migration v3 completed successfully.
echo.
exit /b 0
