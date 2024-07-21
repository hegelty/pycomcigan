import base64
from typing import Optional
import requests
import re
import json
from urllib import parse

comcigan_url = 'http://comci.net:4082'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36'
}


class Lecture:
    period: int
    subject: str
    teacher: str

    def __init__(self, period: int, subject: str, teacher: str):
        self.period = period
        self.subject = subject
        self.teacher = teacher

    def __str__(self):
        return f"{self.period}교시: {self.subject}({self.teacher})"

    def __repr__(self):
        return self.__str__()


class TimeTableData:
    period: int
    subject: str
    teacher: str
    replaced: bool
    original: Optional[Lecture]

    def __init__(self, period: int, subject: str, teacher: str, replaced: bool, original: Optional[Lecture]):
        self.period = period
        self.subject = subject
        self.teacher = teacher
        self.replaced = replaced
        self.original = original

    def __str__(self):
        return f"{self.period}교시: {self.subject}({self.teacher}) {'(대체)' if self.replaced else ''}"

    def __repr__(self):
        return self.__str__()


class TimeTable:
    school_code: int
    school_name: str
    local_code: int
    local_name: str
    school_year: int
    start_date: str
    day_time: list[str]
    update_date: str
    timetable: list[list[list[TimeTableData]]]
    _homeroom_teacher: list[list[str]]

    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5

    def __init__(self,
                 school_name: str,
                 local_code: int = 0,
                 school_code: int = 0,
                 week_num: int = 0):
        """
        :param school_name: 학교 이름
        :param local_code: 교육청 코드(선택)
        :param school_code: 학교 코드(선택)
        :param week_num: 0이면 이번주, 1이면 다음주
        """
        if week_num not in [0, 1]:
            raise ValueError('next_week는 0또는 1의 값을 가져야 합니다.')
        try:
            local_code = int(local_code)
            school_code = int(school_code)
        except Exception:
            raise ValueError('local_code와 school_code는 정수여야 합니다.')

        comcigan_code, code0, code1, code2, code3, code4, code5 = get_code()

        local_code, school_name, school_code = get_school_code(school_name, local_code, school_code, comcigan_code)
        if local_code == -1:
            raise RuntimeError('학교가 2개 이상 존재합니다.')
        elif local_code == -2:
            raise RuntimeError('학교를 찾을 수 없습니다.')

        sc = base64.b64encode(f"{str(code0)}_{school_code}_0_{str(week_num + 1)}".encode('utf-8'))
        resp = requests.get(f'{comcigan_url}{comcigan_code[:7]}{str(sc)[2:-1]}', headers=headers)
        resp.encoding = 'UTF-8'
        resp = resp.text.split('\n')[0]
        resp = json.loads(resp)

        # with open('timetable.json', 'w', encoding='UTF-8') as f:
        #     f.write(json.dumps(resp, ensure_ascii=False, indent=4))

        self.school_code = school_code
        self.school_name = school_name
        self.local_code = local_code
        self.local_name = resp["지역명"]
        self.school_year = resp["학년도"]
        self.start_date = resp["시작일"]
        self.day_time = resp["일과시간"]
        self.update_date = resp["자료" + code3]

        data = []
        teacher_list = resp["자료" + code1]
        teacher_list[0] = ""
        sub_list = resp["자료" + code2]
        sub_list[0] = ""

        original_timetable = resp["자료" + code5]
        grade = 0
        for i in resp["자료" + code4]:
            cls = 0
            if grade == 0:
                data.append([])  # 0학년 추가
                grade += 1
                continue
            for j in i:
                if cls == 0:
                    data.append([[]])  # 학년 + 0반 추가
                    cls += 1
                    continue
                data[grade].append([[]])  # 반추가

                for day in range(1, original_timetable[grade][cls][0] + 1):
                    data[grade][cls].append([])  # 요일 추가
                    for period in range(1, original_timetable[grade][cls][day][0] + 1):
                        original_period = original_timetable[grade][cls][day][period]
                        if j[day][0] < period:
                            period_num = 0
                        else:
                            period_num = j[day][period]

                        data[grade][cls][day].append(
                            TimeTableData(
                                period=period,
                                subject=sub_list[period_num // 1000],
                                teacher=teacher_list[period_num % 100],
                                replaced=period_num != original_period,
                                original=None if period_num == original_period else Lecture(
                                    period=period,
                                    subject=sub_list[original_period // 1000],
                                    teacher=teacher_list[original_period % 100]
                                )
                            )
                        )
                cls += 1
            grade += 1

        self.timetable = data

        homeroom_teacher= resp["담임"]
        for grade in range(len(homeroom_teacher)):
            for cls in range(len(homeroom_teacher[grade])):
                if homeroom_teacher[grade][cls] in [0,255]:
                    del(homeroom_teacher[grade][cls:])
                    break
                else:
                    homeroom_teacher[grade][cls] = teacher_list[homeroom_teacher[grade][cls]]
        self._homeroom_teacher = homeroom_teacher

    def homeroom(self, grade: int, cls: int):
        """
        :param grade: 학년
        :param cls: 반
        :return: 담임 선생님
        """
        return self._homeroom_teacher[grade - 1][cls - 1]

    def __str__(self):
        return f"학교 코드: {self.school_code}\n" \
               f"학교명: {self.school_name}\n" \
               f"지역 코드: {self.local_code}\n" \
               f"지역명: {self.local_name}\n" \
               f"학년도: {self.school_year}\n" \
               f"시작일: {self.start_date}\n" \
               f"일과시간: {self.day_time}\n" \
               f"갱신일시: {self.update_date}\n"

    def __repr__(self):
        return self.__str__()


def get_code():
    resp = requests.get(comcigan_url + '/st', headers=headers)
    resp.encoding = 'euc-kr'
    resp = resp.text
    comcigan_code = re.findall('\\.\\/[0-9]+\\?[0-9]+l', resp)[0][1:]
    code0 = re.findall('sc_data\(\'[0-9]+_', resp)[0][9:-1]
    code1 = re.findall('성명=자료.자료[0-9]+', resp)[0][8:]
    code2 = re.findall('자료.자료[0-9]+\\[sb\\]', resp)[0][5:-4]
    code3 = re.findall('=H시간표.자료[0-9]+', resp)[0][8:]
    code4 = re.findall('일일자료=Q자료\\(자료\\.자료[0-9]+', resp)[0][14:]
    code5 = re.findall('원자료=Q자료\\(자료\\.자료[0-9]+', resp)[0][13:]
    return comcigan_code, code0, code1, code2, code3, code4, code5


def get_school_code(school_name, local_code, school_code, comcigan_code):
    resp = requests.get(comcigan_url + comcigan_code + parse.quote(school_name, encoding='euc-kr'))
    resp.encoding = 'UTF-8'
    resp = json.loads(resp.text.strip(chr(0)))
    if len(resp["학교검색"]) == 0:
        return -2, -2, resp
    elif len(resp["학교검색"]) > 1:  # 2개 이상이 검색될
        if school_code:
            for data in resp["학교검색"]:
                if data[3] == school_code:
                    return data[0], data[2], data[3]
        if local_code:
            for data in resp["학교검색"]:
                if data[0] == local_code:
                    return data[0], data[2], data[3]
        return -1, -1, resp
    return resp['학교검색'][0][0], resp['학교검색'][0][2], resp['학교검색'][0][3]
