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

_SCRIPT = re.compile(r'<script\b[^>]*>(.*?)</script\s*>', re.I | re.S)
_JS_IDENTIFIER = r'[^\W\d][\w$]*|\$[\w$]*'
_POST_OPTIONS = (
    rf"url\s*:\s*'\.(?P<endpoint>/[0-9]+)'\s*,\s*method\s*:\s*(?P<verb>{_JS_IDENTIFIER})\s*,"
    r"\s*contentType\s*:\s*'text/plain;\s*charset=UTF-8'\s*,\s*data\s*:\s*"
)
_SCHOOL_BODY = re.compile(
    rf"\b(?:var|let|const)\s+(?P<input>{_JS_IDENTIFIER})\s*=\s*'(?P<prefix>[0-9]+l)'"
    r"\s*\+\s*encodeURIComponent\(\s*sc\s*\)\s*;\s*"
    r"return\s+\$\.ajax\(\s*\{\s*" + _POST_OPTIONS
    + rf"encodeURIComponent\(\s*btoa\(\s*(?P=input)\s*\+\s*'_(?P<version>{RESPONSE_VERSION})'\s*\)\s*\)"
)
_TIMETABLE_BODY = re.compile(
    r"return\s+\$\.ajax\(\s*\{\s*" + _POST_OPTIONS
    + rf"btoa\([^;{{}}]*?'_(?P<version>{RESPONSE_VERSION})'\s*\)"
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
    post_body: bool = False


def parse_service_protocol(content: str) -> ServiceProtocol:
    declarations = list(_FUNCTION.finditer(content))
    functions = [
        (match.group('name'), content[match.end():next_function], match.end())
        for match, next_function in zip(
            declarations, [match.start() for match in declarations[1:]] + [len(content)]
        )
    ]
    # Parse query and body request pairs together rather than accepting a
    # decoy query request in a page that actually serves body requests.
    named_school = any(name == 'QAjaxSchool' for name, _, _ in functions)
    school_requests = [
        (section, match, body, section_start)
        for name, section, section_start in functions
        if not named_school or name == 'QAjaxSchool'
        for pattern, body in ((_SCHOOL_REQUEST, False), (_SCHOOL_BODY, True))
        for match in pattern.finditer(section)
    ]
    if (not school_requests and not named_school and 'CryptoJS.enc.Hex.parse' not in content
            and not _SCHOOL_BODY.search(content) and not _TIMETABLE_BODY.search(content)):
        match = re.search(r'\.(/\d+\?\d+l)', content)
        if match is None:
            raise RuntimeError('Unable to parse Comcigan service endpoint; the service page structure may have changed')
        return ServiceProtocol(match.group(1))
    if len(school_requests) != 1:
        raise RuntimeError('Unable to parse Comcigan school request protocol')
    school_section, request, post_body, school_start = school_requests[0]
    if post_body:
        endpoint, prefix, version = (request.group(key) for key in ('endpoint', 'prefix', 'version'))
    else:
        endpoint, prefix, version = request.groups()

    timetable_requests = [
        (name, section, match, body, section_start)
        for name, section, section_start in functions
        if not named_school or name == 'QAjaxTimetable'
        for pattern, body in ((_TIMETABLE_REQUEST, False), (_TIMETABLE_BODY, True))
        for match in pattern.finditer(section)
    ]
    if len(timetable_requests) == 1:
        timetable_name, timetable_section, timetable_request, timetable_body, timetable_start = timetable_requests[0]
        timetable_protocol = (
            (timetable_request['endpoint'], timetable_request['version']) if timetable_body
            else timetable_request.groups()
        )
    if (len(timetable_requests) != 1 or timetable_body != post_body
            or timetable_protocol != (endpoint, version)):
        raise RuntimeError(
            'Comcigan service page structure changed: school and timetable request protocols do not match'
        )
    if post_body:
        verb = request['verb']
        # A body request needs both operations in the same inline script
        # and a single statically declared POST method, never a call or
        # an assignment to a computed value.
        scripts = [
            script.group(1) for script in _SCRIPT.finditer(content)
            if script.start(1) <= school_start + request.start() < script.end(1)
            and script.start(1) <= timetable_start + timetable_request.start() < script.end(1)
        ]
        if len(scripts) != 1 or timetable_request['verb'] != verb:
            raise RuntimeError('Invalid or inconsistent Comcigan request method')
        script = scripts[0]
        identifier = rf'(?:{_JS_IDENTIFIER})'
        assignment = list(re.finditer(rf"(?<![\w$.]){re.escape(verb)}\s*=(?!=|>)", script))
        literal_methods = list(re.finditer(
            rf"\A\s*(?:var|let|const)\s+(?:{identifier}\s*=\s*{identifier}\s*,\s*)?"
            rf"(?P<binding>{re.escape(verb)}\s*=)\s*(['\"])POST\2\s*;",
            script,
        ))
        if (len(assignment) != 1 or len(literal_methods) != 1
                or assignment[0].start() != literal_methods[0].start('binding')):
            raise RuntimeError('Invalid or inconsistent Comcigan request method')
    sections = (school_section[request.start():], timetable_section[timetable_request.start():])

    header_name = r"['\"]X-Hour-Token['\"]\s*:"
    header_reference = (
        r"headers\s*:\s*\{[^{}]*?['\"]X-Hour-Token['\"]\s*:\s*"
        r"window\.__HourRequestToken\s*\|\|\s*(['\"])\1"
    )
    advertised = [re.search(header_name, section) is not None for section in sections]
    request_token = None
    if post_body or any(advertised):
        if post_body:
            # Accept the observed header alongside the body in these same
            # Ajax options, not in another object in the surrounding function.
            tails = (school_section[request.end():], timetable_section[timetable_request.end():])
            header_matches = [
                re.match(
                    r"\s*,\s*" + header_reference.replace("[^{}]*?", r"\s*")
                    + rf"\s*\}}(?:\s*,\s*dataType\s*:\s*'text'\s*,\s*success\s*:\s*(?:{_JS_IDENTIFIER}))?"
                    + r"\s*\}\s*\)", tail,
                )
                for tail in tails
            ]
        else:
            header_matches = [re.search(header_reference, section) for section in sections]
        if not all(header_matches):
            raise RuntimeError('Invalid or inconsistent Comcigan request token headers')
        token_matches = list(re.finditer(
            r"\bwindow\.__HourRequestToken\s*=\s*(['\"])([0-9a-fA-F]+)\1\s*;",
            content,
        ))
        if not token_matches or (post_body and len(token_matches) != 1):
            raise RuntimeError('Unable to parse Comcigan request token literal')
        request_token = token_matches[0].group(2)

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

    # Read the school-list formulas, not similar arithmetic for unrelated lists.
    column_suffix = r'\s*\[i\]\s*\[0\]\s*/\s*(\d+)\s*\)\s*\+\s*(\d+)'
    column_prefix = r'Math\.floor\(\s*'
    columns = set(re.findall(
        column_prefix + r'(?:학교명단|H?학교명단\s*\.\s*학교검색)' + column_suffix, content,
    ))
    for name, section, section_start in functions:
        if name == '학교명단_출력하기':
            columns.update(re.findall(column_prefix + 'data' + column_suffix, section))
        sources = r'(?:학교명단|H?학교명단\s*\.\s*학교검색)'
        if name == '학교명단_출력하기':
            sources = r'(?:data|학교명단|H?학교명단\s*\.\s*학교검색)'
        variable_formula = (
            rf'\b(?:var|let|const)\s+(?P<divisor>(?:{_JS_IDENTIFIER}))\s*=\s*(?P<value>\d+)\s*;\s*'
            rf'(?:var|let|const)\s+(?:{_JS_IDENTIFIER})\s*=\s*Math\.floor\(\s*{sources}'
            r'\s*\[i\]\s*\[0\]\s*/\s*(?P=divisor)\s*\)\s*\+\s*(?P<offset>\d+)'
        )
        columns.update((m.group('value'), m.group('offset')) for m in re.finditer(variable_formula, section))
    values = {(int(divisor), int(offset)) for divisor, offset in columns}
    if len(values) != 1:
        raise RuntimeError('Unable to parse Comcigan school code column')
    school_divisor, school_offset = values.pop()
    if school_divisor <= 0 or not 0 <= school_offset <= 64:
        raise RuntimeError('Unable to parse Comcigan school code column')
    text_key, start_date_field, period_times_field = parse_field_encoding(content, required=version.isdecimal())
    # Look up the caller which forwards the four timetable arguments, and
    # collect the first argument from its call sites (the fixed request prefix).
    forward = rf'(?<![\w$]){re.escape(timetable_name)}\s*\(\s*sc\s*,\s*sc2\s*,\s*da1\s*,\s*r\s*,'
    prefixes = {
        value
        for name, section, section_start in functions
        if re.search(forward, section)
        for value in re.findall(rf"(?<![\w$]){re.escape(name)}\s*\(\s*'([0-9]+)_'\s*,", content)
    }
    if len(prefixes) > 1:
        raise RuntimeError('Conflicting Comcigan timetable request prefixes')
    return ServiceProtocol(endpoint + '?' + prefix, bytes.fromhex(key_hex), version,
                           school_divisor, school_offset, request_token,
                           text_key, start_date_field, period_times_field, next(iter(prefixes), None), post_body)
