@echo off
chcp 65001 >nul
title Riven Launcher - Ikon Onbellegini Temizle
echo Windows ikon onbellegi temizleniyor (ekran bir an kararip geri gelebilir)...
taskkill /f /im explorer.exe >nul 2>&1
del /a /f /q "%localappdata%\IconCache.db" >nul 2>&1
del /a /f /q "%localappdata%\Microsoft\Windows\Explorer\iconcache*" >nul 2>&1
del /a /f /q "%localappdata%\Microsoft\Windows\Explorer\thumbcache*" >nul 2>&1
start explorer.exe
echo.
echo Bitti. Gorev cubugunda eski Riven simgesi hala duruyorsa:
echo   1) Gorev cubugundaki eski Riven simgesine sag tikla - "Gorev cubugundan kaldir"
echo   2) Riven Launcher'i yeniden ac, sonra istersen tekrar sabitle.
echo.
pause
