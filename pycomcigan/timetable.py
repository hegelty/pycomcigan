import base64
import re
from typing import List, Optional, Tuple

from .helpers import (
    COMCIGAN_URL,
    get_comcigan_response_for_codes,
    get_response_encoding,
    school_search,
)
from .service_page import decode_service_page
from .service_protocol import parse_service_protocol
from .encrypted_response import decode_response
from .encoded_fields import DATA_FIELD, _DECODER, decode_timetable_fields


def _find_timetable_field_codes(content):
    """Read field names without executing page scripts."""
    wrapper = r'(?:[\w$]+\s*\(\s*)?'
    patterns = {
        'teacher data': rf'\b성명\s*=\s*{wrapper}자료\.({DATA_FIELD})\s*\[\s*th\s*\]',
        'subject data': rf'자료\.({DATA_FIELD})\s*\[\s*sb\s*\]',
        'update data': rf'\bda1\s*=\s*{wrapper}H시간표\.({DATA_FIELD})',
        'current timetable': rf'\b일일자료\s*=\s*Q자료\(\s*자료\.({DATA_FIELD})',
        'original timetable': rf'\b원자료\s*=\s*Q자료\(\s*자료\.({DATA_FIELD})',
    }
    matches = {name: set(re.findall(pattern, content)) for name, pattern in patterns.items()}

    # The cached-update branch supplies the update field to the timetable
    # call. Require the recognized text decoder, not an arbitrary invocation.
    if not matches['update data']:
        decoders = {m['name'] for m in _DECODER.finditer(content)}
        if len(decoders) == 1:
            decoder = re.escape(decoders.pop())
            update = re.compile(
                rf'\bda1\s*=\s*{decoder}\(\s*[\w$]+\.(?P<field>{DATA_FIELD})\s*\)'
                r"""\s*\|\|\s*(?P<quote>['"])0(?P=quote)\s*;\s*\}\s*"""
                r'[\w$]+\s*\(\s*sc\s*,\s*sc2\s*,\s*da1\s*,\s*r\s*,\s*function\s*\(',
            )
            matches['update data'].update(m['field'] for m in update.finditer(content))

    # In modern renderers, the displayed and original period codes are
    # paired as the first and second arguments of the change-display helper.
    # Other arrays, including the room array, don't satisfy this data flow.
    if not matches['current timetable'] or not matches['original timetable']:
        indexes = r'\[\s*학년\s*\]\s*\[\s*반\s*\]\s*\[\s*요일\s*\]\s*\[\s*교시\s*\]'
        period = rf'\(\s*자료\.(?P<{{field}}>{DATA_FIELD})\s*{indexes}\s*\)'
        original_period = period.format(field='original_field')
        current_period = period.format(field='current_field')
        paired = re.compile(
            rf'(?<![\w$.])(?P<old>[\w$]+)\s*=\s*(?P<decode>[\w$]+){original_period}\s*;\s*'
            rf'(?P<new>[\w$]+)\s*=\s*(?P=decode){current_period}\s*;'
            r'(?:(?!\bfunction\b|(?<![\w$.])(?:(?P=old)|(?P=new))\s*=(?!=)).){0,2000}?'
            r'(?<![\w$.])baSplit\(\s*(?P=new)\s*,\s*(?P=old)\s*,\s*자료\.변경알림\s*\)',
            re.S,
        )
        pairs = {
            (m['current_field'], m['original_field'])
            for m in paired.finditer(content)
            if m['old'] != m['new']
        }
        if len(pairs) == 1:
            current, original = pairs.pop()
            matches['current timetable'].add(current)
            matches['original timetable'].add(original)

    codes = []
    for name, values in matches.items():
        if len(values) != 1:
            raise RuntimeError(f'Unable to parse Comcigan {name}; the service page structure may have changed')
        codes.append(values.pop())
    if codes[3] == codes[4]:
        raise RuntimeError('Unable to distinguish Comcigan current and original timetables')
    return tuple(codes)


