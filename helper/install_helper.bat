@echo off
setlocal
rem KaraokeTool helper - install or update on another computer (v1.0.20;
rem v1.0.21: its log also goes to the laptop, KaraokeTool\logs\helpers;
rem v1.0.23: the shortcut starts the helper's window, with the icon;
rem ffmpeg through winget, which keeps it up to date; the work folder
rem kt_work lives in this helper folder on the share and is not copied;
rem PyTorch is tried, and Microsoft's Visual C++ runtime brought up to date
rem when torch does not load; WhisperX, the forced aligner, as on the
rem laptop; the Whisper model and the aligner's are fetched right away;
rem v1.0.24: the shortcut starts the helper without a console, in its
rem window from the first moment (pythonw, helper.py --start); what the
rem helper installed itself is written down, for "Helper verwijderen",
rem which install_helper.bat /remove does as well).
set "HELPER_VERSION=1.0.29"
rem
rem By hand: run this from the share, e.g.
rem   \\10.0.0.18\Tools\KaraokeTool\helper\install_helper.bat
rem Everything is installed on THIS computer, under
rem %LOCALAPPDATA%\KaraokeToolHelper; nothing is written to the share
rem except the helper's work later on. With an NVIDIA card the PyTorch
rem that works on the card is installed; an older card that turns out
rem unusable leaves the processor.
rem
rem /update: the helper keeps itself up to date. When it sees a newer
rem HELPER_VERSION on the share after a job, it stops, and its start file
rem runs a copy of this file with /update: nothing is asked (a question
rem with a time limit at most), and at the end the helper is started
rem again - the loop that keeps every helper on the laptop's version.
rem Python: 3.13 (tools\find_python.bat); an environment made with
rem another Python is made anew, the old one goes.
rem The logs go to the laptop under this computer's name as the helper
rem list shows it (``hostname``), not under %COMPUTERNAME%, which can be
rem another name altogether (v1.0.22).
set "UPDATE="
if /i "%~1"=="/update" set "UPDATE=1"
set "HOME_DIR=%LOCALAPPDATA%\KaraokeToolHelper"
set "OLD_HOME=%LOCALAPPDATA%\KaraokeToolHulp"
set "APP=%HOME_DIR%\app"
set "HOST=%COMPUTERNAME%"
for /f "delims=" %%H in ('hostname 2^>nul') do set "HOST=%%H"
if /i "%~1"=="/remove" goto :remove_helper
rem v1.0.24 (B655): what this helper installed itself, for its removal. A
rem helper from before kept no count: "unknown" (the owner: then it goes).
set "REC=%HOME_DIR%\installed_by_helper.txt"
if not exist "%REC%" if exist "%HOME_DIR%\installed_version.txt" > "%REC%" echo unknown
if not exist "%HOME_DIR%\logs" mkdir "%HOME_DIR%\logs"
set "SHARE="
if defined UPDATE if exist "%HOME_DIR%\share.txt" set /p SHARE=<"%HOME_DIR%\share.txt"
if not defined SHARE for %%I in ("%~dp0..") do set "SHARE=%%~fI"
set "LOG=%HOME_DIR%\logs\install_helper.log"
if exist "%LOG%" move /y "%LOG%" "%HOME_DIR%\logs\install_helper_previous.log" >nul 2>nul
> "%LOG%" echo KaraokeTool helper - install_helper.bat %HELPER_VERSION% %~1 - %DATE% %TIME%
>> "%LOG%" echo Share: %SHARE%
>> "%LOG%" echo Folder: %HOME_DIR%
ver >> "%LOG%"
title KaraokeTool helper - installation %HELPER_VERSION%
rem While this runs, helper_start.bat does not start a second one.
> "%HOME_DIR%\installing.lock" echo %DATE% %TIME%

