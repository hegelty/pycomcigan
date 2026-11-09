"""실서버 상태 검사기의 실패 판정과 로그 노출 방지를 검증한다."""

from copy import deepcopy

import pytest
from requests.exceptions import Timeout

from scripts import check_live_parser as checker


CODES = ('/unused?1l', '107225', '119', '123', '108', '158', '167')
SCHOOL = [5000, 'region', 'school', 123]


def timetable_data(has_subject=True):
    original = [[], [[], [1, [8] + [1001] * 8]]]
    current = deepcopy(original) if has_subject else [[], [[], [1, [0]]]]
    return {
        '지역명': 'region', '학년도': 2026, '시작일': '2026-11-09', '일과시간': [],
        '자료108': '2026-11-09', '자료119': ['', 'teacher'],
        '자료123': ['', 'subject'], '자료158': current,
        '자료167': original, '담임': [[1, 0]],
    }


@pytest.mark.parametrize('has_subject', [True, False])
def test_validate_timetable_accepts_classes_and_holiday(has_subject):
    result = checker.validate_timetable(timetable_data(has_subject), SCHOOL, CODES)
    assert 'start=2026-11-09, classes=1' in result
    assert f'subjects={8 if has_subject else 0}' in result


@pytest.mark.parametrize('field', ['자료158', '자료167'])
@pytest.mark.parametrize('grid', [
    {}, [], [[], {}], [[], [[], {}]], [[], [[], []]],
    [[], [[], [1]]], [[], [[], [1, {}]]], [[], [[], [1, []]]],
    [[], [[], [1, [1]]]], [[], [[], [True, [0]]]],
    [[], [[], [1, [True]]]],
])
def test_malformed_raw_arrays_fail_before_parser_normalization(monkeypatch, field, grid):
    data = timetable_data()
    data[field] = grid

    def should_not_initialize(*args):
        pytest.fail('raw arrays must be validated before parser normalization')

    monkeypatch.setattr(checker.TimeTable, '_initialize_from_data', should_not_initialize)
    with pytest.raises(ValueError):
        checker.validate_timetable(data, SCHOOL, CODES)


@pytest.mark.parametrize('grid', [
    [[], [[], [1, [0]], [1, [0]]]],
    [[], [[], [2, [0], [0]]]],
])
def test_current_and_original_class_and_day_structure_must_match(grid):
    data = timetable_data()
    data['자료158'] = grid
    with pytest.raises(ValueError, match='inconsistent timetable'):
        checker.validate_timetable(data, SCHOOL, CODES)


def test_unpublished_response_fails_validation():
    """
    역할: 미게시 응답을 정상 시간표로 오인하지 않는지 확인한다.
    입력: 필수 필드가 없는 빈 응답.
    출력: 운영 시간표 생성기의 필수 필드 오류를 확인한다.
    """
    with pytest.raises(KeyError):
        checker.validate_timetable({}, [5000, 'region', 'school', 123], ('',) * 7)


def test_main_reports_failure_without_exception_content(monkeypatch, tmp_path, capsys):
    """
    역할: 네트워크 실패가 재시도 없이 실패 코드로 기록되고 원문이 숨겨지는지 확인한다.
    입력: 토큰을 흉내 낸 예외와 임시 Actions 요약 경로.
    출력: 실패 코드와 단계 요약을 확인하고 예외 내용의 노출을 거부한다.
    """
    calls = []
    def fail(report):
        """
        역할: 실서버 호출을 대신해 원문을 포함한 네트워크 실패를 발생시킨다.
        입력: 단계별 검사 결과 목록.
        출력: 네트워크 오류를 발생시킨다.
        """
        calls.append(1)
        checker.begin_step(report, 'Service page and protocol')
        raise Timeout('private-token-and-response')
    summary = tmp_path / 'summary.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))
    monkeypatch.setattr(checker, 'check_live', fail)
    assert checker.main() == 1
    assert calls == [1]
    text = summary.read_text(encoding='utf-8')
    assert '| FAIL | network error or timeout |' in text
    assert 'private-token-and-response' not in text + capsys.readouterr().out


@pytest.mark.parametrize('status', [403, 429])
def test_rejected_requests_are_classified_without_raw_message(status):
    """
    역할: 요청 거부와 제한 오류가 민감한 메시지 없이 구분되는지 확인한다.
    입력: 검사 대상 HTTP 상태 코드.
    출력: 고정된 오류 분류에 상태 코드만 반영되는지 확인한다.
    """
    detail = checker.failure_detail(RuntimeError(f'HTTP {status}: private-token'))
    assert str(status) in detail
    assert 'private-token' not in detail
