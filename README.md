# pycomcigan

[컴시간알리미](http://컴시간학생.kr) 에서 시간표 정보를 가져오는 Python 라이브러리입니다.

## 설치

```sh
$ pip install pycomcigan
```

## 기능
* 시간표 가져오기
* 학교 검색
### 구현 예정
* 담임 정보

## 사용법
```python
from pycomcigan import Timetable, get_school_code

# 학교 검색
# [학교명, 지역명, 학교 코드, 지역 코드] 리스트로 응답
get_school_code("경기")

# 시간표 가져오기
# week_num: 0이면 이번주, 1이면 다음주
timetable = Timetable("경기북과학고", week_num=1)

# 3학년 1반 화요일 시간표
print(timetable.timetable[3][1][timetable.THURSDAY])
```

## 라이센스
[MIT License](LICENSE)