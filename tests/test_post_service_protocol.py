import pytest

from pycomcigan.service_protocol import parse_service_protocol
from test_service_protocol import PAGE


POST_PAGE = "var Qa='POST';\n" + PAGE.replace(
    "return $.ajax({\nurl:'./987654?'+encodeURIComponent(btoa('24680l'+encodeURIComponent(sc)+'_enc5'))",
    "var s1='24680l'+encodeURIComponent(sc);return $.ajax({\n"
    "url:'./987654',method:Qa,contentType:'text/plain; charset=UTF-8',data:encodeURIComponent(btoa(s1+'_enc5'))",
).replace(
    "url:'./987654?'+btoa(sc+sc2+'_'+da1+'_'+r+'_enc5')",
    "url:'./987654',method:Qa,contentType:'text/plain; charset=UTF-8',data:btoa(sc+sc2+'_'+da1+'_'+r+'_enc5')",
)


def test_post_protocol_parses_school_and_timetable_requests():
    protocol = parse_service_protocol(POST_PAGE)
    assert protocol.method == 'POST'
    assert protocol.endpoint == '/987654?24680l'
    assert protocol.version == 'enc5'


def test_post_protocol_validates_both_token_headers():
    token = 'ab12' * 16
    header = ",headers:{'X-Hour-Token':window.__HourRequestToken || ''}"
    page = "window.__HourRequestToken='" + token + "';" + POST_PAGE.replace('});}', header + '});}')
    protocol = parse_service_protocol(page)
    assert protocol.request_token == token
    assert token not in repr(protocol)
    with pytest.raises(RuntimeError, match='token headers'):
        parse_service_protocol(page.replace(header, '', 1))


@pytest.mark.parametrize('page', [
    POST_PAGE.replace("var Qa='POST'", "var Qa='GET'"),
    POST_PAGE.replace("data:btoa(sc+sc2", "method:Other,data:btoa(sc+sc2"),
    POST_PAGE.replace("url:'./987654',method:Qa", "url:'./111111',method:Qa", 1),
])
def test_post_protocol_rejects_unverified_methods(page):
    with pytest.raises(RuntimeError):
        parse_service_protocol(page)
