"""Private AES-CBC adapter backed by PyCryptodomeX's native implementation."""

from Cryptodome.Cipher import AES


def decrypt_cbc(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """Decrypt full AES-CBC blocks and return the raw, still-padded bytes."""
    if not isinstance(key, bytes) or len(key) not in (16, 24, 32):
        raise ValueError("key must be 16, 24, or 32 bytes")
    if not isinstance(iv, bytes) or len(iv) != AES.block_size:
        raise ValueError("iv must be 16 bytes")
    if not isinstance(ciphertext, bytes) or not ciphertext or len(ciphertext) % AES.block_size:
        raise ValueError("ciphertext must be a nonempty multiple of 16 bytes")
    return AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)
