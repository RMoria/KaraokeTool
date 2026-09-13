@echo off
cd /d "%~dp0"

rem De venv staat in de app-map, of - als die alleen-lezen is (bv. Program
rem Files) - in %LOCALAPPDATA%\KaraokeTool (B221). Kies de juiste.
set "VENV=venv"
if not exist "%VENV%\Scripts\python.exe" (
    if exist "%LOCALAPPDATA%\KaraokeTool\venv\Scripts\python.exe" (
        set "VENV=%LOCALAPPDATA%\KaraokeTool\venv"
        rem Data (input/output/cache) staat dan ook daar; geef dat door.
        set "KARAOKETOOL_DATA=%LOCALAPPDATA%\KaraokeTool"
    )
)

if not exist "%VENV%\Scripts\python.exe" (
    echo Virtuele omgeving niet gevonden.
    echo Draai eerst install.bat ^(ook na het verplaatsen van de projectmap^).
    pause
    exit /b 1
)

rem Kijken of er updates zijn (B444). Op de ACHTERGROND en zonder venster:
rem pip moet het netwerk op en dat mag het starten nooit ophouden. Het
rem script bepaalt zelf of het al aan de beurt is (hooguit eens per dag) en
rem schrijft zijn uitkomst naar docs\updates.json; de app leest dat bij de
rem VOLGENDE start en zet het in het logvenster. Het nieuws is dus altijd
rem een start te laat, en dat is beter dan een start die hangt op een trage
rem spiegelserver. Mislukt het, dan is er simpelweg geen nieuws.
if exist "%VENV%\Scripts\pythonw.exe" (
    start "" /b "%VENV%\Scripts\pythonw.exe" tools\check_updates.py
)

rem Start vensterloos via pythonw zodat dit cmd-venster meteen sluit; de
rem activiteit is zichtbaar in de GUI (paneel "Activiteit") en in logs\.
rem Terugval op python.exe als pythonw ontbreekt.
if exist "%VENV%\Scripts\pythonw.exe" (
    start "" "%VENV%\Scripts\pythonw.exe" KaraokeTool.py
) else (
    start "" "%VENV%\Scripts\python.exe" KaraokeTool.py
)
exit /b 0
