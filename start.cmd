@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run setup.cmd before starting Shiyan.
  pause
  exit /b 1
)
start "Shiyan" ".venv\Scripts\pythonw.exe" "%~dp0export_gui.py"
