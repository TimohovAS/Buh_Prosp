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

call :is_port_listening 8000
if errorlevel 1 (
    echo Starting ProspEl backend...
    start "ProspEl Backend" /D "%ROOT%" cmd /k ""%BACKEND_PY%" run.py"
    call :wait_for_port 8000 "Backend" 30
    if errorlevel 1 exit /b %ERRORLEVEL%
) else (
    echo Backend already running on http://127.0.0.1:8000
)

call :is_port_listening 5173
if errorlevel 1 (
    echo Starting ProspEl frontend...
    start "ProspEl Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev -- --host 127.0.0.1"
) else (
    echo Frontend already running on http://127.0.0.1:5173
)

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
call :is_port_listening %PORT%
if not errorlevel 1 (
    echo WARNING: %NAME% port %PORT% already has a listening process.
)
exit /b 0

:is_port_listening
set "PORT=%~1"
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
exit /b %ERRORLEVEL%

:wait_for_port
set "PORT=%~1"
set "NAME=%~2"
set "TRIES=%~3"
echo Waiting for %NAME% on port %PORT%...
:wait_for_port_loop
call :is_port_listening %PORT%
if not errorlevel 1 (
    echo %NAME% is ready.
    exit /b 0
)
if "%TRIES%"=="0" (
    echo ERROR: %NAME% did not start on port %PORT%.
    echo Check the opened %NAME% terminal window for the Python traceback.
    exit /b 1
)
set /a TRIES-=1
timeout /t 1 /nobreak >nul
goto :wait_for_port_loop

:help
echo Usage:
echo   start_dev.cmd          Start backend and frontend in visible terminal windows
echo   start_dev.cmd --check  Check prerequisites without starting servers
exit /b 0
