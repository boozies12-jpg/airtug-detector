@echo off
REM ======================================================================
REM Windows BLE Tracker Search - Startup Script
REM ======================================================================

echo [1/3] Checking Python dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to install Python dependencies. Ensure Python 3.10+ is installed and on PATH.
    pause
    exit /b %ERRORLEVEL%
)

echo [2/3] Checking Node dependencies...
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to install Node dependencies. Ensure Node.js 18+ is installed.
    pause
    exit /b %ERRORLEVEL%
)

echo [3/3] Launching Windows BLE Tracker Search...
start "BLE Backend Server" cmd /k "python -m uvicorn src.api.server:app --host 0.0.0.0 --port 41730"
timeout /t 2 /nobreak >nul
start "BLE Web Interface" cmd /k "npm run dev"

echo.
echo Application started!
echo Open your browser at: http://localhost:41732
echo Press any key to exit this launcher window.
pause
