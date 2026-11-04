# KOSS ROOM 데모 백엔드 (A + B)

동아리방 관리 서비스의 Django JSON API입니다. 기존 B의 입퇴실·채팅·통계·WebSocket 계약을 유지하고 A의 세션 로그인·사용자 프로필·일정·물리적 테이블·일정 참여 모집을 통합했습니다. 프론트엔드는 포함하지 않습니다.

| 범위 | 구현 |
| --- | --- |
| A 사용자 | 기본 `auth.User` + `accounts.Profile`, 비밀번호 로그인·로그아웃·내 정보, CSRF |
| A 일정 | 기간 목록·상세·생성·작성자 수정/취소, 겹침 확인 후 저장, 커밋 이후 알림 |
| A 테이블 | 물리적 테이블 정원·이용 인원, 본인 이용 시작/종료, 동시 단일 이용 |
| A 참여 모집 | 일정 작성자의 정원 설정, 본인 참여/취소, 중복·정원·종료 검증 |
| B | 기존 입퇴실·현재 인원/revision·채팅/재전송·통계·더미 요약·실시간 기능 |

버전은 `requirements.lock.txt` 기준입니다: Python **3.12.14**, Django **5.2.18**, Channels **4.3.2**, Daphne **4.2.3**, psycopg **3.3.6**. PostgreSQL 대상이며 SQLite는 로컬 순차 기능 확인용입니다. `TIME_ZONE="Asia/Seoul"`, `USE_TZ=True`를 유지합니다.

## 바로 실행

기존 `.venv`가 있는 작업 저장소에서:

```sh
cd /Users/kimgyutae/orca/koss-room-backend
source .venv/bin/activate
export DB_ENGINE=sqlite
python manage.py migrate
python manage.py seed_demo
# 새 계정이 필요할 때만 비밀번호를 숨김 입력합니다.
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

`seed_demo`는 일반 사용자 `demo-room-a`, `demo-room-b`, 서로 다른 닉네임, 테이블 3개, 생성일 기준 다음 날 18~19시 한국 시간의 예시 일정과 정원 4명 모집을 만듭니다. 작성자를 자동 참여시키지 않습니다. 계정 비밀번호는 명령 실행 시 직접 정하며 코드에 고정값이 없습니다. 비대화형 실행은 별도로 주입한 `KOSS_DEMO_PASSWORD` 환경변수를 사용하고, 비밀번호를 명령 인자나 커밋 파일에 넣지 않습니다.

반복 실행은 고유 `demo_key`로 이미 생성한 데이터를 찾습니다. 기존 비밀번호·닉네임·로그인 ID·테이블·일정·모집 설정을 덮어쓰거나 종료된 예시 일정을 미래로 옮기지 않습니다. 예시 일정이 지났다면 작성자로 새 일정을 생성하세요. 같은 로그인 ID의 기존 비데모 계정과 충돌하면 전체 명령을 롤백합니다. 기존 계정 비밀번호 변경은 별도로 `python manage.py changepassword <로그인ID>`를 명시적으로 실행합니다.

기존 DB는 `migrate`로 확장합니다. 기본 User를 커스텀 User로 교체하거나 기존 DB/마이그레이션을 삭제하지 않습니다. 프로필이 없는 기존 사용자의 표시 닉네임은 `동아리원`입니다. SQLite 파일을 별도로 지정하려면 `SQLITE_PATH=/원하는/경로.sqlite3`를 설정할 수 있습니다.

새 환경에서만 의존성을 준비합니다:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
```

HTTP와 WebSocket을 **Daphne 프로세스 하나**에서 실행합니다. 현재 `InMemoryChannelLayer`는 프로세스 사이 이벤트를 공유하지 않습니다. `python manage.py runserver --noreload 127.0.0.1:8000`도 설치된 Daphne 개발 서버를 사용합니다.

## PostgreSQL 실행과 검사

본 프로젝트 전용 DB와 개발 계정을 준비하고 `.env.example`을 참고해 접속 정보를 설정합니다. 기존 `.env`가 있다면 덮어쓰지 않습니다. `.env`는 자동 로드하지 않습니다.

```sh
source .venv/bin/activate
set -a
source .env
set +a
# .env: DB_ENGINE=postgresql 및 PGDATABASE/PGUSER/PGPASSWORD/PGHOST/PGPORT
python manage.py migrate
python manage.py seed_demo
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

동시 쓰기 보장은 PostgreSQL의 행 잠금과 DB 제약에 기반합니다. SQLite는 `select_for_update` 행 잠금을 제공하지 않으므로 다중 사용자 공유 데모에는 PostgreSQL을 사용하세요. 테스트 계정은 전용 테스트 DB를 생성할 `CREATEDB` 권한이 필요합니다. 다른 프로젝트나 운영 DB를 테스트 대상으로 사용하지 않습니다.

```sh
python manage.py test tests --noinput
python manage.py makemigrations --check --dry-run
python manage.py check
python -m pip check
git diff --check
```

새 테스트도 모두 `tests/`에 있습니다. SQLite에서는 PostgreSQL 전용 동시성 테스트를 skip합니다. 과거 B 31개 결과와 이번 A+B 실행 결과는 [검증 문서](docs/validation.md)에 구분했습니다.

## 프론트 연결과 데모 정책

1. `GET /api/csrf/` → JSON `csrf_token` 보관.
2. 세션/CSRF 쿠키를 유지하며 `POST /api/auth/login/`에 `username`, `password`, `X-CSRFToken` 전송.
3. **로그인 응답의 새 `csrf_token`으로 교체**하거나 `/api/csrf/`를 다시 호출.
4. `/api/auth/me/`, A/B API 호출 및 같은 세션으로 `/ws/room/` 연결.
5. 로그아웃 POST에도 CSRF를 적용하고 프론트의 소켓을 닫음.

완전한 브라우저 요청 예제는 [연동 문서](docs/integration.md), 각 요청·응답·오류는 [API 문서](docs/api.md)에 있습니다. CORS 전체 허용이나 CSRF 비활성화는 사용하지 않습니다.

테이블은 물리적 좌석 테이블이며 입퇴실과 독립적입니다. 참여 모집도 실제 입실 인원에 영향을 주지 않습니다. 로그아웃·브라우저 종료·소켓 단절로 입퇴실/테이블/참여 상태를 자동 종료하지 않습니다. 일정 취소는 되돌릴 수 없으며 기존 참여 기록은 유지하고 신규 참여를 차단합니다. 취소/종료 이후에도 본인 참여 취소는 가능합니다.

추가 합의가 필요한 항목: 회원가입·프로필 편집, 관리자 권한, 일정 분류 목록·겹침 확인 UI, 테이블 배치·정원 관리, 참여 명단 공개 범위, 장기 이용/퇴실 누락 처리, 기록 보존·탈퇴, 배포·로그인 시도 제한. 이번 작업은 로컬 데모 구현이며 외부 배포·유료 서비스·원격 push를 포함하지 않습니다.
