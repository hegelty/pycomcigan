import base64
import json
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote, unquote

import pytest

from pycomcigan import TimeTable, get_school_code
from pycomcigan.helpers import school_search
from pycomcigan.service_page import decode_service_page
from pycomcigan.service_protocol import parse_service_protocol
from test_service_page import SOURCE, CODES, obfuscate
from test_encrypted_response import envelope


KEY = bytes.fromhex('00112233445566778899aabbccddeeff')
PAGE = """
function QAjaxSchool(sc, success) {return $.ajax({
url:'./987654?'+encodeURIComponent(btoa('24680l'+encodeURIComponent(sc)+'_enc5'))});}
function QAjaxTimetable(sc, sc2, da1, r, success) {
return $.ajax({url:'./987654?'+btoa(sc+sc2+'_'+da1+'_'+r+'_enc5')});}
var key=CryptoJS.enc.Hex.parse((function(a){return a[1]+a[0];})(['8899aabbccddeeff','0011223344556677']));
var r=Math.floor(학교명단[i][0]/5000)+2;
""" + SOURCE


def test_latest_protocol_extracts_page_values():
    protocol = parse_service_protocol(PAGE)
    assert protocol.endpoint == '/987654?24680l'
    assert protocol.key == KEY
    assert protocol.version == 'enc5'
    assert (protocol.school_divisor, protocol.school_offset) == (5000, 2)
    assert TimeTable._get_comcigan_codes(PAGE) == (protocol.endpoint,) + CODES[1:]


def test_protocol_supports_literal_key_and_rejects_executable_key():
    expression = "(function(a){return a[1]+a[0];})(['8899aabbccddeeff','0011223344556677'])"
    assert parse_service_protocol(PAGE.replace(expression, "'" + KEY.hex() + "'")).key == KEY
    with pytest.raises(RuntimeError, match='key expression'):
        parse_service_protocol(PAGE.replace(expression, 'evil()'))


@pytest.mark.parametrize('old,new,error', [
    ("'./987654?'", "'./changed?'", 'school request'),
    ('a[1]+a[0]', 'a[2]+a[0]', 'key indexes'),
    ('/5000', '/0', 'school code column'),
])
def test_changed_protocol_reports_useful_errors(old, new, error):
    with pytest.raises(RuntimeError, match=error):
        parse_service_protocol(PAGE.replace(old, new))


def test_nested_ajax_wrappers_are_decoded_without_execution():
    inner = obfuscate(PAGE).replace('hour-obfuscated-v2', 'hour-ajax-obfuscated-v1')
    inner = inner.removeprefix('<script>').removesuffix('</script>')
    decoded = decode_service_page(obfuscate('before();' + inner + 'after();'))
    assert 'before();' + PAGE + 'after();' in decoded
    assert parse_service_protocol(decoded).key == KEY


def test_multiple_inline_ajax_wrappers_and_invalid_later_wrapper():
    inner = obfuscate('first();').replace('hour-obfuscated-v2', 'hour-ajax-obfuscated-v1')
    assert decode_service_page(inner + inner) == '<script>first();</script>' * 2
    with pytest.raises(RuntimeError, match='hour-ajax-obfuscated-v1'):
        decode_service_page(inner + '<script>/* hour-ajax-obfuscated-v1 */broken</script>')


def test_search_uses_utf8_base64_and_normalizes_variable_school_columns():
    rows = [[5000, '지역', '테스트고', 123],
            [10000, '지역', '테스트고2', 999999, 456],
            [15000, '지역', '테스트고3', 999999, 888888, 789],
            [0, '알림', '없으면 추가 검색하세요', 0]]
    protocol = parse_service_protocol(PAGE)
    with patch('pycomcigan.helpers.get_response_encoding', return_value=SimpleNamespace(text='encrypted')) as get, \
         patch('pycomcigan.helpers.decode_response', return_value={'학교검색': rows}) as decode:
        assert school_search("테스트고 & ~!*'()", protocol.endpoint, protocol) == [
            rows[0], rows[1][:3] + [456], rows[2][:3] + [789]]
    token = get.call_args.args[0].split('?', 1)[1]
    expected = '24680l' + quote("테스트고 & ~!*'()", safe="~()*!.'-") + '_enc5'
    assert token == quote(base64.b64encode(expected.encode('ascii')).decode(), safe='')
    assert base64.b64decode(unquote(token)).decode() == expected
    decode.assert_called_once_with('encrypted', KEY, 'enc5')