class Lecture:
    """Represents a single lecture with period, subject, and teacher information."""

    def __init__(self, period: int, subject: str, teacher: str):
        self.period = period
        self.subject = subject
        self.teacher = teacher

    def __str__(self) -> str:
        return f"{self.period}교시: {self.subject}({self.teacher})"

    def __repr__(self) -> str:
        return self.__str__()


class TimeTableData:
    """Represents timetable data including replacement information."""

    def __init__(self, period: int, subject: str, teacher: str, replaced: bool, original: Optional[Lecture]):
        self.period = period
        self.subject = subject
        self.teacher = teacher
        self.replaced = replaced
        self.original = original

    def __str__(self) -> str:
        replacement_indicator = ' (대체)' if self.replaced else ''
        return f"{self.period}교시: {self.subject}({self.teacher}){replacement_indicator}"

    def __repr__(self) -> str:
        return self.__str__()


def _decode_timetable_response(text: str, codes: Tuple, protocol=None) -> dict:
    """Authenticate and interpret already received response text without I/O."""
    data = decode_response(text, protocol.key if protocol else None,
                           protocol.version if protocol else 'enc5')
    return decode_timetable_fields(data, codes, protocol)


def _validate_raw_timetable(grid):
    """Check counted source arrays before the parser fills missing periods."""
    if not isinstance(grid, list):
        raise ValueError('invalid timetable array')
    classes = {}
    for grade_index, grade in enumerate(grid[1:], 1):
        if not isinstance(grade, list):
            raise ValueError('invalid grade array')
        for class_index, classroom in enumerate(grade[1:], 1):
            if (not isinstance(classroom, list) or not classroom
                    or type(classroom[0]) is not int or classroom[0] <= 0
                    or len(classroom) <= classroom[0]):
                raise ValueError('invalid class day structure')
            classes[grade_index, class_index] = classroom[0]
            for day in classroom[1:classroom[0] + 1]:
                if (not isinstance(day, list) or not day
                        or type(day[0]) is not int or day[0] < 0
                        or len(day) <= day[0]):
                    raise ValueError('invalid day period structure')
    if not classes:
        raise ValueError('empty timetable structure')
    return classes


def _build_timetable(data: dict, teacher_list: List[str], subject_list: List[str], code4: str, code5: str,
                     subject_divisor: int, change_notifications: bool) -> \
        List[List[List[List[TimeTableData]]]]:
    """Build the complete timetable data structure."""
    original_timetable = data[code5]
    current_timetable = data[code4]
    timetable = []

    for grade_idx, grade_data in enumerate(current_timetable):
        if grade_idx == 0:
            timetable.append([])
            continue

        grade_timetable = [[]]  # Start with empty class 0

        for class_idx, class_data in enumerate(grade_data):
            if class_idx == 0:
                continue

            class_timetable = _build_class_timetable(
                grade_idx, class_idx, class_data, original_timetable,
                teacher_list, subject_list, subject_divisor,
                change_notifications
            )
            grade_timetable.append(class_timetable)

        timetable.append(grade_timetable)

    return timetable


def _build_class_timetable(grade_idx: int, class_idx: int, class_data: List,
                           original_timetable: List, teacher_list: List[str],
                           subject_list: List[str], subject_divisor: int,
                           change_notifications: bool) -> List[List[TimeTableData]]:
    """Build timetable for a specific class with guaranteed 8 periods per day."""
    class_timetable = [[]]  # Start with empty day 0
    original_class = original_timetable[grade_idx][class_idx]

    for day in range(1, original_class[0] + 1):
        day_timetable = []

        # Ensure we always have 8 periods per day
        max_periods = max(
            original_class[day][0] if day < len(original_class) else 0,
            class_data[day][0] if day < len(class_data) else 0,
            8  # Force minimum 8 periods
        )

        for period in range(1, max_periods + 1):
            period_data = _create_period_data(
                period, day, class_data, original_class,
                teacher_list, subject_list, subject_divisor,
                change_notifications
            )
            day_timetable.append(period_data)

        class_timetable.append(day_timetable)

    return class_timetable


