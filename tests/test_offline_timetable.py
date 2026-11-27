"""Synthetic offline interpretation and transport/constructor equivalence."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycomcigan import TimeTable
from pycomcigan.service_protocol import parse_service_protocol
from pycomcigan.timetable import Lecture, TimeTableData
from scripts.check_live_parser import validate_timetable
from test_encrypted_response import envelope
from test_post_page_transport import POST_PAGE
from test_service_protocol import KEY
from test_timetable import BASE_PAGE


SCHOOL = (5000, 'region', 'synthetic school', 123)
LEGACY_PAGE = BASE_PAGE.format(
    teacher_expression="성명=자료.자료446[th];",
    subject_expression="과목명=자료.자료492[sb];",
)
MODERN_PAGE = (POST_PAGE.replace('자료119', 'xTeacher')
               .replace('자료123', 'xSubject')
               .replace('자료108', 'xUpdate')
               .replace('자료158', 'xCurrent')
               .replace('자료167', 'xOriginal'))


def sample(codes, marked):
    return {
        '지역명': 'region', '학년도': 2026, '시작일': '2026-11-09',
        '일과시간': ['09:00'], '담임': [[1, 0]],
        codes[2]: ['', 'teacher A*', 'teacher B*'],
        codes[3]: ['', 'subject A', 'subject B'],
        codes[4]: '2026-11-09 12:00',
        codes[5]: [[], [[], [2, [3, '>2002' if marked else 2002, 2002, 0], [0]]]],
        codes[6]: [[], [[], [2, [3, 1001, 2002, 0], [0]]]],
        '분리': 1000 if marked else 100,
        '변경알림': '1' if marked else '0',
    }


def snapshot(table):
    def period(lesson):
        assert isinstance(lesson, TimeTableData)
        original = lesson.original
        if original is not None:
            assert isinstance(original, Lecture)
        return (lesson.period, lesson.subject, lesson.teacher, lesson.replaced,
                None if original is None else (original.period, original.subject, original.teacher))
    return {
        'metadata': (table.school_code, table.local_code, table.school_name,
                     table.local_name, table.school_year, table.start_date,
                     table.update_date, table.day_time, table.homeroom(1, 1)),
        'grid': [[[list(map(period, day)) for day in classroom]
                  for classroom in grade] for grade in table.timetable],
    }


@pytest.mark.parametrize('page,marked', [(LEGACY_PAGE, False), (MODERN_PAGE, True)])
def test_offline_response_matches_public_constructor_and_expected_models(page, marked):
    protocol = parse_service_protocol(page)
    codes = TimeTable._get_comcigan_codes(page)
    data = sample(codes, marked)
    payload = json.dumps(data)
    if marked:
        payload = envelope(payload.encode(), key=KEY)

    with patch('pycomcigan.timetable.get_comcigan_response_for_codes') as service, \
         patch('pycomcigan.timetable.school_search') as search, \
         patch('pycomcigan.timetable.get_response_encoding') as request, \
         patch('pycomcigan.helpers.urlopen') as urlopen:
        offline = TimeTable._from_response(payload, SCHOOL[0], SCHOOL[2], SCHOOL[3], codes, protocol)
        service.assert_not_called()
        search.assert_not_called()
        request.assert_not_called()
        urlopen.assert_not_called()

    with patch('pycomcigan.timetable.get_comcigan_response_for_codes',
               return_value=SimpleNamespace(text=page)), \
         patch('pycomcigan.timetable.school_search', return_value=[SCHOOL]), \
         patch('pycomcigan.timetable.get_response_encoding',
               return_value=SimpleNamespace(text=payload)):
        public = TimeTable(SCHOOL[2], school_code=SCHOOL[3])

    actual = snapshot(offline)
    assert actual == snapshot(public)
    assert actual['metadata'] == (123, 5000, 'synthetic school', 'region', 2026,
                                  '2026-11-09', '2026-11-09 12:00', ['09:00'], 'teacher A')
    assert actual['grid'][0] == []
    assert actual['grid'][1][0] == []
    assert actual['grid'][1][1][0] == []
    first, second = actual['grid'][1][1][1:]
    assert first[:3] == [
        (1, 'subject B', 'teacher B', True, (1, 'subject A', 'teacher A')),
        (2, 'subject B', 'teacher B', False, None),
        (3, '', '', False, None),
    ]
    assert first[3:] == [(p, '', '', False, None) for p in range(4, 9)]
    assert second == [(p, '', '', False, None) for p in range(1, 9)]
    assert validate_timetable(data, SCHOOL, codes) == 'start=2026-11-09, classes=1, subjects=2'


@pytest.mark.parametrize('failure,exception', [
    ('missing', KeyError), ('truncated', ValueError), ('mismatch', ValueError),
])
def test_missing_original_information_is_not_an_empty_lesson(failure, exception):
    protocol = parse_service_protocol(LEGACY_PAGE)
    codes = TimeTable._get_comcigan_codes(LEGACY_PAGE)
    data = sample(codes, False)
    if failure == 'missing':
        del data[codes[6]]
    elif failure == 'truncated':
        data[codes[6]][1][1][1] = [3, 1001]
    else:
        data[codes[6]][1][1] = [1, [0]]
    with pytest.raises(exception):
        TimeTable._from_response(json.dumps(data), SCHOOL[0], SCHOOL[2], SCHOOL[3], codes, protocol)
    with pytest.raises(exception):
        validate_timetable(data, SCHOOL, codes)
