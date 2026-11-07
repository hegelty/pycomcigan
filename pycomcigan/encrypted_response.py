import base64
import binascii
import hashlib
import hmac
import json
import re

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _json_object(text):
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        raise RuntimeError("Invalid JSON response") from None
    if not isinstance(value, dict):
        raise RuntimeError("JSON response root must be an object")
    return value


def decode_response(text: str, key: bytes = None, version: str = 'enc5') -> dict:
    if not isinstance(text, str):
        raise RuntimeError("Response must be text")
    if key is None:
        return _json_object(text.rstrip('\x00\r\n'))
    if not isinstance(key, bytes) or len(key) not in (16, 24, 32):
        raise RuntimeError("Invalid encryption key")
    if version not in ('enc5', 'enc1'):
        raise RuntimeError("Unsupported encryption version")

    fields = text.rstrip('\x00').split(':')
    if len(fields) != 4 or fields[0] not in (version, 'enc1'):
        raise RuntimeError("Encrypted response protocol mismatch")

    try:
        if fields[0] == 'enc5':
            parts = [base64.b64decode(field, validate=True) for field in fields[1:]]
            if any(base64.b64encode(part).decode('ascii') != field
                   for part, field in zip(parts, fields[1:])):
                raise ValueError
        else:
            if any(not re.fullmatch(r'(?:[0-9a-f]{2})*', field) for field in fields[1:]):
                raise ValueError
            parts = [bytes.fromhex(field) for field in fields[1:]]
    except (ValueError, binascii.Error):
        raise RuntimeError("Invalid encrypted response encoding") from None
    iv, ciphertext, tag = parts
    if len(iv) != 16 or len(tag) != 32 or not ciphertext or len(ciphertext) % 16:
        raise RuntimeError("Invalid encrypted response length")

    authenticated = ':'.join(fields[:3]).encode('utf-8')
    expected = hmac.new(hashlib.sha256(key).digest(), authenticated, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise RuntimeError("Encrypted response authentication failed")
    try:
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        decoded = plain.decode('utf-8').rstrip('\x00')
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Invalid encrypted response content") from None
    return _json_object(decoded)
