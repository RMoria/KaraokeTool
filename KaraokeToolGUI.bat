@echo off
cd /d "%~dp0"

rem The venv is in the app folder, or - if that is read-only (Program
rem Files, say) - in %LOCALAPPDATA%\KaraokeTool (B221). Pick the right one.
set "VENV=venv"
if not exist "%VENV%\Scripts\python.exe" (
    if exist "%LOCALAPPDATA%\KaraokeTool\venv\Scripts\python.exe" (
        set "VENV=%LOCALAPPDATA%\KaraokeTool\venv"
        rem The data (input/output/cache) is then there too; pass that on.
        set "KARAOKETOOL_DATA=%LOCALAPPDATA%\KaraokeTool"
    )
)

if not exist "%VENV%\Scripts\python.exe" (
    echo Virtuele omgeving niet gevonden.
    echo Draai eerst install.bat ^(ook na het verplaatsen van de projectmap^).
    pause
    exit /b 1
)

rem Look for updates (B444). In the BACKGROUND and without a window:
rem pip has to go onto the network and that may never hold up the start.
rem The script decides for itself whether its turn has come (once a day at
rem most) and writes its answer to docs\updates.json; the app reads that on
rem the NEXT start and puts it in the log window. So the news is always one
rem start late, which is better than a start that hangs on a slow mirror.
rem If it fails, there is simply no news.
if exist "%VENV%\Scripts\pythonw.exe" (
    start "" /b "%VENV%\Scripts\pythonw.exe" tools\check_updates.py
)

rem Start windowless through pythonw so this cmd window closes at once;
rem the activity is visible in the GUI (the "Activiteit" panel) and in logs\.
rem Falls back to python.exe when pythonw is missing.
if exist "%VENV%\Scripts\pythonw.exe" (
    start "" "%VENV%\Scripts\pythonw.exe" KaraokeTool.py
) else (
    start "" "%VENV%\Scripts\python.exe" KaraokeTool.py
)
exit /b 0
