@echo off
rem KaraokeTool - find the Python the program runs on (v1.0.20).
rem
rem   call tools\find_python.bat [ask^|auto^|none]
rem
rem Looks for Python 3.13. When it is not there: "ask" asks whether to
rem install it with winget (the launcher), "auto" installs it without
rem asking (a helper bringing itself up to date, with nobody at the
rem keyboard), "none" leaves it. Sets PYCMD (the command, quoted when it
rem is a path) and PYVER (3.13); both empty when it is not there.
rem v1.0.22: the fallback on 3.12 went - it is gone from every computer.
call :look
if "%PYVER%"=="3.13" exit /b 0
if /i "%~1"=="none" exit /b 0
if /i "%~1"=="" exit /b 0
where winget >nul 2>nul
if errorlevel 1 exit /b 0
if /i "%~1"=="auto" goto :install
echo.
echo Python 3.13 is not there yet; the program runs on it. The environments
echo are then made again (a large download, once).
choice /C YN /M "Install Python 3.13 now with winget [Y/N]"
if errorlevel 2 exit /b 0
:install
winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
call :look
exit /b 0

:look
set "PYCMD="
set "PYVER="
call :try 3.13
exit /b 0

:try
set "WANT=%~1"
set "SHORT=%WANT:.=%"
py -%WANT% -c "import sys" >nul 2>nul && (
    set "PYCMD=py -%WANT%"
    set "PYVER=%WANT%"
    exit /b 0
)
if exist "%LOCALAPPDATA%\Programs\Python\Python%SHORT%\python.exe" (
    set PYCMD="%LOCALAPPDATA%\Programs\Python\Python%SHORT%\python.exe"
    set "PYVER=%WANT%"
    exit /b 0
)
if exist "%ProgramFiles%\Python%SHORT%\python.exe" (
    set PYCMD="%ProgramFiles%\Python%SHORT%\python.exe"
    set "PYVER=%WANT%"
    exit /b 0
)
python -c "import sys; raise SystemExit(0 if '%%d.%%d' %% sys.version_info[:2] == '%WANT%' else 1)" >nul 2>nul && (
    set "PYCMD=python"
    set "PYVER=%WANT%"
)
exit /b 0
