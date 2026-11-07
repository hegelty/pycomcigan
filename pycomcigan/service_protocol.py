import ast
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ServiceProtocol:
    endpoint: str
    key: Optional[bytes] = None
    version: Optional[str] = None
    school_divisor: Optional[int] = None
    school_offset: int = 0


def parse_service_protocol(content: str) -> ServiceProtocol:
    if 'function QAjaxSchool' not in content:
        match = re.search(r'\.(/\d+\?\d+l)', content)
        if match is None:
            raise RuntimeError('Unable to parse Comcigan service endpoint; the service page structure may have changed')
        return ServiceProtocol(match.group(1))

    request = re.search(
        r"function\s+QAjaxSchool\s*\([^)]*\)\s*\{.*?"
        r"url\s*:\s*'\.(/\d+)\?'\s*\+\s*encodeURIComponent\(btoa\("
        r"'(\d+l)'\s*\+\s*encodeURIComponent\(sc\)\s*\+\s*'_(enc\d+)'\)\)",
        content, re.S,
    )
    if request is None:
        raise RuntimeError('Unable to parse Comcigan school request protocol')
    endpoint, prefix, version = request.groups()

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
    if column is None or int(column.group(1)) == 0:
        raise RuntimeError('Unable to parse Comcigan school code column')
    return ServiceProtocol(endpoint + '?' + prefix, bytes.fromhex(key_hex), version,
                           int(column.group(1)), int(column.group(2)))
