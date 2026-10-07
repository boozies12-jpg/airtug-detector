@echo off
REM ======================================================================
REM Windows BLE Tracker Search - Direct One-Click Launcher
REM ======================================================================
title Windows BLE Tracker Search
color 0B

echo ======================================================================
echo               Windows BLE Tracker Search - Security Pilot
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/2] Verifying Python and dependencies...
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found on your system PATH!
    echo Please download and install Python from https://www.python.org/
    echo NOTE: Check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing required libraries...
    python -m pip install -r requirements.txt
)

echo [2/2] Launching Application Server...
start "" http://localhost:41730

echo.
echo ======================================================================
echo Server is running at http://localhost:41730
echo To use from your Android phone on the same Wi-Fi, open:
echo   http://^<YOUR_COMPUTER_IP^>:41730
echo.
echo Close this window to stop the application.
echo ======================================================================
echo.

python main.py

pause
