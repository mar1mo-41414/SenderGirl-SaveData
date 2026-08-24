[Technical details (English) →](FORMAT-EN.md)

# UserData.saveIt フォーマット解析

セーブファイルの構造・パスワードの特定手順・各フィールドの意味・
実装上の注意点をまとめた技術ドキュメント。使い方だけ知りたい場合は
[README.md](README.md) を参照。

## 1. UserData.saveIt の構造

先頭10バイトが独自ヘッダで、それ以降は素の ZIP ファイル。

```
offset 0-3   : マジック "SVIT" (FourCC)
offset 4-7   : int32 LE = 2  (フォーマットバージョン)
offset 8-9   : フラグ 2バイト (観測値: 01 01。詳細は未解析)
offset 10-   : 標準 ZIP ("PK\x03\x04" から開始)
```

10バイトを取り除くだけで正規の ZIP として扱える:

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

ZIP の中身は常にエントリ1件、名前は固定で `main`
(実際のセーブファイル名 `UserData` とは無関係)。
- 圧縮方式: Deflate
- 暗号化方式: **Traditional PKWARE encryption (ZipCrypto)**。AESではない
- **ZIP64 形式**で書き出される (サイズが小さくても常にこの形式のよう)

## ライブラリの特定

`com.Happygamer.SenderGirl.ipa` は Unity 2017.1.1f1 / IL2CPP ビルド。
`global-metadata.dat` の文字列プールに以下がそのまま含まれており、

```
Unsupported file version: SVIT
Data is no valid SaveIt format. Wrong FOURCC.
Data is encrypted but no password was provided.
SaveIt.dll / SaveIt.SharpZLib.dll
SaveIt.ICSharpCode.SharpZipLib.Encryption.PkzipClassic
```

`UserData.saveIt` は Unity Asset の **「SaveIt」**というセーブ用アセットが
生成するファイルであり、内部で SharpZipLib を `SaveIt.SharpZLib` という
名前空間にリネームして同梱し、ZIP の Traditional (ZipCrypto) 暗号化で
セーブファイルを保護していることが分かった。

## 2. パスワードの特定

### 結論

ゲームコード側 (`SaveIt.TableSerializer.File` のインスタンスに対して
`BinaryTableSerializer.Password` を設定している箇所) が使っているのは、
**IL2CPP バイナリに直接埋め込まれた固定の128文字定数**で、デバイスIDや
乱数など動的な要素からは一切生成されていない。つまり **全デバイス・
全セーブファイルで共通のパスワード** と考えられる (数字4〜8桁や
小文字英数字8桁程度のブルートフォースで見つからないのは、実際の
パスワードが大文字・小文字混在の128文字だったため)。

```
JAuX4Sz2AkGJTvHUN0zCp6ydjLt3TQlTNTjIzJW9WzsorJnyEWy4JApJ73u0cNb34sThe0QmscEDgBhAFDvu0n8TCCSuxAKRmmlEg4CEwYTBxXB9vEyETVyAmZgMefH6
```

`work/UserData.zip` をこのパスワードで実際に復号できることを確認済み
([scripts/decrypt_save.py](scripts/decrypt_save.py))。

### 特定した手順

1. [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) (v6.7.46) に
   `SenderGirl` バイナリと `global-metadata.dat` を渡し、IL2CPP の
   クラス/メソッド定義 (`dump.cs`, `script.json`) を復元。
2. `dump.cs` から以下2メソッドの VA (仮想アドレス) を特定:
   - `SaveIt.TableSerializer.File..ctor(string name)` — VA `0x1005A8F2C`
   - `SaveIt.TableSerializer.BinaryTableSerializer.set_Password(string)` — VA `0x1005B0828`
3. Python の `lief` でバイナリの `__TEXT,__text` セクションを取得し、
   `capstone` で ARM64 として全体をディスアセンブル
   (skipdata を有効化してコード中に混ざるデータ領域をスキップ)。
4. 上記2アドレスへ `BL` している呼び出し元を検索したところ、ゲーム独自
   コード内 (`0x1008efxxx` 付近) に2箇所発見。いずれも
   `File(...)` を生成した直後に `Password` を設定するパターンで、
   `set_Password` 呼び出し直前で `x1` レジスタ (第1引数) が
   `__DATA` セグメント上の固定アドレス (文字列リテラルキャッシュの
   スロット) からロードされていた。
