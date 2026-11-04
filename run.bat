@echo off
rem Run the app straight from source (for testing, without building the exe)
cd /d "%~dp0"
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY set "PY=python"
%PY% -m pip install -r requirements.txt >nul
%PY% -m pip install libtorrent >nul 2>nul
%PY% app\main.py
