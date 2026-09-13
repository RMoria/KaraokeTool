@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  KaraokeTool - installatie
echo ============================================
echo.

rem ---- Waarschuwing bij een tijdelijke/geblokkeerde map --------------
rem Windows-beveiligingsbeleid (AppLocker/Smart App Control/WDAC) blokkeert
rem vaak het laden van DLL's vanuit Temp- of Downloads-mappen ("DLL load
rem failed ... geblokkeerd door een beleid voor toepassingsbeheer", o.a. bij
rem PyAV/faster-whisper). We VERPLAATSEN niets: de app blijft staan waar
rem install.bat staat (B182). We waarschuwen alleen, zodat je zelf de map
rem eventueel naar bv. %USERPROFILE%\KaraokeTool kunt zetten en daar opnieuw
rem install.bat kunt draaien.
echo %~dp0 | findstr /I "\\Temp\\ \\Tmp\\ \\Downloads\\" >nul
if errorlevel 1 goto :after_relocate
echo LET OP: je draait vanuit een tijdelijke map:
echo   %~dp0
echo Windows kan daar het laden van DLL's blokkeren. Werkt het programma
echo straks niet ^(DLL-fout^), zet dan deze hele map ergens anders neer
echo ^(bv. %USERPROFILE%\KaraokeTool^) en draai install.bat daar opnieuw.
choice /C JN /M "Toch hier doorgaan [J/N]"
if errorlevel 2 goto :error
echo.

:after_relocate

rem ---- Python 3.12 zoeken ----------------------------------------
set "PYCMD="
py -3.12 -c "import sys" >nul 2>nul && set "PYCMD=py -3.12"
if not defined PYCMD python -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto :python_ok

echo Python 3.12 is niet gevonden.
where winget >nul 2>nul
if errorlevel 1 (
    echo Winget is niet beschikbaar. Installeer Python 3.12 handmatig via
    echo https://www.python.org/downloads/ en vink "Add to PATH" aan.
    goto :error
)
choice /C JN /M "Python 3.12 nu installeren via winget [J/N]"
if errorlevel 2 goto :error
winget install -e --id Python.Python.3.12
echo.
echo Python is geinstalleerd. Sluit dit venster en draai install.bat
echo OPNIEUW - het nieuwe PATH is pas in een nieuw venster zichtbaar.
pause
exit /b 0

:python_ok
echo [OK] Python 3.12 gevonden.

rem ---- ffmpeg zoeken (PATH of projectmap bin) --------------------
set "FFOK="
where ffmpeg >nul 2>nul && where ffprobe >nul 2>nul && set "FFOK=1"
if exist "bin\ffmpeg.exe" if exist "bin\ffprobe.exe" set "FFOK=1"
if defined FFOK goto :ffmpeg_ok

