"""
SenderGirl (com.Happygamer.SenderGirl) の UserData.saveIt フォーマット。

UserData.saveIt は Unity アセット「SaveIt」(名前空間 SaveIt.*, 内部に
SharpZipLib を SaveIt.SharpZLib としてリネーム同梱) が生成するファイル。

構造:
  offset 0-3   : マジック b"SVIT" (FOURCC。ライブラリのエラー文言
                 "Data is no valid SaveIt format. Wrong FOURCC." に対応)
  offset 4-7   : int32 LE = 2  (フォーマットバージョン)
  offset 8-9   : フラグ 2バイト (観測値は 01 01。詳細未解析)
  offset 10-   : 標準 ZIP ファイルそのもの (PK\\x03\\x04 で開始)

埋め込み ZIP の中身 (com.Happygamer.SenderGirl.ipa 実機データで確認):
  - エントリ1件のみ、名前は常に "main" (セーブファイル名とは無関係の固定名)
  - 圧縮方式: Deflate
  - 暗号化: Traditional PKWARE encryption (ZipCrypto / PkzipClassic)。
    AES ではない。SharpZipLib 側コードの "PkzipClassicCryptoBase" に対応。
  - ZIP64 形式 (サイズが小さくても常にこの形式で書き出される模様)

パスワードはデバイスIDや乱数から動的生成されるものではなく、
アプリの IL2CPP バイナリに埋め込まれた「固定の128文字定数」。
どのデバイス/どのセーブファイルでも同一と考えられる
(SaveIt.TableSerializer.File インスタンスに対して
 BinaryTableSerializer.Password をこの定数でセットしている呼び出し箇所が
 バイナリ中に2箇所あり、いずれも同じ __DATA 上の文字列リテラルスロットを
 参照していることを ARM64 逆アセンブルで確認した)。

解析手法の詳細は README.md を参照。
"""

SVIT_MAGIC = b"SVIT"
SVIT_HEADER_LEN = 10

# ゲームの IL2CPP バイナリ (SenderGirl, arm64) 内の文字列リテラルとして
# 埋め込まれている固定パスワード。
# 特定手順: Il2CppDumper で SaveIt.TableSerializer.BinaryTableSerializer
# .set_Password(string) (VA 0x1005B0828) と File..ctor(string) (VA
# 0x1005A8F2C) のアドレスを特定 → capstone で __TEXT 全体を ARM64
# としてディスアセンブルし、上記2アドレスへの BL 命令の呼び出し元を検索
# → 呼び出し元 (0x1008efab0 / 0x1008efca0 付近) で x1 (第1引数) が
# __DATA 上の固定アドレス (文字列リテラルキャッシュのスロット) から
# ロードされていることを確認 → そのアドレスを Il2CppDumper が出力した
# script.json の ScriptString テーブルで引き、対応する文字列を取得。
# 実際に UserData.saveIt から抽出した ZIP をこのパスワードで復号できる
# ことを確認済み。
SAVEIT_PASSWORD = (
    "JAuX4Sz2AkGJTvHUN0zCp6ydjLt3TQlTNTjIzJW9WzsorJnyEWy4JApJ73u0cNb3"
    "4sThe0QmscEDgBhAFDvu0n8TCCSuxAKRmmlEg4CEwYTBxXB9vEyETVyAmZgMefH6"
)

ZIP_ENTRY_NAME = "main"


def strip_svit_header(raw: bytes) -> bytes:
    """UserData.saveIt の生バイト列から、先頭10バイトの独自ヘッダを除いた
    標準 ZIP バイト列を返す。マジックが一致しない場合は例外を投げる。"""
    if raw[:4] != SVIT_MAGIC:
        raise ValueError(f"SVIT magic not found (got {raw[:4]!r})")
    return raw[SVIT_HEADER_LEN:]


def decrypt_main_entry(raw: bytes, password: str = SAVEIT_PASSWORD) -> bytes:
    """UserData.saveIt の生バイト列を受け取り、復号済みの "main" エントリの
    中身 (SaveIt 独自のバイナリシリアライズ形式) を返す。"""
    import io
    import zipfile

    zip_bytes = strip_svit_header(raw)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        return z.read(ZIP_ENTRY_NAME, pwd=password.encode("ascii"))


def _dos_datetime(dt=None) -> tuple:
    import time

    t = dt or time.localtime()
    dos_time = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    dos_date = (((t.tm_year - 1980) & 0x7F) << 9) | (t.tm_mon << 5) | t.tm_mday
    return dos_time, dos_date


def build_saveit_file(main_payload: bytes, password: str = SAVEIT_PASSWORD) -> bytes:
    """main_payload (SaveIt 独自バイナリシリアライズ形式) を、UserData.saveIt
    としてゲームが読み込める形式 (SVIT ヘッダ + 暗号化ZIP) に包む。

    元ファイルは ZIP64 + data-descriptor 形式だったが、ここでは実サイズが
    事前に分かっているため、それらを使わないシンプルな標準ZIP形式で書き出す
    (ZIP仕様上どちらも正当な形式で、SharpZipLib は両方読めるはず)。
    """
    import struct
    import zlib

    import zipcrypto

    pwd_bytes = password.encode("ascii")
    name_bytes = ZIP_ENTRY_NAME.encode("ascii")

    crc = zlib.crc32(main_payload) & 0xFFFFFFFF
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(main_payload) + compressor.flush()

    encrypted = zipcrypto.encrypt(compressed, pwd_bytes, crc)
    compressed_size = len(encrypted)  # 12-byte header + ciphertext
    uncompressed_size = len(main_payload)

    dos_time, dos_date = _dos_datetime()

    flag_bits = 0x0001  # bit0: encrypted. bit3 (data descriptor) left unset.
    version_needed = 20
    version_made_by = 20

    local_header = struct.pack(
        "<4sHHHHHIIIHH",
        b"PK\x03\x04",
        version_needed,
        flag_bits,
        8,  # deflate
        dos_time,
        dos_date,
        crc,
        compressed_size,
        uncompressed_size,
        len(name_bytes),
        0,
    )
    local_entry = local_header + name_bytes + encrypted

    central_header = struct.pack(
        "<4sHHHHHHIIIHHHHHII",
        b"PK\x01\x02",
        version_made_by,
        version_needed,
        flag_bits,
        8,
        dos_time,
        dos_date,
        crc,
        compressed_size,
        uncompressed_size,
        len(name_bytes),
        0,  # extra field length
        0,  # comment length
        0,  # disk number start
        0,  # internal file attributes
        0,  # external file attributes
        0,  # relative offset of local header
    )
    central_entry = central_header + name_bytes

    central_dir_offset = len(local_entry)
    central_dir_size = len(central_entry)

    eocd = struct.pack(
        "<4sHHHHIIH",
        b"PK\x05\x06",
        0,
        0,
        1,
        1,
        central_dir_size,
        central_dir_offset,
        0,
    )

    zip_bytes = local_entry + central_entry + eocd

    header = SVIT_MAGIC + struct.pack("<i", 2) + b"\x01\x01"
    return header + zip_bytes
