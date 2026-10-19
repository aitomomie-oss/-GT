@echo off
cd /d "%~dp0"
py -3.12 "%~dp0tools\windows_update.py"
if errorlevel 1 (
  echo Update could not start. Install Python 3.12 with Python Launcher.
  pause
)
