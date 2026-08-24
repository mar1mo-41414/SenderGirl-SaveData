"""SaveIt が復号後に返す "main" バイナリの中身のパース/再構築。

構造 (com.Happygamer.SenderGirl.ipa の実データで解析・確認済み):

  offset 0-176 (177バイト) : 固定のヘッダ。SaveIt.TableSerializer が
      1個の名前付きエントリ ("UserData") を、その値の型情報
      (.NET のアセンブリ修飾型名を模した文字列を3つ、フル/短縮形で
      連続して書き出したもの) と共にラップしている。中身は実質固定
      (アプリのバージョンが変わらない限り不変と考えられる) なので、
      HEADER_TEMPLATE としてそのまま保持・再利用する。
  offset 177-180 (4バイト) : int32 LE = 以降に続くペイロードのバイト数。
  offset 181-    : ペイロード本体。**MessagePack** でエンコードされた
      1個の連想配列 (dict)。ここにゲームの実データ (ボリューム設定・
      クッキー数・きずな履歴 等) が全て入っている。

MessagePack ペイロード内の値の型:
  - 大きな数値 (currentCookieCount, totalCookieCount, maxCookie 等) は
    {"flags":int,"hi":int,"mid":int,"lo":int} という4フィールドの
    dict として現れる。これは .NET の System.Decimal の内部表現
    (decimal.GetBits() と同じレイアウト) そのもの。本モジュールでは
    自動的に Python の decimal.Decimal と相互変換する。
  - CreatedAt / ModifiedAt / lastSuspendTime / firstCookieTime などの
    日時フィールドは「西暦1年1月1日 (.NET の DateTime.MinValue) からの
    経過秒数」の整数。ModifiedAt がZIPエントリの実際の更新日時と一致する
    ことで検証済み。
  - friendHistory / friendHistTemp は .NET の List<T> をリフレクションで
    そのままフィールド単位シリアライズしたもの (_items配列 + _size +
    _version)。_items 配列は内部容量ぶんの余剰要素があり、末尾は
    未使用スロットとして null や無効値が入っていることがある。
"""
from __future__ import annotations

import struct
from decimal import Decimal
from pathlib import Path

import mpatch

_REF_MAIN = Path(__file__).resolve().parent.parent / "work" / "main_confirmed.bin"

PAYLOAD_LEN_OFFSET = 177  # ヘッダ末尾、4バイトの int32 LE (ペイロード長)
HEADER_LEN = 181  # ヘッダ全体 (ペイロード長フィールドを含む)


def _load_header_template() -> bytes:
    """既知の復号済みセーブファイルからヘッダ (先頭177バイト、長さ
    フィールドより前) を読み込む。実機データが手元にない環境向けに、
    観測済みの固定バイト列をフォールバックとして埋め込んでおく。"""
    if _REF_MAIN.exists():
        return _REF_MAIN.read_bytes()[: PAYLOAD_LEN_OFFSET]
    return bytes.fromhex(
        "0100000000000000000100000008557365724461746101535379737465"
        "6d2e427974655b5d2c206d73636f726c69622c2056657273696f6e3d322e"
        "302e302e302c2043756c747572653d2c205075626c69634b6579546f6b65"
        "6e3d623737613563353631393334653038392153797374656d2e42797465"
        "5b5d2c206d73636f726c69622c2043756c747572653d1f53797374656d2e"
        "427974652c206d73636f726c69622c2043756c747572653d01000000"
    )


HEADER_TEMPLATE = _load_header_template()
assert len(HEADER_TEMPLATE) == PAYLOAD_LEN_OFFSET


class Decimal96:
    """SaveIt/msgpack 上の {flags,hi,mid,lo} と .NET System.Decimal の
    相互変換。値そのものは python の Decimal として扱う。"""

    __slots__ = ("value",)

    def __init__(self, value: Decimal):
        self.value = value

    def __repr__(self):
        return f"Decimal96({self.value})"

    @classmethod
    def from_bits(cls, d: dict) -> "Decimal96":
        flags, lo, mid, hi = d["flags"], d["lo"], d["mid"], d["hi"]
        sign = -1 if (flags & 0x80000000) else 1
        scale = (flags >> 16) & 0xFF
        unscaled = (hi << 64) | (mid << 32) | lo
        return cls(sign * Decimal(unscaled) / (Decimal(10) ** scale))

    def to_bits(self) -> dict:
        sign, digits, exponent = self.value.normalize().as_tuple()
        unscaled = int("".join(map(str, digits)) or "0")
        scale = -exponent
        if scale < 0:
            unscaled *= 10 ** (-scale)
            scale = 0
        if scale > 28:
            raise ValueError(f"scale {scale} exceeds .NET decimal max (28)")
        if unscaled >= (1 << 96):
            raise ValueError("value too large for a 96-bit decimal")
        lo = unscaled & 0xFFFFFFFF
        mid = (unscaled >> 32) & 0xFFFFFFFF
        hi = (unscaled >> 64) & 0xFFFFFFFF
        flags = (scale & 0xFF) << 16
        if sign:
            flags |= 0x80000000
        return {"flags": flags, "hi": hi, "lo": lo, "mid": mid}


def _is_decimal_dict(v) -> bool:
    return isinstance(v, dict) and set(v.keys()) == {"flags", "hi", "mid", "lo"}


def _walk_decode(obj):
    if _is_decimal_dict(obj):
        return Decimal96.from_bits(obj)
    if isinstance(obj, dict):
        return {k: _walk_decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_decode(v) for v in obj]
    return obj


def _walk_encode(obj):
    if isinstance(obj, Decimal96):
        return obj.to_bits()
    if isinstance(obj, dict):
        return {k: _walk_encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_encode(v) for v in obj]
    return obj


def _payload_slice(raw_main: bytes) -> bytes:
    (payload_len,) = struct.unpack_from("<i", raw_main, PAYLOAD_LEN_OFFSET)
    return raw_main[HEADER_LEN : HEADER_LEN + payload_len]


def decode_main(raw_main: bytes) -> dict:
    """decrypt_save.py 等で復号した "main" バイナリを Python の dict に
    変換する。大きな数値フィールドは Decimal96 でラップされる。"""
    payload = _payload_slice(raw_main)
    root = mpatch.parse(payload)
    return _walk_decode(mpatch.to_plain(root))


def encode_main(original_raw_main: bytes, data: dict) -> bytes:
    """decode_main の逆変換。

    original_raw_main (編集前に読み込んだ "main" バイナリ) のペイロードを
    バイト単位でパースし、data (編集後の値) と突き合わせて、値が変わって
    いない部分は元のバイト列をそのまま、変わった部分だけ元と同じ型/
    バイト幅で書き直すことで、"編集していないのに壊れる" ことを防ぐ。
    ヘッダは HEADER_TEMPLATE を再利用し、ペイロード長だけ書き換える。
    """
    original_payload = _payload_slice(original_raw_main)
    root = mpatch.parse(original_payload)
    plain = _walk_encode(data)
    payload = mpatch.rebuild(root, plain)
    return HEADER_TEMPLATE + struct.pack("<i", len(payload)) + payload
