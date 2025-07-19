import base64
import json
import re
from typing import List, Optional, Tuple
from urllib import parse

import requests

# Constants for Comcigan API
COMCIGAN_URL = 'http://comci.net:4082'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
}


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
        self._validate_inputs(week_num, local_code, school_code)

        # Fetch Comcigan service codes
        comcigan_codes = self._get_comcigan_codes()

        # Resolve school information
        resolved_local_code, resolved_school_name, resolved_school_code = self._resolve_school(
            school_name, local_code, school_code, comcigan_codes[0]
        )

        # Fetch timetable data
        timetable_data = self._fetch_timetable_data(
            resolved_school_code, week_num, comcigan_codes
        )

        # Initialize instance variables
        self._initialize_from_data(
            timetable_data, resolved_local_code, resolved_school_name, resolved_school_code, comcigan_codes
        )

    @staticmethod
    def _validate_inputs(week_num: int, local_code: int, school_code: int) -> None:
        """Validate input parameters."""
        if week_num not in [0, 1]:
            raise ValueError('week_num must be 0 or 1')

        try:
            int(local_code)
            int(school_code)
        except (ValueError, TypeError):
            raise ValueError('local_code and school_code must be integers')

    @staticmethod
    def _get_comcigan_codes() -> Tuple[str, str, str, str, str, str, str]:
        """Fetch all necessary service codes from Comcigan."""
        response = requests.get(COMCIGAN_URL + '/st', headers=HEADERS)
        response.encoding = 'euc-kr'
        content = response.text

        # Extract various codes using regex patterns
        patterns = {
            'comcigan_code': '\\.\\/[0-9]+\\?[0-9]+l',
            'code0': "sc_data\\(\'[0-9]+_",
            'code1': '성명=자료.자료[0-9]+',
            'code2': '자료.자료[0-9]+\\[sb\\]',
            'code3': '=H시간표.자료[0-9]+',
            'code4': '일일자료=Q자료\\(자료\\.자료[0-9]+',
            'code5': '원자료=Q자료\\(자료\\.자료[0-9]+'
        }

        comcigan_code = re.findall(patterns['comcigan_code'], content)[0][1:]
        code0 = re.findall(patterns['code0'], content)[0][9:-1]
        code1 = re.findall(patterns['code1'], content)[0][8:]
        code2 = re.findall(patterns['code2'], content)[0][5:-4]
        code3 = re.findall(patterns['code3'], content)[0][8:]
        code4 = re.findall(patterns['code4'], content)[0][14:]
        code5 = re.findall(patterns['code5'], content)[0][13:]

        return comcigan_code, code0, code1, code2, code3, code4, code5

    def _resolve_school(self, school_name: str, local_code: int, school_code: int, comcigan_code: str) -> Tuple[
        int, str, int]:
        """Resolve school information from search results."""
        search_url = COMCIGAN_URL + comcigan_code + parse.quote(school_name, encoding='euc-kr')
        response = requests.get(search_url, headers=HEADERS)
        response.encoding = 'UTF-8'

        parsed_data = json.loads(response.text.strip(chr(0)))
        search_results = parsed_data["학교검색"]

        if len(search_results) == 0:
            raise RuntimeError('School not found')
        elif len(search_results) > 1:
            return self._handle_multiple_schools(search_results, school_code, local_code)
        else:
            # Single school found
            result = search_results[0]
            return result[0], result[2], result[3]

    @staticmethod
    def _handle_multiple_schools(search_results: List[List], school_code: int, local_code: int) -> Tuple[
        int, str, int]:
        """Handle case when multiple schools are found in search results."""
        if school_code:
            for data in search_results:
                if data[3] == school_code:
                    return data[0], data[2], data[3]

        if local_code:
            for data in search_results:
                if data[0] == local_code:
                    return data[0], data[2], data[3]

        raise RuntimeError('Multiple schools found - please specify school_code or local_code')

    @staticmethod
    def _fetch_timetable_data(school_code: int, week_num: int, comcigan_codes: Tuple) -> dict:
        """Fetch timetable data from Comcigan API."""
        comcigan_code, code0, *_ = comcigan_codes

        # Encode request parameters
        encoded_params = base64.b64encode(f"{code0}_{school_code}_0_{week_num + 1}".encode('utf-8'))
        request_url = f'{COMCIGAN_URL}{comcigan_code[:7]}{str(encoded_params)[2:-1]}'

        response = requests.get(request_url, headers=HEADERS)
        response.encoding = 'UTF-8'

        # Parse first line of response as JSON
        json_data = response.text.split('\n')[0]
        return json.loads(json_data)

    def _initialize_from_data(self, data: dict, local_code: int, school_name: str, school_code: int,
                              comcigan_codes: Tuple) -> None:
        """Initialize instance variables from fetched data."""
        _, _, code1, code2, code3, code4, code5 = comcigan_codes

        # Set basic school information
        self.school_code = school_code
        self.school_name = school_name
        self.local_code = local_code
        self.local_name = data["지역명"]
        self.school_year = data["학년도"]
        self.start_date = data["시작일"]
        self.day_time = data["일과시간"]
        self.update_date = data["자료" + code3]

        # Process teacher and subject lists
        teacher_list = data["자료" + code1]
        teacher_list[0] = ""
        subject_list = data["자료" + code2]
        subject_list[0] = ""

        # Build timetable data structure
        self.timetable = self._build_timetable(
            data, teacher_list, subject_list, code4, code5
        )

        # Process homeroom teacher information
        self._homeroom_teacher = self._process_homeroom_teachers(
            data["담임"], teacher_list
        )

    def _build_timetable(self, data: dict, teacher_list: List[str], subject_list: List[str], code4: str, code5: str) -> \
            List[List[List[List[TimeTableData]]]]:
        """Build the complete timetable data structure."""
        original_timetable = data["자료" + code5]
        current_timetable = data["자료" + code4]
        timetable = []

        for grade_idx, grade_data in enumerate(current_timetable):
            if grade_idx == 0:
                timetable.append([])
                continue

            grade_timetable = [[]]  # Start with empty class 0

            for class_idx, class_data in enumerate(grade_data):
                if class_idx == 0:
                    continue

                class_timetable = self._build_class_timetable(
                    grade_idx, class_idx, class_data, original_timetable,
                    teacher_list, subject_list
                )
                grade_timetable.append(class_timetable)

            timetable.append(grade_timetable)

        return timetable

    def _build_class_timetable(self, grade_idx: int, class_idx: int, class_data: List,
                               original_timetable: List, teacher_list: List[str],
                               subject_list: List[str]) -> List[List[TimeTableData]]:
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
                period_data = self._create_period_data(
                    period, day, class_data, original_class,
                    teacher_list, subject_list
                )
                day_timetable.append(period_data)

            class_timetable.append(day_timetable)

        return class_timetable

    @staticmethod
    def _create_period_data(period: int, day: int, class_data: List,
                            original_class: List, teacher_list: List[str],
                            subject_list: List[str]) -> TimeTableData:
        """Create TimeTableData for a specific period."""
        # Get original period data (handle bounds checking)
        original_period = 0
        if (day < len(original_class) and
                len(original_class[day]) > 0 and
                period <= original_class[day][0] and
                period < len(original_class[day])):
            original_period = original_class[day][period]

        # Get current period data (handle bounds checking)
        current_period = 0
        if (day < len(class_data) and
                len(class_data[day]) > 0 and
                period <= class_data[day][0] and
                period < len(class_data[day])):
            current_period = class_data[day][period]

        # Create original lecture if replacement occurred
        original_lecture = None
        if current_period != original_period and original_period != 0:
            original_lecture = Lecture(
                period=period,
                subject=subject_list[original_period // 1000] if original_period // 1000 < len(subject_list) else "",
                teacher=teacher_list[original_period % 100] if original_period % 100 < len(teacher_list) else ""
            )

        # Get subject and teacher names with bounds checking
        subject_name = ""
        teacher_name = ""

        if current_period != 0:
            subject_idx = current_period // 1000
            teacher_idx = current_period % 100

            if subject_idx < len(subject_list):
                subject_name = subject_list[subject_idx]
            if teacher_idx < len(teacher_list):
                teacher_name = teacher_list[teacher_idx]

        return TimeTableData(
            period=period,
            subject=subject_name,
            teacher=teacher_name,
            replaced=current_period != original_period,
            original=original_lecture
        )

    @staticmethod
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
