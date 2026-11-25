import base64
from unittest.mock import patch
from urllib.parse import quote, unquote

import pytest

from pycomcigan.helpers import school_search
from pycomcigan.service_protocol import parse_service_protocol
from pycomcigan.timetable import TimeTable
from test_post_service_protocol import POST_PAGE
from test_request_transport import response_with_text
from test_service_protocol import CODES


@pytest.mark.parametrize('week', [0, 1])
def test_post_requests_keep_token_and_encode_each_body(week):
    token = 'ab12' * 16
    header = ",headers:{'X-Hour-Token':window.__HourRequestToken || ''}"
    page = "window.__HourRequestToken='" + token + "';" + POST_PAGE.replace('});}', header + '});}')
    protocol = parse_service_protocol(page)
    response = response_with_text('{}')
    with patch('pycomcigan.helpers.urlopen', return_value=response) as request, \
         patch('pycomcigan.helpers.decode_response', return_value={'학교검색': []}):
        assert school_search('학교', protocol.endpoint, protocol) == []
    school = request.call_args.args[0]
    assert school.get_method() == 'POST'
    assert school.full_url == 'http://comci.net:4082/987654'
    assert school.get_header('Content-type') == 'text/plain; charset=UTF-8'
    assert school.get_header('X-hour-token') == token
    decoded = base64.b64decode(unquote(school.data.decode('ascii'))).decode('ascii')
    assert decoded == '24680l' + quote('학교', safe="~()*!.'-", encoding='utf-8') + '_enc5'

    with patch('pycomcigan.helpers.urlopen', return_value=response) as request, \
         patch('pycomcigan.timetable.decode_response', return_value={'ok': True}):
        assert TimeTable._fetch_timetable_data(123, week, CODES, protocol) == {'ok': True}
    timetable = request.call_args.args[0]
    assert timetable.get_method() == 'POST'
    assert timetable.full_url == 'http://comci.net:4082' + CODES[0].split('?', 1)[0]
    assert timetable.get_header('Content-type') == 'text/plain; charset=UTF-8'
    assert timetable.get_header('X-hour-token') == token
    assert base64.b64decode(timetable.data).decode('ascii') == f'{CODES[1]}_123_0_{week + 1}_enc5'
