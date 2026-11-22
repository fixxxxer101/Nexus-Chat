@echo off
rem Nexus Chat setup for Windows - double-click me.
rem Everything happens in setup_win.py; this just finds Python.
cd /d %~dp0
where py >nul 2>nul
if %errorlevel%==0 goto runpy
python setup_win.py %*
goto done
:runpy
py -3 setup_win.py %*
:done
if not "%~1"=="--no-pause" pause
