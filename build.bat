@echo off
setlocal
title DMTOR - Build
cd /d "%~dp0"

echo ============================================
echo   DMTOR - building DMTOR.exe
echo ============================================

rem --- pick a Python that torrent support works with (3.13 / 3.12 / 3.11), else any Python
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo [X] Python is not installed.
  echo     Install Python 3.13 from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH" during setup, then run this file again.
  pause
  exit /b 1
)
echo Using: %PY%
%PY% --version

echo.
echo [1/5] Installing libraries...
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto fail

echo.
echo [2/5] Installing torrent support...
%PY% -m pip install --upgrade libtorrent
%PY% -c "import libtorrent" >nul 2>nul
if errorlevel 1 (
  echo     [!] Torrent support is NOT available with this Python version.
  echo         Install Python 3.13 from python.org and run build.bat again.
  echo         Everything else will still work.
  set "TORRENT=no"
) else (
  echo     Torrent support OK.
  set "TORRENT=yes"
)

echo.
echo [3/5] Building DMTOR.exe ...
set "EXTRA="
if "%TORRENT%"=="yes" set "EXTRA=--hidden-import libtorrent"
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name DMTOR --icon assets\app.ico --add-data "assets;assets" ^
  --paths app %EXTRA% app\main.py
if errorlevel 1 goto fail

echo.
echo [4/5] Getting ffmpeg (for HD video + MP3)...
if exist dist\ffmpeg.exe (
  echo     ffmpeg already there.
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile ffmpeg.zip; Expand-Archive ffmpeg.zip -DestinationPath ffmpeg_tmp -Force; Copy-Item (Get-ChildItem ffmpeg_tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName 'dist\ffmpeg.exe'; Remove-Item ffmpeg.zip, ffmpeg_tmp -Recurse -Force; Write-Host '    ffmpeg OK' } catch { Write-Host '    [!] Could not download ffmpeg - videos will still work (up to ~720p).' }"
)

echo.
echo [5/5] Copying browser extension...
xcopy /E /I /Y extension dist\extension >nul

echo.
echo ============================================
echo   DONE!  Your program is in the "dist" folder:
echo     dist\DMTOR.exe
echo     dist\extension   (load it in Chrome / Edge)
if "%TORRENT%"=="no" echo   Note: built WITHOUT torrent support (see above).
echo ============================================
explorer dist
pause
exit /b 0

:fail
echo.
echo [X] Build failed. Scroll up to see the error.
pause
exit /b 1
