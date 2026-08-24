[日本語版はこちら / Japanese version →](FORMAT.md)

# UserData.saveIt format analysis

Technical documentation covering the save file's structure, how the
password was recovered, what each field means, and implementation
notes/caveats. For usage instructions, see [README-EN.md](README-EN.md).

## 1. `UserData.saveIt` container format

The first 10 bytes are a custom header; everything after that is a plain
zip file.

```
offset 0-3   : magic "SVIT" (a FourCC)
offset 4-7   : int32 LE = 2  (format version)
offset 8-9   : 2 flag bytes (observed value: 01 01, meaning not yet analyzed)
offset 10-   : a standard zip file (starts with "PK\x03\x04")
```

Stripping those 10 bytes yields a normal zip archive:

```bash
dd if=UserData.saveIt of=UserData.zip bs=1 skip=10
unzip -l UserData.zip
```

```
Archive:  UserData.zip
  Length      Date    Time    Name
---------  ---------- -----   ----
     2116  08-24-2026 13:13   main
```

The archive always contains exactly one entry, always named `main`
(unrelated to the actual save file name `UserData`).
- Compression: Deflate
- Encryption: **Traditional PKWARE encryption (ZipCrypto)** — not AES
- Written in **Zip64** format (seemingly always, even for tiny entries)

## Identifying the library

`com.Happygamer.SenderGirl.ipa` is a Unity 2017.1.1f1 / IL2CPP build.
`global-metadata.dat`'s string pool literally contains:

```
Unsupported file version: SVIT
Data is no valid SaveIt format. Wrong FOURCC.
Data is encrypted but no password was provided.
SaveIt.dll / SaveIt.SharpZLib.dll
SaveIt.ICSharpCode.SharpZipLib.Encryption.PkzipClassic
```

`UserData.saveIt` is produced by a Unity Asset called **"SaveIt"**, which
bundles a renamed copy of SharpZipLib (`SaveIt.SharpZLib`) and protects
save files using traditional ZipCrypto encryption.

## 2. Recovering the password

### Result

The game code (wherever it sets `BinaryTableSerializer.Password` on a
`SaveIt.TableSerializer.File` instance) uses a **fixed 128-character
constant baked directly into the IL2CPP binary** — it is not derived from
a device ID, random seed, or any other dynamic input. In other words,
**the same password is used on every device and for every save file**
(a naive brute-force over short numeric or lowercase-alphanumeric
passwords won't find it: the real password is 128 characters and mixes
upper/lower case).

```
JAuX4Sz2AkGJTvHUN0zCp6ydjLt3TQlTNTjIzJW9WzsorJnyEWy4JApJ73u0cNb34sThe0QmscEDgBhAFDvu0n8TCCSuxAKRmmlEg4CEwYTBxXB9vEyETVyAmZgMefH6
```

Verified by actually decrypting `work/UserData.zip` with this password
(see [scripts/decrypt_save.py](scripts/decrypt_save.py)).

### How it was found

1. Ran [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) (v6.7.46)
   against the `SenderGirl` binary and `global-metadata.dat` to recover
   IL2CPP class/method definitions (`dump.cs`, `script.json`).
2. From `dump.cs`, found the virtual addresses of:
   - `SaveIt.TableSerializer.File..ctor(string name)` — VA `0x1005A8F2C`
   - `SaveIt.TableSerializer.BinaryTableSerializer.set_Password(string)` — VA `0x1005B0828`
3. Loaded the `__TEXT,__text` section with `lief` and disassembled the
   whole thing as ARM64 with `capstone` (with `skipdata` enabled to skip
   over embedded data that isn't code).
4. Searched for `BL` instructions targeting those two addresses and found
   two call sites in the game's own code (around `0x1008efxxx`), each
   constructing a `File(...)` and immediately setting `Password`. Right
   before the `set_Password` call, register `x1` (the first argument) was
   loaded from a fixed address in the `__DATA` segment — a slot in the
   IL2CPP string-literal cache.
5. Looked up that slot address in the `ScriptString` table of
   Il2CppDumper's `script.json` (which maps each string-literal cache
   slot to the value it ultimately holds), which resolved to the
   128-character string above.
6. Confirmed by actually decrypting the zip extracted from
   `UserData.saveIt` with that password.

