# 검증 결과와 제한

## 과거 B 검증 기록 — 2026-11-02

기존 문서에 기록된 결과이며 이번 실행 결과와 구분합니다. Python 3.12.14 / Django 5.2.18 / Channels 4.3.2 / Daphne 4.2.3 / psycopg 3.3.6 환경에서:

| 과거 검증 | 당시 기록 |
| --- | --- |
| SQLite `python manage.py test tests` | 28개 통과, PostgreSQL 전용 3개 skip |
| PostgreSQL 17.7 `python manage.py test tests --verbosity 2 --noinput` | 31개 통과, skip 없음 |
| makemigrations check / Django check / pip check / git diff check | 통과 |

당시 `/private/tmp`에 PostgreSQL 17.7 소스를 빌드하고 임시 서버 127.0.0.1:55432에서 검증한 뒤 종료했습니다. 당시 실제 로그인/프로필/일정 저장은 미구현이었고 Django 테스트 로그인으로 B를 검증했습니다.

## 이번 A+B 검증 — 2026-11-04

기준 브랜치 `feat/attendance`, 시작 시 Git 변경 없음. 작업 저장소 `/Users/kimgyutae/orca/koss-room-backend`의 코드를 임시 작업본에 복사해 기존 `.venv`의 Python 3.12.14와 lock 파일의 설치 의존성으로 실행했습니다. 원본 DB에 마이그레이션/seed를 적용하거나 원본 DB를 초기화하지 않았습니다.

