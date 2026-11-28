# 프론트 배포: 같은 주소에서 제공

프론트 빌드 결과를 이 저장소의 `frontend_dist/`에 넣으면 백엔드 서버가 같은 주소에서 함께 제공합니다. 로그인은 세션 쿠키 방식이라 프론트와 API가 같은 주소여야 로그인이 유지됩니다.

| 접속 경로 | 제공 내용 | 캐시 |
| --- | --- | --- |
| `/` | `frontend_dist/index.html` | `no-cache` (배포 즉시 반영) |
| `/assets/...` | `frontend_dist/assets/` (Vite 해시 파일) | 1년, `immutable` |
| `/favicon.svg` 등 루트 파일 | `frontend_dist/` 바로 아래의 `ico·svg·png·jpg·jpeg·webp·webmanifest·txt` | 1시간 |
| `/api/...`, `/accounts/...`, `/ws/room/` | 기존 백엔드 그대로 | — |

`frontend_dist/index.html`이 없으면 `/`는 "프론트 빌드 파일이 아직 없습니다" 안내와 함께 404입니다. 없는 경로를 `index.html`로 돌려주는 전체 경로 가로채기는 하지 않습니다.

## 빌드 반영 절차

1. 프론트 저장소에서 `npm run build`를 실행합니다.
2. `dist/` **안의 내용**(`index.html`, `assets/` 등)을 이 저장소 `frontend_dist/`에 통째로 덮어씁니다. 예전 `assets/` 파일은 지우고 새로 넣습니다.
3. 브랜치에 커밋하고 PR을 올립니다. `main`에 병합되면 Render가 자동으로 다시 배포합니다(약 2분).

Vite 설정의 `base`는 기본값 `/`를 유지합니다.

## 프론트 코드에서 지킬 것

- **API 주소:** 상대 경로(`/api/...`)로 호출합니다. 같은 주소라 쿠키가 자동으로 붙습니다.
- **WebSocket 주소:** `` `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/room/` ``로 연결합니다.
- **로그인:** `/accounts/google/login/`으로 페이지 이동합니다(fetch 아님). 로그인이 끝나면 `/`로 돌아옵니다.
- **로그아웃:** `/accounts/logout/`에 `POST`(폼 제출, `csrfmiddlewaretoken` 포함)하면 `/`로 돌아옵니다. `GET`으로 열면 확인 화면이 나옵니다.
- **POST·PATCH 요청:** `GET /api/csrf/`로 받은 토큰을 `X-CSRFToken` 헤더에 넣습니다.
- **페이지 주소:** `/schedule`처럼 `/` 아래의 페이지 주소에서 새로고침하면 404입니다. 화면 이동은 `/` 안에서 처리하거나(상태·해시 라우팅), 필요한 주소 목록을 백엔드에 알려 주세요.

## 로그인 화면 템플릿

`templates/`가 앱 기본 템플릿보다 먼저 검색됩니다. allauth 화면을 바꾸려면 같은 경로로 파일을 둡니다.

```text
templates/allauth/layouts/base.html
templates/socialaccount/login.html
templates/koss/auth-style.html
```

`socialaccount/login.html`의 폼은 `POST`와 `{% csrf_token %}`을 유지해야 합니다.

## 배포 후 확인

1. `https://koss-room-backend.onrender.com/`에서 프론트 화면이 열립니다.
2. 국민대 Google 로그인 후 `/`로 돌아옵니다.
3. 새로고침해도 로그인이 유지됩니다(`GET /api/accounts/me/` → 200).
4. 닉네임 설정, 예약 생성·수정·취소·참여가 동작합니다.
5. 두 브라우저에서 채팅·입퇴실·일정 변경 알림이 전달됩니다.
6. 로그아웃 후 `/`로 돌아오고 `/api/accounts/me/`가 401입니다.
