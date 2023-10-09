import requests
import re
import json
from urllib import parse

comcigan_url = 'http://comci.net:4082'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
}


def get_code():
    resp = requests.get(comcigan_url + '/st', headers=headers)
    resp.encoding = 'euc-kr'
    resp = resp.text
    comcigan_code = re.findall('\\.\\/[0-9]+\\?[0-9]+l', resp)[0][1:]
    return comcigan_code


def get_school_code(school_name: str):
    """

    :param school_name:
    :return: [
            [지역코드, 지역명, 학교명, 학교코드],
        ...
        ]
    """

    comcigan_code = get_code()
    resp = requests.get(comcigan_url + comcigan_code + parse.quote(school_name, encoding='euc-kr'))
    resp.encoding = 'UTF-8'
    resp = json.loads(resp.text.strip(chr(0)))

    return resp["학교검색"]