5. そのスロットアドレスを Il2CppDumper が出力した `script.json` の
   `ScriptString` テーブル (文字列リテラルキャッシュの各スロットが
   最終的にどの文字列を指すかの対応表) で引いたところ、上記128文字の
   文字列がヒット。
6. 実際に `UserData.saveIt` から抽出した ZIP をこのパスワードで復号し、
   有効なデータが得られることを確認して裏付けた。

## 3. 復号後のデータの構造

復号した `main` エントリ (2116バイト) は2つのパートに分かれる。

```
offset 0-176   (177バイト) : 固定ヘッダ
offset 177-180 (4バイト)   : int32 LE = 以降のペイロードのバイト数
offset 181-    :             ペイロード本体 (MessagePack)
```

### 固定ヘッダ (177バイト)

SaveIt.TableSerializer が「1個の名前付きエントリ ("UserData") とその
値の型情報」をラップしたもの。値の型は `System.Byte[]` で、.NET の
アセンブリ修飾型名をフル/短縮形で3回連続して書き出している (フル形式
1回 + 短縮形2回。おそらく独自のリフレクションベースシリアライザが
型解決のために書き出しているもので、アプリのバージョンが変わらない
限り内容は不変と考えられる)。エディタでは、このヘッダをそのまま
テンプレートとして再利用し、末尾4バイトのペイロード長だけ書き換える。

### ペイロード本体: MessagePack

**MessagePack** 形式でエンコードされた1個の連想配列 (dict)。
これがゲームの実データそのもの。判明したキー一覧 (46個):

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

いくつかの値は素の msgpack のプリミティブ型ではなく、特別な意味を
持つ:

- **巨大な数値 (♡の数など)**: `currentCookieCount` /
  `totalCookieCount` / `maxCookie` / `comingEnemyDamage` は
  `{"flags": int, "hi": int, "mid": int, "lo": int}` という4フィールド
  の dict として現れる。これは **.NET の `System.Decimal` の内部表現**
  (`decimal.GetBits()` と同じレイアウト: `flags` の bit16-23 がスケール
  (10のべき乗)、bit31 が符号、`hi/mid/lo` を連結した96bit整数が仮数部)
  そのもの。桁数の大きい♡の数を正確に (int64を超える精度で)
  保持するために使われていると考えられる。
  `scripts/save_payload.py` の `Decimal96` クラスが Python の
  `decimal.Decimal` と自動的に相互変換する。
- **日時**: `CreatedAt` / `ModifiedAt` / `lastSuspendTime` /
  `firstCookieTime` は「西暦1年1月1日 (.NET の `DateTime.MinValue`) から
  の経過秒数」の整数 (`DateTime.Ticks / 10_000_000` に相当)。
  `ModifiedAt` の値を変換すると、ZIPエントリに実際に記録されていた
  更新日時と完全に一致し、この解釈の正しさを裏付けている。
- **`facilitiesLevel` / `powerupItemLevel` / `tapItemLevel` /
  `teaItemLevel`**: 実機でゲームと突き合わせて確認済み。
  - `facilitiesLevel` (11要素の配列): 自動生産系アイテム (11種類) の
    **所持数**。各アイテムはレベルアップ (`powerupItemLevel`) に伴って
    見た目・名前が4段階で変化する (実機確認済み、名前は下表):

    | # | Lv1 | Lv2 | Lv3 | Lv4 |
    |---|---|---|---|---|
    | 1 | 電柱 | ダンボール | 透明マント | 着ぐるみ |
    | 2 | 監視カメラ | 全方位型監視カメラ | 暗視カメラ | ロボット型監視カメラ |
    | 3 | 探偵さん | サイバー探偵さん | 霊能探偵さん | 名探偵さん |
    | 4 | 監視衛星 | 探査衛星 | キラー衛星 | 宇宙ステーション |
    | 5 | 殺し屋さん | スナイパーさん | ボマーさん | 仕事人さん |
    | 6 | 警察官さん | 刑事さん | FBIさん | 警視総監さん |
    | 7 | 総理大臣さん | 連合国首相さん | 法王さん | 大統領さん |
    | 8 | 調査兵団さん | 巨人兵団さん | 大型巨人兵団さん | 兵長兵団さん |
    | 9 | 寄生さん | 完全寄生さん | 寄生失敗さん | 最強生物さん |
    | 10 | 願いを叶える龍 | 願いを叶えるネコ | 願いを叶えるノート | 願いを叶えるロボ |
    | 11 | 彼の部屋の鍵 | 彼の机の鍵 | 彼の実家の鍵 | 彼の心の鍵 |

  - `powerupItemLevel` (11要素 × 各4要素の配列): 上記11種のアイテム
    それぞれが持つ4段階のレベルアップの**状態**。値の意味:
    `0`=未解放 (詳細非表示・購入不可) / `1`=解放済み(未確認、Newアイコン
    付き) / `2`=確認済み(詳細画面を開いた) / `3`=購入済み。
  - `tapItemLevel` (4要素の配列): 手動タップ強化アイテム
    (お掃除・メイク・トレーニング・ヨガ、の4種) の状態。値の意味は
    `powerupItemLevel` と同じ (0〜3)。
  - `teaItemLevel` (4要素の配列): バックグラウンド中の友達の妨害
    (クリック数を奪われる) を防ぐアイテムの状態。値の意味:
    `0`=未解放 / `1`=解放済み(未購入) / `2`=購入済み (3段階のみ、
    「未確認」状態は無い)。`teaItemLevel` のうち `2` (購入済み) の
    個数 `n` に対して `maxTeaSet = 2n` (0個→0、1個→2、2個→4、3個→6、
    4個→8、と確認されている。`teaset` は `maxTeaSet` を上限とする
    現在の所持数)。