def _create_period_data(period: int, day: int, class_data: List,
                        original_class: List, teacher_list: List[str],
                        subject_list: List[str], subject_divisor: int = 100,
                        change_notifications: bool = False) -> TimeTableData:
    """Create TimeTableData for a specific period."""
    # Get original period data (handle bounds checking)
    original_period_raw = 0
    if (day < len(original_class) and
            len(original_class[day]) > 0 and
            period <= original_class[day][0] and
            period < len(original_class[day])):
        original_period_raw = original_class[day][period]

    # Get current period data (handle bounds checking)
    current_period_raw = 0
    if (day < len(class_data) and
            len(class_data[day]) > 0 and
            period <= class_data[day][0] and
            period < len(class_data[day])):
        current_period_raw = class_data[day][period]

    original_period, original_subject_idx, original_teacher_idx = \
        _decode_period_code(original_period_raw, subject_divisor)
    current_period, subject_idx, teacher_idx = \
        _decode_period_code(current_period_raw, subject_divisor)

    marked_as_replaced = (
        isinstance(current_period_raw, str) and
        current_period_raw.startswith(">")
    )
    replaced = (
        marked_as_replaced if change_notifications
        else current_period != original_period
    )

    # Create original lecture if replacement occurred
    original_lecture = None
    if replaced and original_period != 0:
        original_lecture = Lecture(
            period=period,
            subject=subject_list[original_subject_idx]
            if original_subject_idx < len(subject_list) else "",
            teacher=teacher_list[original_teacher_idx]
            if original_teacher_idx < len(teacher_list) else ""
        )

    # Get subject and teacher names with bounds checking
    subject_name = ""
    teacher_name = ""

    if current_period != 0:
        if subject_idx < len(subject_list):
            subject_name = subject_list[subject_idx]
        if teacher_idx < len(teacher_list):
            teacher_name = teacher_list[teacher_idx]

    return TimeTableData(
        period=period,
        subject=subject_name,
        teacher=teacher_name,
        replaced=replaced,
        original=original_lecture
    )


def _decode_period_code(value, subject_divisor: int) -> Tuple[int, int, int]:
    """Decode Comcigan's packed subject/teacher value.

    Current timetable values can be strings prefixed with ``>`` to mark a
    changed lecture. The final three digits are the teacher index; the
    preceding digits contain the subject index and optional time-group data.
    """
    if value in (None, "", 0, "0"):
        return 0, 0, 0

    value_text = str(value)
    if value_text.startswith(">"):
        value_text = value_text[1:]

    try:
        packed_value = int(value_text)
    except ValueError:
        return 0, 0, 0

    subject_code, teacher_idx = divmod(packed_value, 1000)
    subject_idx = subject_code % subject_divisor
    return packed_value, subject_idx, teacher_idx


def _format_teacher_name(name) -> str:
    """Apply the same masked-name formatting as Comcigan's Q성명."""
    if not isinstance(name, str):
        return ""

    contains_internal_mask = (
        "*" in name and
        not name.startswith("*") and
        not name.endswith("*")
    )
    is_two_character_mask = len(name) == 2 and name[1] == "*"
    if contains_internal_mask or is_two_character_mask:
        return name

    return name.replace("*", "", 1)


def _process_homeroom_teachers(homeroom_data: List[List[int]], teacher_list: List[str]) -> List[List[str]]:
    """Process homeroom teacher data and convert to teacher names."""
    processed_homeroom = []

    for grade_teachers in homeroom_data:
        grade_homeroom = []
        for teacher_code in grade_teachers:
            if teacher_code in [0, 255]:
                break
            if teacher_code < len(teacher_list):
                grade_homeroom.append(teacher_list[teacher_code])
        processed_homeroom.append(grade_homeroom)

    return processed_homeroom

