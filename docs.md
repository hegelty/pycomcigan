# pycomcigan

## 목차

1. [시작하기](#1-시작하기)
    1. [설치](#설치)
    2. [기본 사용법](#기본-사용법)
2. [학교 검색](#2-학교-검색)
3. [시간표](#3-시간표)
    1. [시간표 불러오기](#시간표-불러오기)
    2. [시간표 조회](#시간표-조회)
    3. [담임선생님 조회](#담임선생님-조회)

---

## 1. 시작하기

> python 3.9 미만에서 작동을 보장하지 않습니다.

### 설치

Install package with [pip](https://pypi.org/project/pycomcigan/)

```sh
$ pip install pycomcigan
```

### 기본 사용법

```python
from pycomcigan import TimeTable, get_school_code

# 학교 검색
# [지역코드, 지역명, 학교명, 학교코드] 리스트로 응답
get_school_code("경기")

# 시간표 가져오기
# week_num: 0이면 이번주, 1이면 다음주
timetable = TimeTable("경기북과학고", week_num=1)

# 3학년 1반 화요일 시간표
print(timetable.timetable[3][1][timetable.TUESDAY])

# 3학년 1반 담임선생님
print(timetable.homeroom(3, 1))
```

---

## 2. 학교 검색

```python
from pycomcigan import get_school_code

get_school_code(school_name: str)
```

* `school_name`: 학교 이름(일부 또는 전체)

**return**: 학교 정보 리스트

```python
[
    [지역코드, 지역명, 학교명, 학교코드],
    ...
]
```

---

## 3. 시간표

### 시간표 불러오기

```python
from pycomcigan import TimeTable

timetable = TimeTable(school_name: str, local_code: int = 0, school_code: int = 0, week_num: int = 0)
```

* `school_name`: 학교 이름 (필수)
* `local_code` (Optional): 지역 코드 (기본값: 0)
* `school_code` (Optional): 학교 코드 (기본값: 0)
* `week_num` (Optional): 주차 번호 (기본값: 0)
    - `0`: 이번주 시간표
    - `1`: 다음주 시간표

**예외 발생:**

* `ValueError`: week_num이 0 또는 1이 아닐 때, 또는 코드들이 정수가 아닐 때
* `RuntimeError`: 학교를 찾을 수 없거나 여러 개의 학교가 검색될 때

여러 학교가 검색되는 경우 [학교 검색](#2-학교-검색)을 이용해 정확한 `school_code` 또는 `local_code`를 지정해주세요.

### 시간표 조회

```python
timetable.timetable[grade: int][class_num: int][day: int]
```

* `grade`: 학년
* `class_num`: 반
* `day`: 요일
    * `timetable.MONDAY` (1)
    * `timetable.TUESDAY` (2)
    * `timetable.WEDNESDAY` (3)
    * `timetable.THURSDAY` (4)
    * `timetable.FRIDAY` (5)
* **return**: List[[TimeTableData](#timetabledata)]

**참고:** 시간표는 최대 8교시까지 보장됩니다.

#### TimeTableData

수업 정보를 담고 있는 객체입니다.

* `period` (int): 교시
* `subject` (str): 과목명
* `teacher` (str): 담당 선생님
* `replaced` (bool): 수업 변경 여부
* `original` ([Lecture](#lecture) | None): 원래 수업 정보 (변경된 경우에만)

#### Lecture

원래 수업 정보를 담고 있는 객체입니다.

* `period` (int): 교시
* `subject` (str): 과목명
* `teacher` (str): 담당 선생님

### 담임선생님 조회

```python
timetable.homeroom(grade: int, class_num: int)
```

* `grade`: 학년 (1부터 시작)
* `class_num`: 반 (1부터 시작)

**return**: `str` - 담임선생님 이름