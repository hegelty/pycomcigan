"""실서버 응답을 운영 파서에 전달하고 민감한 원문 없이 상태를 보고한다."""

from datetime import date, datetime, timezone
import os
from pathlib import Path

from requests.exceptions import RequestException

from pycomcigan.helpers import get_comcigan_response_for_codes, school_search
from pycomcigan.service_page import decode_service_page
from pycomcigan.service_protocol import parse_service_protocol
from pycomcigan.timetable import TimeTable

SCHOOL_NAME = '중일고등학교'
MISSING_SCHOOL = '존재하지않는학교'


def validate_raw_timetable(grid):
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


def validate_timetable(data, school, codes):
    """
    역할: 운영 시간표 생성기로 응답을 해석하고 날짜와 수업 구조를 검사한다.
    입력: 복호화된 응답, 정규화된 학교 행, 페이지에서 추출한 자료 코드.
    출력: 시작일과 학급·수업 수를 담은 요약이며 비정상 구조는 오류로 처리한다.
    """
    current = validate_raw_timetable(data['자료' + codes[5]])
    original = validate_raw_timetable(data['자료' + codes[6]])
    if current != original:
        raise ValueError('inconsistent timetable class or day structure')
    table = TimeTable.__new__(TimeTable)
    table._initialize_from_data(data, school[0], school[2], school[3], codes)
    start = date.fromisoformat(table.start_date)
    if type(table.school_year) is not int or not 1900 <= table.school_year <= 9999:
        raise ValueError('invalid school year')
    classes = days = subjects = 0
    for grade in table.timetable[1:]:
        for classroom in grade[1:]:
            classes += 1
            for day in classroom[1:]:
                days += 1
                if len(day) < 8:
                    raise ValueError('missing periods')
                for period, lecture in enumerate(day, 1):
                    if (lecture.period != period or not isinstance(lecture.subject, str)
                            or not isinstance(lecture.teacher, str)):
                        raise ValueError('invalid lecture')
                    subjects += bool(lecture.subject)
    if classes == 0 or days == 0:
        raise ValueError('empty timetable structure')
    return f'start={start.isoformat()}, classes={classes}, subjects={subjects}'


def begin_step(report, name):
    """
    역할: 실패 시에도 진행 단계를 알 수 있도록 검사 시작 상태를 기록한다.
    입력: 실행 결과 목록과 고정된 단계 이름.
    출력: 호출자가 성공 상태와 요약을 채울 결과 행.
    """
    row = {'name': name, 'status': 'FAIL', 'detail': 'not completed'}
    report.append(row)
    print(f'Checking: {name}', flush=True)
    return row


def check_live(report):
    """
    역할: 한 페이지의 프로토콜로 학교 검색과 두 주차 실서버 파싱을 검사한다.
    입력: 단계별 상태를 누적할 결과 목록.
    출력: 성공 시 정상 반환하며 요청이나 파싱 실패는 호출자에게 전달한다.
    """
    row = begin_step(report, 'Service page and protocol')
    content = decode_service_page(get_comcigan_response_for_codes().text)
    protocol = parse_service_protocol(content)
    codes = TimeTable._get_comcigan_codes(content)
    row.update(status='PASS', detail='page decoded; request and data fields parsed')

    row = begin_step(report, 'Exact school search')
    matches = [school for school in school_search(SCHOOL_NAME, protocol.endpoint, protocol)
               if len(school) == 4 and school[2] == SCHOOL_NAME]
    if len(matches) != 1 or type(matches[0][3]) is not int or matches[0][3] <= 0:
        raise ValueError('school must have one exact match and a positive code')
    school = matches[0]
    row.update(status='PASS', detail='one exact match with a valid school code')

    row = begin_step(report, 'Empty school search')
    if school_search(MISSING_SCHOOL, protocol.endpoint, protocol) != []:
        raise ValueError('expected empty school search')
    row.update(status='PASS', detail='empty list parsed successfully')

    for week in (0, 1):
        row = begin_step(report, f'Timetable week_num={week}')
        data = TimeTable._fetch_timetable_data(school[3], week, codes, protocol)
        detail = validate_timetable(data, school, codes)
        row.update(status='PASS', detail=detail)


def failure_detail(error):
    """
    역할: 요청 URL·토큰·응답 내용을 출력하지 않고 실패 종류를 분류한다.
    입력: 검사 중 발생한 예외.
    출력: 고정된 오류 분류 문자열.
    """
    if isinstance(error, RequestException):
        status = getattr(getattr(error, 'response', None), 'status_code', None)
        if type(status) is int:
            return f'HTTP error ({status})'
        return 'network error or timeout'
    if isinstance(error, RuntimeError):
        if 'HTTP 403' in str(error):
            return 'HTTP 403: request rejected or page token expired'
        if 'HTTP 429' in str(error):
            return 'HTTP 429: rate limited; no automatic retry'
        return 'protocol, authentication or parser error'
    return 'invalid response structure or unexpected checker error'


def main():
    """
    역할: 실서버 검사를 실행하고 콘솔과 GitHub Actions 요약에 결과를 기록한다.
    입력: GitHub Actions의 선택적 GITHUB_STEP_SUMMARY 환경 변수.
    출력: 모두 성공하면 종료 코드 0, 실패하면 1.
    """
    report = []
    exit_code = 0
    try:
        check_live(report)
    except Exception as error:
        exit_code = 1
        detail = failure_detail(error)
        if report:
            report[-1]['detail'] = detail
        else:
            report.append({'name': 'Initialization', 'status': 'FAIL', 'detail': detail})
    lines = ['## Parser Health', '',
             f'Checked at {datetime.now(timezone.utc).isoformat()}', '',
             '| Check | Result | Detail |', '|---|---|---|']
    for row in report:
        lines.append(f"| {row['name']} | {row['status']} | {row['detail']} |")
    text = '\n'.join(lines) + '\n'
    print(text)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write(text)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
