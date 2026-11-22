@echo off
rem Nexus_Gate_Installer_Windows.bat - Nexus Gate installer.
rem Double-click me on a fresh PC. I install everything
rem Nexus Gate needs, then hand off to the repo's own setup:
rem   1. Python 3, if no working copy is found
rem   2. Git for Windows, if missing (the app Update needs it)
rem   3. Ollama, if missing
rem   4. The Nexus Gate checkout, cloned from GitHub (public)
rem   5. setup.bat from the checkout: starts Ollama, pulls
rem      the model, installs the app and the desktop shortcut
rem Safe to re-run: whatever is already there is skipped.
title Nexus Gate Installer - Windows
setlocal
set "NEXUS_DIR=%USERPROFILE%\Nexus-Chat"

echo ============================================================
echo  Nexus Gate - from-scratch install
echo  The checkout will live at: %NEXUS_DIR%
echo ============================================================
echo.

rem ---------------- 1. Python ----------------
py -3 --version >nul 2>nul
if not errorlevel 1 goto have_python
python -c "import sys" >nul 2>nul
if not errorlevel 1 goto have_python
echo Python 3 not found - downloading it now...
curl.exe -L -o "%TEMP%\python-installer.exe" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
if errorlevel 1 goto fail_download
echo Installing Python 3 - quiet, per-user, PATH included...
start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Programs\Python\Launcher;%PATH%"
py -3 --version >nul 2>nul
if errorlevel 1 goto fail_python
:have_python
echo Python 3: OK
echo.

rem ---------------- 2. Git ----------------
where git >nul 2>nul
if not errorlevel 1 goto have_git
echo Git not found - downloading Git for Windows...
curl.exe -L -o "%TEMP%\git-installer.exe" "https://github.com/git-for-windows/git/releases/download/v2.48.1.windows.1/Git-2.48.1-64-bit.exe"
if errorlevel 1 goto fail_download
echo Installing Git - quiet. Windows may ask for admin permission; say yes.
start /wait "" "%TEMP%\git-installer.exe" /VERYSILENT /NORESTART
set "PATH=C:\Program Files\Git\cmd;%PATH%"
where git >nul 2>nul
if errorlevel 1 goto fail_git
:have_git
echo Git: OK
echo.

rem ---------------- 3. Ollama ----------------
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" goto have_ollama
where ollama >nul 2>nul
if not errorlevel 1 goto have_ollama
echo Ollama not found - downloading it now...
curl.exe -L -o "%TEMP%\OllamaSetup.exe" "https://ollama.com/download/OllamaSetup.exe"
if errorlevel 1 goto fail_download
echo Installing Ollama - quiet...
start /wait "" "%TEMP%\OllamaSetup.exe" /VERYSILENT /NORESTART
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" goto have_ollama
echo Waiting for Ollama to finish installing...
set /a TRIES=0
:wait_ollama
timeout /t 5 /nobreak >nul
set /a TRIES+=1
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" goto have_ollama
if %TRIES% LSS 24 goto wait_ollama
goto fail_ollama
:have_ollama
echo Ollama: OK
echo.

rem ---------------- 4. The checkout ----------------
if exist "%NEXUS_DIR%\.git" goto have_repo
if exist "%NEXUS_DIR%" goto repo_conflict
echo Cloning Nexus Gate from GitHub...
git clone https://github.com/fixxxxer101/Nexus-Gate.git "%NEXUS_DIR%"
if errorlevel 1 goto fail_clone
goto have_repo
:repo_conflict
echo %NEXUS_DIR% already exists but is not a git checkout.
echo Move that folder aside, then run me again.
goto fail
:have_repo
echo Checkout: OK
echo.

rem ---------------- 5. The repo's own setup ----------------
echo Running the Nexus Gate setup now: it starts Ollama,
echo pulls the model, installs the app and the shortcut.
echo.
call "%NEXUS_DIR%\setup.bat" --no-pause
if errorlevel 1 goto fail_setup
echo.
echo ============================================================
echo  Done - Nexus Gate is installed.
echo ============================================================
if exist "%USERPROFILE%\Desktop\Nexus Gate.lnk" start "" "%USERPROFILE%\Desktop\Nexus Gate.lnk"
pause
exit /b 0

rem ---------------- failures ----------------
:fail_download
echo.
echo A download failed. Check the internet connection,
echo then run me again - finished steps are skipped.
goto fail
:fail_python
echo.
echo Python still does not work after installing.
echo Restart the PC, then run me again.
goto fail
:fail_git
echo.
echo Git still not found after installing.
echo Restart the PC, then run me again.
goto fail
:fail_ollama
echo.
echo Ollama did not finish installing. Install it from
echo https://ollama.com yourself, then run me again.
goto fail
:fail_clone
echo.
echo The git clone failed. Check the internet connection,
echo then run me again.
goto fail
:fail_setup
echo.
echo The Nexus Gate setup reported a problem.
echo Read its messages above, fix that, then run me again.
goto fail
:fail
echo.
echo Install did not finish, but nothing is half-broken:
echo re-running me is always safe.
pause
exit /b 1
