"""バイト単位で元データを保持する MessagePack パーサ/パッチャ。

SaveIt の内部シリアライザは (実測した限り) 素の MessagePack と互換の
タグ体系を使っているが、値をデコードしてから汎用の msgpack エンコーダで
書き戻すと、たとえ値が全く同じでも **ワイヤ上のバイト幅が変わってしまう**
(例: 元は float32 (0xca) で書かれていたボリューム値が、Pythonの
`msgpack.packb()` ではデフォルトで float64 (0xcb) になる。整数も、元は
固定幅 (int32 タグ等) で書かれていたものが、値が小さいと1バイトの
fixint に短縮されてしまう)。

SaveIt側の読み込みロジックがフィールドごとに決まった型/バイト幅を
前提にした「厳密な」読み方をしている場合、この幅のズレだけで
以降のパースが丸ごとズレて壊れる (実機でフリーズを確認済み)。

そこで本モジュールは:
  1. 元の "main" ペイロードをバイト位置つきでパースし (`parse`)、
  2. 編集後の値をこのパース木と突き合わせて、
     - 値が変わっていない箇所は元のバイト列をそのままコピー
     - 値が変わった箇所だけ、元と同じタグ/バイト幅で書き直す
     (新しい値がその幅に収まらない場合のみ、やむを得ず幅を広げる)
  3. 構造そのものが変わった場合 (JSON編集でキー削除/配列長変更など) は、
     その部分だけ通常の (コンパクトな) MessagePack エンコードにフォール
     バックする

という「パッチ適用」方式でペイロードを再構築する。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    kind: str  # 'nil' 'bool' 'int' 'float' 'str' 'bin' 'array' 'map'
    value: Any  # スカラー: python値。array: List[Node]。map: List[Tuple[Node,Node]]
    tag: int
    start: int
    end: int
    raw: bytes


def parse(buf: bytes, off: int = 0) -> Node:
    node, _ = _parse_at(buf, off)
    return node


def _parse_at(buf: bytes, off: int) -> tuple[Node, int]:
    tag = buf[off]
    start = off

    if tag <= 0x7F:
        return Node("int", tag, tag, start, off + 1, buf[start:off + 1]), off + 1
    if 0xE0 <= tag <= 0xFF:
        v = tag - 0x100
        return Node("int", v, tag, start, off + 1, buf[start:off + 1]), off + 1
    if 0x80 <= tag <= 0x8F:
        n = tag & 0x0F
        return _parse_map(buf, start, off + 1, n, tag)
    if 0x90 <= tag <= 0x9F:
        n = tag & 0x0F
        return _parse_array(buf, start, off + 1, n, tag)
    if 0xA0 <= tag <= 0xBF:
        n = tag & 0x1F
        s = buf[off + 1:off + 1 + n]
        end = off + 1 + n
        return Node("str", s.decode("utf-8"), tag, start, end, buf[start:end]), end

    if tag == 0xC0:
        return Node("nil", None, tag, start, off + 1, buf[start:off + 1]), off + 1
    if tag == 0xC2:
        return Node("bool", False, tag, start, off + 1, buf[start:off + 1]), off + 1
    if tag == 0xC3:
        return Node("bool", True, tag, start, off + 1, buf[start:off + 1]), off + 1

    if tag == 0xC4:
        n = buf[off + 1]
        end = off + 2 + n
        return Node("bin", buf[off + 2:end], tag, start, end, buf[start:end]), end
    if tag == 0xC5:
        (n,) = struct.unpack_from(">H", buf, off + 1)
        end = off + 3 + n
        return Node("bin", buf[off + 3:end], tag, start, end, buf[start:end]), end
    if tag == 0xC6:
        (n,) = struct.unpack_from(">I", buf, off + 1)
        end = off + 5 + n
        return Node("bin", buf[off + 5:end], tag, start, end, buf[start:end]), end

    if tag == 0xCA:
        (v,) = struct.unpack_from(">f", buf, off + 1)
        end = off + 5
        return Node("float", v, tag, start, end, buf[start:end]), end
    if tag == 0xCB:
        (v,) = struct.unpack_from(">d", buf, off + 1)
        end = off + 9
        return Node("float", v, tag, start, end, buf[start:end]), end

    int_fmt = {
        0xCC: (">B", 2), 0xCD: (">H", 3), 0xCE: (">I", 5), 0xCF: (">Q", 9),
        0xD0: (">b", 2), 0xD1: (">h", 3), 0xD2: (">i", 5), 0xD3: (">q", 9),
    }
    if tag in int_fmt:
        fmt, size = int_fmt[tag]
        (v,) = struct.unpack_from(fmt, buf, off + 1)
        end = off + size
        return Node("int", v, tag, start, end, buf[start:end]), end

    if tag == 0xD9:
        n = buf[off + 1]
        end = off + 2 + n
        return Node("str", buf[off + 2:end].decode("utf-8"), tag, start, end, buf[start:end]), end
    if tag == 0xDA:
        (n,) = struct.unpack_from(">H", buf, off + 1)
        end = off + 3 + n
        return Node("str", buf[off + 3:end].decode("utf-8"), tag, start, end, buf[start:end]), end
    if tag == 0xDB:
        (n,) = struct.unpack_from(">I", buf, off + 1)
        end = off + 5 + n
        return Node("str", buf[off + 5:end].decode("utf-8"), tag, start, end, buf[start:end]), end

    if tag == 0xDC:
        (n,) = struct.unpack_from(">H", buf, off + 1)
        return _parse_array(buf, start, off + 3, n, tag)
    if tag == 0xDD:
        (n,) = struct.unpack_from(">I", buf, off + 1)
        return _parse_array(buf, start, off + 5, n, tag)
    if tag == 0xDE:
        (n,) = struct.unpack_from(">H", buf, off + 1)
        return _parse_map(buf, start, off + 3, n, tag)
    if tag == 0xDF:
        (n,) = struct.unpack_from(">I", buf, off + 1)
        return _parse_map(buf, start, off + 5, n, tag)

    raise ValueError(f"unsupported msgpack tag 0x{tag:02x} at offset {off}")


def _parse_array(buf, start, off, n, tag) -> tuple[Node, int]:
    items = []
    for _ in range(n):
        node, off = _parse_at(buf, off)
        items.append(node)
    return Node("array", items, tag, start, off, buf[start:off]), off


def _parse_map(buf, start, off, n, tag) -> tuple[Node, int]:
    pairs = []
    for _ in range(n):
        k, off = _parse_at(buf, off)
        v, off = _parse_at(buf, off)
        pairs.append((k, v))
    return Node("map", pairs, tag, start, off, buf[start:off]), off


def to_plain(node: Node):
    if node.kind == "array":
        return [to_plain(n) for n in node.value]
    if node.kind == "map":
        return {to_plain(k): to_plain(v) for k, v in node.value}
    return node.value


# ---------------------------------------------------------------------
# エンコード (パッチ適用)
# ---------------------------------------------------------------------

def _encode_generic(value) -> bytes:
    """構造が変わってしまった部分用の、標準的な (コンパクトな) MessagePack
    エンコーダ。"""
    if value is None:
        return b"\xc0"
    if isinstance(value, bool):
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, int):
        return _encode_int_compact(value)
    if isinstance(value, float):
        return b"\xcb" + struct.pack(">d", value)
    if isinstance(value, str):
        return _encode_str(value)
    if isinstance(value, (bytes, bytearray)):
        n = len(value)
        if n <= 0xFF:
            return b"\xc4" + bytes([n]) + bytes(value)
        if n <= 0xFFFF:
            return b"\xc5" + struct.pack(">H", n) + bytes(value)
        return b"\xc6" + struct.pack(">I", n) + bytes(value)
    if isinstance(value, list):
        n = len(value)
        if n <= 0x0F:
            header = bytes([0x90 | n])
        elif n <= 0xFFFF:
            header = b"\xdc" + struct.pack(">H", n)
        else:
            header = b"\xdd" + struct.pack(">I", n)
        return header + b"".join(_encode_generic(v) for v in value)
    if isinstance(value, dict):
        n = len(value)
        if n <= 0x0F:
            header = bytes([0x80 | n])
        elif n <= 0xFFFF:
            header = b"\xde" + struct.pack(">H", n)
        else:
            header = b"\xdf" + struct.pack(">I", n)
        body = b"".join(_encode_str(k) + _encode_generic(v) for k, v in value.items())
        return header + body
    raise TypeError(f"cannot encode value of type {type(value)}")


def _encode_str(s: str) -> bytes:
    b = s.encode("utf-8")
    n = len(b)
    if n <= 0x1F:
        return bytes([0xA0 | n]) + b
    if n <= 0xFF:
        return b"\xd9" + bytes([n]) + b
    if n <= 0xFFFF:
        return b"\xda" + struct.pack(">H", n) + b
    return b"\xdb" + struct.pack(">I", n) + b


def _encode_int_compact(v: int) -> bytes:
    if 0 <= v <= 0x7F:
        return bytes([v])
    if -32 <= v < 0:
        return bytes([v & 0xFF])
    if 0 <= v <= 0xFF:
        return b"\xcc" + bytes([v])
    if -128 <= v <= 127:
        return b"\xd0" + struct.pack(">b", v)
    if 0 <= v <= 0xFFFF:
        return b"\xcd" + struct.pack(">H", v)
    if -32768 <= v <= 32767:
        return b"\xd1" + struct.pack(">h", v)
    if 0 <= v <= 0xFFFFFFFF:
        return b"\xce" + struct.pack(">I", v)
    if -(2**31) <= v <= 2**31 - 1:
        return b"\xd2" + struct.pack(">i", v)
    if 0 <= v <= 0xFFFFFFFFFFFFFFFF:
        return b"\xcf" + struct.pack(">Q", v)
    if -(2**63) <= v <= 2**63 - 1:
        return b"\xd3" + struct.pack(">q", v)
    raise ValueError(f"integer {v} out of msgpack range")


_INT_WIDTH_ENCODERS = {
    0x00: lambda v: bytes([v]) if 0 <= v <= 0x7F else None,  # placeholder, positive fixint handled separately
    0xCC: lambda v: b"\xcc" + bytes([v]) if 0 <= v <= 0xFF else None,
    0xD0: lambda v: b"\xd0" + struct.pack(">b", v) if -128 <= v <= 127 else None,
    0xCD: lambda v: b"\xcd" + struct.pack(">H", v) if 0 <= v <= 0xFFFF else None,
    0xD1: lambda v: b"\xd1" + struct.pack(">h", v) if -32768 <= v <= 32767 else None,
    0xCE: lambda v: b"\xce" + struct.pack(">I", v) if 0 <= v <= 0xFFFFFFFF else None,
    0xD2: lambda v: b"\xd2" + struct.pack(">i", v) if -(2**31) <= v <= 2**31 - 1 else None,
    0xCF: lambda v: b"\xcf" + struct.pack(">Q", v) if 0 <= v <= 2**64 - 1 else None,
    0xD3: lambda v: b"\xd3" + struct.pack(">q", v) if -(2**63) <= v <= 2**63 - 1 else None,
}


def _encode_int_same_width(original_tag: int, v: int) -> bytes:
    """new int 値を、元と同じタグ/バイト幅で書けるなら書く。収まらない
    場合のみ、やむを得ず標準のコンパクトエンコードにフォールバックする。"""
    if original_tag <= 0x7F or 0xE0 <= original_tag <= 0xFF:
        # 元は1バイトの fixint。fixint の範囲 (-32..127) に収まるなら維持。
        if 0 <= v <= 0x7F:
            return bytes([v])
        if -32 <= v < 0:
            return bytes([v & 0xFF])
        return _encode_int_compact(v)
    fn = _INT_WIDTH_ENCODERS.get(original_tag)
    if fn is not None:
        out = fn(v)
        if out is not None:
            return out
    return _encode_int_compact(v)


def _values_equal(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return a == b


def rebuild(node: Node, new_value) -> bytes:
    """node (元データのパース木) と new_value (編集後のプレーンな値) を
    突き合わせ、変更が無い部分は元のバイト列をそのまま、変更がある部分
    だけ書き換えたバイト列を返す。"""
    if node.kind == "map":
        if not isinstance(new_value, dict):
            return _encode_generic(new_value)
        orig_keys = [k.value for k, _ in node.value]
        if set(orig_keys) - set(new_value.keys()):
            # キーが削除された -> 構造変化。安全のためこのmap全体を素直に再エンコード
            return _encode_generic(new_value)

        extra_keys = [k for k in new_value.keys() if k not in orig_keys]
        n_total = len(orig_keys) + len(extra_keys)

        # ヘッダ (タグ+カウント) は総キー数に応じて選び直す
        if n_total <= 0x0F:
            header = bytes([0x80 | n_total])
        elif n_total <= 0xFFFF:
            header = b"\xde" + struct.pack(">H", n_total)
        else:
            header = b"\xdf" + struct.pack(">I", n_total)

        parts = [header]
        for key_node, val_node in node.value:
            parts.append(key_node.raw)  # キー自体は変更しない前提
            parts.append(rebuild(val_node, new_value[key_node.value]))
        for k in extra_keys:
            parts.append(_encode_str(k))
            parts.append(_encode_generic(new_value[k]))
        return b"".join(parts)

    if node.kind == "array":
        if not isinstance(new_value, list):
            return _encode_generic(new_value)
        if len(new_value) != len(node.value):
            return _encode_generic(new_value)
        parts = []
        n = len(new_value)
        if n <= 0x0F:
            header = bytes([0x90 | n])
        elif n <= 0xFFFF:
            header = b"\xdc" + struct.pack(">H", n)
        else:
            header = b"\xdd" + struct.pack(">I", n)
        parts.append(header)
        for child, v in zip(node.value, new_value):
            parts.append(rebuild(child, v))
        return b"".join(parts)

    # スカラー
    if _values_equal(node.value, new_value):
        return node.raw

    if node.kind == "bool":
        return b"\xc3" if new_value else b"\xc2"
    if node.kind == "nil":
        return _encode_generic(new_value)
    if node.kind == "str":
        return _encode_str(str(new_value))
    if node.kind == "int":
        return _encode_int_same_width(node.tag, int(new_value))
    if node.kind == "float":
        if node.tag == 0xCA:  # float32
            packed = struct.pack(">f", float(new_value))
            return b"\xca" + packed
        return b"\xcb" + struct.pack(">d", float(new_value))
    if node.kind == "bin":
        return _encode_generic(bytes(new_value))

    return _encode_generic(new_value)
