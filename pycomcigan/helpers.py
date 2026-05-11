import requests
from urllib import parse
import json
from typing import List

# Constants for Comcigan API
COMCIGAN_URL = 'http://comci.net:4082'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
}

"""
constant for hangul encoding
Note: Using 'cp949' and not 'euc-kr'
See: https://encoding.spec.whatwg.org/#legacy-multi-byte-korean-encodings
* Internet webpages use euc-kr == Windows Codepage 949 / UHC / 확장 완성형
* Python uses euc-kr == IBM Code Page 970 / 완성
"""
KOR_ENC = 'cp949'

def get_response_encoding(url: str, encoding: str) -> requests.Response:
    response = requests.get(url, headers=HEADERS)
    response.encoding = encoding
    return response


def get_comcigan_response_for_codes() -> requests.Response:
    """Fetch all necessary service page from Comcigan for response codes."""
    return get_response_encoding(f"{COMCIGAN_URL}/st", KOR_ENC)


def encode_school_name(school_name: str) -> str:
    """
    Convert school name to its bytes encoded in CP949 (aka whatwg standard's 'EUC-KR')
    """
    return parse.quote(school_name, encoding=KOR_ENC)


def school_search(school_name: str, comcigan_code: str) -> List[List]:
    """
    Search for schools by name and return their information.

    Args:
        school_name (str): Name of the school to search for
        comcigan_code (str): Previously extracted Comcigan service code

    Returns:
        List[List]: List of school information in format:
                   [[region_code, region_name, school_name, school_code], ...]
    """
    school_name_encoded = encode_school_name(school_name)
    search_url = f"{COMCIGAN_URL}{comcigan_code}{school_name_encoded}"
    response = get_response_encoding(search_url, 'UTF-8')

    parsed_data = json.loads(response.text.strip(chr(0)))
    return parsed_data["학교검색"]