echo ffmpeg/ffprobe niet gevonden.
where winget >nul 2>nul
if errorlevel 1 (
    echo Winget is niet beschikbaar. Zie README.md voor handmatige
    echo installatie van ffmpeg ^(of zet de exe's in de map bin^).
    goto :ffmpeg_done
)
choice /C JN /M "ffmpeg nu installeren via winget [J/N]"
if errorlevel 2 (
    echo Zonder ffmpeg werkt de audioverwerking niet; zie README.md.
    goto :ffmpeg_done
)
winget install -e --id Gyan.FFmpeg
echo Let op: ffmpeg is pas zichtbaar in NIEUWE vensters.
goto :ffmpeg_done

:ffmpeg_ok
echo [OK] ffmpeg gevonden.
:ffmpeg_done

rem ---- Schrijfbare locatie voor venv + data (B221) ----------------
rem Is de app-map alleen-lezen (bv. Program Files), dan komen de venv en de
rem data (input/output/cache) in %LOCALAPPDATA%\KaraokeTool. De launcher
rem detecteert dat en geeft de datamap door aan het programma.
set "VENV=venv"
echo schrijftest> ".karaoketool_write_test" 2>nul
if exist ".karaoketool_write_test" (
    del ".karaoketool_write_test" >nul 2>nul
) else (
    set "VENV=%LOCALAPPDATA%\KaraokeTool\venv"
    echo LET OP: deze map is niet schrijfbaar.
    echo   venv en data komen in %LOCALAPPDATA%\KaraokeTool
    if not exist "%LOCALAPPDATA%\KaraokeTool" mkdir "%LOCALAPPDATA%\KaraokeTool"
)

rem ---- Virtuele omgeving ------------------------------------------
if exist "%VENV%\Scripts\python.exe" goto :venv_ok
echo Virtuele omgeving maken...
%PYCMD% -m venv "%VENV%"
if not exist "%VENV%\Scripts\python.exe" goto :error
:venv_ok
echo [OK] Virtuele omgeving aanwezig (%VENV%).

rem ---- Packages installeren ---------------------------------------
echo Packages installeren (dit kan even duren)...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

rem ---- Grote modellen (verplicht) ----------------------------------
rem De app leunt inmiddels sterk op Demucs (zang scheiden) en WhisperX
rem (forced alignment + energie-analyse van de zangstem). Ze worden daarom
rem altijd geinstalleerd (B195). We tonen vooraf de download-omvang en
rem geven de kans om te stoppen (Ctrl+C) voordat de grote download begint.
echo.
echo ============================================
echo  Grote modellen worden nu geinstalleerd
echo ============================================
echo Demucs en WhisperX trekken PyTorch mee: samen een grote download
echo (ongeveer 3 tot 5 GB, eenmalig). Deze modellen zijn nodig voor de
echo restzang-detectie, 'karaoke van origineel', de forced alignment en de
echo zangstem-analyse. Het ritme-anker gebruikt librosa (zit al in de
echo kerninstallatie).
echo.
echo Druk op een toets om te beginnen, of sluit dit venster (Ctrl+C) als je
echo nu geen grote download wilt.
pause

echo.
echo [1/2] Demucs (grote download via PyTorch)...
"%VENV%\Scripts\python.exe" -m pip install demucs || echo Let op: Demucs installeren mislukte; restzang-detectie en 'karaoke van origineel' vallen terug.

echo.
echo [2/2] WhisperX (grote download via PyTorch)...
"%VENV%\Scripts\python.exe" -m pip install whisperx || echo Let op: WhisperX installeren mislukte; forced alignment valt terug op de Whisper-timing.
rem (Het ritme-anker gebruikt librosa - dat zit al in de kerninstallatie,
rem  geen aparte download of compiler nodig.)

rem ---- Extra fonts (alleen ontbrekende ophalen) --------------------
echo.
echo Fonts controleren (alleen ontbrekende worden opgehaald)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ProgressPreference='SilentlyContinue';" ^
 "$dir=Join-Path (Get-Location) 'assets\fonts';" ^
 "if(-not (Test-Path $dir)){New-Item -ItemType Directory -Path $dir | Out-Null};" ^
 "$want=@('BebasNeue|bebasneue','Anton|anton','Oswald|oswald','Montserrat|montserrat','BarlowCondensed|barlowcondensed','ArchivoBlack|archivoblack','PassionOne|passionone','LilitaOne|lilitaone','TitanOne|titanone','ConcertOne|concertone','Bungee|bungee','LuckiestGuy|luckiestguy','Righteous|righteous','Audiowide|audiowide','RussoOne|russoone','Fredoka|fredoka','Baloo2|baloo2','Kanit|kanit','SairaCondensed|sairacondensed','Rubik|rubik');" ^
 "foreach($w in $want){" ^
 "  $p=$w.Split('|'); $name=$p[0]; $fam=$p[1];" ^
 "  if(Get-ChildItem -Path $dir -Filter ($name+'*.ttf') -ErrorAction SilentlyContinue){continue};" ^
 "  Write-Host ('  ophalen: ' + $name);" ^
 "  foreach($base in @('ofl','apache')){" ^
 "    try{$items=Invoke-RestMethod -Uri ('https://api.github.com/repos/google/fonts/contents/'+$base+'/'+$fam) -Headers @{'User-Agent'='karaoketool'} -ErrorAction Stop}catch{continue};" ^
 "    $ttf=@($items | Where-Object {$_.name -like ($name+'-Regular.ttf') -or $_.name -like ($name+'[[]wght[]].ttf')});" ^
 "    if($ttf.Count -eq 0){$ttf=@($items | Where-Object {$_.name -like '*.ttf'})};" ^
 "    foreach($f in $ttf){$safe=($f.name -replace '\[.*?\]','');try{Invoke-WebRequest -Uri $f.download_url -OutFile (Join-Path $dir $safe) -ErrorAction Stop; Write-Host ('    '+$safe)}catch{Write-Host ('    mislukt: '+$f.name)}};" ^
 "    break;" ^
 "  }" ^
 "}" ^
 "Write-Host '[OK] Fonts gecontroleerd.'"

rem ---- Controle ----------------------------------------------------
echo.
echo Installatie controleren...
"%VENV%\Scripts\python.exe" -c "import numpy, soundfile, faster_whisper, librosa, scipy, rapidfuzz, PySide6, PIL, langdetect; print('[OK] Kernpakketten aanwezig (faster-whisper ' + __import__('importlib.metadata', fromlist=['version']).version('faster-whisper') + ')')"
if errorlevel 1 goto :error
echo Grote modellen:
"%VENV%\Scripts\python.exe" -c "import importlib.util as u;[print('   - '+n+': '+('aanwezig' if u.find_spec(m) else 'niet geinstalleerd')) for n,m in (('Demucs','demucs'),('WhisperX','whisperx'))]"

echo.
echo ============================================
echo  Installatie gereed.
echo  Start het programma met KaraokeToolGUI.bat
echo ============================================
pause
exit /b 0

:error
echo.
echo ============================================
echo  INSTALLATIE MISLUKT
echo  Lees de foutmeldingen hierboven.
echo ============================================
pause
exit /b 1
