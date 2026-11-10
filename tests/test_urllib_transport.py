"""Offline coverage for the standard-library HTTP transport."""
import io
import json
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from pycomcigan.helpers import (
    COMCIGAN_URL, HEADERS, KOR_ENC, get_comcigan_response_for_codes,
    get_response_encoding, school_search,
)


def response_with_bytes(body, status=200):
    response = Mock(status=status)
    response.read.return_value = body
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


@pytest.mark.parametrize('encoding,text', [('UTF-8', '한글'), ('cp949', '뷁')])
def test_success_decodes_body_and_closes_response(encoding, text):
    response = response_with_bytes(text.encode(encoding))
    headers = dict(HEADERS)
    with patch('pycomcigan.helpers.urlopen', return_value=response) as get:
        result = get_response_encoding('http://example.test/data', encoding)
    assert result.text == text
    assert result.status_code == 200
    request = get.call_args.args[0]
    assert request.full_url == 'http://example.test/data'
    assert request.get_method() == 'GET'
    assert request.get_header('User-agent') == HEADERS['User-Agent']
    assert HEADERS == headers
    response.__exit__.assert_called_once()


def test_service_page_uses_cp949_including_euc_kr_extension():
    response = response_with_bytes('뷁'.encode('cp949'))
    with patch('pycomcigan.helpers.urlopen', return_value=response) as get:
        assert get_comcigan_response_for_codes().text == '뷁'
    assert KOR_ENC == 'cp949'
    assert get.call_args.args[0].full_url == COMCIGAN_URL + '/st'


def test_invalid_bytes_are_replaced_like_requests_text():
    with patch('pycomcigan.helpers.urlopen', return_value=response_with_bytes(b'\xffok')):
        assert get_response_encoding('http://example.test', 'utf-8').text == '\ufffdok'


@pytest.mark.parametrize('status', [403, 404, 429, 500])
def test_http_errors_close_response_without_retry(status):
    body = io.BytesIO('오류'.encode('cp949'))
    error = HTTPError('http://example.test', status, 'error', {}, body)
    expected = RuntimeError if status in (403, 429) else HTTPError
    with patch('pycomcigan.helpers.urlopen', side_effect=error) as get:
        with pytest.raises(expected):
            get_response_encoding('http://example.test', 'cp949')
    assert body.closed
    get.assert_called_once()


@pytest.mark.parametrize('error', [URLError('DNS failure'), TimeoutError('timed out')])
def test_network_errors_propagate_without_retry(error):
    with patch('pycomcigan.helpers.urlopen', side_effect=error) as get:
        with pytest.raises(type(error)) as caught:
            get_response_encoding('http://example.test', 'utf-8')
    assert caught.value is error
    get.assert_called_once()


def test_read_failure_closes_response():
    response = response_with_bytes(b'')
    response.read.side_effect = OSError('connection interrupted')
    with patch('pycomcigan.helpers.urlopen', return_value=response):
        with pytest.raises(OSError, match='connection interrupted'):
            get_response_encoding('http://example.test', 'utf-8')
    response.__exit__.assert_called_once()


def test_school_search_uses_utf8_response_and_cp949_query():
    schools = [[1, '지역', '뷁고', 123]]
    body = (json.dumps({'학교검색': schools}, ensure_ascii=False) + '\x00').encode('utf-8')
    with patch('pycomcigan.helpers.urlopen', return_value=response_with_bytes(body)) as get:
        assert school_search('뷁', '/search?') == schools
    assert get.call_args.args[0].full_url == COMCIGAN_URL + '/search?%94%EE'
