@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Running DB migration v21: eFaktura PDF download settings...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\migrate_v21_efaktura_file_downloads.py %*
if errorlevel 1 (
  echo [ERROR] DB migration v21 failed.
  exit /b 1
)

echo.
echo [ProspEl] DB migration v21 completed successfully.
echo.
exit /b 0
