[English README →](README-EN.md)

# SenderGirl-SaveData

iOS アプリ「ゆるヤミ彼女」(`com.Happygamer.SenderGirl`) のセーブデータ
`UserData.saveIt` を復号・編集するための非公式ツール群。

暗号化フォーマットの解析、パスワードの特定、データ構造の解読を行い、
その成果を使った GUI セーブエディタを同梱しています。

## 免責事項

- 本プロジェクトは **非公式のファンツール** であり、アプリの開発元・
  配信元とは一切関係ありません。
- 自分が所有する自分自身のセーブデータを、バックアップ・確認・編集
  する目的での利用を想定しています。
- 改変したセーブデータの利用は自己責任です。アプリがフリーズする等の
  不具合が実際に確認されています (詳細は [FORMAT.md](FORMAT.md) 参照)。
  **編集前には必ず元ファイルのバックアップを取ってください**
  (エディタは上書き保存時に自動で `.bak` を作成しますが、念のため
  別の場所にもコピーを残すことを推奨します)。
- 特に `currentCrystal` (課金アイテム) を編集すると高確率でアプリが
  フリーズします。GUIの「簡単編集」タブからは意図的に除外しています。

## できること

- `UserData.saveIt` の復号 / 再暗号化 (CLI・ライブラリ)
- GUIエディタでの主要フィールドの編集
  (♡の数・音量・キャラクター名、生産アイテムの所持数・
  レベルアップ状態 など)
- 全フィールドの生JSON閲覧・編集 (上級者向け)

## 使い方

必要なもの:
- Python 3.8 以上 (追加パッケージのインストール不要)
- 対象アプリの `UserData.saveIt` (端末のアプリデータのバックアップ等
  から取得。取得方法は本リポジトリの対象外)

### GUIエディタ

```bash
python3 scripts/gui_editor.py
```

Mac 用にはスタンドアロンの `.app` としてビルドすることも可能です
(`scripts/build_mac.sh`)。Windows で `.exe` を作りたい場合は、
Windows 実機で `scripts/build_windows.bat` を実行してください
(PyInstaller はクロスコンパイルできないため)。

### CLI (復号だけしたい場合)

```bash
python3 scripts/decrypt_save.py UserData.saveIt main.bin
```

## 技術詳細

ファイルフォーマットの構造・パスワードを特定した手順・各フィールドの
意味・既知の不具合などの技術的な内容は [FORMAT.md](FORMAT.md) に
まとめています。

## ディレクトリ構成

```
scripts/
  saveit_format.py    SVITヘッダ解析・パスワード定数・ZIP暗号化/復号
  zipcrypto.py         Traditional PKZIP暗号 (ZipCrypto) の純Python実装
  mpatch.py             バイト位置つきMessagePackパーサ/差分パッチャ
  save_payload.py      main バイナリ (ヘッダ+MessagePack) のパース/構築
  decrypt_save.py      CLI: UserData.saveIt -> 復号済み main バイナリ
  gui_editor.py         GUI本体 (Tkinter)
  build_mac.sh          Mac用 .app ビルドスクリプト
  build_windows.bat     Windows用 .exe ビルドスクリプト (Windows機で実行)
```

`*.ipa` / `*.saveIt` 等の著作物・個人データは `.gitignore` で
リポジトリから除外しています。再現する場合は自分で入手した
`com.Happygamer.SenderGirl.ipa` と `UserData.saveIt` を用意してください。
