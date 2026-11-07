"""Decode known Comcigan page wrappers as data, never as JavaScript."""

import json
import re


_SCRIPT = re.compile(r'(<script\b[^>]*>)(.*?)(</script\s*>)', re.I | re.S)
_MARKER = '/* hour-obfuscated-v2 */'
_AJAX_MARKER = '/* hour-ajax-obfuscated-v1 */'
_ERROR = 'Unable to decode Comcigan hour-obfuscated-v2 service page'


def _decode_script(script: str) -> str:
    """Read only the literal arguments of the known wrapper's invocation.

    JSON decoding deliberately rejects executable expressions and JavaScript-only
    literals. The wrapper body and the reconstructed source are never evaluated.
    """
    invocation = re.search(r'\}\s*\)\s*\(\s*(?=\[)', script)
    if invocation is None:
        raise ValueError('missing literal fragment array')
    fragments, end = json.JSONDecoder().raw_decode(script, invocation.end())
    key_match = re.fullmatch(r'\s*,\s*([0-9]{1,3})\s*\)\s*;?\s*', script[end:])
    if key_match is None:
        raise ValueError('invalid decoder key or invocation')
    key = int(key_match.group(1))
    if key > 255 or not isinstance(fragments, list):
        raise ValueError('invalid decoder arguments')

    decoded = []
    for fragment in fragments:
        if (not isinstance(fragment, list) or len(fragment) != 2
                or type(fragment[0]) is not int or fragment[0] not in (0, 1)
                or not isinstance(fragment[1], str)):
            raise ValueError('invalid fragment')
        plain, value = fragment
        if plain:
            decoded.append(value)
            continue
        if len(value) % 4 or re.fullmatch(r'[0-9a-fA-F]*', value) is None:
            raise ValueError('invalid hexadecimal fragment')
        # The position counter restarts for each fragment, as in the wrapper.
        units = bytearray()
        for offset in range(0, len(value), 4):
            unit = int(value[offset:offset + 4], 16) ^ ((key + offset // 4 * 13) & 255)
            units.extend(unit.to_bytes(2, 'little'))
        decoded.append(units.decode('utf-16-le', errors='surrogatepass'))
    # A surrogate pair may be split between fragments. Normalize only after
    # joining so the result matches the complete JavaScript UTF-16 string.
    return ''.join(decoded).encode(
        'utf-16-le', errors='surrogatepass'
    ).decode('utf-16-le', errors='surrogatepass')


def decode_service_page(content: str) -> str:
    """Restore every hour-obfuscated-v2 script, leaving legacy pages unchanged."""
    def replace(match: re.Match) -> str:
        script = match.group(2)
        if not script.lstrip().startswith(_MARKER):
            return match.group(0)
        try:
            decoded = _decode_script(script)
        except (ValueError, TypeError, RecursionError) as error:
            raise RuntimeError(_ERROR) from error
        return match.group(1) + decoded + match.group(3)

    content = _SCRIPT.sub(replace, content)
    # Ajax wrappers sit inline among ordinary functions, inside the outer script.
    while _AJAX_MARKER in content:
        start = content.index(_AJAX_MARKER)
        try:
            invocation = re.search(r'\}\s*\)\s*\(\s*(?=\[)', content[start:])
            if invocation is None:
                raise ValueError('missing Ajax invocation')
            payload_start = start + invocation.end()
            _, end = json.JSONDecoder().raw_decode(content, payload_start)
            tail = re.match(r'\s*,\s*[0-9]{1,3}\s*\)\s*;?', content[end:])
            if tail is None:
                raise ValueError('invalid Ajax invocation')
            stop = end + tail.end()
            decoded = _decode_script(content[start:stop])
            if _AJAX_MARKER in decoded:
                raise ValueError('unexpected nested Ajax wrapper')
        except (ValueError, TypeError, RecursionError) as error:
            raise RuntimeError('Unable to decode Comcigan hour-ajax-obfuscated-v1 service page') from error
        content = content[:start] + decoded + content[stop:]
    return content
