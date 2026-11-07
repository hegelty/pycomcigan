"""Decode known Comcigan page wrappers as data, never as JavaScript."""

import json
import re


_SCRIPT = re.compile(r'(<script\b[^>]*>)(.*?)(</script\s*>)', re.I | re.S)
_MARKER = '/* hour-obfuscated-v2 */'
_AJAX_MARKER = '/* hour-ajax-obfuscated-v1 */'
_MAX_PAGE_SIZE = 16 * 1024 * 1024
_MAX_PASSES = 4
_MARKERS = (_MARKER, _AJAX_MARKER)
_INVOCATION = re.compile(r'\}\s*\)\s*\(\s*(?=\[)')
_TAIL = re.compile(r'\s*,\s*[0-9]{1,3}\s*\)\s*;?')


def _decode_script(script: str, max_size: int = None) -> str:
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

    if max_size is None:
        max_size = _MAX_PAGE_SIZE
    decoded = []
    size = 0
    for fragment in fragments:
        if (not isinstance(fragment, list) or len(fragment) != 2
                or type(fragment[0]) is not int or fragment[0] not in (0, 1)
                or not isinstance(fragment[1], str)):
            raise ValueError('invalid fragment')
        plain, value = fragment
        # Count UTF-16 units conservatively before allocating decoded fragments.
        # Plain strings count Python characters; encoded strings count code units.
        size += len(value) if plain else len(value) // 4
        if size > max_size:
            raise ValueError('decoded page exceeds size limit')
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
    """Restore known wrappers in four passes; limit pages to 16 MiB UTF-8.

    Decoded hexadecimal fragments are conservatively measured in UTF-16 units.
    """
    if len(content) > _MAX_PAGE_SIZE or len(content.encode('utf-8', errors='surrogatepass')) > _MAX_PAGE_SIZE:
        raise RuntimeError('Comcigan service page exceeds size limit')

    for _ in range(_MAX_PASSES):
        if not any(marker in content for marker in _MARKERS):
            return content
        pieces = []
        cursor = 0
        size = 0
        for script_match in _SCRIPT.finditer(content):
            position = script_match.start(2)
            script_end = script_match.end(2)
            while position < script_end:
                hits = [(content.find(marker, position, script_end), marker) for marker in _MARKERS]
                hits = [(start, marker) for start, marker in hits if start >= 0]
                if not hits:
                    break
                start, marker = min(hits)
                try:
                    # Do not let a broken wrapper borrow a sibling's invocation.
                    next_marker = min((p for p, _ in hits if p > start), default=script_end)
                    same_marker = content.find(marker, start + len(marker), script_end)
                    if same_marker >= 0:
                        next_marker = min(next_marker, same_marker)
                    invocation = _INVOCATION.search(content, start + len(marker), next_marker)
                    if invocation is None:
                        raise ValueError('missing literal fragment array')
                    _, end = json.JSONDecoder().raw_decode(content, invocation.end())
                    if end > script_end:
                        raise ValueError('payload extends beyond script')
                    tail = _TAIL.match(content, end, script_end)
                    if tail is None:
                        raise ValueError('invalid decoder invocation')
                    stop = tail.end()
                    prefix_size = start - cursor
                    budget = _MAX_PAGE_SIZE - size - prefix_size
                    decoded = _decode_script(content[start:stop], budget)
                    pieces.extend((content[cursor:start], decoded))
                    size += prefix_size + len(decoded)
                    cursor = position = stop
                except (ValueError, TypeError, RecursionError) as error:
                    raise RuntimeError(f'Unable to decode Comcigan {marker[3:-3]} service page') from error
        if not pieces:
            break
        if size + len(content) - cursor > _MAX_PAGE_SIZE:
            raise RuntimeError('Comcigan service page exceeds size limit')
        pieces.append(content[cursor:])
        content = ''.join(pieces)
        if len(content.encode('utf-8', errors='surrogatepass')) > _MAX_PAGE_SIZE:
            raise RuntimeError('Comcigan service page exceeds size limit')
    for marker in _MARKERS:
        if marker in content:
            raise RuntimeError(f'Unable to decode Comcigan {marker[3:-3]} service page: unresolved marker after {_MAX_PASSES} passes')
    return content
