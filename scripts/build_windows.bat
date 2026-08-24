@echo off
REM Windows 用スタンドアロン .exe を作成する (Windows機で実行すること)。
REM 事前に: pip install -r ..\requirements.txt -r requirements-dev.txt
cd /d "%~dp0"
pyinstaller --windowed --name "SenderGirlSaveEditor" --noconfirm ^
  --distpath ..\dist --workpath ..\build --specpath .. ^
  gui_editor.py
echo done: ..\dist\SenderGirlSaveEditor\SenderGirlSaveEditor.exe
