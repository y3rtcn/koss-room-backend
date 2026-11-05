# A + B · 프론트 연동

## 사용자와 닉네임

기본 `auth.User`를 그대로 사용하고 `accounts.Profile`을 OneToOne으로 추가했습니다. 기존 `auth`/B 마이그레이션은 수정하지 않습니다. 기존 사용자를 강제로 프로필에 백필하지 않으며 프로필 없는 사용자도 로그인하고 B를 사용할 수 있습니다.

표시 닉네임의 명시적 진입점은 `accounts.nicknames.display_nickname(user)`입니다. 프로필 닉네임 → 기존 `ROOM_NICKNAME_FIELD`(기본 `nickname`) → `동아리원` 순서입니다. 로그인 ID·이메일·비밀번호 필드는 대체 표시를 차단합니다. 기존 B의 `ROOM_NICKNAME_FIELD="first_name"` 테스트도 호환됩니다. B 변경은 채팅 서비스에서 이 함수를 호출하도록 한 부분으로 제한했습니다. 채팅에 저장된 닉네임 스냅샷은 프로필 변경으로 바뀌지 않습니다.

회원가입·프로필 편집은 이번 데모 범위에 없습니다. `seed_demo`가 비밀번호 해싱을 사용하는 일반 사용자 2명과 별도 닉네임을 생성합니다. 비밀번호 없는 로그인/사용자 선택 우회 API는 없습니다.

## 브라우저 연결 순서

프론트와 API는 같은 사이트에서 제공하거나 개발 프록시로 `/api/`, `/ws/`를 같은 출처로 연결합니다. 쿠키는 `SameSite=Lax`, 세션은 HttpOnly입니다. 서로 무관한 외부 사이트 간 쿠키 연동을 가정하지 않습니다. 프론트의 실제 Origin을 `WS_ALLOWED_ORIGINS`와 필요시 `CSRF_TRUSTED_ORIGINS`에 **정확히** 등록합니다. CORS `*`, CSRF 예외 처리로 해결하지 않습니다. 예를 들어 프론트가 `http://localhost:5173`이면 프록시의 WebSocket 업그레이드를 켜고 그 Origin을 허용 목록에 추가하세요.

아래 코드는 같은 출처 브라우저 프론트에서 실행하는 예시입니다. 자격 증명은 로그인 폼에서 전달하며 소스에 비밀번호를 넣지 않습니다.

