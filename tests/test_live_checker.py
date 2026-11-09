"""실서버 상태 검사기의 실패 판정과 로그 노출 방지를 검증한다."""

from types import SimpleNamespace

import pytest
from requests.exceptions import Timeout

from scripts import check_live_parser as checker


@pytest.mark.parametrize('has_subject', [True, False])
def test_validate_timetable_accepts_classes_and_holiday(monkeypatch, has_subject):
    """
    역할: 정상 수업과 휴일의 빈 수업을 모두 정상 구조로 판정하는지 확인한다.
    입력: 과목 유무를 나타내는 테스트 매개변수와 패치 도구.
    출력: 학급 수와 날짜가 포함된 요약을 확인한다.
    """
    def initialize(table, *args):
        """
        역할: 시간표 구조 검사용 학급과 교시를 구성한다.
        입력: 초기화할 시간표와 사용하지 않는 운영 생성기 인자.
        출력: 전달한 시간표의 검사 대상 필드를 설정한다.
        """
        table.start_date = '2026-11-09'
        table.school_year = 2026
        day = [SimpleNamespace(period=p, subject='subject' if has_subject else '', teacher='')
               for p in range(1, 9)]
        table.timetable = [[], [[], [[], day]]]
    monkeypatch.setattr(checker.TimeTable, '_initialize_from_data', initialize)
    result = checker.validate_timetable({}, [5000, 'region', 'school', 123], ())
    assert 'start=2026-11-09, classes=1' in result
    assert f'subjects={8 if has_subject else 0}' in result


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
