# pycomcigan

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/hegelty/pycomcigan/python-publish.yml?label=action&logo=github&style=flat-square)](https://github.com/hegelty/pycomcigan/actions)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pycomcigan)](https://pypi.org/project/pycomcigan/)
[![PyPI](https://img.shields.io/pypi/v/pycomcigan)](https://pypi.org/project/pycomcigan/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/pycomcigan)](https://pypi.org/project/pycomcigan/)
[![GitHub](https://img.shields.io/github/license/hegelty/pycomcigan)](LICENSE)

[컴시간알리미](http://컴시간학생.kr) 에서 시간표 정보를 가져오는 Python 라이브러리입니다.

컴시간알리미 구조에 대한 설명은 [comcigan.md](comcigan.md)를 참고하세요.

## 설치

```sh
$ pip install pycomcigan
```

## 기능

* 시간표 가져오기
* 학교 검색
* 담임 정보

## 사용법

### [Docs](/docs.md)

### 예제

```python
from pycomcigan import TimeTable, get_school_code

# 학교 검색
# [학교명, 지역명, 학교 코드, 지역 코드] 리스트로 응답
get_school_code("경기")

# 시간표 가져오기
# week_num: 0이면 이번주, 1이면 다음주
timetable = TimeTable("경기북과학고", week_num=1)

# 시간표 출력
for day in timetable.timetable[3][1]:
    for time in day:
        print(time, end=" ")
    print()

# 3학년 1반 담임선생님
print(timetable.homeroom(3, 1))

print(timetable)
```

## 라이센스

[MIT License](LICENSE)
