import base64
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycomcigan.helpers import decode_text, school_search
from pycomcigan.service_protocol import parse_service_protocol
from pycomcigan.timetable import TimeTable
from test_service_protocol import PAGE


KEY = bytes([34, 68, 63, 44])
NEW_PAGE = PAGE + '''
function QnmsbChange(value) { var key=String.fromCharCode(34,68,63,44); }
var start = new Date(QnmsbChange(자료.자료143));
var period = 자료.자료130[교시-1];
'''


def encode(value):
    data = value.encode('cp949')
    return base64.b64encode(bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(data))).decode('ascii')


def test_encoded_school_search_and_metadata():
    protocol = parse_service_protocol(NEW_PAGE)
    assert (protocol.text_key, protocol.start_field, protocol.periods_field) == (KEY, '자료143', '자료130')
    rows = [[5000, encode('서울'), encode('학교'), encode('12345')], [0, '', '', '']]
    with patch('pycomcigan.helpers.get_response_encoding', return_value=SimpleNamespace(text='response')), \
         patch('pycomcigan.helpers.decode_response', return_value={'학교검색': rows}):
        assert school_search('학교', protocol.endpoint, protocol) == [[5000, '서울', '학교', 12345]]


def test_encoded_timetable_fields_are_decoded():
    protocol = parse_service_protocol(NEW_PAGE)
    data = {'지역명': encode('서울'), '자료143': encode('2026-11-09'), '자료130': ['09:00'],
            '자료108': encode('2026-11-10'), '자료119': [encode(''), encode('김*')],
            '자료123': [0, encode('수학')]}
    TimeTable._decode_timetable_text(data, ('', '', '119', '123', '108', '', ''), protocol)
    assert data['지역명'] == '서울'
    assert data['시작일'] == '2026-11-09'
    assert data['일과시간'] == ['09:00']
    assert data['자료108'] == '2026-11-10'
    assert data['자료119'] == ['', '김*']
    assert data['자료123'] == [0, '수학']


def test_invalid_encoded_text_fails():
    with pytest.raises(RuntimeError, match='encoded text'):
        decode_text('not base64!', KEY)


def test_null_school_code_raises_runtime_error():
    protocol = parse_service_protocol(NEW_PAGE)
    rows = [[5000, encode('서울'), encode('학교'), None]]
    with patch('pycomcigan.helpers.get_response_encoding', return_value=SimpleNamespace(text='response')), \
         patch('pycomcigan.helpers.decode_response', return_value={'학교검색': rows}), \
         pytest.raises(RuntimeError, match='school code column'):
        school_search('학교', protocol.endpoint, protocol)
