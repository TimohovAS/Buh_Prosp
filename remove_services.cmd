@echo off
setlocal
cd /d "%~dp0"

echo [ProspEl] Stopping services...
sc.exe stop ProspEl-Web >nul 2>nul
sc.exe stop ProspEl-Backend >nul 2>nul

set "NSSM=C:\Tools\nssm\win64\nssm.exe"
if not exist "%NSSM%" (
  where nssm >nul 2>nul
  if errorlevel 1 (
    echo [WARN] nssm.exe not found. Trying sc delete...
    sc.exe delete ProspEl-Web >nul 2>nul
    sc.exe delete ProspEl-Backend >nul 2>nul
    echo [ProspEl] Done.
    exit /b 0
  )
  for /f "delims=" %%i in ('where nssm') do (
    set "NSSM=%%i"
    goto :nssm_found
  )
)

:nssm_found
echo [ProspEl] NSSM: %NSSM%

"%NSSM%" remove ProspEl-Web confirm >nul 2>nul
"%NSSM%" remove ProspEl-Backend confirm >nul 2>nul

echo [ProspEl] Services removed.
exit /b 0
