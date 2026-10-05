@echo off
setlocal
rem KaraokeTool helper - start (v1.0.20).
set "HELPER_VERSION=1.0.29"
rem
rem install_helper.bat puts this file in %LOCALAPPDATA%\KaraokeToolHelper
rem and a shortcut "KaraokeTool helper" on the desktop. At every start it
rem   1. finds the laptop: the folder the installation came from, and when
rem      that does not answer the laptop by name, its last known addresses
rem      and at last the own network (tools\helper.py --find, which keeps
rem      what worked in share.txt);
rem   2. looks whether the share has a newer installer (HELPER_VERSION);
rem      then it runs a copy of that installer with /update in a window of
rem      its own and ends - the installer starts the helper again when it
rem      is done;
rem   3. starts the helper. When the helper sees a newer version after a
rem      job (exit code 3), all of this happens again.
rem Close the window to stop the helper.
rem v1.0.21: what it says goes into logs\helper_start.log as well, and the
rem whole logs folder onto the laptop, in KaraokeTool\logs\helpers\<this
rem computer> (the helper itself does that every five minutes too).
rem v1.0.22: <this computer> is its name as the helper list shows it
rem (``hostname``); %COMPUTERNAME% can be another name altogether.
rem v1.0.23: the helper shows itself in a window of its own with the
rem program's icon (pythonw, --window); this console is started minimized
rem by the shortcut. Exit code 4: the owner stopped it from that window
rem ("stop after the current round" or "stop now") - then this ends
rem without waiting for a key.
rem v1.0.24 (B653): the shortcut no longer starts this file - it starts
rem pythonw with tools\helper.py --start, which does all of this in the
rem helper's window, without a console. This file stays as the way in by
rem hand, and for a computer where the window cannot start.
cd /d "%~dp0"
set "HOST=%COMPUTERNAME%"
for /f "delims=" %%H in ('hostname 2^>nul') do set "HOST=%%H"
title KaraokeTool helper %HELPER_VERSION%
if not exist "logs" mkdir "logs"
set "LOG=%~dp0logs\helper_start.log"
rem One file that grows at every start: past a megabyte it starts anew.
if exist "%LOG%" for %%A in ("%LOG%") do if %%~zA GTR 1000000 move /y "%LOG%" "%~dp0logs\helper_start_previous.log" >nul
>> "%LOG%" echo ---- %DATE% %TIME% helper_start.bat %HELPER_VERSION%
rem What is left of the helper's old name, once nothing holds it.
if exist "%LOCALAPPDATA%\KaraokeToolHulp" rd /s /q "%LOCALAPPDATA%\KaraokeToolHulp" >nul 2>nul
rem An installation running (it started this helper's update): not twice.
set "BUSY="
if exist "installing.lock" (
    powershell -NoProfile -Command "if((Get-Item 'installing.lock').LastWriteTime -gt (Get-Date).AddHours(-3)){exit 1}" >nul 2>nul
    if errorlevel 1 set "BUSY=1"
)
if defined BUSY (
    call :say The helper is being updated right now; it starts by itself afterwards.
    timeout /t 15 >nul
    exit /b 0
)

:again
set "SHARE="
if exist "share.txt" set /p SHARE=<share.txt
if not exist "app\venv\Scripts\python.exe" goto :install
rem An environment whose Python is gone (removed by hand, say): install.
"app\venv\Scripts\python.exe" -c "" >nul 2>nul
if errorlevel 1 goto :install
"app\venv\Scripts\python.exe" "app\tools\helper.py" --find "%SHARE%" >nul 2>>"%LOG%"
if errorlevel 1 (
    call :say KaraokeTool on the laptop cannot be found ^(off, asleep, or the folder no longer shared?^). Looking again in a minute.
    timeout /t 60 /nobreak >nul
    goto :again
)
set /p SHARE=<share.txt
call :say Laptop found: %SHARE%
call :mirror
"app\venv\Scripts\python.exe" "app\tools\helper.py" --needs-update "%SHARE%" >nul 2>nul
if errorlevel 1 goto :install
set "PYW=app\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=app\venv\Scripts\python.exe"
"%PYW%" "app\tools\helper.py" --share "%SHARE%" --window
if errorlevel 4 if not errorlevel 5 goto :owner_stopped
if errorlevel 3 if not errorlevel 4 goto :again
echo.
call :say The helper has stopped.
call :mirror
pause
exit /b 0

:owner_stopped
call :say The helper was stopped from its window.
call :mirror
exit /b 0

:install
call :say A newer version is ready on %SHARE%; installing it now.
copy /y "%SHARE%\helper\install_helper.bat" "install_helper_run.bat" >nul 2>nul
if errorlevel 1 (
    call :say Could not fetch the installation from %SHARE%. Trying again in a minute.
    timeout /t 60 /nobreak >nul
    goto :again
)
call :mirror
rem Through cmd /c: a batch file started directly keeps its window open
rem at a prompt when it ends.
start "KaraokeTool helper - installatie" cmd /c ""%~dp0install_helper_run.bat" /update"
exit /b 0

rem ---- A line on the screen and in the log ---------------------------
:say
echo(%*
>> "%LOG%" echo(%TIME% %*
exit /b 0

rem ---- The logs onto the laptop (newer files only) --------------------
:mirror
if not defined SHARE exit /b 0
robocopy "%~dp0logs" "%SHARE%\logs\helpers\%HOST%" /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul 2>nul
exit /b 0