| 실제 실행 | 결과 |
| --- | --- |
| SQLite `python manage.py test tests --noinput` | **59개 중 49개 통과, PostgreSQL 전용 10개 skip**, 실패 없음 |
| PostgreSQL 17.7 `python manage.py test tests --noinput --verbosity 1` | **59개 모두 통과**, skip 없음 |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py check` | 문제 없음 |
| `python -m pip check` | `No broken requirements found` (샌드박스의 pip 캐시 접근 경고만 있음) |
| 변경/신규 파일 `git diff --no-index --check` | 공백 오류 없음 |
| 기존 SQLite DB 복사본에 `python manage.py migrate --noinput` | A 신규 마이그레이션 5개 적용 성공 |

원래 B 테스트 31개는 수정하지 않고 모두 유지했습니다. A 테스트 28개를 `tests/test_accounts.py`, `tests/test_schedules.py`, `tests/test_tables.py`, `tests/test_a_concurrency.py`에 추가했습니다. 초기 PostgreSQL 실행에서 집계 목록의 기본 정렬 차이로 실패 1건을 발견했고 일정/테이블 목록에 명시적인 정렬을 추가한 뒤 전체 59개를 재실행해 통과했습니다.

### DB와 환경 격리

기존 로컬 DB는 `auth.User`와 B 마이그레이션이 적용된 상태였습니다. SQLite backup API로 복사본 `/private/tmp/koss-room-a-work/existing-db-check.sqlite3`을 만든 뒤 그 복사본만 업그레이드했습니다. `auth_user`, `attendance_visit`, `attendance_occupancystate`, `chat_message`, `django_session`의 전체 행을 전후 비교하여 동일함을 확인했습니다. 당시 원본에는 사용자/방문/채팅/세션 0행, OccupancyState 1행이 있었습니다. 비어 있지 않은 운영 데이터 전체에 대한 별도 이관 검증을 주장하지 않습니다.

PostgreSQL은 기존 임시 바이너리 `/private/tmp/koss-pg17/bin`을 사용해 **새 전용 클러스터** `/private/tmp/koss-room-a-pgdata`, 포트 **55439**를 만들었습니다. 다른 프로젝트 DB와 기존 PostgreSQL 클러스터를 사용하지 않았습니다. 테스트 이름은 `test_koss_room_a_validation`; Django가 생성하고 종료 시 삭제했습니다. 새 패키지 설치/전역 환경 변경은 없습니다. 검증 후 전용 임시 PostgreSQL 서버를 정상 종료했습니다.

실행한 PostgreSQL 테스트 명령:

```sh
DB_ENGINE=postgresql PGDATABASE=koss_room_a_validation PGUSER=kimgyutae \
PGHOST=127.0.0.1 PGPORT=55439 \
/Users/kimgyutae/orca/koss-room-backend/.venv/bin/python manage.py test tests --noinput --verbosity 1
```

이 주소는 이번 검증용이며 팀의 개발 DB 설정이 아닙니다. PostgreSQL의 공유 메모리 생성/서버 시작/접속은 샌드박스에서 차단되어 승인을 받아 실행했습니다.

### 이번 테스트가 확인한 것

- 로그인·로그아웃 및 A의 모든 변경 경로에서 실제 CSRF 검증(`Client(enforce_csrf_checks=True)`). 로그인 전 토큰 요구, 로그인 후 회전, 이전 토큰 거부.
- 올바른 비밀번호의 실제 `/api/auth/login/` 세션으로 B 입실·채팅·조회. 비활성/잘못된 비밀번호 차단, 응답에 사용자 ID·닉네임만 포함.
- 로그인 API가 발급한 쿠키를 실제 ASGI `/ws/room/` 라우터에 전달해 연결, 입실 이벤트, 채팅 닉네임, 일정 API 저장 후 `schedule.changed` 수신. 로그아웃 API 이후 HTTP 401, 기존 소켓 4401, 같은 쿠키 재연결 거부.
- 프로필 닉네임 우선, 기존 기본 User/`ROOM_NICKNAME_FIELD` 테스트 호환, 개인정보 대체값 차단, 채팅 스냅샷 유지.
- 일정 조회/페이지, 작성자 권한(모집 포함), 시간/텍스트/ID 검증, 생성·수정 겹침 확인, 자기 제외, 취소 일정 제외, 인접 경계 허용.
- 실제 일정 저장 트랜잭션 커밋 이후에만 이벤트 발생, 생성/취소 롤백 시 DB·이벤트 모두 취소. 기존 B의 알림 실패/세션 만료/Origin 테스트 유지.
- 테이블 중복 시작/종료, 이동 전 종료, 정원, 다른 사용자 지정 거부, 다른 테이블 종료로 기존 이용이 바뀌지 않음. 테이블·참여 상태가 Visit/OccupancyState를 변경하지 않음.
- 모집 중복/정원/현재 인원 이하 축소 거부, 미참여 취소, 비활성 모집, 취소·종료 일정 신규 참여 차단, 기존 참여자의 멱등 재시도/취소 허용.
- DB 양수/시간 CHECK와 중복 이용/참여 유일 제약.
- seed 재실행 시 사용자/테이블/일정 중복 없음, 비밀번호·닉네임·사용자가 바꾼 이름/일정 유지, 기존 로그인 ID 충돌 시 전체 롤백.
- PostgreSQL 별도 스레드/연결 동시성: B 입퇴실/채팅 3개 + A 테이블 정원·같은 사용자 재시도·다른 테이블 경쟁, 모집 정원/중복 참여·취소, 정원 축소와 참여 경쟁, 일정 취소와 참여 경쟁, 일정 생성/수정 겹침 경쟁 7개.

## 남은 제한

- SQLite 실행은 PostgreSQL 행 잠금/동시성 보장의 근거가 아닙니다. 동시성 근거는 위 PostgreSQL 실행입니다.
- WebSocket 검증은 Channels `WebsocketCommunicator`를 사용한 실제 ASGI 앱 통합 테스트입니다. 브라우저 UI·실제 TCP/Daphne 네트워크 E2E·HTTPS/프록시 구성은 별도로 검증하지 않았습니다.
- 단일 Daphne/InMemory 채널의 최선형 알림만 지원하며 다중 프로세스 전달·부하/장기 안정성 테스트는 하지 않았습니다.
- idle 소켓은 로그아웃 즉시 push 종료되지 않고 다음 프레임/이벤트 때 인증 재검사합니다. 프론트 로그아웃 시 닫기와 주기 ping이 필요합니다.
- 로그인 시도 제한·계정 복구/회원가입·프로필 편집·테이블 편집·자동 퇴실/이용 만료·보존/탈퇴 정책·배포는 미구현 또는 합의 필요 항목입니다.
- 원격 push·외부 배포·유료 서비스·프론트 신규 개발은 수행하지 않았습니다.

## 데모 프론트 연동 검증 — 2026-11-05

기존 A/B 서비스·모델·마이그레이션·인증 규칙을 유지하고 웹 화면과 경로만 추가했습니다. 이번 변경은 로컬 UI 작업이며 원격 push/외부 배포는 수행하지 않았습니다. 위 2026-11-04의 브라우저 미검증 기록과 구분합니다.

| 이번 실행 | 결과 |
| --- | --- |
| `python manage.py test tests --noinput` | 62개 중 **52개 통과, PostgreSQL 전용 10개 skip**, 실패 없음 |
| `python manage.py makemigrations --check --dry-run` | 변경 없음 |
| `python manage.py check` | 문제 없음 |
| `node --check webui/assets/app.js`, `node --check tests/ui-smoke.mjs` | 문법 검사 통과 |
| `python tests/run_ui_smoke.py` (별도 Playwright 모듈/Chrome 경로 지정) | 실제 HTTP/Daphne/WebSocket 브라우저 통합 테스트 통과 |
| `git diff --check` | 공백 오류 없음 |

연결된 in-app 브라우저가 없어 별도 Headless Chrome의 임시 브라우저 컨텍스트로 검증했습니다. Playwright 도구는 `/private/tmp/koss-room-ui-tools`에 설치했고 프로젝트 런타임 의존성에 추가하지 않았습니다. 테스트 실행마다 임시 SQLite DB를 만들고 `migrate`, 무작위 비밀번호의 `seed_demo`, 임시 포트의 단일 Daphne 서버로 진행했습니다. 기존 `db.sqlite3`와 기존 계정 비밀번호는 변경하지 않았습니다. 테스트 서버와 브라우저는 종료합니다.

실제로 클릭/입력해 확인한 흐름:

- 틀린 비밀번호 오류 → 실제 로그인 → 회전한 CSRF로 변경 요청 → 로그아웃 후 API 401 및 새로고침 후 로그인 화면.
- 독립된 두 브라우저 세션에서 입실/퇴실 인원 실시간 반영, 프로필 닉네임 표시.
- 테이블 이용 시작/종료, 타 계정 목록 조회, 입실 인원과 독립적임 확인.
- 채팅 전송/다른 세션 실시간 수신/중복 없이 표시. `<img ... onerror=...>` 문자열이 HTML 요소가 아닌 텍스트로 표시됨 확인.
- 일정 생성/타 세션 실시간 반영, 겹침 안내 → 명시적 체크 → 저장, 일정 수정/취소.
- 모집 정원 설정, 두 사용자 참여, 참여자 수 이하 정원 축소 오류 표시, 참여 취소, 타 작성자의 수정 버튼 미표시.
- 데스크톱 1440px 및 모바일 390px 화면과 모바일 다이얼로그 스크린샷 확인. 모바일 가로 넘침 없음, 브라우저 JS 예외 없음.

웹 경로 테스트(`tests/test_webui.py`)는 루트 화면/허용 CSS·JS 제공, 임의 파일/없는 경로 404, 변경 메서드 거부를 확인합니다. 브라우저 스크립트는 `tests/run_ui_smoke.py`와 `tests/ui-smoke.mjs`이며 재현 명령은 README에 있습니다.

이번 UI 검증에서 PostgreSQL 동시성 테스트는 다시 실행하지 않았습니다. PostgreSQL 59개 통과 기록은 위 2026-11-04 실행 결과입니다. 브라우저 검증은 Chrome/SQLite 기반이며 다른 브라우저·HTTPS 배포·부하 테스트·모바일 실기기까지 검증한 것은 아닙니다.