def _parse_timetable_data(data, codes):
    """Interpret decoded fields as the existing timetable models and metadata.

    Raw field names and counted arrays stay within the interpretation layer.
    Validate source structure before padding legitimate empty periods.
    """
    _, _, teacher_code, subject_code, update_code, current_code, original_code = codes
    current = _validate_raw_timetable(data[current_code])
    original = _validate_raw_timetable(data[original_code])
    if current != original:
        raise ValueError('inconsistent timetable class or day structure')

    teachers = [_format_teacher_name(name) for name in data[teacher_code]]
    subjects = list(data[subject_code])
    subjects[0] = ""
    return {
        "local_name": data["지역명"],
        "school_year": data["학년도"],
        "start_date": data["시작일"],
        "day_time": data["일과시간"],
        "update_date": data[update_code],
        "timetable": _build_timetable(
            data, teachers, subjects, current_code, original_code,
            int(data.get("분리", 100)), str(data.get("변경알림")) == "1"
        ),
        "_homeroom_teacher": _process_homeroom_teachers(data["담임"], teachers),
    }


class TimeTable:
    """Main class for fetching and storing school timetable information."""

    # Class constants for weekdays
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5

    def __init__(self, school_name: str, local_code: int = 0, school_code: int = 0, week_num: int = 0):
        """
        Initialize TimeTable with school information.

        Args:
            school_name (str): Name of the school
            local_code (int, optional): Education office code
            school_code (int, optional): School code
            week_num (int): Week number (0 for current week, 1 for next week)

        Raises:
            ValueError: If week_num is not 0 or 1, or if codes are not integers
            RuntimeError: If multiple schools found or school not found
        """
        local_code, school_code = self._validate_inputs(week_num, local_code, school_code)

        # Fetch Comcigan service codes
        content = decode_service_page(get_comcigan_response_for_codes().text)
        protocol = parse_service_protocol(content)
        comcigan_codes = self._get_comcigan_codes(content)

        # Resolve school information
        resolved_local_code, resolved_school_name, resolved_school_code = self._resolve_school(
            school_name, local_code, school_code, comcigan_codes[0], protocol
        )

        # Fetch timetable data
        timetable_data = self._fetch_timetable_data(
            resolved_school_code, week_num, comcigan_codes, protocol
        )

        # Initialize instance variables
        self._initialize_from_data(
            timetable_data, resolved_local_code, resolved_school_name, resolved_school_code, comcigan_codes
        )

    @staticmethod
    def _validate_inputs(week_num: int, local_code: int, school_code: int) -> Tuple[int, int]:
        """Validate input parameters."""
        if week_num not in [0, 1]:
            raise ValueError('week_num must be 0 or 1')

        try:
            return int(local_code), int(school_code)
        except (ValueError, TypeError):
            raise ValueError('local_code and school_code must be integers')

    @staticmethod
    def _get_comcigan_codes(content=None) -> Tuple[str, str, str, str, str, str, str]:
        """Fetch all necessary service codes from Comcigan."""
        if content is None:
            content = decode_service_page(get_comcigan_response_for_codes().text)

        # Comcigan periodically renames the JSON fields embedded in this page.
        # Read the field names at their use sites, including the older 자료NNN
        # names and optional text decoder calls.
        protocol = parse_service_protocol(content)
        prefix = protocol.timetable_prefix
        if prefix is None:
            legacy_call = re.search(r"\bsc_data\(\s*'([0-9]+)_", content)
            if legacy_call is None or (protocol.version and protocol.version.isdecimal()):
                raise RuntimeError('Unable to parse Comcigan timetable request prefix')
            prefix = legacy_call.group(1)
        return (protocol.endpoint, prefix, *_find_timetable_field_codes(content))

    def _resolve_school(self, school_name: str, local_code: int, school_code: int, comcigan_code: str, protocol=None) -> Tuple[
        int, str, int]:
        """Resolve school information from search results."""
        search_results = [
            row for row in school_search(school_name, comcigan_code, protocol)
            if (not school_code or row[3] == school_code)
            and (not local_code or row[0] == local_code)
        ]
        if not search_results:
            raise RuntimeError('School not found')
        if len(search_results) > 1:
            raise RuntimeError('Multiple schools found - please specify school_code or local_code')
        result = search_results[0]
        return result[0], result[2], result[3]

    @staticmethod
    def _request_timetable(school_code: int, week_num: int, comcigan_codes: Tuple, protocol=None) -> str:
        """Fetch response text; do not interpret the timetable here."""
        comcigan_code, code0, *_ = comcigan_codes

        # Encode request parameters
        suffix = f'_{protocol.version}' if protocol and protocol.version else ''
        encoded_params = base64.b64encode(f"{code0}_{school_code}_0_{week_num + 1}{suffix}".encode('utf-8'))
        endpoint = comcigan_code.split('?', 1)[0]
        request_url = f'{COMCIGAN_URL}{endpoint}?{encoded_params.decode("ascii")}'

        if protocol is not None and getattr(protocol, 'post_body', False):
            response = get_response_encoding(f'{COMCIGAN_URL}{endpoint}', 'UTF-8',
                                             request_token=protocol.request_token, body=encoded_params)
        elif protocol is not None and protocol.request_token is not None:
            response = get_response_encoding(request_url, 'UTF-8', request_token=protocol.request_token)
        else:
            response = get_response_encoding(request_url, 'UTF-8')

        return response.text

    @staticmethod
    def _fetch_timetable_data(school_code: int, week_num: int, comcigan_codes: Tuple, protocol=None) -> dict:
        """Fetch and decode the response, retaining the existing internal contract."""
        text = TimeTable._request_timetable(school_code, week_num, comcigan_codes, protocol)
        return _decode_timetable_response(text, comcigan_codes, protocol)

    @classmethod
    def _from_data(cls, data, local_code, school_name, school_code, codes):
        """Internal no-I/O construction path shared with the health checker."""
        table = cls.__new__(cls)
        table._initialize_from_data(data, local_code, school_name, school_code, codes)
        return table

    @classmethod
    def _from_response(cls, text, local_code, school_name, school_code, codes, protocol=None):
        """Interpret already received response text without requesting a school or timetable."""
        return cls._from_data(_decode_timetable_response(text, codes, protocol),
                              local_code, school_name, school_code, codes)

    def _initialize_from_data(self, data: dict, local_code: int, school_name: str, school_code: int,
                              comcigan_codes: Tuple) -> None:
        """Assign public metadata and interpreted timetable models."""
        parsed = _parse_timetable_data(data, comcigan_codes)
        self.school_code = school_code
        self.school_name = school_name
        self.local_code = local_code
        self.__dict__.update(parsed)

    # Retain existing private helpers used by the offline regression tests.
    _build_timetable = staticmethod(_build_timetable)
    _build_class_timetable = staticmethod(_build_class_timetable)
    _create_period_data = staticmethod(_create_period_data)
    _decode_period_code = staticmethod(_decode_period_code)
    _format_teacher_name = staticmethod(_format_teacher_name)
    _process_homeroom_teachers = staticmethod(_process_homeroom_teachers)

    def homeroom(self, grade: int, cls: int) -> str:
        """
        Get homeroom teacher for specific grade and class.

        Args:
            grade (int): Grade number (1-indexed)
            cls (int): Class number (1-indexed)

        Returns:
            str: Name of the homeroom teacher
        """
        if (grade - 1 < len(self._homeroom_teacher) and
                cls - 1 < len(self._homeroom_teacher[grade - 1])):
            return self._homeroom_teacher[grade - 1][cls - 1]
        return ""

    def __str__(self) -> str:
        return (f"School Code: {self.school_code}\n"
                f"School Name: {self.school_name}\n"
                f"Region Code: {self.local_code}\n"
                f"Region Name: {self.local_name}\n"
                f"School Year: {self.school_year}\n"
                f"Start Date: {self.start_date}\n"
                f"Day Time: {self.day_time}\n"
                f"Update Date: {self.update_date}")

    def __repr__(self) -> str:
        return self.__str__()
