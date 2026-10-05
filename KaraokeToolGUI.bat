@echo off
setlocal
cd /d "%~dp0"

rem KaraokeTool - start, and install or bring up to date what is needed
rem (v1.0.19: install.bat went up in this file; v1.0.20: Python 3.13 and
rem an NVIDIA card).
rem
rem At every start this checks, in a moment, whether the installation is
rem complete and up to date (tools\setup_check.py): the packages the
rem program asks for, the steps of the setup, the choice about Roformer.
rem Only when something is missing or changed does it install - the first
rem time everything, asking about the large download and Roformer once;
rem later only what is needed, without questions. Everything it shows
rem then also goes into logs\install.log (the run before is kept as
rem install_previous.log). Then the program starts.
rem
rem v1.0.20: the program runs on Python 3.13 (tools\find_python.bat). An
rem environment made with another Python is made anew and the old one is
rem set aside in _to_delete. With an NVIDIA card the versions that
rem compute on the card are installed and the card is tested once
rem (python -m modules.cuda): the program uses it only for what worked.
rem v1.0.22: Python 3.12 is gone from every computer, so the fallback on
rem it and the clean-up of it went as well.

rem ---- A writable place for the venv, the data and the log (B221) --
rem If the app folder is read-only (Program Files, say), the venv and the
rem data (input/output/cache) go to %LOCALAPPDATA%\KaraokeTool; the program
rem is told where the data is.
set "VENV=venv"
set "LOGDIR=logs"
set "CONFIGDIR=config"
set "READONLY="
echo schrijftest> ".karaoketool_write_test" 2>nul
if exist ".karaoketool_write_test" (
    del ".karaoketool_write_test" >nul 2>nul
) else (
    set "VENV=%LOCALAPPDATA%\KaraokeTool\venv"
    set "LOGDIR=%LOCALAPPDATA%\KaraokeTool\logs"
    set "CONFIGDIR=%LOCALAPPDATA%\KaraokeTool\config"
    set "READONLY=1"
    set "KARAOKETOOL_DATA=%LOCALAPPDATA%\KaraokeTool"
    if not exist "%LOCALAPPDATA%\KaraokeTool" mkdir "%LOCALAPPDATA%\KaraokeTool"
)
if not exist "%CONFIGDIR%" mkdir "%CONFIGDIR%"
set "CHOICE=%CONFIGDIR%\roformer_choice.txt"
rem Its name up to v1.0.19.
if exist "%CONFIGDIR%\roformer_keuze.txt" if not exist "%CHOICE%" move /y "%CONFIGDIR%\roformer_keuze.txt" "%CHOICE%" >nul 2>nul
set "ROFORMER=?"
if exist "%CHOICE%" set /p ROFORMER=<"%CHOICE%"
rem An installation from before v1.0.19 with the Roformer environment:
rem the owner chose it then.
if "%ROFORMER%"=="?" if exist "%VENV%_separator\Scripts\python.exe" set "ROFORMER=J"

rem ---- Up to date? -----------------------------------------------------
call tools\find_python.bat none
set "CUDA="
set "CUDAFLAG="
where nvidia-smi >nul 2>nul && set "CUDA=1"
if defined CUDA set "CUDAFLAG=--cuda"
rem What v1.0.20 and v1.0.21 kept about Python 3.12.
for %%F in (python_choice.txt python312_keep.txt) do if exist "%CONFIGDIR%\%%F" del "%CONFIGDIR%\%%F" >nul 2>nul
if exist "%LOGDIR%\python312_home.txt" del "%LOGDIR%\python312_home.txt" >nul 2>nul
set "FIRST="
if not exist "%VENV%\Scripts\python.exe" (
    set "FIRST=1"
    goto :setup
)
if not defined PYCMD goto :setup
%PYCMD% tools\setup_check.py --same-python "%VENV%" >nul 2>nul || goto :setup
if /i "%ROFORMER%"=="J" if not exist "%VENV%_separator\Scripts\python.exe" goto :setup
%PYCMD% tools\setup_check.py "%VENV%" %ROFORMER% %CUDAFLAG% >nul 2>nul
if errorlevel 1 goto :setup
goto :start_app

:setup
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOG=%LOGDIR%\install.log"
if exist "%LOG%" move /y "%LOG%" "%LOGDIR%\install_previous.log" >nul 2>nul
if exist "%LOGDIR%\install_vorige.log" del "%LOGDIR%\install_vorige.log" >nul 2>nul
> "%LOG%" echo KaraokeTool KaraokeToolGUI.bat - install/update - %DATE% %TIME%
>> "%LOG%" echo Folder: %~dp0
ver >> "%LOG%"

echo ============================================
if defined FIRST (echo  KaraokeTool - installation) else (echo  KaraokeTool - update)
echo ============================================
echo.

