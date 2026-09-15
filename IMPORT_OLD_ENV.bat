@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "OLD=C:\Users\Professional\Downloads\crypto_exchange_tg_mvp_full\crypto_exchange_tg_full\.env"
if exist "%OLD%" (
  copy /Y "%OLD%" ".env" >nul
  echo .env imported from the previous project.
) else (
  echo Previous .env was not found.
  echo Create .env from .env.example and enter your BOT_TOKEN and admin settings.
)
pause
