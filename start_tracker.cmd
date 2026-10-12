@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" launch_tracker.py
) else (
  start "" "..\.venv\Scripts\pythonw.exe" launch_tracker.py
)
