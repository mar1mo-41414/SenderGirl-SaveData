[日本語版はこちら / Japanese README →](README.md)

# SenderGirl-SaveData

An unofficial toolkit for decrypting and editing `UserData.saveIt`, the
save file of the iOS app "SenderGirl" (`com.Happygamer.SenderGirl`).

Includes the results of reverse-engineering the encrypted container
format, recovering the password, and decoding the data structure, plus a
GUI save editor built on top of that work.

## Disclaimer

- This is an **unofficial fan-made tool**, not affiliated with the
  app's developer or publisher in any way.
- It's meant for backing up, inspecting, and editing **your own** save
  data that you already own.
- Using an edited save file is at your own risk. On-device freezes have
  actually been observed with certain edits (see
  [FORMAT-EN.md](FORMAT-EN.md) for details). **Always back up the
  original file before editing** (the editor auto-creates a `.bak` on
  overwrite, but keeping a separate copy elsewhere is recommended too).
- In particular, editing `currentCrystal` (the paid/premium currency)
  reliably freezes the app. It's intentionally excluded from the GUI's
  "Simple edit" tab.

## What it does

- Decrypt / re-encrypt `UserData.saveIt` (CLI / library)
- Edit the most commonly-wanted fields through a GUI
  (cookie counts, volume, the character's name, how many of each
  production item you own and their upgrade states, etc.)
- View/edit every field as raw JSON (advanced use)

## Usage

Requirements:
- Python 3.8+ (no extra packages needed)
- Your own copy of `UserData.saveIt` (obtained from a backup of the
  app's data on your device — how to extract it is outside this
  repo's scope)

### GUI editor

```bash
python3 scripts/gui_editor.py
```

A standalone Mac `.app` build is also possible
(`scripts/build_mac.sh`). To build a Windows `.exe`, run
`scripts/build_windows.bat` on an actual Windows machine (PyInstaller
can't cross-compile).

### CLI (decrypt only)

```bash
python3 scripts/decrypt_save.py UserData.saveIt main.bin
```

## Technical details

The container format, how the password was recovered, what each field
means, and known issues are documented in
[FORMAT-EN.md](FORMAT-EN.md).

## Layout

```
scripts/
  saveit_format.py    SVIT header parsing, password constant, zip encrypt/decrypt
  zipcrypto.py         Pure-Python implementation of traditional PKZIP (ZipCrypto) encryption
  mpatch.py             Byte-range-tracking MessagePack parser / diff patcher
  save_payload.py      Parsing/building of the main payload (header + MessagePack)
  decrypt_save.py      CLI: UserData.saveIt -> decrypted main payload
  gui_editor.py         The GUI itself (Tkinter)
  build_mac.sh          Mac .app build script
  build_windows.bat     Windows .exe build script (run on a Windows machine)
```

`*.ipa` / `*.saveIt` and other copyrighted/personal data are excluded
from the repo via `.gitignore`. To reproduce, supply your own copy of
`com.Happygamer.SenderGirl.ipa` and `UserData.saveIt`.
