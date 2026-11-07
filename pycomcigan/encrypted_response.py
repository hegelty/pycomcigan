import base64
import binascii
import hashlib
import hmac
import json
import re

from ._aes import decrypt_cbc


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
    if not isinstance(version, str) or not re.fullmatch(r'enc[0-9]+', version):
        raise RuntimeError("Unsupported encryption version")

    fields = text.rstrip('\x00').split(':')
    if len(fields) != 4 or fields[0] not in (version, 'enc1'):
        raise RuntimeError("Encrypted response protocol mismatch")

    try:
        if fields[0] != 'enc1':
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
        padded = decrypt_cbc(key, iv, ciphertext)
        padding_size = padded[-1]
        if not 1 <= padding_size <= 16 or padded[-padding_size:] != bytes([padding_size]) * padding_size:
            raise ValueError('Invalid PKCS7 padding')
        plain = padded[:-padding_size]
        decoded = plain.decode('utf-8').rstrip('\x00')
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Invalid encrypted response content") from None
    return _json_object(decoded)
