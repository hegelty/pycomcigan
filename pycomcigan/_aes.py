"""Bounded AES-CBC decryption adapted from Bo Zhu's AES-Python.

Source: https://github.com/boppreh/aes/tree/de5a5cd53b2866ccab74c46b10c413d74d275b36
Original AES-128 implementation by Bo Zhu; the cited project is maintained by
BoppreH. This module retains only key expansion, inverse block rounds, and CBC
decryption. It returns raw decrypted bytes; callers own padding validation.

MIT License

Copyright (c) 2024 BoppreH

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


_S_BOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76"
    "ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d83115"
    "04c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f84"
    "53d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa8"
    "51a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d1973"
    "60814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479"
    "e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
    "703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df"
    "8ca1890dbfe6426841992d0fb054bb16"
)

_INV_S_BOX = bytes.fromhex(
    "52096ad53036a538bf40a39e81f3d7fb"
    "7ce339829b2fff87348e4344c4dee9cb"
    "547b9432a6c2233dee4c950b42fac34e"
    "082ea16628d924b2765ba2496d8bd125"
    "72f8f66486689816d4a45ccc5d65b692"
    "6c704850fdedb9da5e154657a78d9d84"
    "90d8ab008cbcd30af7e45805b8b34506"
    "d02c1e8fca3f0f02c1afbd0301138a6b"
    "3a9111414f67dcea97f2cfcef0b4e673"
    "96ac7422e7ad3585e2f937e81c75df6e"
    "47f11a711d29c5896fb7620eaa18be1b"
    "fc563e4bc6d279209adbc0fe78cd5af4"
    "1fdda8338807c731b11210592780ec5f"
    "60517fa919b54a0d2de57a9f93c99cef"
    "a0e03b4dae2af5b0c8ebbb3c83539961"
    "172b047eba77d626e169146355210c7d"
)

_R_CON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40,
          0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D, 0x9A)
_ROUNDS_BY_KEY_SIZE = {16: 10, 24: 12, 32: 14}


def _bytes_to_matrix(data: bytes) -> list[list[int]]:
    return [list(data[i:i + 4]) for i in range(0, len(data), 4)]


def _matrix_to_bytes(matrix: list[list[int]]) -> bytes:
    return bytes(value for word in matrix for value in word)


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _add_round_key(state: list[list[int]], key: list[list[int]]) -> None:
    for row in range(4):
        for column in range(4):
            state[row][column] ^= key[row][column]


def _inv_sub_bytes(state: list[list[int]]) -> None:
    for row in range(4):
        for column in range(4):
            state[row][column] = _INV_S_BOX[state[row][column]]


def _inv_shift_rows(state: list[list[int]]) -> None:
    state[0][1], state[1][1], state[2][1], state[3][1] = (
        state[3][1], state[0][1], state[1][1], state[2][1])
    state[0][2], state[1][2], state[2][2], state[3][2] = (
        state[2][2], state[3][2], state[0][2], state[1][2])
    state[0][3], state[1][3], state[2][3], state[3][3] = (
        state[1][3], state[2][3], state[3][3], state[0][3])


def _xtime(value: int) -> int:
    return (((value << 1) ^ 0x1B) & 0xFF) if value & 0x80 else value << 1


def _mix_single_column(column: list[int]) -> None:
    total = column[0] ^ column[1] ^ column[2] ^ column[3]
    first = column[0]
    column[0] ^= total ^ _xtime(column[0] ^ column[1])
    column[1] ^= total ^ _xtime(column[1] ^ column[2])
    column[2] ^= total ^ _xtime(column[2] ^ column[3])
    column[3] ^= total ^ _xtime(column[3] ^ first)


def _inv_mix_columns(state: list[list[int]]) -> None:
    for column in state:
        u = _xtime(_xtime(column[0] ^ column[2]))
        v = _xtime(_xtime(column[1] ^ column[3]))
        column[0] ^= u
        column[1] ^= v
        column[2] ^= u
        column[3] ^= v
    for column in state:
        _mix_single_column(column)


class _AES:
    """Per-call AES schedule; the key is not retained outside this instance."""

    def __init__(self, key: bytes) -> None:
        self._rounds = _ROUNDS_BY_KEY_SIZE[len(key)]
        words = _bytes_to_matrix(key)
        word_count = len(key) // 4
        round_constant_index = 1
        while len(words) < (self._rounds + 1) * 4:
            word = list(words[-1])
            if len(words) % word_count == 0:
                word.append(word.pop(0))
                word = [_S_BOX[value] for value in word]
                word[0] ^= _R_CON[round_constant_index]
                round_constant_index += 1
            elif len(key) == 32 and len(words) % word_count == 4:
                word = [_S_BOX[value] for value in word]
            previous = words[-word_count]
            words.append([a ^ b for a, b in zip(word, previous)])
        self._round_keys = [words[i:i + 4] for i in range(0, len(words), 4)]

    def decrypt_block(self, ciphertext: bytes) -> bytes:
        state = _bytes_to_matrix(ciphertext)
        _add_round_key(state, self._round_keys[-1])
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        for round_index in range(self._rounds - 1, 0, -1):
            _add_round_key(state, self._round_keys[round_index])
            _inv_mix_columns(state)
            _inv_shift_rows(state)
            _inv_sub_bytes(state)
        _add_round_key(state, self._round_keys[0])
        return _matrix_to_bytes(state)


def decrypt_cbc(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """Decrypt full AES-CBC blocks and return the raw, still-padded bytes."""
    if not isinstance(key, bytes) or len(key) not in _ROUNDS_BY_KEY_SIZE:
        raise ValueError("key must be 16, 24, or 32 bytes")
    if not isinstance(iv, bytes) or len(iv) != 16:
        raise ValueError("iv must be 16 bytes")
    if not isinstance(ciphertext, bytes) or not ciphertext or len(ciphertext) % 16:
        raise ValueError("ciphertext must be a nonempty multiple of 16 bytes")

    aes = _AES(key)
    plaintext = bytearray()
    previous = iv
    for offset in range(0, len(ciphertext), 16):
        block = ciphertext[offset:offset + 16]
        plaintext.extend(_xor_bytes(previous, aes.decrypt_block(block)))
        previous = block
    return bytes(plaintext)
