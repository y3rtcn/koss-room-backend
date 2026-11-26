# 검증 결과와 남은 연결 작업

검증일: 2026-11-02. Python 3.12.14 / Django 5.2.18 / Channels 4.3.2 / Daphne 4.2.3 / psycopg 3.3.6.

## 실행 결과

| 검증 | 결과 |
| --- | --- |
| SQLite `python manage.py test tests` | 28개 통과, PostgreSQL 전용 3개 skip |
| PostgreSQL 17.7 `python manage.py test tests --verbosity 2 --noinput` | **31개 모두 통과**, skip 없음 |
| `python manage.py makemigrations --check --dry-run` | 모델과 마이그레이션 일치 |
| `python manage.py check` | 문제 없음 |
| `python -m pip check` | 의존성 문제 없음 |
| `git diff --check` | 공백 오류 없음 |

PostgreSQL 공식 17.7 소스를 `/private/tmp`에서 빌드해 임시 DB 서버(127.0.0.1:55432)로 검증했습니다. 시스템 PostgreSQL 설치·다른 프로젝트 DB·전역 Python 환경은 변경하지 않았습니다. 테스트 DB는 테스트 종료 시 삭제하고, 임시 DB 서버는 검증 후 중지했습니다. 이 임시 바이너리는 개발용 DB 설치를 대신하지 않으며, 배포 버전 선택 시 최신 보안 패치를 다시 확인합니다.

## 주요 검증 범위

- 같은 사용자의 중복/동시 입실·퇴실, 서로 다른 사용자의 동시 입퇴실 시 일관된 인원·revision.
- DB가 열린 방문 중복과 역전된 입퇴실 시간을 직접 거부.
- CSRF, 비로그인 차단, 본문으로 다른 사용자 지정 불가.
- 채팅 저장, 동일 UUID의 재전송·동시 재전송, 키와 내용 충돌, 길이·JSON·Unicode 검증.
- 한국 시간 자정 경계, 이전/이후 ID 페이지 조회, 닉네임 스냅샷.
- 실제 ASGI 라우터를 통한 세션 쿠키 인증, Origin 거부, 소켓 송수신, 연결 종료 후 입실 유지, 재접속 후 저장 대화 조회.
- 로그아웃·세션 만료 이후 소켓 송수신 차단.
- DB 커밋 후 알림, 롤백 시 알림 취소, 알림 실패 시 저장 데이터 유지.
- A의 일정 알림 어댑터 호출 및 롤백 처리.
- 시간 가중 평균, 최대 동시 인원, 동일 시각 입퇴실, 자정 넘김, 열린 방문, 빈 날짜와 미래 날짜.
- 고정 더미 요약의 예시/비AI 표시.

B의 연결 흐름은 `tests/test_realtime.py`의 `test_full_authenticated_flow_and_reconnect`가 검증합니다. 테스트 세션으로 로그인한 뒤 입실 → 인원 이벤트 → 소켓 채팅·저장 → 재접속·HTTP 대화 복구 → 퇴실 → 통계 조회를 수행합니다.

## 배포 설정 검증 (2026-11-26)

`render.yaml`의 빌드·시작 명령을 Render와 같은 환경 변수(`DJANGO_DEBUG=0`, 생성한 `DJANGO_SECRET_KEY`, `DATABASE_URL`, `RENDER_EXTERNAL_HOSTNAME`, `PORT`)로 로컬 임시 PostgreSQL 16.15에 대해 실행했습니다. Render·Neon 실제 계정에서는 아직 실행하지 않았습니다.

| 검증 | 결과 |
| --- | --- |
| `DATABASE_URL`로 PostgreSQL 전체 `python manage.py test` | 102개 모두 통과, skip 없음 |
| SQLite 전체 `python manage.py test` | 통과, PostgreSQL 전용 5개 skip |
| 빌드 명령(의존성 설치 + `migrate`) | 성공 |
| `python manage.py check --deploy` | HSTS 하위 도메인·preload 경고 2개만 (`onrender.com` 하위 주소라 적용하지 않음) |
| 프록시 HTTPS 헤더로 `GET /api/csrf/` | `200` |
| HTTPS 헤더 없는 요청 | `301` → `https://` |
| 비로그인 `GET /api/attendance/me/` | `401 authentication_required` |
| 등록되지 않은 Host | `400` |
| `/accounts/google/login/` | `200` |
| WebSocket: 다른 Origin / 세션 없음 | 둘 다 handshake `403` |
| WebSocket: 서비스 Origin + 세션 | `connected` 수신 |
| CSRF 포함 입실 → 소켓 `attendance.updated` → 소켓 채팅 `chat.ack`·`chat.message` → 퇴실 | 모두 정상 |
| CSRF 없는 POST | `403 csrf_failed` |

## 아직 확인하지 않은 것

- A가 구현할 실제 로그인·커스텀 사용자 모델·닉네임, 일정 저장 코드와의 통합. 테스트는 Django 기본 사용자 및 테스트 로그인 세션을 사용합니다.
- 프론트엔드 브라우저와의 실제 통합. 기존 데모는 수정하지 않았으며 화면 QA는 하지 않았습니다.
- Render·Neon 실제 계정에서의 배포와 Google 로그인 콜백. 절차는 [배포 문서](deploy.md)에 있습니다. 다른 도메인 프론트를 위한 CORS는 열지 않았습니다.
- 여러 서버/프로세스의 실시간 전달. 현재는 한 Daphne 프로세스의 메모리 채널입니다.
- 퇴실 누락 보정, 자동 보존기간·회원 탈퇴 정책, 일정 목적별 통계 담당 결정.

공통 설정과 사용자 모델을 A와 합의하기 전까지 검토용 구현안으로 취급합니다. 상세 계약은 [연동 문서](integration.md)를 참고합니다.