- **`friendHistory` / `friendHistTemp`**: .NET の `List<T>` を
  リフレクションでフィールド単位そのままシリアライズしたもの
  (`_items` 配列 + `_size` + `_version`)。`_items` は内部容量ぶんの
  余剰要素を持ち、末尾は未使用スロット (null 等) になっていることが
  ある。編集時にうっかり壊しやすい部分なので、エディタでは基本的に
  「詳細 (JSON)」タブでの直接編集のみ対応。

### 解析手法

`msgpack.Unpacker` でオフセットを総当たりし、「デコードが成功し、
かつ残りバイト数をちょうど使い切る」オフセットを探索したところ
offset 181 (=ヘッダ長177+4) で一発的中し、46キーの辞書がまるごと
デコードできた。Decimal / 日時の解釈は、他のフィールドとの大小関係
(累計 ≥ 現在値など) や、ZIPのタイムスタンプとの一致によって裏付けた。

## 4. セーブエディタ (GUI) の実装メモ

[scripts/gui_editor.py](scripts/gui_editor.py) — Tkinter 製。
Python 標準の Tkinter のみを使っているため Mac / Windows どちらでも
同じコードで動く。使い方は [README.md](README.md) を参照。

### 動作確認

- decrypt → decode → 値を編集 → encode → 暗号化ZIP再構築 → 再度decrypt
  → decode という完全な往復を行い、編集した値が正しく反映され、
  編集していない他の値 (Decimal96・多バイト文字含む) が一切変化しない
  ことをテスト済み。
- 再構築した暗号化ZIPは、本実装の復号処理 (Python標準 `zipfile`) と、
  独立実装である Info-ZIP `unzip` コマンドの両方で問題なく復号・検証
  (`unzip -t`) できることを確認済み。
- GUI自体もビルド済み `.app` を実際に起動し、画面が正しく表示される
  こと、および開く/編集/保存の内部ロジックが実際に動作することを確認
  済み。実機での動作確認 (フリーズしないこと) も確認済み。

### 実機で発生した不具合とその修正

**症状**: エディタで保存した `UserData.saveIt` を実機に入れると、Unity
スプラッシュの後のゲームロゴ画面でフリーズする。**何も編集せずに開いて
上書きしただけでも同じ症状が発生した。**

**原因**: 初期実装は、MessagePackペイロードを一旦Pythonのdictに
デコードしたあと、標準の `msgpack.packb()` で丸ごと再エンコードして
いた。この方式だと、**値そのものは同じでも、ワイヤ上のバイト表現
(型の幅) が変わってしまう** ケースがあった。実例:
`BGMVolume`/`SEVolume` は元データでは float32 (4バイト, タグ `0xca`)
だったが、Pythonの `msgpack.packb()` はPythonの `float` を常に
float64 (8バイト, タグ `0xcb`) として書き出すため、**編集していない
のに** ワイヤ表現が変わっていた。SaveIt側のパーサがバイト幅に敏感な
実装になっていると見られ、この差分だけでパースが丸ごとズレて
フリーズに至ったと考えられる。

