# 실서버 파서 상태 검사

`Parser Health`는 기본 브랜치의 코드를 한국 시간 매일 00:00, 06:00,
12:00, 18:00에 검사한다. UTC cron은 `0 3,9,15,21 * * *`이며
Actions 탭의 `Run workflow`로도 실행할 수 있다.

먼저 Poetry 2.1.3으로 잠금 파일의 의존성을 설치하고 오프라인 회귀 테스트를
실행한다. 통과하면 서비스 페이지를 한 번 읽어 같은 프로토콜과 토큰으로
정확한 학교 검색·검색 결과 없음·두 주차 시간표 요청을 검사한다.
기본 대상은 `중일고등학교`이며 실행당 실서버 요청은 정상 경로에서 5회다.
HTTP 요청별 제한시간은 기존 클라이언트의 30초이며 자동 재시도는 없다.

암호화 응답의 인증과 복호화는 운영 코드를 사용한다. 시간표 생성까지 실행해
날짜·학년도·학급·요일·교시 구조와 문자열 자료형을 검사한다. 학급과 요일이
있어야 하지만 방학·휴일의 빈 수업은 허용하므로 수업 수를 고정하지 않는다.
두 요청의 실제 시작일을 요약에 기록하며 오늘 날짜나 7일 간격을 강제하지 않는다.
게시 기간 선택의 정확성까지 보장하는 검사는 아니다.

게시되지 않은 시간표 등으로 필수 필드가 없으면 실패로 기록한다.
실패는 네트워크·서버 장애와 파서 변경 모두를 의미할 수 있으므로 Actions의
실패 단계와 서버의 게시 상태를 함께 확인한다. 오류 시 즉시 중단하며
HTTP 403·429는 별도 분류한다. 토큰·암호 키·응답 원문·교사명·과목명과
예외의 원문 및 traceback은 로그나 아티팩트로 저장하지 않는다.

로컬 실행:

```sh
python -m pip install poetry==2.1.3
poetry install --no-interaction
poetry run python -W error -m pytest -q
poetry run python -m scripts.check_live_parser
```

포크에서는 GitHub Actions와 `Parser Health` 워크플로를 활성화해야 한다.
예약 실행은 기본 브랜치에 있는 워크플로만 사용하며, 포크는 원본 master를
자동 동기화하지 않는다. 이후 원본 변경은 직접 반영해야 한다.
GitHub 부하로 예약 실행이 지연·누락될 수 있고, 공개 저장소에 60일간 활동이
없으면 예약 워크플로가 자동 비활성화될 수 있다.

참고: [GitHub 예약 실행 문서](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