echo ============================================
echo  KaraokeTool helper %HELPER_VERSION% - installation
echo ============================================
echo Program on the share:  %SHARE%
echo Installing into:       %HOME_DIR%
echo.
if not exist "%SHARE%\KaraokeTool.py" (
    echo The folder %SHARE% holds no KaraokeTool.
    echo Start this file from the shared folder, e.g.
    echo   \\10.0.0.18\Tools\KaraokeTool\helper\install_helper.bat
    >> "%LOG%" echo No KaraokeTool found on %SHARE%.
    goto :error
)

rem ---- The program, fetched from the share -------------------------------
echo Fetching the program from the share...
robocopy "%SHARE%" "%APP%" /MIR /XD venv venv_separator models input output cache logs config _to_delete __pycache__ .git kt_work /XF *.log /NFL /NDL /NJH /NJS /NP >> "%LOG%" 2>&1
if errorlevel 8 (
    echo Could not fetch the program from %SHARE%.
    >> "%LOG%" echo robocopy failed.
    goto :error
)

rem ---- Python 3.13 ---------------------------------------------------------
set "ASK=ask"
if defined UPDATE set "ASK=auto"
set "HADPY="
call "%APP%\tools\find_python.bat" none
if "%PYVER%"=="3.13" set "HADPY=1"
call "%APP%\tools\find_python.bat" %ASK%
if not defined HADPY if "%PYVER%"=="3.13" call :record python
if not defined PYCMD (
    echo Python 3.13 was not found and could not be installed.
    echo Install Python 3.13 from https://www.python.org/downloads/ and
    echo run this file again.
    >> "%LOG%" echo No Python found.
    goto :error
)
set "TEE=%PYCMD% "%APP%\tools\tee_run.py" "%LOG%" --"
call :say [OK] Python %PYVER% found: %PYCMD%
call :say [OK] Program fetched to %APP%

rem ---- ffmpeg ------------------------------------------------------------
rem v1.0.23: through winget, for this user (no rights needed): at every
rem update of the helper winget brings it up to date too. A copy in the
rem program's bin folder still counts when there is one.
set "FFOK="
where ffmpeg >nul 2>nul && where ffprobe >nul 2>nul && set "FFOK=1"
if not defined FFOK if exist "%APP%\bin\ffmpeg.exe" if exist "%APP%\bin\ffprobe.exe" set "FFOK=1"
winget list -e --id Gyan.FFmpeg >nul 2>nul && %TEE% winget upgrade -e --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements
if defined FFOK goto :ffmpeg_ok
call :say ffmpeg not found; installing it with winget...
%TEE% winget install -e --id Gyan.FFmpeg --scope user --accept-source-agreements --accept-package-agreements && call :record ffmpeg || call :say Note: installing ffmpeg failed; without ffmpeg the helper can do nothing.
goto :ffmpeg_done
:ffmpeg_ok
call :say [OK] ffmpeg found.
:ffmpeg_done

rem ---- An NVIDIA card? ------------------------------------------------------
set "CUDA="
where nvidia-smi >nul 2>nul && set "CUDA=1"
if defined CUDA (
    call :say NVIDIA card found; the versions that compute on the card are installed.
    %TEE% nvidia-smi
) else (
    call :say No NVIDIA card found; the helper computes on the processor.
)
rem cu126 still carries the older cards; a version found on both indexes
rem is taken from the card's (its local version label sorts higher).
set "TORCHIDX="
if defined CUDA set "TORCHIDX=--extra-index-url https://download.pytorch.org/whl/cu126"

