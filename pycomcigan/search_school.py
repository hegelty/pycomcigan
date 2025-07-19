import json
import re
from typing import List
from urllib import parse

import requests

# Constants for Comcigan API
COMCIGAN_URL = 'http://comci.net:4082'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
}


def get_comcigan_code() -> str:
    """
    Fetch Comcigan service code from the main page.

    Returns:
        str: The extracted Comcigan service code
    """
    response = requests.get(COMCIGAN_URL + '/st', headers=HEADERS)
    response.encoding = 'euc-kr'

    return re.findall('\\.\\/[0-9]+\\?[0-9]+l', response.text)[0][1:]


def get_school_code(school_name: str) -> List[List]:
    """
    Search for schools by name and return their information.

    Args:
        school_name (str): Name of the school to search for

    Returns:
        List[List]: List of school information in format:
                   [[region_code, region_name, school_name, school_code], ...]
    """
    comcigan_code = get_comcigan_code()

    # Build search URL with encoded school name
    search_url = COMCIGAN_URL + comcigan_code + parse.quote(school_name, encoding='euc-kr')

    response = requests.get(search_url, headers=HEADERS)
    response.encoding = 'UTF-8'

    # Parse response and remove null characters
    parsed_data = json.loads(response.text.strip(chr(0)))

    return parsed_data["학교검색"]
