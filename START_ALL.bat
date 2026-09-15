@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: execute INSTALL.bat
  pause
  exit /b 1
)
start "Crypto Exchange Web" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn web:app --host 127.0.0.1 --port 8001"
timeout /t 2 /nobreak >nul
start "Crypto Exchange Telegram Bot" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe bot.py"
echo Web:   http://127.0.0.1:8001/
echo Admin: http://127.0.0.1:8001/admin
pause
