# KOSS ROOM 백엔드

동아리방 관리 프로젝트의 **백엔드 B 구현안**입니다. 공통 Django 프로젝트가 없던 초기 저장소에서 시작했습니다. `config/`는 실행·테스트용 최소 제안이며, 실제 사용자 모델·로그인·루트 URL은 백엔드 A와 합의 후 통합합니다. 프론트엔드 코드는 포함하지 않습니다.

## 구현 범위

| 담당 | 기능 | 현재 상태 |
| --- | --- | --- |
| B | 입실·퇴실, 본인 상태, 현재 인원 | 구현, DB 제약 및 PostgreSQL 행 잠금 |
| B | 인원 알림, 채팅 저장·조회·실시간 전달 | 구현, 세션 인증·Origin 검증·중복 전송 방지 |
| B | 일정 변경 알림 전달 | 호출 함수 구현, A의 저장 코드 연결 필요 |
| B | 시간대별 평균/최대 인원, 더미 요약 | 구현, 한국 시간·시간 가중 평균 |
| A | 사용자·로그인·일정·테이블·참여 모집 | 미구현, 이번 범위에서 제외 |
| 공동 협의 | 배포, 일정 목적별 통계 | 미확정 |

버전: Python **3.12.14**, Django **5.2.18**, Channels **4.3.2**, Daphne **4.2.3**, psycopg **3.3.6**. 대상 DB는 PostgreSQL **17.x**입니다. `requirements.lock.txt`에는 설치 후 확인한 전체 의존성을 고정했습니다. 전역 Python이나 다른 프로젝트 환경을 변경하지 않습니다.

## 빠른 로컬 실행

모든 명령은 저장소 루트에서 실행합니다. 현재 컴퓨터의 경로입니다. 다른 팀원은 자신의 clone 경로로 바꿉니다.

```sh
cd /Users/kimgyutae/orca/koss-room-backend
```

Python 3.12가 설치되어 있다면:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
cp .env.example .env
# .env에는 본인이 작성한 로컬 설정만 넣습니다.
set -a
source .env
set +a
python manage.py migrate
python manage.py check
python manage.py runserver --noreload 127.0.0.1:8000
```

현재 작업 환경에는 `.venv`가 이미 만들어져 있습니다. 이 경우 가상환경 생성·설치는 생략하고 `source .venv/bin/activate`부터 실행할 수 있습니다. 기존 `.env`가 있다면 복사로 덮어쓰지 않고 내용을 비교합니다. `uv` 사용자는 `uv venv --python 3.12.14 .venv`로 전용 환경을 생성할 수도 있습니다.

기본 SQLite는 빠른 기능 확인용입니다. **동시에 들어오는 요청의 정확성은 PostgreSQL에서 보장·검증합니다.** SQLite로 여러 사용자가 동시에 쓰는 공유 서버를 운영하지 않습니다. `.env`는 자동으로 읽지 않으므로 새 터미널에서는 위 `source` 명령을 다시 실행합니다.

HTTP와 WebSocket은 같은 서버에서 동작합니다. 현재 InMemory 채널 설정에서는 **Daphne 프로세스 하나**만 실행합니다. 별도 HTTP 서버/워커로 나누면 실시간 알림이 전달되지 않습니다. 재시작·연결 끊김은 퇴실을 의미하지 않습니다.

로그인은 Google 계정으로만 합니다. 브라우저에서 `/accounts/google/login/`으로 이동하면 되고, 국민대 계정(`@kookmin.ac.kr`)만 허용합니다. 로컬에서는 `.env`에 `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`이 있어야 합니다. 로그인 전에는 인증이 필요한 API가 `401`을 반환하는 것이 정상입니다(CSRF가 없는 POST는 먼저 `403`). 테스트는 Django 테스트 세션으로 로그인 이후 흐름을 검증합니다. 비밀번호 로그인과 데모 로그인은 없습니다.

## PostgreSQL 설정

각자 로컬 PostgreSQL 17 DB와 사용자 계정을 준비합니다. 개발용 DB 사용자는 테스트 DB를 생성할 `CREATEDB` 권한도 필요합니다. 운영 계정에 이 권한을 부여하지 않습니다.

저장소 루트의 `.env`를 본인의 접속 정보로 수정합니다.

```dotenv
DB_ENGINE=postgresql
PGDATABASE=koss_room
PGUSER=koss_room
PGPASSWORD=your-local-password
PGHOST=127.0.0.1
PGPORT=5432
PGSSLMODE=prefer
```

```sh
cd /Users/kimgyutae/orca/koss-room-backend
source .venv/bin/activate
set -a
source .env
set +a
python manage.py migrate
python manage.py test tests --verbosity 2
python manage.py runserver --noreload 127.0.0.1:8000
```

**A가 커스텀 사용자 모델을 사용할 예정이면 공유 DB의 최초 마이그레이션 전에 먼저 확정하세요.** B 외래키·마이그레이션은 `AUTH_USER_MODEL`을 참조합니다. 현재 기본 `auth.User`는 테스트용 기본값이며 팀의 사용자 모델 결정을 대신하지 않습니다. 기존 DB를 임의로 삭제·초기화하지 않습니다.

## 테스트

```sh
cd /Users/kimgyutae/orca/koss-room-backend
source .venv/bin/activate
python manage.py test tests --verbosity 2
python manage.py makemigrations --check --dry-run
python manage.py check
python -m pip check
```

DB 환경 변수에 따라 해당 엔진을 사용합니다. SQLite에서는 PostgreSQL 전용 동시성 테스트가 skip됩니다. PostgreSQL에서는 동일 사용자 동시 입퇴실, 서로 다른 사용자 동시 입퇴실, 동일 메시지 동시 재전송을 포함해 실행합니다. 테스트용 DB는 Django가 만들고 종료 시 정리합니다.

실제 ASGI 라우팅·Origin 검사·세션 쿠키를 통한 WebSocket 연결, 저장 이후 알림, 재접속 조회, 로그아웃·세션 만료, 자정 경계와 통계 계산을 검증합니다. 테스트 계정은 테스트 DB 안에서만 생성합니다.

## 팀원에게 전달할 문서

- [API·WebSocket 명세 및 응답 예시](docs/api.md)
- [A 연동 계약과 합의할 항목](docs/integration.md)
- [검증 결과와 남은 제한](docs/validation.md)
- [무료 배포 절차 (Render + Neon)](docs/deploy.md)
- [프론트 배포: 같은 주소에서 제공](docs/frontend-deploy.md)
- [AI 분석 API 연결](docs/ai-integration.md)

가상환경, DB 파일, `.env`, 실제 비밀번호·토큰은 커밋하지 않습니다. 마이그레이션은 코드와 함께 커밋합니다. 기능 브랜치의 PR을 서로 검토한 후 병합합니다.

배포 설정은 `render.yaml`(Render 무료 웹 서비스)과 `DATABASE_URL`(Neon 무료 PostgreSQL)로 준비했습니다. 가입·대시보드 설정 절차와 무료 조건은 [배포 문서](docs/deploy.md)를 따릅니다. 유료 API는 연결하지 않았습니다. AI 호출 없이 고정 더미 문구만 반환합니다.
