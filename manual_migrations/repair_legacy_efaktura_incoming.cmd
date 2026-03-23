@echo off
setlocal
cd /d "%~dp0\.."

echo.
echo [ProspEl] Repairing legacy incoming eFaktura records...
echo [ProspEl] Working dir: %CD%
echo.

if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found: venv\Scripts\python.exe
  exit /b 1
)

.\venv\Scripts\python.exe backend\scripts\repair_legacy_efaktura_incoming.py
if errorlevel 1 (
  echo [ERROR] Legacy incoming eFaktura repair failed.
  exit /b 1
)

echo.
echo [ProspEl] Legacy incoming eFaktura repair completed successfully.
echo.
exit /b 0