rem ---- The program's environment -----------------------------------------
set "VENV=%APP%\venv"
if exist "%VENV%\Scripts\python.exe" (
    %PYCMD% "%APP%\tools\setup_check.py" --same-python "%VENV%" >nul 2>nul || call :renew "%VENV%"
)
if not exist "%VENV%\Scripts\python.exe" %TEE% %PYCMD% -m venv "%VENV%"
if not exist "%VENV%\Scripts\python.exe" goto :error
%TEE% "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
if defined CUDA %TEE% "%VENV%\Scripts\python.exe" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126 || call :say Note: installing PyTorch for the card failed; the helper computes on the processor.
if defined CUDA %TEE% "%VENV%\Scripts\python.exe" -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || call :say Note: installing the CUDA libraries for Whisper failed; Whisper then listens on the processor.
%TEE% "%VENV%\Scripts\python.exe" -m pip install -r "%APP%\requirements.txt"
if errorlevel 1 goto :error
rem v1.0.23 (B652): WhisperX, the forced aligner, as on the laptop - and
rem first, as there: it pins its PyTorch, and Demucs is content with it.
%TEE% "%VENV%\Scripts\python.exe" -m pip install whisperx %TORCHIDX% || call :say Note: installing WhisperX failed; this helper then takes no rounds that lay the text on the voice.
%TEE% "%VENV%\Scripts\python.exe" -m pip install -U "demucs>=4.1" %TORCHIDX% || call :say Note: installing Demucs failed.
call :torch_check "%VENV%"

rem ---- The Roformer environment ---------------------------------------------
set "SEPENV=%APP%\venv_separator"
if exist "%SEPENV%\Scripts\python.exe" (
    %PYCMD% "%APP%\tools\setup_check.py" --same-python "%SEPENV%" >nul 2>nul || call :renew "%SEPENV%"
)
if not exist "%SEPENV%\Scripts\python.exe" %TEE% %PYCMD% -m venv "%SEPENV%"
if not exist "%SEPENV%\Scripts\python.exe" (
    call :say Note: the Roformer environment could not be made; the helper then does only Demucs rounds.
    goto :after_roformer
)
%TEE% "%SEPENV%\Scripts\python.exe" -m pip install --upgrade pip
if defined CUDA %TEE% "%SEPENV%\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu126 || call :say Note: PyTorch for the card in the Roformer environment failed.
rem v1.0.24 (B654): the processor's onnxruntime, also with a card. The [gpu]
rem extra brings onnxruntime-gpu, built for another CUDA than the card's
rem PyTorch, and it is only for the .onnx models, which we do not use: the
rem Roformer models run on PyTorch, on the card. What an older helper has
rem of onnxruntime-gpu goes.
set "SEPKIND=cpu"
"%SEPENV%\Scripts\python.exe" -m pip show onnxruntime-gpu >nul 2>nul && "%SEPENV%\Scripts\python.exe" -m pip uninstall -y onnxruntime-gpu >> "%LOG%" 2>&1 && set "ORT_AGAIN=1"
%TEE% "%SEPENV%\Scripts\python.exe" -m pip install --upgrade "audio-separator[%SEPKIND%]" audioread "librosa>=0.10,<1" %TORCHIDX% || (
    call :say Note: installing audio-separator failed; the helper then does only Demucs rounds.
    goto :after_roformer
)
rem Both packages are the module onnxruntime: the one that went took files of
rem the other with it.
if defined ORT_AGAIN %TEE% "%SEPENV%\Scripts\python.exe" -m pip install --force-reinstall --no-deps onnxruntime
call :torch_check "%SEPENV%"
echo Trial separation of three seconds of tone; this also fetches the first model...
%TEE% "%SEPENV%\Scripts\python.exe" "%APP%\tools\roformer_separate.py" --selftest "%APP%\models\audio_separator" model_bs_roformer_ep_317_sdr_12.9755.ckpt || call :say Note: the trial separation with Roformer failed; see the message above.
:after_roformer

rem ---- What this computer will do -------------------------------------------
echo.
echo Checking the card and the lanes...
%TEE% "%VENV%\Scripts\python.exe" "%APP%\tools\helper.py" --check
rem v1.0.23 (B648): the Whisper model of the rounds now, not at the first
rem round; B652: and the forced aligner's models.
%TEE% "%VENV%\Scripts\python.exe" "%APP%\tools\helper.py" --prefetch-whisper
>> "%LOG%" echo.
>> "%LOG%" echo ---- pip check / pip list ----
"%VENV%\Scripts\python.exe" -m pip check >> "%LOG%" 2>&1
"%VENV%\Scripts\python.exe" -m pip list >> "%LOG%" 2>&1

