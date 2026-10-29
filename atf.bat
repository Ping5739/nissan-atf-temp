@echo off
rem Launcher for atf_monitor.py (Nissan Y62/Z62 ATF + coolant temperature, ELM327-mode adapter).
rem Keep this file in the same folder as atf_monitor.py. Double-click to run.
rem
rem Optional switches (from a Command Prompt):
rem   atf.bat                 live ATF readings on COM6 (no coolant)
rem   atf.bat -l              also log to atf_log_YYYYMMDD_HHMMSS.csv
rem   atf.bat -p COM5 -f      different port, show degrees F
rem   atf.bat -c -i 5         include engine coolant, read every 5 seconds
rem
rem   -p PORT   COM port (default COM6)
rem   -l        log readings to a timestamped CSV in this folder
rem   -f        Fahrenheit
rem   -c        also read engine coolant (off by default)
rem   -i SECS   seconds between readings (default 2)

setlocal EnableExtensions
cd /d "%~dp0"

set "PORT=COM6"
set "INTERVAL=2"
set "EXTRA="
set "LOG=0"
set "COOLANT=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="-p" (set "PORT=%~2" & shift & shift & goto parse)
if /i "%~1"=="-i" (set "INTERVAL=%~2" & shift & shift & goto parse)
if /i "%~1"=="-l" (set "LOG=1" & shift & goto parse)
if /i "%~1"=="-f" (set "EXTRA=%EXTRA% --fahrenheit" & shift & goto parse)
if /i "%~1"=="-c" (set "COOLANT=1" & shift & goto parse)
if /i "%~1"=="-h" goto help
if /i "%~1"=="/?" goto help
echo Unknown option: %~1
goto help

:parsed
if "%COOLANT%"=="0" set "EXTRA=%EXTRA% --no-coolant"
if not exist "atf_monitor.py" (
    echo Can't find atf_monitor.py in %~dp0
    echo Put atf.bat and atf_monitor.py in the same folder.
    goto end
)

rem Find a working Python ("python" can be a Microsoft Store stub, so test it)
set "PY="
python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY (py -c "import sys" >nul 2>&1 && set "PY=py")
if not defined PY (
    echo Python not found. Install it from python.org and tick "Add Python to PATH".
    goto end
)

rem Install pyserial on first run if needed
%PY% -c "import serial" >nul 2>&1
if errorlevel 1 (
    echo Installing pyserial...
    %PY% -m pip install --user pyserial
    if errorlevel 1 (
        echo pyserial install failed.
        goto end
    )
)

if "%LOG%"=="1" (
    for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"
)
if "%LOG%"=="1" (
    set "EXTRA=%EXTRA% --log "atf_log_%STAMP%.csv""
    echo Logging to %~dp0atf_log_%STAMP%.csv
)

echo Close any other OBD software or terminal using %PORT% first.
echo Press Ctrl+C to stop.
echo.
%PY% atf_monitor.py --port %PORT% --interval %INTERVAL% %EXTRA%
goto end

:help
echo.
echo Usage: atf.bat [-p PORT] [-l] [-f] [-c] [-i SECS]
echo   -p PORT   COM port (default COM6)
echo   -l        log readings to a timestamped CSV
echo   -f        Fahrenheit
echo   -c        also read engine coolant (off by default)
echo   -i SECS   seconds between readings (default 2)

:end
echo.
pause
endlocal
