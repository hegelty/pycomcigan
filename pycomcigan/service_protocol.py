import ast
import re
from dataclasses import dataclass, field
from typing import Optional

from .encoded_fields import parse_field_encoding
from .encrypted_response import RESPONSE_VERSION


_FUNCTION = re.compile(r'\bfunction\s+(?P<name>[\w$]+)\s*\([^)]*\)\s*\{')
_SCHOOL_REQUEST = re.compile(
    r"url\s*:\s*'\.(/[0-9]+)\?'\s*\+\s*encodeURIComponent\(\s*btoa\(\s*"
    rf"'([0-9]+l)'\s*\+\s*encodeURIComponent\(\s*sc\s*\)\s*\+\s*'_({RESPONSE_VERSION})'\s*\)\s*\)"
)
_TIMETABLE_REQUEST = re.compile(
    rf"url\s*:\s*'\.(/[0-9]+)\?'\s*\+\s*btoa\([^;{{}}]*?'_({RESPONSE_VERSION})'\s*\)"
)


@dataclass
class ServiceProtocol:
    endpoint: str
    key: Optional[bytes] = None
    version: Optional[str] = None
    school_divisor: Optional[int] = None
    school_offset: int = 0
    request_token: Optional[str] = field(default=None, repr=False)
    text_key: Optional[bytes] = field(default=None, repr=False)
    start_date_field: Optional[str] = None
    period_times_field: Optional[str] = None
    timetable_prefix: Optional[str] = None


def parse_service_protocol(content: str) -> ServiceProtocol:
    declarations = list(_FUNCTION.finditer(content))
    functions = [
        (match.group('name'), content[match.end():next_function])
        for match, next_function in zip(
            declarations, [match.start() for match in declarations[1:]] + [len(content)]
        )
    ]
    # Older encrypted pages use stable names. New pages rename the functions
    # while keeping the structure of the two request URLs.
    named_school = any(name == 'QAjaxSchool' for name, _ in functions)
    school_requests = [
        (section, match)
        for name, section in functions
        if (not named_school or name == 'QAjaxSchool')
        for match in _SCHOOL_REQUEST.finditer(section)
    ]
    if not school_requests and not named_school and 'CryptoJS.enc.Hex.parse' not in content:
        match = re.search(r'\.(/\d+\?\d+l)', content)
        if match is None:
            raise RuntimeError('Unable to parse Comcigan service endpoint; the service page structure may have changed')
        return ServiceProtocol(match.group(1))
    if len(school_requests) != 1:
        raise RuntimeError('Unable to parse Comcigan school request protocol')
    school_section, request = school_requests[0]
    endpoint, prefix, version = request.groups()

    timetable_requests = [
        (name, section, match)
        for name, section in functions
        if not named_school or name == 'QAjaxTimetable'
        for match in _TIMETABLE_REQUEST.finditer(section)
    ]
    if len(timetable_requests) != 1 or timetable_requests[0][2].groups() != (endpoint, version):
        raise RuntimeError(
            'Comcigan service page structure changed: school and timetable request protocols do not match'
        )
    timetable_name, timetable_section, timetable_request = timetable_requests[0]
    sections = (school_section[request.start():], timetable_section[timetable_request.start():])

    header_name = r"['\"]X-Hour-Token['\"]\s*:"
    header_reference = (
        r"headers\s*:\s*\{[^{}]*?['\"]X-Hour-Token['\"]\s*:\s*"
        r"window\.__HourRequestToken\s*\|\|\s*(['\"])\1"
    )
    advertised = [re.search(header_name, section) is not None for section in sections]
    request_token = None
    if any(advertised):
        if not all(re.search(header_reference, section) for section in sections):
            raise RuntimeError('Invalid or inconsistent Comcigan request token headers')
        token_match = re.search(
            r"\bwindow\.__HourRequestToken\s*=\s*(['\"])([0-9a-fA-F]+)\1\s*;",
            content,
        )
        if token_match is None:
            raise RuntimeError('Unable to parse Comcigan request token literal')
        request_token = token_match.group(2)

    key_match = re.search(r'var\s+key\s*=\s*CryptoJS\.enc\.Hex\.parse\((.*?)\);', content, re.S)
    if key_match is None:
        raise RuntimeError('Unable to parse Comcigan response key')
    expression = key_match.group(1).strip()
    literal = re.fullmatch(r"'([0-9a-fA-F]+)'", expression)
    if literal:
        key_hex = literal.group(1)
    else:
        pieces = re.fullmatch(
            r'\(function\(a\)\{return\s+(a\[\d+\](?:\+a\[\d+\])*)\s*;\}\)\((\[.*\])\)',
            expression, re.S,
        )
        if pieces is None:
            raise RuntimeError('Unable to parse Comcigan response key expression')
        # Only a literal hex array and explicit numeric indexes are interpreted.
        if re.fullmatch(r"\[\s*'[0-9a-fA-F]+'(?:\s*,\s*'[0-9a-fA-F]+')*\s*\]", pieces.group(2)) is None:
            raise RuntimeError('Invalid Comcigan response key fragments')
        fragments = ast.literal_eval(pieces.group(2))
        indexes = [int(i) for i in re.findall(r'a\[(\d+)\]', pieces.group(1))]
        if any(i >= len(fragments) for i in indexes):
            raise RuntimeError('Invalid Comcigan response key indexes')
        key_hex = ''.join(fragments[i] for i in indexes)
    if len(key_hex) not in (32, 48, 64):
        raise RuntimeError('Invalid Comcigan response key size')

    column = re.search(r'Math\.floor\(학교명단\[i\]\[0\]\s*/\s*(\d+)\)\s*\+\s*(\d+)', content)
    if (column is None or int(column.group(1)) <= 0
            or not 0 <= int(column.group(2)) <= 64):
        raise RuntimeError('Unable to parse Comcigan school code column')
    text_key, start_date_field, period_times_field = parse_field_encoding(content, required=version.isdecimal())
    # Look up the caller which forwards the four timetable arguments, and
    # collect the first argument from its call sites (the fixed request prefix).
    forward = rf'(?<![\w$]){re.escape(timetable_name)}\s*\(\s*sc\s*,\s*sc2\s*,\s*da1\s*,\s*r\s*,'
    prefixes = {
        value
        for name, section in functions
        if re.search(forward, section)
        for value in re.findall(rf"(?<![\w$]){re.escape(name)}\s*\(\s*'([0-9]+)_'\s*,", content)
    }
    if len(prefixes) > 1:
        raise RuntimeError('Conflicting Comcigan timetable request prefixes')
    return ServiceProtocol(endpoint + '?' + prefix, bytes.fromhex(key_hex), version,
                           int(column.group(1)), int(column.group(2)), request_token,
                           text_key, start_date_field, period_times_field, next(iter(prefixes), None))
