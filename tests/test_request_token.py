import pytest

from pycomcigan.service_protocol import ServiceProtocol, parse_service_protocol
from test_service_protocol import PAGE


TOKEN = 'AB12' * 16
HEADER = ",headers:{'X-Hour-Token':window.__HourRequestToken || ''}"
TOKEN_PAGE = "<script>window.__HourRequestToken='" + TOKEN + "';</script>" + PAGE.replace(
    '});}', HEADER + '});}'
)


def test_legacy_page_has_no_token():
    assert parse_service_protocol(PAGE).request_token is None


def test_token_page_parses_literal_without_exposing_it_in_repr():
    protocol = parse_service_protocol(TOKEN_PAGE)
    assert protocol.request_token == TOKEN
    assert TOKEN not in repr(protocol)
    assert ServiceProtocol('/endpoint').request_token is None


@pytest.mark.parametrize('expression', ["''", '42', "'xyz'", "'AB' + evil()", 'evil()'])
def test_missing_or_invalid_token_is_rejected(expression):
    page = TOKEN_PAGE.replace("'" + TOKEN + "'", expression)
    with pytest.raises(RuntimeError, match='token literal') as error:
        parse_service_protocol(page)
    assert expression not in str(error.value)


def test_missing_declaration_is_rejected():
    page = TOKEN_PAGE.replace("window.__HourRequestToken='" + TOKEN + "';", '')
    with pytest.raises(RuntimeError, match='token literal'):
        parse_service_protocol(page)


@pytest.mark.parametrize('index', [0, 1])
def test_header_required_in_both_request_functions(index):
    position = TOKEN_PAGE.find(HEADER) if index == 0 else TOKEN_PAGE.rfind(HEADER)
    page = TOKEN_PAGE[:position] + TOKEN_PAGE[position + len(HEADER):]
    page += "function unrelated(){return $.ajax({headers:{'X-Hour-Token':window.__HourRequestToken || ''}});}"
    with pytest.raises(RuntimeError, match='token headers'):
        parse_service_protocol(page)


def test_wrong_header_value_is_rejected():
    page = TOKEN_PAGE.replace('window.__HourRequestToken || \'\'', '123', 1)
    with pytest.raises(RuntimeError, match='token headers'):
        parse_service_protocol(page)
