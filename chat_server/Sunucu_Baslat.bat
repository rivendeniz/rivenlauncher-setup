@echo off
title Riven Mesaj Sunucusu
cd /d "%~dp0"
echo ============================================
echo   Riven Mesaj Sunucusu
echo ============================================
echo.

set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo HATA: Python bulunamadi. python.org adresinden Python 3 kur
  echo ve kurulumda "Add Python to PATH" kutusunu isaretle.
  echo.
  pause
  exit /b 1
)

set "PW="
set /p PW=Sunucu sifresi belirle (bos birakirsan herkes baglanabilir): 
echo.
echo Sunucu 8780 portunda aciliyor. Windows guvenlik duvari sorarsa "Izin ver"e bas.
echo Launcher'a yazilacak adres asagida gosterilecek (127.0.0.1 = ayni bilgisayar).
echo DIKKAT: 0.0.0.0 adresini launcher'a YAZMA, calismaz.
echo Bu pencereyi kapatma, kapanirsa sunucu durur.
echo.

if defined PW (
  %PY% riven_chat_server.py --port 8780 --password "%PW%"
) else (
  %PY% riven_chat_server.py --port 8780
)
echo.
echo Sunucu durdu. Yukaridaki hata mesajini oku.
pause