**修正**: [scripts/mpatch.py](scripts/mpatch.py) を新設し、MessagePack
ペイロードを「バイト位置つき」でパースするように変更。保存時は
編集前の生バイト列と編集後の値を突き合わせ、**値が変わっていない
部分は元のバイト列をそのままコピーし、値が変わった部分だけ元と
同じ型/バイト幅で書き直す** (新しい値がその幅に収まらない場合のみ、
標準のMessagePackエンコード規則に従って幅を広げる) 方式に変更した。
`msgpack` パッケージへの依存はこれに伴い削除。

**検証**: 修正後、「一切編集せずに開いて保存」した結果が
**編集前のバイト列と完全に一致 (100% byte-identical)** することを
確認済み。一部フィールドを編集した場合も、変更点だけがピンポイントで
書き換わり (例: bool 1フィールドのトグルだけなら差分は1バイトのみ)、
無関係な箇所は一切変化しないことを確認済み。実機で「編集なしで保存」
「一部フィールドだけ編集して保存」のいずれもフリーズしなくなったことを
確認済み。

なお、BGMのON/OFFトグルは保存・読み込み自体は正しく動作している
(JSON上の値は正しく反映される) が、実機でトグルしても実際の音声再生
挙動には反映されない、という報告がある。セーブエディタの本質的な問題
ではないため、これ以上は追わないこととした。

### ⚠️ `currentCrystal` (クリスタル) を編集すると起動直後にフリーズする

課金アイテムである「クリスタル」の値 (`currentCrystal`) を書き換えると、
アプリ起動直後にフリーズすることが実機で確認された。**このフィールドは
GUIの「簡単編集」タブから削除済み** (触りたい場合は自己責任で
「詳細 (JSON)」タブから編集すること。フリーズを覚悟すること)。

さらに検証したところ、**値が127以下ならどんな数字でもフリーズせず、
128以上にすると必ずフリーズする**ことが判明した。これは符号付き8bit
整数 (`sbyte`, 範囲 -128〜127) のオーバーフロー境界と正確に一致する。
おそらくゲーム内部のどこかで `currentCrystal` を (少なくとも一部の
処理経路で) `sbyte` として扱っており、128以上の値がオーバーフロー/
不正な値を引き起こしてクラッシュしていると考えられる。ショップ画面には
1400個購入できるボタンが存在するため、実際の購入処理はおそらく別の
(より広い型の) 経路を通っており、この狭い型は編集時にしか顕在化しない
潜在バグの可能性がある。あるいは何らかの配列のインデックスとして
使われていて127個までしか領域が無い、という可能性も考えられる。
確証はないが、127/128という境界値は上記以外では説明がつきにくい。

### 残っている注意点

- 元のZIPは ZIP64 + data descriptor 形式だったが、エディタが書き出す
  ZIPはサイズが事前に分かっているため、それらを使わないシンプルな
  標準ZIP形式で書き出している。ZIP仕様上どちらも正当な形式で
  SharpZipLib は両方読めるはずで、実機でのフリーズ解消も確認済みだが、
  ZIP形式の違いそのものが原因でなかったことまでは厳密には切り分けて
  いない (今回のフリーズの主因はMessagePackのバイト幅不一致だった)。
- 数値を編集して元の型の幅に収まらない大きな値にした場合 (例:
  0 (1バイトの fixint) → 55555 のような大幅な増加)、その項目だけは
  バイト幅が変わる (=その項目以降のオフセットがずれる)。これはどんな
  実装でも原理上避けられない。ただし元データ自体も値に応じて
  可変長のコンパクトな幅を使っている (実測で確認済み: `round`(=0) は
  1バイト、`clickMakeCount`(=1000000) は5バイト、など) ため、この
  ケースでの書き出しは MessagePack の標準的な最小幅エンコードに従って
  おり、SaveIt自身が同じ値を書いた場合と近い形になっていると考えられる。
- GUIのホイール/トラックパッドスクロールは、マウスホイールでは動作を
  確認しているが、一部のトラックパッド環境 (他のユーティリティ等との
  組み合わせ) では反応しないケースが報告されている。原因未特定。
  スクロールバーのドラッグは常に有効。

## 5. 【関西弁版】(SenderGirlK) 対応

姉妹作 **【関西弁版】ゆるヤミ彼女と100万件のメッセージ**
(`com.Happygamer.SenderGirlK`) の復号済みIPA・実機の
`UserData.saveIt` を入手して調査した結果、以下が判明した。

### 判明したこと

- **暗号化パスワードは無印と完全に共通**。無印用に特定した128文字の
  定数キーで、K版の `UserData.saveIt` もそのまま復号できた
  (2026-08-25 実データで確認)。
