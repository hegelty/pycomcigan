import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from pycomcigan.helpers import HEADERS, get_response_encoding, school_search
from pycomcigan.service_protocol import parse_service_protocol
from pycomcigan.timetable import TimeTable
from pycomcigan import get_school_code
from test_encrypted_response import envelope
from test_service_protocol import PAGE, KEY, CODES


TOKEN = 'ab' * 32
TOKEN_PAGE = "window.__HourRequestToken='" + TOKEN + "';" + PAGE.replace(
    "});}", ",headers:{'X-Hour-Token':window.__HourRequestToken || ''}});}")


def test_http_transport_adds_token_per_request_without_mutating_global_headers():
    response = Mock(status_code=200)
    with patch('pycomcigan.helpers.requests.get', return_value=response) as get:
        assert get_response_encoding('http://example.test/data', 'UTF-8', TOKEN) is response
        assert get.call_args.kwargs['headers']['X-Hour-Token'] == TOKEN
        get_response_encoding('http://example.test/page', 'cp949')
        assert 'X-Hour-Token' not in get.call_args.kwargs['headers']
    assert 'X-Hour-Token' not in HEADERS
    assert response.encoding == 'cp949'
    assert response.raise_for_status.call_count == 2


@pytest.mark.parametrize('status,message', [(403, 'HTTP 403.*token'), (429, 'HTTP 429.*retry later')])
def test_rejected_request_is_not_decrypted_or_retried(status, message):
    response = Mock(status_code=status)
    with patch('pycomcigan.helpers.requests.get', return_value=response) as get, \
         pytest.raises(RuntimeError, match=message) as error:
        get_response_encoding('http://example.test/data', 'UTF-8', TOKEN)
    get.assert_called_once()
    assert TOKEN not in str(error.value)
    response.raise_for_status.assert_not_called()


def test_other_http_failure_is_raised_before_json_parsing():
    response = Mock(status_code=500)
    response.raise_for_status.side_effect = requests.HTTPError('500 Server Error')
    with patch('pycomcigan.helpers.requests.get', return_value=response), pytest.raises(requests.HTTPError):
        get_response_encoding('http://example.test/data', 'UTF-8', TOKEN)


def test_search_and_timetable_use_token_from_same_page():
    protocol = parse_service_protocol(TOKEN_PAGE)
    schools = {'학교검색': [[5000, 'region', 'school', 123]]}
    search_response = SimpleNamespace(text=envelope(json.dumps(schools).encode(), key=KEY))
    with patch('pycomcigan.helpers.get_response_encoding', return_value=search_response) as get:
        assert school_search('school', protocol.endpoint, protocol)[0][3] == 123
    assert get.call_args.kwargs['request_token'] == TOKEN
    response = SimpleNamespace(text=envelope(b'{"ok":true}', key=KEY))
    for week in (0, 1):
        with patch('pycomcigan.timetable.get_response_encoding', return_value=response) as get:
            assert TimeTable._fetch_timetable_data(123, week, CODES, protocol) == {'ok': True}
        assert get.call_args.kwargs['request_token'] == TOKEN


@pytest.mark.parametrize('week', [0, 1])
def test_public_api_transmits_page_token_to_both_requests(week):
    data = {
        '지역명': '지역', '학년도': 2026, '시작일': '2026-11-02', '일과시간': [],
        '자료108': '2026-11-03', '자료119': ['', '교사'], '자료123': ['', '수학'],
        '자료158': [[], [[], [1, [1, 1001]]]],
        '자료167': [[], [[], [1, [1, 1001]]]], '담임': [[1, 0]],
    }
    schools = envelope(json.dumps({'학교검색': [[5000, '지역', '테스트고', 123]]}).encode(), key=KEY)
    responses = [Mock(status_code=200, text=TOKEN_PAGE), Mock(status_code=200, text=schools),
                 Mock(status_code=200, text=envelope(json.dumps(data).encode(), key=KEY))]
    with patch('pycomcigan.helpers.requests.get', side_effect=responses) as get:
        table = TimeTable('테스트고', week_num=week)
    assert table.school_code == 123
    assert table.timetable[1][1][1][0].subject == '수학'
    assert 'X-Hour-Token' not in get.call_args_list[0].kwargs['headers']
    assert [call.kwargs['headers']['X-Hour-Token'] for call in get.call_args_list[1:]] == [TOKEN, TOKEN]
    with patch('pycomcigan.helpers.requests.get', side_effect=responses[:2]) as get:
        assert get_school_code('테스트고')[0][3] == 123
    assert get.call_args.kwargs['headers']['X-Hour-Token'] == TOKEN
