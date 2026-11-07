import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from pycomcigan.encrypted_response import decode_response


KEY = bytes(range(16))
# Fixed synthetic ciphertexts generated with pycryptodomex 3.24.2 before removing
# that dependency; tests never use the production AES code to encrypt fixtures.
FIXTURES = json.loads((Path(__file__).parent / 'fixtures/aes-cbc-ciphertexts.json').read_text(encoding='utf-8'))
# Independently generated using .NET Aes CBC/PKCS7 and HMACSHA256 in
# PowerShell: key 00..0f, IV 10..1f, UTF-8 plaintext {"ok":true}.
VECTOR = ('enc5:EBESExQVFhcYGRobHB0eHw==:5qwiig2JsPsr050re7hAlw=='
          ':uoiWXDAUodQRZA57IZSlqskaqUPqWPZ13zbz5DmwYEQ=')


def envelope(data, version='enc5', key=KEY, padded=False):
    iv = bytes(range(16, 32))
    if not padded:
        size = 16 - len(data) % 16
        data += bytes([size]) * size
    cipher = bytes.fromhex(FIXTURES[key.hex() + ':' + iv.hex() + ':' + data.hex()])
    encode = bytes.hex if version == 'enc1' else (lambda b: base64.b64encode(b).decode('ascii'))
    head = ':'.join((version, encode(iv), encode(cipher)))
    tag = hmac.new(hashlib.sha256(key).digest(), head.encode(), hashlib.sha256).digest()
    return head + ':' + encode(tag)


def test_fixed_independent_vector():
    assert decode_response(VECTOR, KEY) == {'ok': True}
    assert decode_response(VECTOR + '\x00\x00', KEY) == {'ok': True}


@pytest.mark.parametrize('version', ['enc5', 'enc1'])
@pytest.mark.parametrize('key', [bytes(range(16)), bytes(range(24)), bytes(range(32))])
def test_versions_and_key_lengths(version, key):
    assert decode_response(envelope(b'{"n":1}\x00\x00', version, key), key) == {'n': 1}


def test_version_mismatch():
    with pytest.raises(RuntimeError, match='protocol mismatch'):
        decode_response(VECTOR, KEY, version='enc1')
    with pytest.raises(RuntimeError, match='protocol mismatch'):
        decode_response(VECTOR, KEY, version='enc6')


@pytest.mark.parametrize('version', ['enc2', 'enc6', 'enc9'])
def test_other_version_envelopes(version):
    assert decode_response(envelope(b'{"n":1}', version), KEY, version=version) == {'n': 1}
    assert decode_response(envelope(b'{"n":1}', 'enc1'), KEY, version=version) == {'n': 1}


def test_spoofed_prefix_rejected():
    spoofed = VECTOR.replace('enc5:', 'enc6:', 1)
    with pytest.raises(RuntimeError, match='authentication'):
        decode_response(spoofed, KEY, version='enc6')


@pytest.mark.parametrize('version', ['', 'enc', 'enc-1', 'enc5x', 'ENC5', 'enc５',
                                     'enc5\n', None, 5])
def test_invalid_version(version):
    with pytest.raises(RuntimeError, match='Unsupported'):
        decode_response(VECTOR, KEY, version=version)


@pytest.mark.parametrize('text', ['{}', '{}\x00\n', '{"x":1}\n\x00'])
def test_plaintext(text):
    assert isinstance(decode_response(text), dict)
    with pytest.raises(RuntimeError, match='protocol mismatch'):
        decode_response(text, KEY)


@pytest.mark.parametrize('index', [1, 2, 3])
def test_tampering_rejected(index):
    fields = VECTOR.split(':')
    part = bytearray(base64.b64decode(fields[index]))
    part[0] ^= 1
    fields[index] = base64.b64encode(part).decode()
    with pytest.raises(RuntimeError, match='authentication'):
        decode_response(':'.join(fields), KEY)


def test_wrong_key_and_no_leaked_content():
    with pytest.raises(RuntimeError, match='authentication') as error:
        decode_response(VECTOR, b'x' * 16)
    assert VECTOR not in str(error.value)
    assert 'xxxxxxxx' not in str(error.value)


@pytest.mark.parametrize('field', ['!', 'AB==', 'AAAA\n', 'AAAA===='])
def test_invalid_base64(field):
    fields = VECTOR.split(':')
    fields[1] = field
    with pytest.raises(RuntimeError, match='encoding'):
        decode_response(':'.join(fields), KEY)


@pytest.mark.parametrize('field', ['AA', '0', 'aa '])
def test_invalid_hex(field):
    fields = envelope(b'{}', 'enc1').split(':')
    fields[1] = field
    with pytest.raises(RuntimeError, match='encoding'):
        decode_response(':'.join(fields), KEY)


@pytest.mark.parametrize('index,data', [(1, b''), (1, b'0' * 15), (2, b''),
                                         (2, b'0' * 15), (3, b'0' * 31)])
def test_invalid_lengths(index, data):
    fields = VECTOR.split(':')
    fields[index] = base64.b64encode(data).decode()
    with pytest.raises(RuntimeError, match='length'):
        decode_response(':'.join(fields), KEY)


def test_authenticated_invalid_padding():
    with pytest.raises(RuntimeError, match='content'):
        decode_response(envelope(b'A' * 16, padded=True), KEY)


@pytest.mark.parametrize('data', [b'A' * 15 + b'\x00', b'A' * 15 + b'\x11', b'A' * 14 + b'\x01\x02'])
def test_pkcs7_rejects_invalid_range_and_mixed_padding(data):
    with pytest.raises(RuntimeError, match='content'):
        decode_response(envelope(data, padded=True), KEY)


def test_pkcs7_removes_complete_padding_block():
    padded = b'{"ok":true}' + b' ' * 5 + bytes([16]) * 16
    assert decode_response(envelope(padded, padded=True), KEY) == {'ok': True}


def test_authenticated_invalid_utf8():
    with pytest.raises(RuntimeError, match='content'):
        decode_response(envelope(b'\xff'), KEY)


@pytest.mark.parametrize('payload', [b'{oops}', b'[]', b'null', b'1'])
def test_authenticated_invalid_json_or_root(payload):
    with pytest.raises(RuntimeError, match='JSON'):
        decode_response(envelope(payload), KEY)


def test_invalid_key():
    with pytest.raises(RuntimeError, match='key'):
        decode_response(VECTOR, b'short')
