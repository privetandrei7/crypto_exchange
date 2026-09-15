@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating Python environment...
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
echo [2/2] Installing dependencies...
.venv\Scripts\python.exe -m pip install --proxy="" -r requirements.txt
if not exist ".env" copy /Y ".env.example" ".env" >nul
echo.
echo Installation finished.
echo Edit .env and set BOT_TOKEN, SECRET_KEY, ADMIN_USER, ADMIN_PASSWORD.
pause
