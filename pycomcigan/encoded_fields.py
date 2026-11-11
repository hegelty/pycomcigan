"""Decode the literal QnmsbChange field format without running JavaScript."""

import base64
import binascii
import re


_DECODER = re.compile(
    r'function\s+QnmsbChange\s*\(\s*(?P<value>[\w$]+)\s*\)\s*\{\s*'
    r'if\s*\(\s*(?P=value)\s*==\s*undefined\s*\|\|\s*'
    r'(?P=value)\s*===\s*(?:\'\'|"")\s*\)\s*return\s*(?:\'\'|"")\s*;\s*'
    r'var\s+(?P<key>[\w$]+)\s*=\s*String\.fromCharCode\(\s*'
    r'(?P<numbers>[0-9]{1,3}(?:\s*,\s*[0-9]{1,3})*)\s*\)\s*;\s*'
    r'var\s+(?P<raw>[\w$]+)\s*=\s*atob\(\s*(?P=value)\s*\)\s*;\s*'
    r'var\s+(?P<bytes>[\w$]+)\s*=\s*new\s+Uint8Array\(\s*(?P=raw)\.length\s*\)\s*;\s*'
    r'for\s*\(\s*var\s+(?P<index>[\w$]+)\s*=\s*0\s*;\s*'
    r'(?P=index)\s*<\s*(?P=bytes)\.length\s*;\s*(?P=index)\+\+\s*\)\s*\{\s*'
    r'(?P=bytes)\[\s*(?P=index)\s*\]\s*=\s*'
    r'(?P=raw)\.charCodeAt\(\s*(?P=index)\s*\)\s*\^\s*'
    r'(?P=key)\.charCodeAt\(\s*(?P=index)\s*%\s*(?P=key)\.length\s*\)\s*;\s*\}\s*'
    r'return\s+new\s+TextDecoder\(\s*[\'"]euc-kr[\'"]\s*,\s*'
    r'\{\s*fatal\s*:\s*true\s*\}\s*\)\.decode\(\s*(?P=bytes)\s*\)\s*;\s*\}',
    re.S,
)


def parse_field_encoding(content):
    """Accept only the known decoder and literal byte key and field references."""
    if re.search(r'\bQnmsbChange\s*\(', content) is None:
        return None, None, None
    match = _DECODER.search(content)
    if match is None:
        raise RuntimeError('Unable to parse Comcigan text field decoder')
    numbers = match.group('numbers').split(',')
    if len(numbers) > 256 or any(int(number) > 255 for number in numbers):
        raise RuntimeError('Invalid Comcigan text field key')
    key = bytes(int(number) for number in numbers)
    dates = set(re.findall(
        r'new\s+Date\(\s*QnmsbChange\(\s*자료\.(자료[0-9]+)\s*\)\s*\)', content,
    ))
    periods = set(re.findall(
        r'자료\.(자료[0-9]+)\[\s*교시\s*-\s*1\s*\]', content,
    ))
    if len(dates) != 1 or len(periods) != 1:
        raise RuntimeError('Unable to parse Comcigan date or period-time fields')
    return key, dates.pop(), periods.pop()


def decode_field(value, key):
    """Decode Base64, repeating byte XOR, then strict browser-compatible CP949."""
    if value is None or value == '':
        return ''
    if not isinstance(value, str) or not isinstance(key, bytes) or not key:
        raise RuntimeError('Invalid encoded Comcigan text field')
    try:
        raw = base64.b64decode(value, validate=True)
        if base64.b64encode(raw).decode('ascii') != value:
            raise ValueError
        return bytes(byte ^ key[i % len(key)] for i, byte in enumerate(raw)).decode('cp949')
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise RuntimeError('Invalid encoded Comcigan text field') from None


def decode_timetable_fields(data, codes, protocol):
    """Restore the public schema after the response envelope is authenticated."""
    if protocol is None or protocol.text_key is None:
        return data
    decoded = dict(data)
    try:
        for field in ('자료' + codes[2], '자료' + codes[3]):
            if not isinstance(data[field], list):
                raise ValueError
            decoded[field] = [
                '' if field == '자료' + codes[3] and index == 0
                else decode_field(value, protocol.text_key)
                for index, value in enumerate(data[field])
            ]
        for field in ('지역명', '자료' + codes[4], protocol.start_date_field):
            decoded[field] = decode_field(data[field], protocol.text_key)
        if '학교명' in data:
            decoded['학교명'] = decode_field(data['학교명'], protocol.text_key)
        if not isinstance(data[protocol.period_times_field], list):
            raise ValueError
        decoded['시작일'] = decoded[protocol.start_date_field]
        decoded['일과시간'] = data[protocol.period_times_field]
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('Invalid encoded Comcigan timetable fields') from None
    return decoded
