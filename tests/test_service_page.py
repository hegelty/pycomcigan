"""Offline regression coverage for issue #9; no remote code is executed."""
import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycomcigan import TimeTable, get_school_code
from pycomcigan.search_school import get_comcigan_code
from pycomcigan.service_page import decode_service_page


# Synthetic wrapper matching the public issue. Test data contains no real names.
WRAPPER = '''<script>/* hour-obfuscated-v2 */(function(a,k){var s='',i,j,b;
for(i=0;i<a.length;i++){if(a[i][0]){s+=a[i][1];continue;}b=a[i][1];
for(j=0;j<b.length;j+=4){s+=String.fromCharCode(parseInt(b.substr(j,4),16)^((k+(j/4)*13)&255));}}
(0,eval)(s);})(PAYLOAD,KEY);</script>'''
SOURCE = """url:'./165823?47241l'; sc_data('107225_', sc, 1, '0');
성명=Q성명(자료.자료119[th]); 과목명=Q과목명(자료.자료123[sb]);
da1=H시간표.자료108;
일일자료=Q자료(자료.자료158[학년][반][요일][교시]);
원자료=Q자료(자료.자료167[학년][반][요일][교시]);"""
CODES = ('/165823?47241l', '107225', '119', '123', '108', '158', '167')


def encode(text, key):
    data = text.encode('utf-16-le', errors='surrogatepass')
    return ''.join(f'{int.from_bytes(data[i:i+2], "little") ^ ((key + i // 2 * 13) & 255):04X}'
                   for i in range(0, len(data), 2))


def wrap(fragments, key=100):
    return WRAPPER.replace('PAYLOAD', json.dumps(fragments)).replace('KEY', str(key))


def obfuscate(source, key=100):
    # Separate encoded fragments exercise index reset, with plaintext between.
    return wrap([[0, encode(source[:20], key)], [1, source[20:35]],
                 [0, encode(source[35:], key)]], key)


@pytest.mark.parametrize('key', [0, 100, 255])
def test_decodes_fragments_with_unicode_escapes_and_counter_reset(key):
    source = '한글 😀 "quoted" \\ path\n' + SOURCE
    assert decode_service_page(obfuscate(source, key)) == '<script>' + source + '</script>'


def test_preserves_plain_page_exactly():
    page = '<html><script>' + SOURCE + '</script><p>legacy</p></html>'
    assert decode_service_page(page) == page


def test_decodes_multiple_scripts_and_preserves_unrelated_content():
    page = '<p>before</p>' + obfuscate(SOURCE[:80]) + '<script>ordinary();</script>' + obfuscate(SOURCE[80:], 255)
    assert decode_service_page(page) == ('<p>before</p><script>' + SOURCE[:80]
        + '</script><script>ordinary();</script><script>' + SOURCE[80:] + '</script>')


def test_does_not_execute_restored_source(tmp_path):
    target = tmp_path / 'must-not-exist'
    source = f'__import__("pathlib").Path({str(target)!r}).touch()'
    assert source in decode_service_page(obfuscate(source))
    assert not target.exists()


@pytest.mark.parametrize('fragments,key', [
    ([[0, '123']], 1), ([[0, 'ZZZZ']], 1), ([[2, 'plain']], 1),
    ([[True, 'plain']], 1), ([[0, 1234]], 1), ([[0]], 1),
    ([{'0': '0000'}], 1), ([[0, '0000']], 256), ([[0, '0000']], -1),
])
def test_rejects_malformed_payload(fragments, key):
    with pytest.raises(RuntimeError, match='Unable to decode Comcigan hour-obfuscated-v2'):
        decode_service_page(wrap(fragments, key))


def test_rejects_expressions_instead_of_literal_arguments():
    page = WRAPPER.replace('PAYLOAD', '[[0,evil()]]').replace('KEY', '100')
    with pytest.raises(RuntimeError, match='Unable to decode'):
        decode_service_page(page)


def test_rejects_extra_executable_invocation_arguments():
    page = wrap([[1, SOURCE]]).replace(']],100)', ']],100,evil())')
    with pytest.raises(RuntimeError, match='Unable to decode'):
        decode_service_page(page)