## 3. Structure of the decrypted payload

The decrypted `main` entry (2116 bytes) has two parts:

```
offset 0-176   (177 bytes) : fixed header
offset 177-180 (4 bytes)   : int32 LE = length of the payload that follows
offset 181-    :             the payload itself (MessagePack)
```

### Fixed header (177 bytes)

SaveIt.TableSerializer wraps "one named entry (`UserData`) plus its
value's type info". The value's declared type is `System.Byte[]`, and
its .NET assembly-qualified name is written out three times (once in
full, twice abbreviated) — presumably artifacts of a reflection-based
custom serializer resolving types. This is boilerplate that shouldn't
change between saves of the same app version, so the editor reuses it
verbatim as a template and only rewrites the trailing 4-byte payload
length.

### Payload: MessagePack

The payload is a single **MessagePack**-encoded map — this is the
game's actual data. All 46 keys found:

```
UniqueKey, Name, BGMOn, SEOn, VIBEOn, BGMVolume, SEVolume,
CreatedAt, ModifiedAt, boyfriendName, round, eventCompleteLevel,
currentCookieCount, currentCrystal, clickMakeCount, autoMakeSpeed,
comingEnemy, comingEnemyAppearTime, comingEnemyBackTime,
comingEnemyKind, comingEnemyDamage, lastSuspendTime, tutoProgress,
shopBadgeFlg, totalCookieCount, maxCookie, firstCookieTime,
totalClickMakeCount, totalClickCount, comeEnemyCount, repelEnemyCount,
useRepelItemCount, lostCookieCount, friendHistory, friendHistTemp,
facilitiesLevel, powerupItemLevel, tapItemLevel, teaItemLevel,
maxTeaSet, teaset, openActionIds, appReview, appReviewCrystal,
boostAvailavleTime, boostOnTime
```

A few values carry special meaning beyond plain msgpack primitives:

- **Large numbers (heart counts)**: `currentCookieCount` /
  `totalCookieCount` / `maxCookie` / `comingEnemyDamage` appear as a
  4-field map `{"flags": int, "hi": int, "mid": int, "lo": int}`. This
  is exactly the internal wire layout of **.NET's `System.Decimal`**
  (same as `decimal.GetBits()`: bits 16-23 of `flags` hold the scale,
  bit 31 the sign, and `hi/mid/lo` concatenated form a 96-bit unscaled
  integer) — presumably used to keep very large heart counts precise
  beyond what an int64 could hold. `scripts/save_payload.py`'s
  `Decimal96` class converts these to/from Python's `decimal.Decimal`
  automatically.
