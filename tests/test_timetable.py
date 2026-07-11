from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pycomcigan.timetable import TimeTable


BASE_PAGE = """
<script>
school_ra(sc) {{ $.ajax({{ url:'./36179?17384l'+sc }}); }}
function sc_data(sc, sc2, r, nw) {{
    if (nw == '0') {{ da1 = H시간표.자료244; }}
    일일자료=Q자료(자료.자료147[학년][반][요일][교시]);
    원자료=Q자료(자료.자료481[학년][반][요일][교시]);
    {teacher_expression}
    {subject_expression}
}}
function sc_disp(sc) {{ sc_data('73629_', sc, 1, '0'); }}
</script>
"""


@pytest.mark.parametrize(
    ("teacher_expression", "subject_expression"),
    [
        (
            "성명=자료.자료446[th];",
            "과목명=자료.자료492[sb];",
        ),
        (
            "성명=Q성명(자료.자료446[th]);",
            "과목명=Q과목명(자료.자료492[sb]);",
        ),
    ],
)
def test_get_comcigan_codes_supports_legacy_and_wrapped_fields(
    teacher_expression, subject_expression
):
    response = SimpleNamespace(
        text=BASE_PAGE.format(
            teacher_expression=teacher_expression,
            subject_expression=subject_expression,
        )
    )

    with patch(
        "pycomcigan.timetable.get_comcigan_response_for_codes",
        return_value=response,
    ):
        assert TimeTable._get_comcigan_codes() == (
            "/36179?17384l",
            "73629",
            "446",
            "492",
            "244",
            "147",
            "481",
        )


def test_get_comcigan_codes_reports_changed_page_structure():
    response = SimpleNamespace(
        text=BASE_PAGE.format(
            teacher_expression="",
            subject_expression="과목명=Q과목명(자료.자료492[sb]);",
        )
    )

    with patch(
        "pycomcigan.timetable.get_comcigan_response_for_codes",
        return_value=response,
    ), pytest.raises(RuntimeError, match="teacher data"):
        TimeTable._get_comcigan_codes()


def test_create_period_data_decodes_marked_string_values():
    teachers = [""] * 124
    teachers[122] = "original teacher"
    teachers[123] = "current teacher"
    subjects = [""] * 9
    subjects[7] = "current subject"
    subjects[8] = "original subject"

    lecture = TimeTable._create_period_data(
        period=1,
        day=1,
        class_data=[0, [1, ">7123"]],
        original_class=[1, [1, 8122]],
        teacher_list=teachers,
        subject_list=subjects,
        subject_divisor=1000,
        change_notifications=True,
    )

    assert lecture.subject == "current subject"
    assert lecture.teacher == "current teacher"
    assert lecture.replaced is True
    assert lecture.original.subject == "original subject"
    assert lecture.original.teacher == "original teacher"


def test_create_period_data_keeps_legacy_change_detection():
    teachers = [""] * 13
    teachers[11] = "original teacher"
    teachers[12] = "current teacher"
    subjects = [""] * 9
    subjects[7] = "current subject"
    subjects[8] = "original subject"

    lecture = TimeTable._create_period_data(
        period=1,
        day=1,
        class_data=[0, [1, 7012]],
        original_class=[1, [1, 8011]],
        teacher_list=teachers,
        subject_list=subjects,
    )

    assert lecture.subject == "current subject"
    assert lecture.teacher == "current teacher"
    assert lecture.replaced is True
    assert lecture.original.subject == "original subject"
    assert lecture.original.teacher == "original teacher"


@pytest.mark.parametrize(
    ("raw_name", "formatted_name"),
    [
        ("박성*", "박성"),
        ("김*수", "김*수"),
        ("김*", "김*"),
        (None, ""),
    ],
)
def test_format_teacher_name_matches_comcigan(raw_name, formatted_name):
    assert TimeTable._format_teacher_name(raw_name) == formatted_name
