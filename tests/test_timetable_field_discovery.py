import base64
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad

from pycomcigan import TimeTable
from pycomcigan.encrypted_response import decode_response
from test_encoded_fields import DECODER, FIXTURES, response
from test_post_page_transport import POST_PAGE, TOKEN
from test_service_protocol import KEY


UPDATE = """function load(sc,sc2,r,nw) {
var da1='0'; if (nw == '0') { da1=decodeText(cached.xUpdated) || '0'; }
QAjaxTimetable(sc, sc2, da1, r, function(data) {});
}"""
RENDERER = """function render() {
oldCode=periodCode(자료.xOriginal[학년][반][요일][교시]);
newCode=periodCode(자료.xCurrent[학년][반][요일][교시]);
var room=자료.xRoom[학년][반][요일][교시];
var other=notThePeriod(자료.decoy[학년][반][요일][교시]);
var value=baSplit(newCode, oldCode, 자료.변경알림);
}"""
PAGE = (
    POST_PAGE.replace('da1=H시간표.자료108;', '')
    .replace('일일자료=Q자료(자료.자료158[학년][반][요일][교시]);', '')
    .replace('원자료=Q자료(자료.자료167[학년][반][요일][교시]);', '')
    .replace('</script>', UPDATE + RENDERER + DECODER.replace('QnmsbChange', 'decodeText') + '</script>')
)


@pytest.mark.parametrize('week', [0, 1])
def test_posts_authenticated_timetable_with_correct_modern_field_roles(week):
    t = decode_response(FIXTURES['timetable'], KEY, 'enc5')
    t['xUpdated'] = t.pop('자료108')
    t['xCurrent'] = t.pop('자료158')
    t['xOriginal'] = t.pop('자료167')
    t['xOriginal'][1][1][1][1] = 0
    iv = bytes(range(16))
    ciphertext = AES.new(KEY, AES.MODE_CBC, iv).encrypt(pad(json.dumps(t).encode(), 16))
    prefix = b':'.join([b'enc5', base64.b64encode(iv), base64.b64encode(ciphertext)])
    tag = hmac.new(hashlib.sha256(KEY).digest(), prefix, hashlib.sha256).digest()
    timetable = (prefix + b':' + base64.b64encode(tag)).decode('ascii')
    with patch('pycomcigan.helpers.urlopen', side_effect=[
        response(PAGE, 'cp949'), response(FIXTURES['search']), response(timetable),
    ]) as request:
        table = TimeTable('테스트고', school_code=123, week_num=week)
    assert table.update_date == '2026-11-11 12:34:56'
    assert table.timetable[1][1][1][0].subject == '수학'
    assert TimeTable._get_comcigan_codes(PAGE)[4:] == ('xUpdated', 'xCurrent', 'xOriginal')
    assert [c.args[0].get_header('X-hour-token') for c in request.call_args_list] == [None, TOKEN, TOKEN]
    assert [c.args[0].get_method() for c in request.call_args_list] == ['GET', 'POST', 'POST']


@pytest.mark.parametrize('changes,message', [
    (lambda p: p.replace(UPDATE, UPDATE.replace('decodeText(cached.xUpdated)', 'other(cached.xUpdated)')), 'update data'),
    (lambda p: p.replace(UPDATE, UPDATE + UPDATE.replace('load(', 'otherLoad(').replace('xUpdated', 'xDecoy')), 'update data'),
    (lambda p: p.replace(RENDERER, RENDERER.replace('baSplit(newCode, oldCode', 'baSplit(oldCode, newCode')), 'current timetable'),
    (lambda p: p.replace(RENDERER, RENDERER.replace('var value=', 'newCode=anotherValue; var value=')), 'current timetable'),
    (lambda p: p.replace(RENDERER, RENDERER + RENDERER.replace('render(', 'renderOther(').replace('xOriginal', 'xDecoy')), 'current timetable'),
    (lambda p: p.replace(RENDERER, RENDERER.replace('xOriginal', 'xCurrent')), 'distinguish'),
])
def test_ambiguous_or_unlinked_fields_fail_before_post(changes, message):
    with patch('pycomcigan.helpers.urlopen', return_value=response(changes(PAGE), 'cp949')) as request:
        with pytest.raises(RuntimeError, match=message):
            TimeTable('테스트고', school_code=123)
    request.assert_called_once()
    assert request.call_args.args[0].get_method() == 'GET'
