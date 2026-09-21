@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  KaraokeTool - installatie
echo ============================================
echo.

rem ---- Warning for a temporary or blocked folder --------------------
rem Windows security policy (AppLocker/Smart App Control/WDAC) often
rem blocks the loading of DLLs from Temp or Downloads folders ("DLL load
rem failed ... blocked by an application control policy", among others
rem with PyAV/faster-whisper). We MOVE nothing: the app stays where
rem install.bat is (B182). We only warn, so that you can put the folder
rem somewhere like %USERPROFILE%\KaraokeTool yourself and run install.bat
rem again from there.
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

rem ---- Look for Python 3.12 --------------------------------------
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

rem ---- Look for ffmpeg (PATH or the project's bin folder) --------
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

rem ---- A writable place for the venv and the data (B221) ---------
rem If the app folder is read-only (Program Files, say), the venv and the
rem data (input/output/cache) go to %LOCALAPPDATA%\KaraokeTool. The
rem launcher sees that and passes the data folder to the program.
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

rem ---- Virtual environment ----------------------------------------
if exist "%VENV%\Scripts\python.exe" goto :venv_ok
echo Virtuele omgeving maken...
%PYCMD% -m venv "%VENV%"
if not exist "%VENV%\Scripts\python.exe" goto :error
:venv_ok
echo [OK] Virtuele omgeving aanwezig (%VENV%).

rem ---- Install the packages ---------------------------------------
echo Packages installeren (dit kan even duren)...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

rem ---- The large models (always) -----------------------------------
rem The app leans heavily on Demucs (separating the vocals) and WhisperX
rem (forced alignment plus the energy analysis of the vocal stem), so
rem they are always installed (B195). The download size is shown first
rem and there is a chance to stop (Ctrl+C) before it starts.
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
rem (The rhythm anchor uses librosa - that is in the core install
rem  already, no separate download and no compiler needed.)

rem ---- Extra fonts (fetch only the missing ones) ------------------
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

rem ---- Check -------------------------------------------------------
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