@pytest.mark.parametrize('page', ['<script>' + SOURCE + '</script>', obfuscate(SOURCE)])
def test_both_code_extractors_support_plain_and_obfuscated_pages(page):
    response = SimpleNamespace(text=page)
    with patch('pycomcigan.timetable.get_comcigan_response_for_codes', return_value=response):
        assert TimeTable._get_comcigan_codes() == CODES
    with patch('pycomcigan.search_school.get_comcigan_response_for_codes', return_value=response):
        assert get_comcigan_code() == CODES[0]


def test_school_search_reports_missing_endpoint():
    with patch('pycomcigan.search_school.get_comcigan_response_for_codes', return_value=SimpleNamespace(text='<html/>')):
        with pytest.raises(RuntimeError, match='service endpoint'):
            get_comcigan_code()


def test_public_school_search_uses_decoded_endpoint():
    result = [[1, '지역', '테스트고', 123]]
    with patch('pycomcigan.helpers.get_response_encoding', side_effect=[
        SimpleNamespace(text=obfuscate(SOURCE)),
        SimpleNamespace(text=json.dumps({'학교검색': result}) + '\x00'),
    ]) as get:
        assert get_school_code('테스트고') == result
        assert '/165823?47241l' in get.call_args.args[0]


@pytest.mark.parametrize('endpoint', ['/36179?17384l', '/165823?47241l'])
@pytest.mark.parametrize('week', [0, 1])
def test_timetable_request_supports_variable_length_paths(endpoint, week):
    with patch('pycomcigan.timetable.get_response_encoding', return_value=SimpleNamespace(text='{}\n')) as get:
        assert TimeTable._fetch_timetable_data(123, week, (endpoint,) + CODES[1:]) == {}
        url = get.call_args.args[0]
        assert url.split('?')[0].endswith(endpoint.split('?')[0])
        assert base64.b64decode(url.split('?')[1]).decode() == f'107225_123_0_{week + 1}'


@pytest.mark.parametrize('week', [0, 1])
def test_public_timetable_flow_with_obfuscated_page(week):
    data = {
        '지역명': '지역', '학년도': 2026, '시작일': '2026-11-02', '일과시간': [],
        '자료108': '2026-11-03', '자료119': ['', '교사'], '자료123': ['', '수학'],
        '자료158': [[], [[], [1, [1, 1001]]]],
        '자료167': [[], [[], [1, [1, 1001]]]], '담임': [[1, 0]],
    }
    with patch('pycomcigan.timetable.get_comcigan_response_for_codes', return_value=SimpleNamespace(text=obfuscate(SOURCE))), \
         patch('pycomcigan.timetable.school_search', return_value=[[1, '지역', '테스트고', 123]]), \
         patch('pycomcigan.timetable.get_response_encoding', return_value=SimpleNamespace(text=json.dumps(data))):
        result = TimeTable('테스트고', week_num=week)
    assert result.timetable[1][1][1][0].subject == '수학'
    assert result.timetable[1][1][1][0].teacher == '교사'
    assert result.homeroom(1, 1) == '교사'
    assert result.update_date == '2026-11-03'


def test_handles_case_insensitive_tags_and_empty_fragments():
    page = wrap([[0, ''], [1, ''], [0, encode('자료😀', 100).lower()]])
    page = page.replace('<script>', '<SCRIPT type="text/javascript">').replace('</script>', '</SCRIPT >')
    assert decode_service_page(page) == '<SCRIPT type="text/javascript">자료😀</SCRIPT >'


def test_marked_script_without_invocation_is_rejected():
    with pytest.raises(RuntimeError, match='Unable to decode'):
        decode_service_page('<script>/* hour-obfuscated-v2 */broken</script>')


def test_invalid_later_block_is_not_silently_ignored():
    with pytest.raises(RuntimeError, match='Unable to decode'):
        decode_service_page(obfuscate(SOURCE) + wrap([[0, 'bad']]))


def test_surrogate_pair_can_cross_fragment_boundaries():
    page = wrap([[0, encode('\ud83d', 100)], [0, encode('\ude00', 100)]])
    assert decode_service_page(page) == '<script>😀</script>'