rem ---- The start file, the shortcut, the version ---------------------------
rem v1.0.24 (B653): the shortcut starts pythonw with helper.py --start - the
rem window at once, no console; helper_start.bat stays as the way in by hand
rem (and the one a computer without Qt falls back on).
copy /y "%APP%\helper\helper_start.bat" "%HOME_DIR%\helper_start.bat" >nul
set "PYW=%APP%\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%APP%\venv\Scripts\python.exe"
if not exist "%REC%" type nul > "%REC%"
> "%HOME_DIR%\share.txt" echo %SHARE%
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop');$old=Join-Path $d 'KaraokeTool hulp.lnk';if(Test-Path $old){Remove-Item $old};$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'KaraokeTool helper.lnk'));$s.TargetPath='%PYW%';$s.Arguments='\"%APP%\tools\helper.py\" --start';$s.WorkingDirectory='%HOME_DIR%';$s.IconLocation='%APP%\assets\icons\karaoketool.ico,0';$s.WindowStyle=1;$s.Save()" >> "%LOG%" 2>&1
rem The old folder goes when nothing holds it (its window may still be open;
rem then helper_start.bat tries again at every start).
if exist "%OLD_HOME%" rd /s /q "%OLD_HOME%" >nul 2>nul
"%VENV%\Scripts\python.exe" "%APP%\tools\helper.py" --installed %HELPER_VERSION%
call :say Helper %HELPER_VERSION% geinstalleerd.
echo.
echo ============================================
echo  Helper %HELPER_VERSION% installed; it starts now.
echo  Later you start it with "KaraokeTool helper" on the desktop.
echo ============================================
echo Everything above is also in %LOG%
echo and on the laptop in %SHARE%\logs\helpers\%HOST%.
call :mirror
del "%HOME_DIR%\installing.lock" >nul 2>nul
start "" "%PYW%" "%APP%\tools\helper.py" --start
if not defined UPDATE timeout /t 15 >nul
exit /b 0

:error
echo.
echo ============================================
echo  INSTALLATION FAILED
echo ============================================
>> "%LOG%" echo INSTALLATION FAILED
echo Everything above is also in %LOG%
call :mirror
del "%HOME_DIR%\installing.lock" >nul 2>nul
if not defined UPDATE (
    pause
    exit /b 1
)
rem Updating by itself: try again in ten minutes (the share may be away).
echo Trying again in ten minutes.
timeout /t 600 /nobreak >nul
if exist "%APP%\venv\Scripts\pythonw.exe" (
    start "" "%APP%\venv\Scripts\pythonw.exe" "%APP%\tools\helper.py" --start
) else if exist "%HOME_DIR%\helper_start.bat" start "KaraokeTool helper" cmd /c ""%HOME_DIR%\helper_start.bat""
exit /b 1

rem ---- Can PyTorch load? (v1.0.23, B649) ------------------------------------
rem On Probook every package was installed, yet torch stopped on c10.dll:
rem Microsoft's Visual C++ runtime was missing, and then too old. Then
rem winget brings it up to date - for the whole computer, so Windows may
rem ask for permission - and torch is tried again.
:torch_check
"%~1\Scripts\python.exe" -c "import torch" >nul 2>nul
if errorlevel 1 goto :torch_broken
call :say [OK] PyTorch loads in %~nx1.
exit /b 0
:torch_broken
>> "%LOG%" echo ---- import torch in %~1 ----
"%~1\Scripts\python.exe" -c "import torch" >> "%LOG%" 2>&1
%PYCMD% "%APP%\tools\setup_check.py" --vc-runtime >> "%LOG%" 2>&1
if errorlevel 1 goto :torch_vc
call :say Note: PyTorch does not load in %~nx1, although the Visual C++ package is complete; the message is in %LOG%.
exit /b 1
:torch_vc
call :vc_update
"%~1\Scripts\python.exe" -c "import torch" >nul 2>nul
if errorlevel 1 goto :torch_still
call :say [OK] PyTorch loads in %~nx1 now.
exit /b 0
:torch_still
call :say Note: PyTorch still does not load in %~nx1. Install Microsoft's Visual C++ package x64 by hand, https://aka.ms/vs/17/release/vc_redist.x64.exe, and run this file again.
exit /b 1

