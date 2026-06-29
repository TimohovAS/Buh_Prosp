@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "FRONTEND_DIR=%ROOT%frontend"
set "BACKEND_PY=%ROOT%venv\Scripts\python.exe"

if /I "%~1"=="--help" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="/?" goto :help

call :check
if errorlevel 1 exit /b %ERRORLEVEL%

if /I "%~1"=="--check" (
    echo OK: dev prerequisites found.
    exit /b 0
)

call :port_warning 8000 "Backend"
call :port_warning 5173 "Frontend"

echo Starting ProspEl backend...
start "ProspEl Backend" /D "%ROOT%" cmd /k ""%BACKEND_PY%" run.py"

echo Starting ProspEl frontend...
start "ProspEl Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev -- --host 127.0.0.1"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo.
echo Close the opened terminal windows to stop the servers.
exit /b 0

:check
if not exist "%BACKEND_PY%" (
    echo ERROR: backend Python was not found:
    echo   %BACKEND_PY%
    echo Create the virtual environment and install backend dependencies first.
    exit /b 1
)

if not exist "%ROOT%run.py" (
    echo ERROR: run.py was not found in:
    echo   %ROOT%
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo ERROR: frontend package.json was not found in:
    echo   %FRONTEND_DIR%
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found in PATH.
    echo Install Node.js or open a terminal where npm is available.
    exit /b 1
)

exit /b 0

:port_warning
set "PORT=%~1"
set "NAME=%~2"
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo WARNING: %NAME% port %PORT% already has a listening process.
)
exit /b 0

:help
echo Usage:
echo   start_dev.cmd          Start backend and frontend in visible terminal windows
echo   start_dev.cmd --check  Check prerequisites without starting servers
exit /b 0