@pytest.mark.parametrize('rows', [None, [[10000, '지역', '학교', 999]], [['bad', '지역', '학교', 123]]])
def test_invalid_search_payload_is_not_reported_as_no_school(rows):
    with patch('pycomcigan.helpers.get_response_encoding', return_value=SimpleNamespace(text='encrypted')), \
         patch('pycomcigan.helpers.decode_response', return_value={'학교검색': rows}), \
         pytest.raises(RuntimeError, match='Invalid Comcigan'):
        school_search('학교', '/unused', parse_service_protocol(PAGE))


def test_empty_search_result_is_preserved():
    with patch('pycomcigan.helpers.get_response_encoding', return_value=SimpleNamespace(text='encrypted')), \
         patch('pycomcigan.helpers.decode_response', return_value={'학교검색': []}):
        assert school_search('학교', '/unused', parse_service_protocol(PAGE)) == []


@pytest.mark.parametrize('week', [0, 1])
def test_latest_timetable_request(week):
    protocol = parse_service_protocol(PAGE)
    with patch('pycomcigan.timetable.get_response_encoding', return_value=SimpleNamespace(text='encrypted')) as get, \
         patch('pycomcigan.timetable.decode_response', return_value={'시작일': '2026-11-02'}):
        assert TimeTable._fetch_timetable_data(123, week, (protocol.endpoint,) + CODES[1:], protocol)['시작일']
    assert base64.b64decode(get.call_args.args[0].split('?')[1]).decode() == f'107225_123_0_{week + 1}_enc5'


def test_public_search_fetches_protocol_once():
    with patch('pycomcigan.search_school.get_comcigan_response_for_codes', return_value=SimpleNamespace(text=PAGE)) as get, \
         patch('pycomcigan.search_school.school_search', return_value=[]) as search:
        assert get_school_code('테스트고') == []
    get.assert_called_once()
    assert search.call_args.args[2].key == KEY


@pytest.mark.parametrize('week', [0, 1])
def test_public_flow_with_encrypted_search_and_timetable(week):
    data = {
        '지역명': '지역', '학년도': 2026, '시작일': '2026-11-02', '일과시간': [],
        '자료108': '2026-11-03', '자료119': ['', '교사'], '자료123': ['', '수학'],
        '자료158': [[], [[], [1, [1, 1001]]]],
        '자료167': [[], [[], [1, [1, 1001]]]], '담임': [[1, 0]],
    }
    schools = {'학교검색': [[10000, '지역', '테스트고', 999999, 123],
                         [0, '알림', '없으면 추가 검색하세요', 0]]}
    encrypted_schools = envelope(json.dumps(schools).encode(), key=KEY)
    encrypted_timetable = envelope(json.dumps(data).encode(), key=KEY)
    with patch('pycomcigan.helpers.get_response_encoding', side_effect=[
        SimpleNamespace(text=obfuscate(PAGE)), SimpleNamespace(text=encrypted_schools),
    ]):
        assert get_school_code('테스트고') == [[10000, '지역', '테스트고', 123]]
    with patch('pycomcigan.timetable.get_comcigan_response_for_codes', return_value=SimpleNamespace(text=obfuscate(PAGE))) as page, \
         patch('pycomcigan.helpers.get_response_encoding', return_value=SimpleNamespace(text=encrypted_schools)), \
         patch('pycomcigan.timetable.get_response_encoding', return_value=SimpleNamespace(text=encrypted_timetable)):
        table = TimeTable('테스트고', week_num=week)
    page.assert_called_once()
    assert table.school_code == 123
    assert table.timetable[1][1][1][0].subject == '수학'
    assert table.timetable[1][1][1][0].teacher == '교사'
    assert table.homeroom(1, 1) == '교사'
