@echo off
setlocal
cd /d "%~dp0"
title Static BBS Bot

REM ---- Already set up? Just open the bot. ----
if exist ".venv\Scripts\pythonw.exe" goto launch

echo.
echo  Static BBS Bot - first-time setup
echo  ---------------------------------
echo  This only happens once. It needs an internet connection and takes a few minutes.
echo.

REM ---- Find Python (prefer versions the bot is tested with) ----
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.12 3.13 3.11) do (
        if not defined PY (
            py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
        )
    )
    if not defined PY set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo  [!] Python was not found on this computer.
    echo.
    echo      1. Install Python 3.12 from https://www.python.org/downloads/
    echo      2. On the first install screen, TICK "Add python.exe to PATH".
    echo      3. Then double-click this file again.
    echo.
    pause
    exit /b 1
)
echo  Using Python: %PY%

echo  [1/2] Creating the bot's private Python folder (.venv)...
%PY% -m venv .venv
if errorlevel 1 (
    echo  [!] Could not create the .venv folder. Try moving the bot to Documents and run again.
    pause
    exit /b 1
)
echo  [2/2] Downloading and installing the bot's packages (about 300 MB)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [!] Package install failed.
    echo      - Check your internet connection.
    echo      - If you installed a very new Python - 3.14 or later - install Python 3.12 instead.
    echo      Then double-click this file again.
    rmdir /s /q .venv
    pause
    exit /b 1
)
echo.
echo  Setup complete! Opening Static BBS Bot...

:launch
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
exit /b 0