- ペイロードのキー数は49個 (無印は46個)。無印の全フィールドが同じ
  意味で存在し、それに加えて以下の3フィールドが追加されている
  (実機検証、2026-08-25):
  - `openClothesIds` — 15要素の配列。着せ替え衣装の開放状態。
    `0`=未解放 / `1`=解放済み(未着用) / `2`=解放済み(着用歴あり)。
    衣装自体に固有の名前は無い (説明文はあるが簡単な名前は無い) との
    こと。
  - `selectClothes` — 単一の int。選択中の衣装ID。`-1`=未選択。
  - `nextTapItemAvailStatus` — 単一の int。**意味は未だ不明**
    (無視してよい値の可能性もある)。
- `facilitiesLevel` (11種) / `powerupItemLevel` (各4段階) は無印と
  **完全に同一** (アイテムの並び順・名前とも無印と同じ。無印で
  「電柱」だったものはK版でも「電柱」)。`maxTeaSet` の計算式
  (購入済み `teaItemLevel` の個数 × 2) も無印と同じ。
- `tapItemLevel` の要素数が7個 (無印は4個)。名前は衣装名で、無印とは
  完全に別:

  | # | 名前 | 解放条件 |
  |---|---|---|
  | 1 | 猛虎おろしな服 | - |
  | 2 | インテリ女子な服 | 部屋タップ300回 |
  | 3 | おりぼんモンスターな服 | - |
  | 4 | タコヤキはっぴーな服 | 部屋タップ750回 |
  | 5 | フライングアイドルな服 | - |
  | 6 | ミナミの女王な服 | 部屋タップ1250回 |
  | 7 | 新世界タワーな服 | - |

  解放条件の「部屋タップ回数」は `totalClickCount` の値と見られる
  (タップで増える数値そのものではなく、タップした回数)。

### ⚠️ `totalClickCount` (部屋タップ回数) を編集するとフリーズする

上記の解放条件に使われているためか、`totalClickCount` を直接編集
すると実機でフリーズすることが確認された (2026-08-25)。他のどの値
との整合性が必要なのかは未検証。**タップ回数はいじらず、
`tapItemLevel` の状態を直接書き換えて解放する方が安全**
(この方法なら実際に確認済みで、タップ回数を合わせなくても問題なく
使えている)。`currentCrystal` と同様、このフィールドはGUIの
「簡単編集」タブから除外している。無印・K版共通の項目のため、
この注意点は無印にも当てはまる可能性がある。

### エンベロープ (ヘッダ) の長さが違う

外側のエンベロープ (「UserData」という名前 + 値の型情報を書き出した
部分) はアプリのビルドに使われた .NET ランタイムのバージョン文字列
が異なるため、無印 (177バイト) と K版 (156バイト) でバイト長が
異なる。具体的には型記述文字列が
`"System.Byte[], mscorlib, Version=2.0.5.0, Culture=neutral, PublicKeyToken=null"`
のように、無印 (`"...Version=2.0.0.0..."`、`Culture=neutral` を省略した
短い形式) と微妙に違う内容になっている。

このため `scripts/save_payload.py` は「先頭Nバイトは固定」という
決め打ちをやめ、.NET の7bitエンコード長さプレフィックス形式に従って
エンベロープを毎回きちんとパースする方式に変更した。これにより、
無印・K版のどちらのファイルを渡しても (ヘッダ長を意識せずに)
同じ関数で正しく読み書きできる。

### GUIでの扱い

- ファイルを開くと `openClothesIds` などK版専用キーの有無で自動的に
  無印/K版を判定し、右上に判定結果のバッジを表示する。
- K版限定のフィールドは「関西弁版限定」という専用タブに分離した
  (無印のセーブを開いている間はこのタブは無効化される)。
  `selectClothes` / `openClothesIds` は意味が確定したため選択肢
  つきで編集できる。`nextTapItemAvailStatus` は意味が未だ不明なため
  生の数値のまま編集する形にしている。
- `tapItemLevel` の行数は読み込んだデータの実際の長さ (無印なら4、
  K版なら7) に応じて動的に生成している。

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

`*.ipa` / `*.saveIt` および解析用の中間生成物 (`work/` 以下: 展開した
IPA 本体、Il2CppDumper の出力、逆アセンブル結果など) は著作物・個人の
セーブデータであるため `.gitignore` でリポジトリから除外している。
再現する場合は [README.md](README.md) の手順に従って
`com.Happygamer.SenderGirl.ipa` と `UserData.saveIt` を用意すること。