rem Once per installation: upgrade what winget knows, install (again)
rem when files are still missing.
:vc_update
if defined VCDONE exit /b 0
set "VCDONE=1"
call :say Microsoft's Visual C++ package is missing or too old; winget updates it. Windows may ask for permission.
winget list -e --id Microsoft.VCRedist.2015+.x64 >nul 2>nul
if errorlevel 1 goto :vc_install
%TEE% winget upgrade -e --id Microsoft.VCRedist.2015+.x64 --silent --accept-source-agreements --accept-package-agreements
%PYCMD% "%APP%\tools\setup_check.py" --vc-runtime >nul 2>nul
if not errorlevel 1 exit /b 0
:vc_install
%TEE% winget install -e --id Microsoft.VCRedist.2015+.x64 --silent --force --accept-source-agreements --accept-package-agreements
exit /b 0

rem ---- What the helper installed itself, written down (v1.0.24, B655) --------
:record
findstr /x /i /c:"%~1" "%REC%" >nul 2>nul || >> "%REC%" echo %~1
exit /b 0

rem ---- The helper off this computer (v1.0.24, B655) ----------------------------
rem install_helper.bat /remove: as "Helper verwijderen" in its window. With
rem its Python the helper does it itself (a running one is asked to stop
rem first); without, at least its folder and the shortcut go.
:remove_helper
echo This takes the KaraokeTool helper off this computer: its folder, the
echo shortcut, the downloaded models, and ffmpeg and Python 3.13 if the
echo helper installed them itself. The logs on the laptop stay.
choice /C YN /M "Remove the helper [Y/N]"
if errorlevel 2 exit /b 0
if exist "%APP%\venv\Scripts\python.exe" "%APP%\venv\Scripts\python.exe" "%APP%\tools\helper.py" --remove && exit /b 0
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop');foreach($n in 'KaraokeTool helper.lnk','KaraokeTool hulp.lnk'){$p=Join-Path $d $n;if(Test-Path $p){Remove-Item $p}}" >nul 2>nul
rd /s /q "%HOME_DIR%" >nul 2>nul
if exist "%HOME_DIR%" echo Could not remove all of %HOME_DIR%; remove that folder by hand.
exit /b 0

rem ---- An environment made with another Python goes ---------------------------
:renew
%PYCMD% "%APP%\tools\setup_check.py" --python-of "%~1" > "%HOME_DIR%\logs\python_of_env.txt" 2>nul
set /p OLDPY=<"%HOME_DIR%\logs\python_of_env.txt"
call :say Environment %~1 was made with Python %OLDPY%; it is made again with %PYVER%.
rd /s /q "%~1" >nul 2>nul
exit /b 0

rem ---- The logs onto the laptop, in KaraokeTool\logs\helpers\<computer> ----
rem (v1.0.21; newer files only, the share may be away)
:mirror
if not exist "%SHARE%\KaraokeTool.py" exit /b 0
robocopy "%HOME_DIR%\logs" "%SHARE%\logs\helpers\%HOST%" /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul 2>nul
exit /b 0

rem ---- A line on the screen and in the log -------------------------------
:say
echo(%*
>> "%LOG%" echo(%*
exit /b 0
