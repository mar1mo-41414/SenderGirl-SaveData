@echo off
REM Build a standalone Windows .exe. Run on an actual Windows machine.
REM Prerequisite: pip install -r ..\requirements.txt -r requirements-dev.txt
REM (Note: comments in this file are kept ASCII-only on purpose. UTF-8
REM Japanese text in .bat comments gets mis-decoded on Japanese-locale
REM cmd.exe (codepage 932) and can corrupt line parsing.)
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo [ERROR] pyinstaller not found on PATH.
  echo Run this first: pip install -r ..\requirements.txt -r requirements-dev.txt
  exit /b 1
)

pyinstaller --windowed --name "SenderGirlSaveEditor" --noconfirm ^
  --distpath ..\dist --workpath ..\build --specpath .. ^
  gui_editor.py
if errorlevel 1 (
  echo [ERROR] pyinstaller failed. See output above.
  exit /b 1
)

echo done: ..\dist\SenderGirlSaveEditor\SenderGirlSaveEditor.exe
