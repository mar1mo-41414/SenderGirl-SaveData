"""Traditional PKWARE ZIP encryption (ZipCrypto / "PkzipClassic").

Python's stdlib `zipfile` can only *read* ZipCrypto-encrypted entries, not
write them, and `pyzipper` only writes AES. SaveIt (the Unity asset used by
SenderGirl) uses classic ZipCrypto, so this module implements the standard
PKWARE stream cipher directly. The algorithm is the well-known one described
in the ZIP APPNOTE.TXT (section 6.1).
"""
import random


def _make_crc_table():
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (0xEDB88320 ^ (c >> 1)) if (c & 1) else (c >> 1)
        table.append(c)
    return table


_CRC_TABLE = _make_crc_table()


def _crc_update(crc: int, byte: int) -> int:
    return _CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)


class ZipCryptoCipher:
    """One ZipCrypto keystream, seeded from a password. Use either
    `encrypt_byte` for every byte of a stream, or `decrypt_byte`, but not a
    mix of both on the same instance."""

    def __init__(self, password: bytes):
        self.k0 = 0x12345678
        self.k1 = 0x23456789
        self.k2 = 0x34567890
        for b in password:
            self._update_keys(b)

    def _update_keys(self, byte: int) -> None:
        self.k0 = _crc_update(self.k0, byte)
        self.k1 = (self.k1 + (self.k0 & 0xFF)) & 0xFFFFFFFF
        self.k1 = (self.k1 * 134775813 + 1) & 0xFFFFFFFF
        self.k2 = _crc_update(self.k2, (self.k1 >> 24) & 0xFF)

    def _stream_byte(self) -> int:
        temp = (self.k2 | 2) & 0xFFFF
        return ((temp * (temp ^ 1)) >> 8) & 0xFF

    def encrypt_byte(self, plain_byte: int) -> int:
        cipher_byte = plain_byte ^ self._stream_byte()
        self._update_keys(plain_byte)
        return cipher_byte

    def decrypt_byte(self, cipher_byte: int) -> int:
        plain_byte = cipher_byte ^ self._stream_byte()
        self._update_keys(plain_byte)
        return plain_byte


def encrypt(data: bytes, password: bytes, crc32_value: int, rng=None) -> bytes:
    """Encrypt `data` (already-compressed entry bytes) ZipCrypto-style.
    Returns the 12-byte encryption header followed by the ciphertext.
    `crc32_value` must be the CRC-32 of the *uncompressed* file data (used as
    the header's verification byte, matching the classic/non-streamed
    scheme where general-purpose bit 3 is not set)."""
    rng = rng or random.SystemRandom()
    header = bytes(rng.randrange(256) for _ in range(11)) + bytes([(crc32_value >> 24) & 0xFF])
    cipher = ZipCryptoCipher(password)
    out = bytearray(len(header) + len(data))
    for i, b in enumerate(header):
        out[i] = cipher.encrypt_byte(b)
    offset = len(header)
    for i, b in enumerate(data):
        out[offset + i] = cipher.encrypt_byte(b)
    return bytes(out)


def decrypt(data: bytes, password: bytes) -> bytes:
    """Inverse of `encrypt`: `data` includes the 12-byte header."""
    cipher = ZipCryptoCipher(password)
    for b in data[:12]:
        cipher.decrypt_byte(b)
    out = bytearray(len(data) - 12)
    for i, b in enumerate(data[12:]):
        out[i] = cipher.decrypt_byte(b)
    return bytes(out)
