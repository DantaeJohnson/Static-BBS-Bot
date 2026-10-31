@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run "Start Static BBS Bot.bat" once first to install everything.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
pause
