@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" sniff_sdr.py
) else (
  "..\.venv\Scripts\python.exe" sniff_sdr.py
)
echo Capture finished. If a file was created, its path is shown above.
pause
