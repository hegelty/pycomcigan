"""NIST SP 800-38A F.2 CBC vectors, for the native AES adapter, without padding.

https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38a.pdf
"""
from unittest.mock import patch

import pytest

from pycomcigan._aes import decrypt_cbc
from pycomcigan.encrypted_response import decode_response
from test_encrypted_response import KEY, VECTOR


IV = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
PLAINTEXT = bytes.fromhex(
    '6bc1bee22e409f96e93d7e117393172a'
    'ae2d8a571e03ac9c9eb76fac45af8e51'
    '30c81c46a35ce411e5fbc1191a0a52ef'
    'f69f2445df4f9b17ad2b417be66c3710')


@pytest.mark.parametrize('key,ciphertext', [
    ('2b7e151628aed2a6abf7158809cf4f3c',
     '7649abac8119b246cee98e9b12e9197d5086cb9b507219ee95db113a917678b2'
     '73bed6b8e3c1743b7116e69e222295163ff1caa1681fac09120eca307586e1a7'),
    ('8e73b0f7da0e6452c810f32b809079e562f8ead2522c6b7b',
     '4f021db243bc633d7178183a9fa071e8b4d9ada9ad7dedf4e5e738763f69145a'
     '571b242012fb7ae07fa9baac3df102e008b0e27988598881d920a9e64f5615cd'),
    ('603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4',
     'f58c4c04d6e5f1ba779eabfb5f7bfbd69cfc4e967edb808d679f777bc6702c7d'
     '39f23369a9d9bacfa530e26304231461b2eb05e2c39be9fcda6c19078c6a9d1b'),
])
def test_nist_cbc_all_blocks_and_key_lengths(key, ciphertext):
    assert decrypt_cbc(bytes.fromhex(key), IV, bytes.fromhex(ciphertext)) == PLAINTEXT


@pytest.mark.parametrize('key,iv,ciphertext', [
    (b'k' * 15, IV, b'c' * 16), (b'k' * 17, IV, b'c' * 16),
    (KEY, b'i' * 15, b'c' * 16), (KEY, b'i' * 17, b'c' * 16),
    (KEY, IV, b''), (KEY, IV, b'c' * 15), (KEY, IV, b'c' * 17),
])
def test_invalid_aes_inputs(key, iv, ciphertext):
    with pytest.raises(ValueError):
        decrypt_cbc(key, iv, ciphertext)


def test_authentication_failure_does_not_reach_aes():
    with patch('pycomcigan.encrypted_response.decrypt_cbc') as decrypt, \
         pytest.raises(RuntimeError, match='authentication'):
        decode_response(VECTOR, b'x' * 16)
    decrypt.assert_not_called()
