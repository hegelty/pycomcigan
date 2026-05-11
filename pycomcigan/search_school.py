import re
from typing import List

from .helpers import school_search, get_comcigan_response_for_codes


def get_comcigan_code() -> str:
    """
    Fetch Comcigan service code from the main page.

    Returns:
        str: The extracted Comcigan service code
    """
    response = get_comcigan_response_for_codes()

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
    return school_search(school_name, get_comcigan_code())
