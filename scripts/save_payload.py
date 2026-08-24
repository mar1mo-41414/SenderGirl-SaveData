"""SaveIt が復号後に返す "main" バイナリの中身のパース/再構築。

構造 (com.Happygamer.SenderGirl.ipa / com.Happygamer.SenderGirlK.ipa の
実データで解析・確認済み):

  1個の名前付きエントリ ("UserData") を、その値の型情報 (.NET の
  アセンブリ修飾型名を模した文字列を3つ、フル/短縮形で連続して書き
  出したもの) と共にラップした「エンベロープ」に続けて、
  ペイロード長 (int32 LE) + ペイロード本体 (**MessagePack**) が
  入っている。

  エンベロープの中身 (型記述の文字列など) はアプリのビルド設定
  (使用した.NETランタイムのバージョン等) によって長さが変わりうる
  ことが分かっている (無印「ゆるヤミ彼女」と、姉妹作の【関西弁版】
  で実際に異なる長さだった: 177バイト vs 156バイト)。そのため、
  「先頭Nバイトは固定」という決め打ちはせず、.NET の7bitエンコード
  長さプレフィックス形式に従って毎回きちんとパースすることで、
  どちらの版でも (将来別の版が出ても) 同じコードで扱えるようにして
  いる。

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

【関西弁版】(com.Happygamer.SenderGirlK) 固有の差分 (実データで確認済み、
未検証部分あり):
  - 暗号化パスワードは無印と共通 (同じ128文字定数で復号できた)。
  - ペイロードのキー数が49個 (無印は46個)。無印の全フィールドに加えて
    openClothesIds / selectClothes / nextTapItemAvailStatus の3つが
    追加されている (おそらく衣装/コスチューム関連の要素だが、実機での
    意味確認はまだ)。
  - tapItemLevel の要素数が7個 (無印は4個)。
"""
from __future__ import annotations

import struct
from decimal import Decimal

import mpatch

# エンベロープ先頭、"UserData" という名前より前にある固定長の部分
# (フォーマットバージョン等の int32 が2つ + フラグ1バイト + エントリ数
# int32)。中身の意味までは踏み込まず、単にこのバイト数だけ読み飛ばす。
_ENVELOPE_PREFIX_LEN = 8 + 1 + 4


def _read_7bit_int(buf: bytes, pos: int) -> tuple[int, int]:
    """.NET の 7bit エンコード整数 (BinaryWriter.Write7BitEncodedInt と
    同じ形式) を pos から読み、(値, 読み終わった位置) を返す。"""
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _parse_envelope(raw_main: bytes) -> tuple[bytes, bytes]:
    """raw_main (復号済み "main" バイナリ) をパースし、
    (ペイロード長フィールドまでを含むヘッダのプレフィックス,
     ペイロード本体のバイト列) を返す。"""
    pos = _ENVELOPE_PREFIX_LEN
    name_len, pos = _read_7bit_int(raw_main, pos)
    pos += name_len  # エントリ名 ("UserData") 本体はスキップ
    pos += 1  # 値の型を示すタグバイト
    for _ in range(3):  # 型記述の文字列が3つ連続する
        str_len, pos = _read_7bit_int(raw_main, pos)
        pos += str_len
    pos += 4  # int32 (配列の次元数など。中身は使わない)

    length_field_pos = pos
    (payload_len,) = struct.unpack_from("<i", raw_main, pos)
    pos += 4

    prefix = raw_main[:length_field_pos]
    payload = raw_main[pos : pos + payload_len]
    return prefix, payload


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


# 【関西弁版】(SenderGirlK) にしか存在しないキー。これが1つでも入っていれば
# K版のセーブデータと判定する。
K_ONLY_KEYS = ("openClothesIds", "selectClothes", "nextTapItemAvailStatus")


def is_k_variant(data: dict) -> bool:
    return any(k in data for k in K_ONLY_KEYS)


def decode_main(raw_main: bytes) -> dict:
    """decrypt_save.py 等で復号した "main" バイナリを Python の dict に
    変換する。大きな数値フィールドは Decimal96 でラップされる。
    無印/【関西弁版】どちらの形式でも (エンベロープ長の違いを自動的に
    吸収して) 同じ関数で読める。"""
    _, payload = _parse_envelope(raw_main)
    root = mpatch.parse(payload)
    return _walk_decode(mpatch.to_plain(root))


def encode_main(original_raw_main: bytes, data: dict) -> bytes:
    """decode_main の逆変換。

    original_raw_main (編集前に読み込んだ "main" バイナリ) からエンベロープ
    (ヘッダ) を実際にパースして再利用し、ペイロード部分はバイト単位で
    パースして値が変わっていない部分は元のバイト列をそのまま、変わった
    部分だけ元と同じ型/バイト幅で書き直すことで、"編集していないのに
    壊れる" ことを防ぐ。ペイロード長フィールドだけは新しい値に書き換える。
    """
    prefix, original_payload = _parse_envelope(original_raw_main)
    root = mpatch.parse(original_payload)
    plain = _walk_encode(data)
    payload = mpatch.rebuild(root, plain)
    return prefix + struct.pack("<i", len(payload)) + payload
