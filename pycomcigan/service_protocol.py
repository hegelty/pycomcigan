import ast
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServiceProtocol:
    endpoint: str
    key: Optional[bytes] = None
    version: Optional[str] = None
    school_divisor: Optional[int] = None
    school_offset: int = 0
    request_token: Optional[str] = field(default=None, repr=False)
    text_key: Optional[bytes] = field(default=None, repr=False)
    start_field: Optional[str] = None
    periods_field: Optional[str] = None


def parse_service_protocol(content: str) -> ServiceProtocol:
    if re.search(r'\bfunction\s+QAjaxSchool\s*\(', content) is None:
        match = re.search(r'\.(/\d+\?\d+l)', content)
        if match is None:
            raise RuntimeError('Unable to parse Comcigan service endpoint; the service page structure may have changed')
        return ServiceProtocol(match.group(1))

    request = re.search(
        r"function\s+QAjaxSchool\s*\([^)]*\)\s*\{(?:(?!\bfunction\b).)*?"
        r"url\s*:\s*'\.(/\d+)\?'\s*\+\s*encodeURIComponent\(btoa\("
        r"'(\d+l)'\s*\+\s*encodeURIComponent\(sc\)\s*\+\s*'_(enc\d+)'\)\)",
        content, re.S,
    )
    if request is None:
        raise RuntimeError('Unable to parse Comcigan school request protocol')
    endpoint, prefix, version = request.groups()

    timetable_request = re.search(
        r"function\s+QAjaxTimetable\s*\([^)]*\)\s*\{(?:(?!\bfunction\b).)*?"
        r"url\s*:\s*'\.(/\d+)\?'\s*\+\s*btoa\([^;{}]*?'_(enc[0-9]+)'\s*\)",
        content, re.S,
    )
    if timetable_request is None or timetable_request.groups() != (endpoint, version):
        raise RuntimeError(
            'Comcigan service page structure changed: school and timetable request protocols do not match'
        )

    sections = []
    for match in (request, timetable_request):
        next_function = re.search(r'\bfunction\s+\w+\s*\(', content[match.end():])
        end = match.end() + next_function.start() if next_function else len(content)
        sections.append(content[match.start():end])

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
    text_key = None
    if re.search(r'function\s+QnmsbChange\s*\(', content):
        key = re.search(r'function\s+QnmsbChange\s*\([^)]*\)\s*\{[^{}]*?String\.fromCharCode\(\s*([\d\s,]+)\)', content)
        if key is None:
            raise RuntimeError('Unable to parse Comcigan text decoding key')
        try:
            text_key = bytes(int(n.strip()) for n in key.group(1).split(','))
        except ValueError as error:
            raise RuntimeError('Invalid Comcigan text decoding key') from error
        if not text_key:
            raise RuntimeError('Invalid Comcigan text decoding key')
    start_field = periods_field = None
    if text_key:
        start = re.search(r'new\s+Date\(\s*QnmsbChange\(\s*자료\.(자료\d+)\s*\)\s*\)', content)
        periods = re.search(r'자료\.(자료\d+)\s*\[\s*교시\s*-\s*1\s*\]', content)
        if not start or not periods:
            raise RuntimeError('Unable to parse Comcigan timetable metadata fields')
        start_field, periods_field = start.group(1), periods.group(1)
    return ServiceProtocol(endpoint + '?' + prefix, bytes.fromhex(key_hex), version,
                           int(column.group(1)), int(column.group(2)), request_token, text_key,
                           start_field, periods_field)
