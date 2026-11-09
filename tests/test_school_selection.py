from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycomcigan.timetable import TimeTable
from test_request_transport import TOKEN_PAGE


ROWS = [
    [5000, 'Region A', 'School A', 123],
    [5000, 'Region A', 'School B', 456],
    [6000, 'Region B', 'School C', 789],
]


@pytest.mark.parametrize(
    'rows,local_code,school_code,expected',
    [
        ([ROWS[0]], 5000, 123, (5000, 'School A', 123)),
        (ROWS, 5000, 456, (5000, 'School B', 456)),
        (ROWS, 0, 789, (6000, 'School C', 789)),
        (ROWS, 6000, 0, (6000, 'School C', 789)),
        ([ROWS[0]], 0, 0, (5000, 'School A', 123)),
    ],
)
def test_resolve_school_requires_all_specified_codes(rows, local_code, school_code, expected):
    with patch('pycomcigan.timetable.school_search', return_value=rows):
        assert TimeTable.__new__(TimeTable)._resolve_school(
            'School', local_code, school_code, 'endpoint'
        ) == expected


@pytest.mark.parametrize(
    'rows,local_code,school_code,message',
    [
        ([ROWS[0]], 0, 456, 'School not found'),
        ([ROWS[0]], 6000, 0, 'School not found'),
        (ROWS, 5000, 999, 'School not found'),
        (ROWS, 5000, 789, 'School not found'),
        (ROWS, 5000, 0, 'Multiple schools found'),
        (ROWS, 0, 0, 'Multiple schools found'),
        ([], 0, 0, 'School not found'),
    ],
)
def test_resolve_school_rejects_missing_or_ambiguous_matches(rows, local_code, school_code, message):
    with patch('pycomcigan.timetable.school_search', return_value=rows), \
         pytest.raises(RuntimeError, match=message):
        TimeTable.__new__(TimeTable)._resolve_school('School', local_code, school_code, 'endpoint')


@pytest.mark.parametrize(
    'local_code,school_code,selected',
    [(5000, 456, ROWS[1]), ('5000', '456', ROWS[1]), ('0', '789', ROWS[2]), ('6000', '0', ROWS[2])],
)
def test_constructor_normalizes_codes_before_selection(local_code, school_code, selected):
    with patch('pycomcigan.timetable.get_comcigan_response_for_codes', return_value=SimpleNamespace(text=TOKEN_PAGE)), \
         patch('pycomcigan.timetable.school_search', return_value=ROWS), \
         patch.object(TimeTable, '_fetch_timetable_data', return_value={'sentinel': True}) as fetch, \
         patch.object(TimeTable, '_initialize_from_data') as initialize:
        TimeTable('School', local_code=local_code, school_code=school_code)
    assert fetch.call_args.args[0] == selected[3]
    assert initialize.call_args.args[1:4] == (selected[0], selected[2], selected[3])


@pytest.mark.parametrize('local_code,school_code', [('invalid', 0), (0, 'invalid')])
def test_invalid_codes_fail_before_network(local_code, school_code):
    with patch('pycomcigan.timetable.get_comcigan_response_for_codes') as service, \
         patch('pycomcigan.timetable.school_search') as search, \
         patch.object(TimeTable, '_fetch_timetable_data') as fetch, \
         pytest.raises(ValueError):
        TimeTable('School', local_code=local_code, school_code=school_code)
    service.assert_not_called()
    search.assert_not_called()
    fetch.assert_not_called()


def test_constructor_does_not_fetch_timetable_when_codes_conflict():
    with patch('pycomcigan.timetable.get_comcigan_response_for_codes', return_value=SimpleNamespace(text=TOKEN_PAGE)), \
         patch('pycomcigan.timetable.school_search', return_value=ROWS), \
         patch.object(TimeTable, '_fetch_timetable_data') as fetch, \
         pytest.raises(RuntimeError, match='School not found'):
        TimeTable('School', local_code='5000', school_code='789')
    fetch.assert_not_called()
