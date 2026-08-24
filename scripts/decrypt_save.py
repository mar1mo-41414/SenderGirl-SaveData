#!/usr/bin/env python3
"""UserData.saveIt を復号して中身の "main" エントリを取り出すCLI。

使い方:
    python3 decrypt_save.py UserData.saveIt output_main.bin

標準ライブラリのみで動作 (Python 3.8+)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from saveit_format import decrypt_main_entry  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <UserData.saveIt> <output.bin>", file=sys.stderr)
        return 1

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    raw = in_path.read_bytes()
    data = decrypt_main_entry(raw)
    out_path.write_bytes(data)
    print(f"decrypted {len(data)} bytes -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
