@echo off
rem Nexus Gate app-only reinstall for Windows - double-click me.
rem Skips Ollama and the models; just reinstalls the app itself.
cd /d %~dp0
where py >nul 2>nul
if %errorlevel%==0 goto runpy
python setup_win.py --app-only %*
goto done
:runpy
py -3 setup_win.py --app-only %*
:done
if not "%~1"=="--no-pause" pause