```js
let csrfToken;
let roomSocket;
let heartbeat;

async function refreshCsrf() {
  const response = await fetch('/api/csrf/', { credentials: 'same-origin' });
  if (!response.ok) throw new Error('CSRF 초기화 실패');
  csrfToken = (await response.json()).csrf_token;
}

async function api(path, { method = 'GET', body } = {}) {
  const headers = {};
  if (method !== 'GET') headers['X-CSRFToken'] = csrfToken;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {
    method, headers, credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error?.message || '요청 실패');
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

async function signIn(username, password) {
  await refreshCsrf();
  const result = await api('/api/auth/login/', {
    method: 'POST', body: { username, password },
  });
  csrfToken = result.csrf_token; // 로그인 시 회전한 토큰으로 교체
  return result.user;
}

async function loadRoom() {
  const me = await api('/api/auth/me/');
  const presence = await api('/api/attendance/me/');
  const tables = await api('/api/tables/');
  const start = new Date();
  const end = new Date(start.getTime() + 7 * 86400000);
  const query = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
  const schedules = await api(`/api/schedules/?${query}`);
  return { me, presence, tables, schedules };
}

function connectRoom(onEvent) {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  roomSocket = new WebSocket(`${scheme}//${location.host}/ws/room/`);
  // 브라우저가 로그인 세션 쿠키를 자동 첨부합니다. URL에 토큰을 넣지 않습니다.
  roomSocket.onopen = () => {
    heartbeat = setInterval(() => {
      if (roomSocket.readyState === WebSocket.OPEN) {
        roomSocket.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);
  };
  roomSocket.onmessage = event => onEvent(JSON.parse(event.data));
  roomSocket.onclose = () => clearInterval(heartbeat);
}

async function signOut() {
  await api('/api/auth/logout/', { method: 'POST' });
  clearInterval(heartbeat);
  roomSocket?.close();
  csrfToken = undefined;
}
```

`signIn(로그인폼ID, 로그인폼비밀번호)` → `loadRoom()` → `connectRoom(이벤트처리함수)` 순서로 사용합니다. `connectRoom`은 현재 연결을 종료한 뒤 한 번씩 호출합니다. `401`/소켓 `4401`에서는 로그인 화면으로 돌아가고 상태를 다시 읽습니다. 로그인/계정 전환 후 소켓도 새로 연결합니다. 다른 탭에서 로그인하여 토큰이 회전했다면 `/api/csrf/`를 다시 읽고 사용자 의도를 확인한 뒤 변경 요청을 재시도합니다.

A/B 호출 예시:

```js
await api('/api/attendance/check-in/', { method: 'POST' });
const tables = await api('/api/tables/');
const tableId = tables.tables[0].id;
await api(`/api/tables/${tableId}/use/`, { method: 'POST', body: {} });

const startsAt = new Date(Date.now() + 86400000);
const endsAt = new Date(startsAt.getTime() + 3600000);
const draft = {
  title: '프로젝트 모임', description: '다음 데모 준비', category: 'study',
  starts_at: startsAt.toISOString(), ends_at: endsAt.toISOString(),
};
// 409 schedule_overlap이면 error.data.error.details.conflicts를 화면에 표시합니다.
// 사용자가 확인한 뒤에만 draft.confirm_overlap = true로 다시 요청합니다.
const { schedule } = await api('/api/schedules/', { method: 'POST', body: draft });
await api(`/api/schedules/${schedule.id}/recruitment/`, { method: 'PUT', body: { capacity: 4 } });
await api(`/api/schedules/${schedule.id}/participation/`, { method: 'POST', body: {} });

const message = { content: '안녕하세요!', client_id: crypto.randomUUID() };
await api('/api/chat/messages/', { method: 'POST', body: message });
// 채팅 재시도는 동일 message 객체/UUID를 사용합니다.
await api(`/api/schedules/${schedule.id}/participation/`, { method: 'DELETE', body: {} });
await api(`/api/tables/${tableId}/use/`, { method: 'DELETE', body: {} });
await api('/api/attendance/check-out/', { method: 'POST' });
await signOut();
```

## 트랜잭션과 DB 제약

모든 쓰기는 해당 서비스 함수를 통해 수행합니다. 관리자/다른 앱에서 직접 모델을 수정하면 집계·권한·잠금·알림 규약을 우회할 수 있습니다.

| 대상 | PostgreSQL 잠금 | DB 제약/보장 |
| --- | --- | --- |
| B 입퇴실·채팅 | 기존 `OccupancyState(pk=1)` 잠금 유지 | 열린 방문 유일, 메시지 사용자/UUID 유일, revision·커서 순서 |
| A 일정 생성·수정·취소 | A 전용 `CalendarLock(pk=1)`, 기존 일정 행 순서 | 양의 시간 구간; 겹침 확인과 저장을 직렬화 |
| A 모집 설정·참여·취소 | 같은 Schedule 행 잠금 | `(schedule,user)` 유일, 정원 양수; 잠금 아래 참여 수 검사 |
| A 테이블 시작·종료 | User → 요청 Table 행 순서 | 사용자당 열린 이용 조건부 유일, 정원 양수, 이용 종료 >= 시작 |

정원은 여러 행을 세는 조건이므로 단일 행 CHECK만으로 보장할 수 없습니다. PostgreSQL에서 **모든 해당 서비스 쓰기가 같은 부모 행을 잠근 뒤 개수를 검사**하는 방식으로 정원 초과를 막습니다. 테이블은 사용자 행을 먼저 잠가 서로 다른 테이블로 동시에 보내는 요청도 직렬화합니다. DB 유일 제약은 중복 사용자 기록을 추가로 막습니다. 테이블 정원 수정 API는 없으며 향후 추가할 경우 동일 Table 잠금과 현재 인원 검사 정책이 필요합니다.

일정 생성/수정은 빈 달력에서도 `CalendarLock`을 잠그므로 동시에 겹치는 일정이 두 건 승인되는 문제를 막습니다. 기본은 겹침 거부, `confirm_overlap:true`일 때는 의도적으로 겹침 저장을 허용합니다. 겹침은 이 서비스 수준 정책이며 DB exclusion constraint는 사용하지 않습니다. 모집 설정/참여와 일정 취소가 경쟁하면 일정 행 잠금으로 순서가 정해집니다. 참여가 먼저 완료된 뒤 일정이 취소되는 경우 기존 참여 기록을 유지하는 정책입니다.

SQLite에는 이 행 잠금 보장이 없습니다. 순차 API 기능과 유일/CHECK 제약만 확인할 수 있으며 동시성 테스트는 skip합니다. PostgreSQL 테스트는 별도 연결·동시 시작 barrier로 정원 경쟁, 사용자 단일 이용, 참여 재시도, 정원 축소 경쟁, 취소/참여 경쟁, 일정 생성/수정 겹침 경쟁을 검사합니다.

`CalendarLock`은 새 데이터 마이그레이션에서 생성합니다. 기존 B의 `OccupancyState`나 Visit/Message를 A 코드가 수정하지 않습니다. 테이블 이용/모집 참여는 입실 기록을 만들거나 인원·revision을 변경하지 않습니다.

## 일정 이벤트와 실시간 복구

`schedules.services`에서 권한/입력 검증과 저장을 수행하는 `transaction.atomic` 안에 기존 함수를 연결했습니다.

```python
with transaction.atomic():
    schedule.save()
    notify_schedule_change(schedule_id=schedule.pk, action='created')
```

기존 `transaction.on_commit` 구현을 유지해 롤백 시 알림은 나가지 않습니다. 일정 생성·수정·취소에 각각 `created`/`updated`/`cancelled`, 실제 모집/참여 변경에는 `updated`를 전송합니다. 이벤트에는 일정 ID와 action만 포함하므로 HTTP로 다시 조회하세요. 전송 실패가 이미 커밋된 DB 저장을 실패로 바꾸지 않습니다.

현재 InMemory 채널은 **Daphne 프로세스 하나**에서만 사용합니다. 재시작·채널 용량 초과·단절로 이벤트를 놓칠 수 있으므로 전달 보장은 없습니다. 저장 DB를 기준으로 복구합니다. 소켓 접속/재접속·탭 복귀 시 본인 입퇴실/인원/일정/테이블을 읽고 활성 화면에서는 약 30초마다 HTTP 조회합니다. 테이블 전용 이벤트는 없습니다.

채팅은 마지막으로 **연속 조회 완료한 ID** 이후를 `after_id`로 페이지 끝까지 조회합니다. 가장 큰 실시간 메시지 ID만으로 복구 커서를 올리면 중간 유실을 건너뛸 수 있습니다. 날짜가 바뀌거나 며칠 단절됐다면 날짜별로 읽습니다. 채팅은 HTML 삽입 없이 텍스트로 렌더링합니다.

입퇴실 `revision`이 이미 반영한 값 이하면 무시합니다. 다른 탭에서 상태를 바꿀 수 있으므로 이벤트 수신 시 `/api/attendance/me/`도 조회합니다. 채팅은 `message.id`로 중복 제거하고 ID 오름차순 표시하며 `chat.ack`/`chat.message` 도착 순서에는 의존하지 않습니다.

로그아웃/세션 만료는 다음 소켓 송신 또는 이벤트 수신 시 `4401`로 닫힙니다. 즉시 서버 push 종료 타이머는 없으며 30초 ping으로 유휴 연결도 확인합니다. 브라우저는 로그아웃 성공 시 자체 소켓을 바로 닫아야 합니다. 로그아웃/소켓 단절로 입퇴실·테이블 이용·참여 상태를 자동 종료하지 않습니다.

## 데모 정책과 추가 합의

- 물리적 테이블 가정, 한 사람의 동시 한 테이블 이용, 수동 종료. 테이블 배치/정원 편집 UI·자동 만료는 미정.
- 일정은 자유 분류, 제목/시간 수정 가능, 취소는 영구 상태. 과거 일정 등록과 종료 일정의 일반 수정도 허용하며 기존 참여는 유지. 종료 후 모집 설정/신규 참여는 금지.
- 겹침 확인은 모든 현재 겹침 허용 플래그. 특정 충돌 목록에 대한 버전 확인/재승인 정책은 미정.
- 모집은 일정 하위 기능, 참여 명단 공개 없음, 취소 시 기존 참여 유지. 작성자 자동 참여 없음.
- 관리자에게 별도 수정 권한 없음. 회원가입·닉네임 편집·회원 탈퇴·기록 보존 정책은 추가 합의 필요.
- 채팅 자동 삭제·자동 퇴실·일정 목적별 입실 통계는 없음. AI 요약은 기존 고정 더미.
- 배포/HTTPS/프록시·로그인 시도 제한·여러 프로세스 실시간 전달은 후속 작업. 이번에는 외부 배포나 프론트 UI를 개발하지 않음.
