# 무료 배포: Render(서버) + Neon(PostgreSQL)

서버는 Render 무료 웹 서비스 1개, DB는 Neon 무료 PostgreSQL입니다. 둘 다 카드 없이 GitHub 계정으로 가입할 수 있습니다. 무료 조건은 2026-11-26에 각 공식 문서로 확인했습니다. 진행 전에 다시 확인하세요.

| 서비스 | 무료 조건 | 이 프로젝트에 주는 영향 |
| --- | --- | --- |
| Render 웹 서비스 | 15분 동안 HTTP 요청·WebSocket 메시지가 없으면 잠들고, 다음 요청 때 약 1분 걸려 깨어남. 월 750시간. 파일 시스템은 재시작 때 초기화 | 첫 접속이 느릴 수 있음. SQLite 사용 불가 → Neon 사용 |
| Neon PostgreSQL | 프로젝트당 저장 1GB, 월 100 CU-시간, 5분 유휴 시 일시 정지 후 자동 재개 | 하루 약 50명 규모에 충분. 1GB를 넘기면 쓰기 실패 |

Render 무료 PostgreSQL은 생성 30일 후 만료되므로 쓰지 않습니다.

## 1. Neon에서 DB 만들기

1. https://neon.com 에 가입합니다.
2. **New project**: Postgres 17, 리전 **AWS Asia Pacific (Singapore)** 를 고릅니다. Render 서버도 싱가포르라 지연이 가장 적습니다.
3. 프로젝트 대시보드에서 **Connect**를 누르고 **Connection pooling을 끈** 연결 문자열을 복사합니다.
   `postgresql://사용자:비밀번호@ep-...ap-southeast-1.aws.neon.tech/neondb?sslmode=require...` 형태입니다.
   - 풀러 주소(`-pooler.`)를 넣어도 동작하도록 서버 측 커서를 자동으로 끄지만, 직접 연결을 권장합니다.
   - 이 문자열은 비밀번호를 포함합니다. 레포·단톡방에 올리지 않습니다.

## 2. Render에 서버 배포

1. 이 PR이 `main`에 병합된 뒤 진행합니다. `render.yaml`이 배포할 브랜치에 있어야 합니다.
2. https://render.com 에 GitHub 계정으로 가입하고, Render GitHub 앱에 이 저장소 접근을 허용합니다.
3. **New → Blueprint** → `koss-room-backend` 저장소와 `main` 브랜치를 선택합니다.
4. Render가 `render.yaml`을 읽고 아래 값을 묻습니다.
   - `DATABASE_URL`: 1단계에서 복사한 Neon 연결 문자열
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: Google OAuth 클라이언트 값
   - `DJANGO_SECRET_KEY`는 Render가 자동 생성하고, `DJANGO_DEBUG=0`은 파일에 들어 있습니다.
5. **Apply**로 배포합니다. 빌드 단계에서 의존성 설치와 `migrate`가 실행됩니다.
6. 완료되면 서비스 주소가 생깁니다. 보통 `https://koss-room-backend.onrender.com`이며, 이름이 이미 쓰였으면 뒤에 임의 문자가 붙습니다.

서비스 주소는 Render가 `RENDER_EXTERNAL_HOSTNAME`으로 넣어 주며, 설정이 이를 `ALLOWED_HOSTS`와 `WS_ALLOWED_ORIGINS`에 자동으로 추가합니다. 직접 도메인을 연결하면 그 도메인을 `DJANGO_ALLOWED_HOSTS`, `WS_ALLOWED_ORIGINS` 환경 변수에 추가합니다.

이후 `main`에 푸시할 때마다 자동으로 다시 배포됩니다(`autoDeployTrigger: commit`).

## 3. Google 로그인 콜백 등록

Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → 사용 중인 OAuth 클라이언트 → **승인된 리디렉션 URI**에 추가합니다.

```
https://<서비스 주소>/accounts/google/login/callback/
```

로컬용 `http://127.0.0.1:8000/accounts/google/login/callback/`는 그대로 두어도 됩니다.

## 4. 배포 확인

| 요청 | 기대 결과 |
| --- | --- |
| `GET https://<서비스 주소>/api/csrf/` | `200`, `{"csrf_token":"..."}` |
| `GET https://<서비스 주소>/api/attendance/me/` (비로그인) | `401`, `authentication_required` |
| `http://`로 접속 | `https://`로 이동 |
| 브라우저에서 `/accounts/google/login/` → 국민대 계정 로그인 | 프론트 홈 `/`로 이동, `/api/accounts/me/` 200 |

잠든 상태라면 첫 요청에 약 1분이 걸립니다. Render 대시보드의 **Logs**에서 시작 로그와 오류를 확인합니다.

## 운영 시 주의

- **프로세스 하나만 실행합니다.** 실시간 알림은 메모리 채널이라 인스턴스를 늘리면 서로 다른 인스턴스 사이에 전달되지 않습니다. 재시작·잠들기 때 이벤트를 놓칠 수 있으므로 프론트는 [연동 문서](integration.md)대로 HTTP로 다시 조회합니다.
- **잠들기:** 화면이 열린 동안 프론트가 약 30초마다 `ping`을 보내면 WebSocket 메시지로 활동이 유지됩니다. 모든 탭이 닫히고 15분이 지나면 잠듭니다. 잠들기와 재시작은 퇴실을 의미하지 않습니다.
- **프론트 연결:** 세션 쿠키(`SameSite=Lax`)를 쓰고 CORS를 열지 않았습니다. 다른 도메인(Vercel 등, `localhost` 포함)의 프론트는 이 주소를 직접 호출해 로그인 상태를 유지할 수 없습니다. 프론트 빌드를 같은 도메인에서 함께 제공하는 구성은 별도 작업입니다. 개발 중에는 로컬 백엔드와 개발 서버 프록시를 사용합니다.
- **비밀값**은 Render 대시보드의 Environment에만 둡니다. Neon 비밀번호가 노출되면 Neon에서 비밀번호를 재설정하고 `DATABASE_URL`을 바꿉니다.
