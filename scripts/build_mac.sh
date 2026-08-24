#!/usr/bin/env bash
# Mac 用スタンドアロン .app を作成する。
# 実行環境に pip install -r ../requirements.txt -r requirements-dev.txt 済みであること。
set -euo pipefail
cd "$(dirname "$0")"
pyinstaller --windowed --name "SenderGirlSaveEditor" --noconfirm \
  --distpath ../dist --workpath ../build --specpath .. \
  gui_editor.py
echo "done: ../dist/SenderGirlSaveEditor.app"