rem ---- Warning for a temporary or blocked folder --------------------
rem Windows security policy (AppLocker/Smart App Control/WDAC) often
rem blocks the loading of DLLs from Temp or Downloads folders ("DLL load
rem failed ... blocked by an application control policy", among others
rem with PyAV/faster-whisper). We MOVE nothing: the app stays where
rem KaraokeToolGUI.bat is (B182). We only warn, so that you can put the folder
rem somewhere like %USERPROFILE%\KaraokeTool yourself and start KaraokeToolGUI.bat
rem again from there.
echo %~dp0 | findstr /I "\\Temp\\ \\Tmp\\ \\Downloads\\" >nul
if errorlevel 1 goto :after_relocate
echo NOTE: you are running from a temporary folder:
echo   %~dp0
echo Windows may block loading DLLs there. If the program does not work
echo later ^(DLL error^), put this whole folder somewhere else
echo ^(e.g. %USERPROFILE%\KaraokeTool^) and start KaraokeToolGUI.bat there.
choice /C YN /M "Continue here anyway [Y/N]"
if errorlevel 2 goto :error
echo.

:after_relocate

rem ---- Python 3.13 ------------------------------------------------
call tools\find_python.bat ask
if defined PYCMD goto :python_ok
echo Python 3.13 was not found.
>> "%LOG%" echo Python 3.13 not found.
echo Install Python 3.13 from https://www.python.org/downloads/ ^(tick
echo "Add to PATH"^) and start KaraokeToolGUI.bat again.
goto :error

:python_ok
set "TEE=%PYCMD% tools\tee_run.py "%LOG%" --"
call :say [OK] Python %PYVER% found: %PYCMD%

