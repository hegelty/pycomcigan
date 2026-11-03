import re
from typing import List

from .helpers import get_comcigan_response_for_codes, school_search
from .service_page import decode_service_page


def get_comcigan_code() -> str:
    """
    Fetch Comcigan service code from the main page.

    Returns:
        str: The extracted Comcigan service code
    """
    response = get_comcigan_response_for_codes()

    content = decode_service_page(response.text)
    match = re.search(r'\.(/\d+\?\d+l)', content)
    if match is None:
        raise RuntimeError(
            "Unable to parse Comcigan service endpoint; the service page structure may have changed"
        )
    return match.group(1)


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
