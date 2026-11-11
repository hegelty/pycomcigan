"""Synthetic coverage for the November 2026 QnmsbChange field format."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pycomcigan import TimeTable, get_school_code
from pycomcigan.encoded_fields import decode_field, decode_timetable_fields
from pycomcigan.service_protocol import parse_service_protocol
from test_request_transport import TOKEN, TOKEN_PAGE


FIELD_KEY = b'Key1'
DECODER = '''
function QnmsbChange(value) {
    if(value==undefined || value==='') return '';
    var key=String.fromCharCode(75,101,121,49);
    var raw=atob(value);
    var bytes=new Uint8Array(raw.length);
    for(var i=0;i<bytes.length;i++) {
        bytes[i]=raw.charCodeAt(i)^key.charCodeAt(i%key.length);
    }
    return new TextDecoder('euc-kr',{fatal:true}).decode(bytes);
}
var start=new Date(QnmsbChange(자료.자료901));
var time=자료.자료902[교시-1];
'''
PAGE = TOKEN_PAGE.replace('da1=H시간표.자료108;', 'da1=QnmsbChange(H시간표.자료108);') + DECODER
FIXTURES = json.loads((Path(__file__).parent / 'fixtures/encoded-fields-responses.json').read_text())


@pytest.mark.parametrize('encoded,expected', [
    ('ipPGmw==', '지역'), ('34s=', '뷁'), ('+tbC1mE=', '교사*'),
    ('95O+4Q==', '수학'), ('eVVLB2ZUSBx7XA==', '2026-11-09'),
    ('', ''), (None, ''),
])
def test_independent_iconv_and_node_field_vectors(encoded, expected):
    assert decode_field(encoded, FIELD_KEY) == expected


@pytest.mark.parametrize('value', ['!', 'AB==', 'yg==', '95O+4Q==\n', 0, [], {}])
def test_invalid_fields_fail_without_exposing_source(value):
    with pytest.raises(RuntimeError, match='Invalid encoded Comcigan text field'):
        decode_field(value, FIELD_KEY)


def test_protocol_reads_literal_key_and_metadata_fields():
    protocol = parse_service_protocol(PAGE)
    assert protocol.text_key == FIELD_KEY
    assert protocol.start_date_field == '자료901'
    assert protocol.period_times_field == '자료902'
    assert 'text_key' not in repr(protocol)
    assert TOKEN not in repr(protocol)
    assert TimeTable._get_comcigan_codes(PAGE)[4] == '108'
    changed = PAGE.replace('75,101,121,49', '51,52,53').replace('자료901', '자료777').replace('자료902', '자료778')
    protocol = parse_service_protocol(changed)
    assert protocol.text_key == b'345'
    assert protocol.start_date_field == '자료777'
    assert protocol.period_times_field == '자료778'


@pytest.mark.parametrize('old,new', [
    ('75,101,121,49', ''), ('75,101,121,49', '256'),
    ('75,101,121,49', 'evil()'), ('^key.charCodeAt', '+key.charCodeAt'),
    ("fatal:true", "fatal:false"), ("'euc-kr'", "'utf-8'"),
])
def test_unknown_decoder_is_rejected(old, new):
    with pytest.raises(RuntimeError, match='text field decoder|text field key'):
        parse_service_protocol(PAGE.replace(old, new))


def test_missing_decoder_with_remaining_call_sites_is_rejected():
    page = PAGE.replace(DECODER, DECODER[DECODER.index('var start='):])
    with pytest.raises(RuntimeError, match='text field decoder'):
        parse_service_protocol(page)


@pytest.mark.parametrize('expression', [
    'new Date(QnmsbChange(자료.자료901))', '자료.자료902[교시-1]',
])
def test_metadata_fields_are_required(expression):
    with pytest.raises(RuntimeError, match='date or period-time fields'):
        parse_service_protocol(PAGE.replace(expression, 'unknown'))


def response(text, encoding='utf-8'):
    result = Mock(status=200)
    result.read.return_value = text.encode(encoding)
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


def test_public_school_search_decodes_variable_code_column_and_footer():
    with patch('pycomcigan.helpers.urlopen', side_effect=[
        response(PAGE, 'cp949'), response(FIXTURES['search']),
    ]):
        assert get_school_code('테스트고') == [[5000, '지역', '테스트고', 123], [10000, '지역', '테스트고', 456]]
    with patch('pycomcigan.helpers.urlopen', side_effect=[
        response(PAGE, 'cp949'), response(FIXTURES['empty']),
    ]):
        assert get_school_code('존재하지않는학교') == []


@pytest.mark.parametrize('week', [0, 1])
def test_public_timetable_flow_restores_dates_times_names_and_subjects(week):
    with patch('pycomcigan.helpers.urlopen', side_effect=[
        response(PAGE, 'cp949'), response(FIXTURES['search']), response(FIXTURES['timetable']),
    ]) as get:
        table = TimeTable('테스트고', school_code=123, week_num=week)
    assert table.school_code == 123
    assert table.local_name == '지역'
    assert table.start_date == '2026-11-09'
    assert table.update_date == '2026-11-11 12:34:56'
    assert table.day_time == ['09:00']
    assert table.timetable[1][1][1][0].subject == '수학'
    assert table.timetable[1][1][1][0].teacher == '교사'
    assert table.homeroom(1, 1) == '교사'
    assert [call.args[0].get_header('X-hour-token') for call in get.call_args_list] == [None, TOKEN, TOKEN]


def test_normalization_keeps_legacy_data_and_does_not_modify_input():
    protocol = parse_service_protocol(PAGE)
    codes = TimeTable._get_comcigan_codes(PAGE)
    data = {'자료119': ['', '+tbC1mE='], '자료123': [0, '95O+4Q=='],
            '지역명': 'ipPGmw==', '자료108': 'eVVLB2ZUSBx6VFkAeV9KBXFQTw==',
            '자료901': 'eVVLB2ZUSBx7XA==', '자료902': ['09:00']}
    before = deepcopy(data)
    decoded = decode_timetable_fields(data, codes, protocol)
    assert decoded['자료123'] == ['', '수학']
    assert decoded['시작일'] == '2026-11-09'
    assert data == before
    assert decode_timetable_fields(data, codes, parse_service_protocol(TOKEN_PAGE)) is data
    del data['자료901']
    with pytest.raises(RuntimeError, match='Invalid encoded Comcigan timetable fields'):
        decode_timetable_fields(data, codes, protocol)


def test_failed_envelope_authentication_never_reaches_field_decoding():
    protocol = parse_service_protocol(PAGE)
    codes = TimeTable._get_comcigan_codes(PAGE)
    head, tag = FIXTURES['timetable'].rsplit(':', 1)
    tampered = head + ':' + ('A' if tag[0] != 'A' else 'B') + tag[1:]
    with patch('pycomcigan.helpers.urlopen', return_value=response(tampered)), \
         patch('pycomcigan.timetable.decode_timetable_fields') as decode, \
         pytest.raises(RuntimeError, match='authentication failed'):
        TimeTable._fetch_timetable_data(123, 0, codes, protocol)
    decode.assert_not_called()
