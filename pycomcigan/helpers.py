import base64
from dataclasses import dataclass
from typing import List
from urllib import parse

from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .encrypted_response import decode_response
from .service_protocol import ServiceProtocol

# Constants for Comcigan API
COMCIGAN_URL = 'http://comci.net:4082'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
}

# Comcigan labels Korean pages as EUC-KR, but browsers decode that label as
# Windows code page 949. Python exposes that encoding as cp949.
# See: https://encoding.spec.whatwg.org/#legacy-multi-byte-korean-encodings
KOR_ENC = 'cp949'


def decode_text(value, key):
    if key is None or value is None:
        return value
    if not isinstance(value, str):
        raise RuntimeError('Invalid Comcigan encoded text')
    try:
        encoded = base64.b64decode(value, validate=True)
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(encoded)).decode(KOR_ENC)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError('Invalid Comcigan encoded text') from error


@dataclass(frozen=True)
class _Response:
    """The response fields consumed by this library."""

    text: str
    status_code: int


def get_response_encoding(url: str, encoding: str, request_token: str = None) -> _Response:
    """Fetch a page with per-request headers and a 30-second timeout.

    HTTP 403/429 retain the token/rate-limit errors; other HTTP and network
    failures propagate as urllib/OSError exceptions. Response streams are closed
    on success, HTTP errors, and read failures.
    """
    headers = dict(HEADERS)
    if request_token is not None:
        headers['X-Hour-Token'] = request_token
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            return _Response(
                text=response.read().decode(encoding, errors='replace'),
                status_code=response.status,
            )
    except HTTPError as error:
        error.close()
        if error.code == 403:
            raise RuntimeError('Comcigan request rejected (HTTP 403); the page token may have expired') from None
        if error.code == 429:
            raise RuntimeError('Comcigan rate limit reached (HTTP 429); retry later') from None
        raise


def get_comcigan_response_for_codes() -> _Response:
    """Fetch the Comcigan service page used to extract response codes."""
    return get_response_encoding(f"{COMCIGAN_URL}/st", KOR_ENC)


def encode_school_name(school_name: str) -> str:
    """URL-encode a school name using Comcigan's Korean encoding."""
    return parse.quote(school_name, encoding=KOR_ENC)


def school_search(school_name: str, comcigan_code: str, protocol: ServiceProtocol = None) -> List[List]:
    """
    Search for schools by name and return their information.

    Args:
        school_name (str): Name of the school to search for
        comcigan_code (str): Previously extracted Comcigan service code

    Returns:
        List[List]: List of school information in format:
                   [[region_code, region_name, school_name, school_code], ...]
    """
    if protocol is not None and protocol.version:
        endpoint, prefix = protocol.endpoint.split('?', 1)
        # Match JavaScript encodeURIComponent, including its punctuation safe set.
        encoded_name = parse.quote(school_name, safe="~()*!.'-", encoding='utf-8')
        token = base64.b64encode(f'{prefix}{encoded_name}_{protocol.version}'.encode('ascii')).decode('ascii')
        search_url = f'{COMCIGAN_URL}{endpoint}?{parse.quote(token, safe="")}'
    else:
        school_name_encoded = encode_school_name(school_name)
        search_url = f"{COMCIGAN_URL}{comcigan_code}{school_name_encoded}"
    if protocol is not None and protocol.request_token is not None:
        response = get_response_encoding(search_url, 'UTF-8', request_token=protocol.request_token)
    else:
        response = get_response_encoding(search_url, 'UTF-8')

    parsed_data = decode_response(response.text, protocol.key if protocol else None,
                                  protocol.version if protocol else 'enc5')
    rows = parsed_data.get('학교검색')
    if not isinstance(rows, list):
        raise RuntimeError('Invalid Comcigan school search response: missing school list')
    if protocol is None or protocol.school_divisor is None:
        return rows
    results = []
    for row in rows:
        if (not isinstance(row, list) or len(row) < 4 or type(row[0]) is not int
                or row[0] < 0):
            raise RuntimeError('Invalid Comcigan school search row')
        # Search responses include an "알림" footer, not a selectable school.
        if row[0] == 0:
            continue
        column = row[0] // protocol.school_divisor + protocol.school_offset
        if not 3 <= column < len(row):
            raise RuntimeError('Invalid Comcigan school code column')
        if protocol.text_key is None:
            if type(row[column]) is not int:
                raise RuntimeError('Invalid Comcigan school code column')
            results.append(row[:3] + [row[column]])
        else:
            code = decode_text(row[column], protocol.text_key)
            if not code.isascii() or not code.isdigit():
                raise RuntimeError('Invalid Comcigan school code column')
            results.append([row[0], decode_text(row[1], protocol.text_key),
                            decode_text(row[2], protocol.text_key), int(code)])
    return results