- **Timestamps**: `CreatedAt` / `ModifiedAt` / `lastSuspendTime` /
  `firstCookieTime` are integers counting seconds since 0001-01-01
  (.NET's `DateTime.MinValue`), i.e. `DateTime.Ticks / 10_000_000`.
  Converting `ModifiedAt` yields exactly the same timestamp that the zip
  entry itself recorded as its last-modified time, which confirms this
  interpretation.
- **`facilitiesLevel` / `powerupItemLevel` / `tapItemLevel` /
  `teaItemLevel`**: confirmed against the live app.
  - `facilitiesLevel` (array of 11): how many of each of the 11
    auto-production items the player owns. Each item's name/appearance
    changes across 4 upgrade stages (`powerupItemLevel`) — confirmed
    on-device:

    | # | Lv1 | Lv2 | Lv3 | Lv4 |
    |---|---|---|---|---|
    | 1 | 電柱 (utility pole) | ダンボール (cardboard box) | 透明マント (invisibility cloak) | 着ぐるみ (mascot costume) |
    | 2 | 監視カメラ (surveillance camera) | 全方位型監視カメラ (omni camera) | 暗視カメラ (night-vision camera) | ロボット型監視カメラ (robot camera) |
    | 3 | 探偵さん (detective) | サイバー探偵さん (cyber detective) | 霊能探偵さん (psychic detective) | 名探偵さん (master detective) |
    | 4 | 監視衛星 (surveillance satellite) | 探査衛星 (probe satellite) | キラー衛星 (killer satellite) | 宇宙ステーション (space station) |
    | 5 | 殺し屋さん (hitman) | スナイパーさん (sniper) | ボマーさん (bomber) | 仕事人さん (hired professional) |
    | 6 | 警察官さん (police officer) | 刑事さん (detective/cop) | FBIさん (FBI agent) | 警視総監さん (superintendent-general) |
    | 7 | 総理大臣さん (prime minister) | 連合国首相さん (allied premier) | 法王さん (pope) | 大統領さん (president) |
    | 8 | 調査兵団さん (survey corps) | 巨人兵団さん (titan corps) | 大型巨人兵団さん (colossal titan corps) | 兵長兵団さん (captain's corps) |
    | 9 | 寄生さん (parasite) | 完全寄生さん (full parasite) | 寄生失敗さん (failed parasite) | 最強生物さん (strongest being) |
    | 10 | 願いを叶える龍 (wish-granting dragon) | 願いを叶えるネコ (wish-granting cat) | 願いを叶えるノート (wish-granting notebook) | 願いを叶えるロボ (wish-granting robot) |
    | 11 | 彼の部屋の鍵 (his room key) | 彼の机の鍵 (his desk key) | 彼の実家の鍵 (his family home key) | 彼の心の鍵 (the key to his heart) |

  - `powerupItemLevel` (array of 11, each an array of 4): the 4-stage
    upgrade state for each of those 11 items. `0`=locked (hidden, no
    details, can't buy) / `1`=unlocked (unseen, shows a "New" badge) /
    `2`=seen (its detail screen was opened) / `3`=purchased.
  - `tapItemLevel` (array of 4): state of the 4 manual-tap power-up
    items (お掃除/cleaning, メイク/makeup, トレーニング/training,
    ヨガ/yoga), same 0-3 meaning as above.
  - `teaItemLevel` (array of 4): state of the items that prevent
    friends from interrupting background play (which otherwise steal
    clicks). `0`=locked / `1`=unlocked(not purchased) /
    `2`=purchased (only 3 states — no "seen" state). For `n` = the count
    of `2`s in `teaItemLevel`, `maxTeaSet = 2n` (0→0, 1→2, 2→4, 3→6,
    4→8 — confirmed on-device; `teaset` is the current holding, capped
    at `maxTeaSet`).
- **`friendHistory` / `friendHistTemp`**: a .NET `List<T>` serialized
  field-by-field via reflection (`_items` array + `_size` + `_version`).
  The `_items` array has spare capacity beyond `_size`, with unused
  trailing slots (often null). Easy to corrupt if edited carelessly, so
  the editor only exposes these through the raw "Advanced (JSON)" tab.

### Methodology

Brute-forced the offset at which `msgpack.Unpacker` both succeeds *and*
consumes every remaining byte; offset 181 (header length 177 + 4) hit on
the first try and decoded the full 46-key map. The Decimal/timestamp
interpretations were corroborated by cross-field sanity checks (e.g.
lifetime totals ≥ current values) and by the exact match against the
zip entry's own timestamp.

## 4. Save editor (GUI) implementation notes

[scripts/gui_editor.py](scripts/gui_editor.py) — a Tkinter GUI. Since it
only uses Python's standard-library Tkinter, the same code runs on both
Mac and Windows. See [README-EN.md](README-EN.md) for usage.

### Verification performed

- Full round trip tested: decrypt → decode → edit values → encode →
  rebuild the encrypted zip → decrypt again → decode, confirming edited
  values land correctly and every untouched value (including Decimal96
  fields and multi-byte text) is byte-for-byte unchanged.
- The rebuilt encrypted zip was verified to decrypt cleanly both with
  this project's own reader (Python's stdlib `zipfile`) and with an
  independent implementation, Info-ZIP's `unzip` (`unzip -t`).
- The packaged `.app` itself was launched and visually confirmed to
  render correctly, and the GUI's open/edit/save logic was exercised
  directly and confirmed to work. On-device testing (no freeze)
  confirmed as well.

### A real freeze bug found on-device, and its fix

**Symptom**: loading an editor-saved `UserData.saveIt` on the actual
device froze the app at the game's logo screen, right after the Unity
splash. **This happened even when nothing was edited** — just opening
the file and saving it back caused the same freeze.

**Root cause**: the original implementation decoded the MessagePack
payload into a Python dict, then re-encoded the *entire* thing from
scratch with `msgpack.packb()`. That approach can change a value's
**wire-level byte width even when the logical value is unchanged**. For
example, `BGMVolume`/`SEVolume` were originally float32 (4 bytes, tag
`0xca`), but Python's `msgpack.packb()` always writes a Python `float`
as float64 (8 bytes, tag `0xcb`) — so the wire representation changed
**even without any edit**. SaveIt's parser appears to be sensitive to
this byte width, and that single mismatch was enough to desync the rest
of the parse and freeze the app.

**Fix**: added [scripts/mpatch.py](scripts/mpatch.py), a MessagePack
parser that tracks each value's exact byte range. On save, the pre-edit
raw bytes are diffed against the post-edit values: **byte ranges whose
value is unchanged are copied verbatim from the original**, and only
byte ranges that actually changed are re-encoded, using the *same*
type/width as the original wherever the new value still fits (widening
only when it doesn't, following standard MessagePack rules). The
`msgpack` PyPI package is no longer a dependency.

**Verification**: after the fix, opening a file and saving it with zero
edits now produces output that is **100% byte-identical** to the
original. Editing a single field only touches that field's bytes (e.g.
toggling one boolean changes exactly 1 byte) — nothing else moves.
On-device testing confirmed neither "save with no edits" nor "save with
a few fields edited" freezes anymore.

One open question: toggling BGM on/off saves and reloads correctly
(the JSON value round-trips fine), but doesn't actually seem to affect
audio playback in-game. Not investigated further — it's outside the
save editor's core purpose.

### ⚠️ Editing `currentCrystal` freezes the app on launch

Changing the value of `currentCrystal` (the paid/premium currency) was
confirmed on-device to freeze the app right on launch. **This field has
been removed from the GUI's "Simple edit" tab.** If you want to touch it
anyway, do so at your own risk via the "Advanced (JSON)" tab — expect a
freeze.

Further testing narrowed it down further: **any value up to 127 is
fine; 128 or above always freezes.** That boundary matches exactly the
overflow point of a signed 8-bit integer (`sbyte`, range -128 to 127).
The most likely explanation is that somewhere in the game (at least
along some code path) `currentCrystal` is handled as an `sbyte`, and a
value of 128+ triggers an overflow or otherwise invalid state that
crashes the app. Since the in-game shop offers a "buy 1400" button, the
real purchase flow presumably goes through a different (wider-typed)
path — meaning this narrow type might be a latent bug in the game itself
that only a save editor's direct value edit exposes. An alternative
explanation is that the value is used as an index into some array sized
for only 127 entries. Neither is confirmed, but no simpler explanation
fits the exact 127/128 boundary as well.

### Remaining caveats

- The original zip used Zip64 + a data descriptor; since the editor
  knows the exact size upfront, it writes a simpler standard (non-
  Zip64, no data descriptor) zip instead. Both are valid per the zip
  spec and SharpZipLib should read either, and the on-device freeze fix
  above has been confirmed, but whether the zip-format difference itself
  matters was not specifically isolated (the freeze's root cause was the
  MessagePack byte-width mismatch above).
- If you edit a number to a value that no longer fits the original
  field's byte width (e.g. `0`, a 1-byte fixint, changed to `55555`),
  that field's byte width necessarily grows (shifting everything after
  it in the payload) — no implementation can avoid this. That said, the
  original data itself already uses value-dependent compact widths
  (confirmed by inspection: `round` (=0) is 1 byte, `clickMakeCount`
  (=1000000) is 5 bytes, etc.), so widening follows standard MessagePack
  minimal-width rules and should look close to what SaveIt itself would
  produce for that value.
- Wheel/trackpad scrolling in the GUI has been confirmed to work with a
  physical mouse wheel; some trackpad setups (particularly with other
  input-related utilities installed) have been reported not to respond.
  Root cause not identified. Dragging the scrollbar itself always works.

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

`*.ipa` / `*.saveIt` and intermediate research artifacts (everything
under `work/`: the unpacked IPA, Il2CppDumper output, disassembly, etc.)
are excluded from the repo via `.gitignore`, since they are copyrighted
app data / personal save data. To reproduce, supply your own copy of
`com.Happygamer.SenderGirl.ipa` and `UserData.saveIt` and follow the
steps in [README-EN.md](README-EN.md).
