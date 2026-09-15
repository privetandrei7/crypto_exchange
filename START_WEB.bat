@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: execute INSTALL.bat
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m uvicorn web:app --host 127.0.0.1 --port 8001
