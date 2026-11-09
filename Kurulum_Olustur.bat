@echo off
setlocal
cd /d "%~dp0"
title Riven Launcher - Kurulum Dosyasi Olusturucu
echo ============================================
echo   Riven Launcher - Setup.exe olusturuluyor
echo ============================================
echo.

echo [1/4] Gerekli paketler kuruluyor...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :hata

echo.
echo [2/4] RivenLauncher.exe derleniyor (birkac dakika surebilir)...
python -m PyInstaller --noconfirm --clean RivenLauncher.spec
if errorlevel 1 goto :hata
rem Windows eski ikonu onbellekten gostermesin diye ikon onbellegini yeniler
ie4uinit.exe -show >nul 2>&1

echo.
echo [3/4] Inno Setup araniyor...
call :findiscc
if defined ISCC goto :derle
echo Inno Setup yok, winget ile kuruluyor (izin penceresi cikabilir)...
winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
call :findiscc
if defined ISCC goto :derle
goto :noinno

:derle
echo.
echo [4/4] Kurulum sihirbazi olusturuluyor...
"%ISCC%" installer.iss
if errorlevel 1 goto :hata
echo.
echo ============================================
echo   HAZIR!
echo   Kurulum dosyasi: %~dp0installer\RivenLauncher-Setup.exe
echo   (Kurulumsuz klasor: %~dp0dist\RivenLauncher\RivenLauncher.exe)
echo ============================================
echo.
echo Not: Imzasiz oldugu icin Windows SmartScreen uyari verebilir:
echo "Ek bilgi" - "Yine de calistir" de. Kodu kendin derledigin icin guvenli.
explorer "%~dp0installer"
pause
exit /b 0

:findiscc
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
exit /b 0

:noinno
echo.
echo Inno Setup otomatik kurulamadi. Elle kur (ucretsiz, 1 dakika):
echo   https://jrsoftware.org/isdl.php   ^(Inno Setup 6 - stable^)
echo Kurduktan sonra bu dosyayi tekrar calistir.
echo.
echo Simdilik kurulumsuz hazir: %~dp0dist\RivenLauncher\RivenLauncher.exe
pause
exit /b 1

:hata
echo.
echo Bir hata olustu, yukaridaki mesaji kontrol et.
pause
exit /b 1
