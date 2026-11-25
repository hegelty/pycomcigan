import base64
import json
from urllib.parse import unquote
from unittest.mock import patch

import pytest

from pycomcigan import TimeTable, get_school_code
from pycomcigan.service_protocol import parse_service_protocol
from test_encrypted_response import envelope
from test_request_transport import response_with_text
from test_service_protocol import KEY, PAGE


TOKEN = 'ab' * 32
TOKEN_LITERAL = f"window.__HourRequestToken='{TOKEN}';"
VERB = "var decoder = pageDecoder, requestVerb='POST';"
HEADER = ",headers:{'X-Hour-Token':window.__HourRequestToken || ''}"
SUFFIX = ",dataType:'text',success:success"
ORIGINAL_SCHOOL = "url:'./987654?'+encodeURIComponent(btoa('24680l'+encodeURIComponent(sc)+'_enc5'))"
ORIGINAL_TABLE = "url:'./987654?'+btoa(sc+sc2+'_'+da1+'_'+r+'_enc5')"
BODY_OPTIONS = "url:'./987654',method:requestVerb,contentType:'text/plain; charset=UTF-8',data:"
SCHOOL = BODY_OPTIONS + "encodeURIComponent(btoa(query+'_enc5'))"
TABLE = BODY_OPTIONS + "btoa(sc+sc2+'_'+da1+'_'+r+'_enc5')"
POST_PAGE = (
    '<script>' + VERB + TOKEN_LITERAL + PAGE.replace(
        'return $.ajax({\n' + ORIGINAL_SCHOOL,
        "var query='24680l'+encodeURIComponent(sc);return $.ajax({" + SCHOOL + HEADER + SUFFIX,
    ).replace(ORIGINAL_TABLE, TABLE + HEADER + SUFFIX) + '</script>'
)


@pytest.mark.parametrize('change,error', [
    (lambda p: p.replace(VERB, VERB + "requestVerb=computeMethod();"), 'request method'),
    (lambda p: p.replace(VERB, '').replace('</script>', '</script><script>' + VERB + '</script>'), 'request method'),
    (lambda p: p.replace(VERB, "if (x) {\n" + VERB + " }"), 'request method'),
    (lambda p: p.replace(VERB, VERB.replace("'POST'", "'GET'")), 'request method'),
    (lambda p: p.replace(TABLE, TABLE.replace('requestVerb', 'decoyVerb')), 'request method'),
    (lambda p: p.replace(TABLE, ORIGINAL_TABLE), 'protocols do not match'),
    (lambda p: p.replace(TABLE, TABLE + HEADER + SUFFIX + '});return $.ajax({' + TABLE),
     'protocols do not match'),
    (lambda p: p.replace(HEADER, '', 1).replace(TOKEN_LITERAL,
               TOKEN_LITERAL + "var decoy={headers:{'X-Hour-Token':window.__HourRequestToken || ''}};"),
     'token headers'),
    (lambda p: p.replace(HEADER, HEADER + ",headers:{}", 1), 'token headers'),
    (lambda p: p.replace(TOKEN_LITERAL, TOKEN_LITERAL * 2), 'token literal'),
])
def test_post_protocol_fails_closed(change, error):
    with pytest.raises(RuntimeError, match=error) as caught:
        parse_service_protocol(change(POST_PAGE))
    assert TOKEN not in str(caught.value)


def posted_responses():
    data = {
        '지역명': '지역', '학년도': 2026, '시작일': '2026-11-02', '일과시간': [],
        '자료108': '2026-11-03', '자료119': ['', '교사'], '자료123': ['', '수학'],
        '자료158': [[], [[], [1, [1, 1001]]]], '자료167': [[], [[], [1, [1, 1001]]]],
        '담임': [[1, 0]],
    }
    result = {'학교검색': [[5000, '지역', '테스트고', 123]]}
    responses = [response_with_text(POST_PAGE), response_with_text(envelope(json.dumps(result).encode(), key=KEY)),
                 response_with_text(envelope(json.dumps(data).encode(), key=KEY))]
    responses[0].read.return_value = POST_PAGE.encode('cp949')
    return responses


@pytest.mark.parametrize('week', [0, 1])
def test_public_apis_preserve_post_bodies_and_authenticated_results(week):
    responses = posted_responses()
    with patch('pycomcigan.helpers.urlopen', side_effect=responses) as get:
        table = TimeTable('테스트고', week_num=week)
    page, school, timetable = [call.args[0] for call in get.call_args_list]
    assert table.school_code == 123
    assert table.timetable[1][1][1][0].subject == '수학'
    assert page.get_method() == 'GET' and page.get_header('X-hour-token') is None
    for request in (school, timetable):
        assert request.get_method() == 'POST'
        assert request.full_url.endswith('/987654')
        assert request.get_header('Content-type') == 'text/plain; charset=UTF-8'
        assert request.get_header('X-hour-token') == TOKEN
    assert base64.b64decode(unquote(school.data.decode('ascii'))).decode().endswith('_enc5')
    assert '%' not in timetable.data.decode('ascii')
    assert base64.b64decode(timetable.data).decode().endswith(f'_123_0_{week + 1}_enc5')
    with patch('pycomcigan.helpers.urlopen', side_effect=responses[:2]):
        assert get_school_code('테스트고')[0][3] == 123


def test_timetable_rejects_unauthenticated_post_response_without_retrying():
    responses = posted_responses()
    responses[2] = response_with_text('{"untrusted": true}')
    with patch('pycomcigan.helpers.urlopen', side_effect=responses) as get:
        with pytest.raises(RuntimeError, match='Encrypted response protocol mismatch'):
            TimeTable('테스트고')
    assert get.call_count == 3
