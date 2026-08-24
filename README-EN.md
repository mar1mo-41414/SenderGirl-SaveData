[日本語版はこちら / Japanese README →](README.md)

# SenderGirl-SaveData

An unofficial toolkit for decrypting and editing `UserData.saveIt`, the
save file of the iOS app "ゆるヤミ彼女" (bundle id `com.Happygamer.SenderGirl`).

Includes the results of reverse-engineering the encrypted container
format, recovering the password, and decoding the data structure, plus a
GUI save editor built on top of that work.

## Supported app

**Only the original "ゆるヤミ彼女" (`com.Happygamer.SenderGirl`) is
supported.**

There's a sister title, **【関西弁版】ゆるヤミ彼女と100万件のメッセージ**
("Kansai-dialect version", `com.Happygamer.SenderGirlK`). It's
fundamentally the same game — item names etc. appear identical, and it
also uses a `UserData.saveIt` save file — but **this tool does not
support it**, because:

- There's no guarantee the encryption password is the same (it's a
  constant embedded in each app's own binary, so the password recovered
  for the original may not decrypt the K version's saves).
- Any additional unlockable content may map to the data structure
  differently than in the original.
- The K version's actual save data has not been examined at all.

If you want to use this with the K version, follow the methodology in
[FORMAT-EN.md](FORMAT-EN.md) to re-derive the password and verify the
structure yourself first.

## Disclaimer

- This is an **unofficial fan-made tool**, not affiliated with the
  app's developer or publisher in any way.
- It's meant for backing up, inspecting, and editing **your own** save
  data that you already own.
- Using an edited save file is at your own risk. On-device freezes have
  actually been observed with certain edits (see
  [FORMAT-EN.md](FORMAT-EN.md) for details). **Always back up the
  original file before editing** (the editor auto-creates a timestamped
  backup under `~/.SGSE_bak/` on overwrite, but keeping a separate copy
  elsewhere is recommended too).
- In particular, editing `currentCrystal` (the paid/premium currency)
  reliably freezes the app. It's intentionally excluded from the GUI's
  "Simple edit" tab.

## What it does

- Decrypt / re-encrypt `UserData.saveIt` (CLI / library)
- Edit the most commonly-wanted fields through a GUI
  (heart counts, volume, the character's name, how many of each
  production item you own and their upgrade states, etc.)
- View/edit every field as raw JSON (advanced use)

## Download (pre-built GUI)

Pre-built binaries for Mac (Apple Silicon) and Windows (x64) are
available on the
[Releases page](https://github.com/mar1mo-41414/SenderGirl-SaveData/releases).
GitHub Actions builds and attaches them automatically for every tagged
release (`.github/workflows/build.yml`).

These are unsigned/unnotarized builds, so the OS will warn you on first
launch:
- Mac: right-click → "Open", or run
  `xattr -cr SenderGirlSaveEditor.app` to clear the quarantine flag.
- Windows: if SmartScreen warns you, click "More info" → "Run anyway".

## Usage (running from source)

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