rem ---- Look for ffmpeg (PATH, or the project's bin folder) --------
rem v1.0.23: winget installs it for this user (no rights needed) and
rem keeps it up to date; it is brought up to date at every setup.
set "FFOK="
where ffmpeg >nul 2>nul && where ffprobe >nul 2>nul && set "FFOK=1"
if not defined FFOK if exist "bin\ffmpeg.exe" if exist "bin\ffprobe.exe" set "FFOK=1"
winget list -e --id Gyan.FFmpeg >nul 2>nul && %TEE% winget upgrade -e --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements
if defined FFOK goto :ffmpeg_ok

call :say ffmpeg/ffprobe not found.
where winget >nul 2>nul
if errorlevel 1 (
    echo Winget is not available. See README.md for installing ffmpeg
    echo by hand ^(or put the exe files in the bin folder^).
    >> "%LOG%" echo ffmpeg not found and winget is missing.
    goto :ffmpeg_done
)
choice /C YN /M "Install ffmpeg now with winget [Y/N]"
if errorlevel 2 (
    echo Without ffmpeg the audio processing does not work; see README.md.
    >> "%LOG%" echo ffmpeg: not installed, by choice.
    goto :ffmpeg_done
)
%TEE% winget install -e --id Gyan.FFmpeg --scope user
call :say Note: ffmpeg is only visible in NEW windows.
goto :ffmpeg_done

:ffmpeg_ok
call :say [OK] ffmpeg found.
:ffmpeg_done

if not defined READONLY goto :writable_ok
call :say NOTE: this folder cannot be written.
call :say   venv and data go to %LOCALAPPDATA%\KaraokeTool
:writable_ok

rem ---- An NVIDIA card? ---------------------------------------------
rem cu126 still carries the older cards. With the card's index next to
rem the ordinary one, pip takes PyTorch from the card's: its local version
rem label ("+cu126") sorts above the same version without one.
set "TORCHIDX="
if defined CUDA (
    call :say NVIDIA card found; the versions that compute on the card are installed.
    %TEE% nvidia-smi
    set "TORCHIDX=--extra-index-url https://download.pytorch.org/whl/cu126"
)

rem ---- Environments made with another Python are set aside -----------
if exist "%VENV%\Scripts\python.exe" (
    %PYCMD% tools\setup_check.py --same-python "%VENV%" >nul 2>nul || call :set_aside "%VENV%" || goto :error
)
if exist "%VENV%_separator\Scripts\python.exe" (
    %PYCMD% tools\setup_check.py --same-python "%VENV%_separator" >nul 2>nul || call :set_aside "%VENV%_separator"
)

rem ---- Virtual environment ----------------------------------------
if exist "%VENV%\Scripts\python.exe" goto :venv_ok
echo Making the virtual environment...
%TEE% %PYCMD% -m venv "%VENV%"
if not exist "%VENV%\Scripts\python.exe" goto :error
:venv_ok
call :say [OK] Virtual environment present: %VENV%

rem ---- Install the packages ---------------------------------------
echo Installing packages (this may take a while)...
%TEE% "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
%TEE% "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

rem ---- The large models (always) -----------------------------------
rem The app leans heavily on Demucs (separating the vocals) and WhisperX
rem (forced alignment plus the energy analysis of the vocal stem), so
rem they are always installed (B195). The download size is shown first
rem and there is a chance to stop (Ctrl+C) before it starts.
echo.
echo ============================================
echo  Installing the large models now
echo ============================================
echo Demucs and WhisperX bring PyTorch along: together a large download
echo (about 3 to 5 GB, once). These models are needed for the
echo residual vocal detection, 'karaoke from original', the forced alignment and the
echo vocal analysis. The rhythm anchor uses librosa (already in the
echo core installation).
echo.
echo Note: because everything also goes into the log, pip shows no
echo progress bar. A large download may look silent for minutes.
if defined FIRST (
    echo Press a key to begin, or close this window ^(Ctrl+C^) if you
    echo do not want a large download now.
    pause
)

echo.
rem WhisperX first: it pins its PyTorch, and Demucs is content with it.
echo [1/3] WhisperX (large download through PyTorch)...
%TEE% "%VENV%\Scripts\python.exe" -m pip install whisperx %TORCHIDX% || call :say Note: installing WhisperX failed; the forced alignment falls back to the Whisper timing.

echo.
echo [2/3] Demucs...
%TEE% "%VENV%\Scripts\python.exe" -m pip install -U "demucs>=4.1" %TORCHIDX% || call :say Note: installing Demucs failed; residual vocal detection and 'karaoke from original' fall back.
if defined CUDA %TEE% "%VENV%\Scripts\python.exe" -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || call :say Note: installing the CUDA libraries for Whisper failed; Whisper then listens on the processor.
rem (The rhythm anchor uses librosa - that is in the core install
rem  already, no separate download and no compiler needed.)

rem ---- Careful separation with Roformer (optional, B591) ----------
rem python-audio-separator pins its own torch and numpy, so it gets an
rem environment of its own next to the program's venv; the program
rem starts it as a subprocess, the way it starts Demucs. Its models go
rem into a models folder beside that environment, not into Temp.
echo.
echo [3/3] Careful separation with Roformer (optional; the choice is remembered)
echo An environment of its own next to the program, with PyTorch and two models:
echo about 3 GB together. Needed for the 'Roformer' setting, the clean
echo music of High and Normal, and test 1.5.14; without it Demucs is used.
if "%ROFORMER%"=="?" (
    choice /C YN /M "Install Roformer separation [Y/N]"
    if errorlevel 2 (set "ROFORMER=N") else (set "ROFORMER=J")
)
> "%CHOICE%" echo %ROFORMER%
if /i "%ROFORMER%"=="N" (
    >> "%LOG%" echo Roformer: not chosen.
    goto :after_roformer
)
set "SEPENV=%VENV%_separator"
set "SEPBASE=."
if not "%VENV%"=="venv" set "SEPBASE=%LOCALAPPDATA%\KaraokeTool"
if not exist "%SEPENV%\Scripts\python.exe" %TEE% %PYCMD% -m venv "%SEPENV%"
if not exist "%SEPENV%\Scripts\python.exe" (
    call :say Note: the Roformer environment could not be made.
    goto :after_roformer
)
%TEE% "%SEPENV%\Scripts\python.exe" -m pip install --upgrade pip
rem v1.0.15: librosa 1.0 no longer brings audioread, and audio-separator
rem still imports it on its first line - every Roformer separation of the
rem second 1.5.14 night stopped there. Both named, so pip keeps them.
set "SEPKIND=cpu"
if defined CUDA set "SEPKIND=gpu"
%TEE% "%SEPENV%\Scripts\python.exe" -m pip install --upgrade "audio-separator[%SEPKIND%]" audioread "librosa>=0.10,<1" %TORCHIDX% || (
    call :say Note: installing audio-separator failed; the 'Roformer' setting falls back to Demucs.
    goto :after_roformer
)
%TEE% "%SEPENV%\Scripts\python.exe" -c "import audio_separator.separator" || call :say Note: the Roformer environment is installed but does not load; see the message above.
echo Fetching the models...
%TEE% "%SEPENV%\Scripts\python.exe" tools\roformer_separate.py --download "%SEPBASE%\models\audio_separator" model_bs_roformer_ep_317_sdr_12.9755.ckpt mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt || call :say Note: fetching the models failed; they are fetched at first use.
echo Trial separation of three seconds of tone...
%TEE% "%SEPENV%\Scripts\python.exe" tools\roformer_separate.py --selftest "%SEPBASE%\models\audio_separator" model_bs_roformer_ep_317_sdr_12.9755.ckpt || call :say Note: the trial separation with Roformer failed; see the message above. Roformer will not work.
>> "%LOG%" echo.
>> "%LOG%" echo ---- pip check / pip list, Roformer environment ----
"%SEPENV%\Scripts\python.exe" -m pip check >> "%LOG%" 2>&1
"%SEPENV%\Scripts\python.exe" -m pip list >> "%LOG%" 2>&1
:after_roformer

rem ---- Extra fonts (fetch only the missing ones) ------------------
echo.
echo Checking fonts (only missing ones are fetched)...
%TEE% powershell -NoProfile -ExecutionPolicy Bypass -Command ^
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
 "    foreach($f in $ttf){$safe=($f.name -replace '\[.*?\]','');try{Invoke-WebRequest -Uri $f.download_url -OutFile (Join-Path $dir $safe) -ErrorAction Stop; Write-Host ('    '+$safe)}catch{Write-Host ('    failed: '+$f.name)}};" ^
 "    break;" ^
 "  }" ^
 "}" ^
 "Write-Host '[OK] Fonts gecontroleerd.'"

rem ---- Check -------------------------------------------------------
echo.
echo Checking the installation...
%TEE% "%VENV%\Scripts\python.exe" -c "import numpy, soundfile, faster_whisper, librosa, scipy, rapidfuzz, PySide6, PIL, langdetect; print('[OK] Kernpakketten aanwezig (faster-whisper ' + __import__('importlib.metadata', fromlist=['version']).version('faster-whisper') + ')')"
if errorlevel 1 goto :error
echo Large models:
%TEE% "%VENV%\Scripts\python.exe" -c "import importlib.util as u;[print('   - '+n+': '+('present' if u.find_spec(m) else 'not installed')) for n,m in (('Demucs','demucs'),('WhisperX','whisperx'))]"
if exist "%VENV%_separator\Scripts\python.exe" (call :say    - Roformer: present) else (call :say    - Roformer: not installed, optional)
>> "%LOG%" echo.
>> "%LOG%" echo ---- pip check / pip list, program environment ----
"%VENV%\Scripts\python.exe" -m pip check >> "%LOG%" 2>&1
"%VENV%\Scripts\python.exe" -m pip list >> "%LOG%" 2>&1

rem ---- The card test ------------------------------------------------
if defined CUDA (
    echo Testing the graphics card ^(a sum and one second of Whisper^)...
    %TEE% "%VENV%\Scripts\python.exe" -m modules.cuda --write "%CONFIGDIR%\cuda.json"
) else (
    "%VENV%\Scripts\python.exe" -m modules.cuda --none "%CONFIGDIR%\cuda.json" >nul 2>nul
)


echo.
echo ============================================
echo  Installation done; the program starts.
echo ============================================
call :say Installation ready.
%PYCMD% tools\setup_check.py "%VENV%" %ROFORMER% %CUDAFLAG% --write
echo Everything above is also in %LOG%
timeout /t 5 >nul

:start_app
rem Look for updates (B444). In the BACKGROUND and without a window:
rem pip has to go onto the network and that may never hold up the start.
rem The script decides for itself whether its turn has come (once a day at
rem most) and writes its answer to docs\updates.json; the app reads that on
rem the NEXT start and puts it in the log window.
if exist "%VENV%\Scripts\pythonw.exe" (
    start "" /b "%VENV%\Scripts\pythonw.exe" tools\check_updates.py
)

rem Start windowless through pythonw so this window closes at once; the
rem activity is visible in the GUI and in logs\. Falls back to python.exe.
if exist "%VENV%\Scripts\pythonw.exe" (
    start "" "%VENV%\Scripts\pythonw.exe" KaraokeTool.py
) else (
    start "" "%VENV%\Scripts\python.exe" KaraokeTool.py
)
exit /b 0

:error
echo.
echo ============================================
echo  INSTALLATION FAILED
echo  Read the error messages above.
echo ============================================
>> "%LOG%" echo INSTALLATION FAILED
echo Everything above is also in %LOG%
pause
exit /b 1

rem ---- An environment made with another Python, set aside -------------
:set_aside
%PYCMD% tools\setup_check.py --python-of "%~1" > "%LOGDIR%\python_of_env.txt" 2>nul
set /p OLDPY=<"%LOGDIR%\python_of_env.txt"
%PYCMD% tools\setup_check.py --set-aside "%~1" "%~dp0..\_to_delete" "%~dp0_to_delete" > "%LOGDIR%\set_aside.txt" 2>nul
if errorlevel 1 (
    call :say Note: %~1 ^(Python %OLDPY%^) could not be set aside; close KaraokeTool and try again.
    exit /b 1
)
set /p GONE=<"%LOGDIR%\set_aside.txt"
call :say Environment %~1 ^(Python %OLDPY%^) is now in %GONE%; it is made again with Python %PYVER%.
set "FIRST=1"
exit /b 0

rem ---- A line on the screen and in the log ---------------------------
:say
echo(%*
>> "%LOG%" echo(%*
exit /b 0
