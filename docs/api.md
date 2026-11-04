# KOSS ROOM A + B API / WebSocket

Base path: `/api/`. WebSocket: `/ws/room/`. 경로 끝 `/`를 포함합니다. 로그인은 아래 A 인증 API를 사용합니다. 모든 기능 API와 소켓은 활성 로그인 사용자의 Django 세션 쿠키가 필요합니다. `/api/csrf/`와 `/api/auth/login/`만 비로그인 접근을 허용합니다. 로그인도 CSRF 검증을 받습니다.

## 공통 규칙

- HTTP JSON 응답, 시간은 오프셋 포함 ISO 8601(보통 UTC `+00:00`). 날짜별 조회와 통계는 `Asia/Seoul`로 처리합니다.
- 사용자 ID는 커스텀 사용자 PK 대응을 위해 문자열, 방문/메시지 ID는 정수입니다.
- 변경 요청은 세션 쿠키와 `X-CSRFToken`이 필요합니다. `GET /api/csrf/`가 CSRF 쿠키 및 `{"csrf_token":"..."}`을 반환합니다. A 로그인 이후 토큰이 회전할 수 있으므로 다시 가져옵니다.
- JSON 요청 본문은 16 KiB 이하, 채팅은 `Content-Type: application/json`. POST 입퇴실은 본문 없이 사용합니다. 입퇴실 API에 보낸 사용자 ID는 사용하지 않습니다.
- 인증 실패 `401`; CSRF 실패 `403`; 잘못된 요청 `400`; 멱등키 충돌 `409`; 본문 초과 `413`; 잘못된 콘텐츠 타입 `415`; 지원하지 않는 메서드 `405`. CSRF 미들웨어가 먼저 실행되어 비로그인 POST도 CSRF가 없으면 `403`이 될 수 있습니다.
- 기능 API 오류 예시: `{"error":{"code":"authentication_required","message":"로그인이 필요합니다."}}`. 잘못된 Host, 존재하지 않는 경로 등 프레임워크 오류는 JSON 계약에 포함하지 않습니다.
- 예약 예상 인원·일정 참여 인원은 아래 현재 인원에 포함되지 않습니다.
- 날짜는 `0001-01-02`~`9999-12-30` 범위입니다(날짜 경계 계산을 위한 양 끝 제외).

## 입퇴실

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/attendance/me/` | 내 열린 방문 + 현재 인원 |
| GET | `/api/attendance/occupancy/` | 현재 인원·변경 순번 |
| POST | `/api/attendance/check-in/` | 현재 로그인 사용자 입실, 항상 200 |
| POST | `/api/attendance/check-out/` | 현재 로그인 사용자 퇴실, 항상 200 |

입실 응답 예시:

```json
{
  "is_inside": true,
  "active_visit": {"id": 1, "entered_at": "2026-11-02T01:00:00+00:00", "exited_at": null},
  "current_count": 1,
  "revision": 1,
  "changed": true
}
```

반복 입실은 동일 방문을 유지하며 `changed:false`, 인원·revision 유지. 반복 퇴실도 `changed:false`. 퇴실 후 `is_inside:false`, `active_visit:null`. `GET me`는 `changed`를 제외한 같은 구조. `GET occupancy`는 `{"current_count":1,"revision":1}`.

`revision`은 방 전체의 실제 입퇴실 변경마다 증가합니다. 브라우저 종료·WebSocket 단절·일정 참여·자정 경과는 입퇴실을 일으키지 않습니다. 장시간 열린 방문도 별도 보정 정책이 정해지기 전까지 인원에 포함됩니다.

## 채팅 전송과 조회

### POST `/api/chat/messages/`

```json
{"content":"안녕하세요!","client_id":"663b6bd6-4708-4a2b-ac2b-050cf82877f8"}
```

내용은 원문 기준 최대 **500자**(Python Unicode code point), 앞뒤 공백을 제거하며 공백만 있는 메시지, NUL 문자, 유효하지 않은 Unicode는 거부합니다. UUID `client_id`는 사용자별 재시도 키입니다. 같은 키·같은 정규화 내용은 기존 메시지를 반환하고, 다른 내용이면 `409 client_id_conflict`.

첫 저장은 `201`, 재시도는 `200`:

```json
{
  "created": true,
  "message": {
    "id": 12,
    "user_id": "3",
    "nickname": "동아리원",
    "content": "안녕하세요!",
    "client_id": "663b6bd6-4708-4a2b-ac2b-050cf82877f8",
    "created_at": "2026-11-02T01:05:00+00:00"
  }
}
```

닉네임은 `accounts.Profile.nickname`을 우선 사용하며, 프로필이 없으면 허용된 `ROOM_NICKNAME_FIELD`를 조회하고 최종 기본값은 `동아리원`입니다. 이메일·로그인 ID·비밀번호는 대체값으로 사용하지 않습니다. 프론트는 모든 메시지를 텍스트로 렌더링해야 합니다.

### GET `/api/chat/messages/?date=2026-11-02&limit=50`

| 매개변수 | 기본값 | 허용 범위 / 의미 |
| --- | --- | --- |
| `date` | 한국 시간 오늘 | `YYYY-MM-DD`, 해당 날 00:00 이상 다음 날 00:00 미만 |
| `limit` | 50 | 1~100 |
| `before_id` | 없음 | 양의 정수, 해당 ID 이전의 최근 메시지; 과거 페이지 |
| `after_id` | 없음 | 양의 정수, 해당 ID 이후의 오래된 순 메시지; 재접속 복구 |

두 커서는 동시에 사용할 수 없습니다. 모든 응답의 메시지 배열은 ID 오름차순입니다. 커서가 없으면 해당 날짜의 최근 N개를 반환합니다. 0을 커서로 보내지 않습니다. 과거 내역 조회는 커서 없이 최초 조회로 시작합니다.

```json
{
  "date": "2026-11-02",
  "timezone": "Asia/Seoul",
  "messages": [],
  "has_more": false,
  "next_before_id": null,
  "next_after_id": null
}
```

배열 항목은 전송 응답의 `message`와 동일합니다. 다음 페이지가 있을 때 방향에 맞는 `next_before_id` 또는 `next_after_id`를 반환합니다. 복구 루프는 `has_more:false`까지 읽습니다.

**보존 정책(현재 개발안): 자동 삭제 없음, 기간 미확정.** 자정은 조회 날짜만 바꾸며 기존 대화는 DB에 남습니다. 날짜별 무작위 익명 별명·영구 삭제·AI 처리는 구현하지 않습니다. 최종 보존 기간은 팀 합의 후 별도 변경합니다.

## 통계

### GET `/api/analytics/daily/?date=2026-10-31`

날짜 생략 시 한국 시간 오늘. 각 방문을 조회 날짜와 현재 시각까지 잘라 계산합니다. 구간은 `[입실, 퇴실)`이며 같은 시각의 퇴실과 입실은 합산 처리하여 최고 인원을 부풀리지 않습니다.

예: 10:00~10:30 한 명, 10:15~10:45 다른 한 명이면 10시 시간대의 평균은 `(1800 + 1800) / 3600 = 1`, 최고는 2명입니다. 퇴실하지 않은 기록은 `as_of`까지만 반영합니다.

```json
{
  "date": "2026-10-31",
  "timezone": "Asia/Seoul",
  "basis": "button_records",
  "as_of": "2026-11-02T01:10:00+00:00",
  "observed_seconds": 86400.0,
  "visit_count": 2,
  "unique_users": 2,
  "person_seconds": 3600.0,
  "average_count": 0.0417,
  "peak_count": 2,
  "hourly": [
    {"hour": 10, "observed_seconds": 3600.0, "average_count": 1.0, "peak_count": 2}
  ]
}
```

위 `hourly`는 설명을 위해 10시 항목만 발췌했습니다. 실제 응답은 0~23시 **24개**입니다.

- `visit_count`: 관측 구간과 양의 시간으로 겹치는 방문 수(전날 입실 포함, 동일 사용자의 재입실은 별개).
- `unique_users`: 그 방문들의 고유 사용자 수.
- `person_seconds`: 모든 방문의 체류 초 합계.
- `average_count`: `person_seconds / observed_seconds`, 소수 넷째 자리 반올림. 각 상태의 유지 시간을 반영합니다.
- 지나간 구간에 기록이 없으면 평균/최고 0. 아직 관측하지 않은 미래 구간은 평균/최고 `null`, 관측 초 0. 오늘의 진행 중 시간대는 경과한 초만 분모로 사용합니다.
- 하루 전체 평균도 오늘은 자정부터 현재까지의 경과 초가 분모입니다. 미래 날짜는 방문 수 0, 평균/최고 `null`.
- 기록을 통한 실제 입실 통계이며 센서 측정·미래 예측·일정 목적별 통계가 아닙니다.

### GET `/api/analytics/summary/`

```json
{
  "is_dummy": true,
  "source": "fixed_example",
  "uses_ai": false,
  "summary": "[예시] 이용 기록이 쌓이면 시간대별 동아리방 이용 현황을 확인할 수 있습니다."
}
```

## WebSocket `/ws/room/`

Django 세션 쿠키로 인증하며 허용 Origin에서만 연결합니다. 인증 실패는 accept 이전 거부(ASGI close code `4401`, 브라우저는 handshake 403/1006으로 보일 수 있음). Origin 불일치도 handshake 거부. 연결 후 인증 만료는 `4401`, 16 KiB 초과 애플리케이션 프레임은 `1009`로 종료합니다.

연결 직후:

```json
{"type":"connected","data":{"is_inside":false,"active_visit":null,"current_count":0,"revision":0}}
```

클라이언트 전송:

```json
{"type":"chat.send","content":"안녕하세요!","client_id":"663b6bd6-4708-4a2b-ac2b-050cf82877f8"}
```

REST와 같은 검증·멱등키를 사용합니다. 발신자에게 `{"type":"chat.ack","data":{"created":true,"message":{...}}}` 응답. 최초 저장만 전체 연결에 `chat.message` 이벤트를 보냅니다. 발신자도 둘 다 받으므로 메시지 ID로 중복 제거합니다. 재시도면 ack의 `created:false`, 추가 broadcast 없음.

공통 broadcast envelope:

```json
{
  "type": "attendance.updated",
  "event_id": "29215079-4ef5-485a-9ed9-3a90185d94a8",
  "occurred_at": "2026-11-02T01:00:00+00:00",
  "data": {"current_count": 1, "revision": 1}
}
```

| 이벤트 | `data` |
| --- | --- |
| `attendance.updated` | `current_count`, `revision` |
| `chat.message` | `message`: REST와 동일한 저장 메시지 |
| `schedule.changed` | `schedule_id`: 문자열, `action`: created / updated / cancelled |

`event_id`는 전송 UUID이며 DB 재생 커서가 아닙니다. `occurred_at`은 이벤트 생성 시각이고 커밋 이후 전달됩니다. 채팅 식별자는 `message.id`, 인원 정렬 기준은 `revision`입니다.

입퇴실·일정 변경을 소켓 명령으로 받지 않습니다. 입퇴실은 CSRF를 적용한 REST, 일정 변경은 A API를 사용합니다.

`{"type":"ping"}` → `{"type":"pong"}`. 잘못된 JSON, 이진 프레임, 알 수 없는 type, 잘못된 채팅은 `{"type":"error","error":{"code":"...","message":"..."}}`. 내용 검증 실패 시 DB에 저장하지 않습니다.

이벤트 전달은 최선형입니다. 재접속/주기적 HTTP 재조회, 날짜 변경 처리, 세션 만료 처리 세부사항은 [연동 문서](integration.md)를 따릅니다.

## A 공통 규칙

A 변경 요청의 JSON 본문은 `Content-Type: application/json`, 본문이 비어 있는 작업은 `{}`를 보냅니다. 로그아웃은 본문 없이 호출할 수 있습니다. 본문은 16 KiB 이하입니다. 알 수 없는 JSON 필드는 `400 invalid_fields`; 작성자/참여자/이용자는 항상 세션의 `request.user`로 결정합니다. 모든 경로 끝에 `/`를 붙입니다.

`auth.User`를 유지합니다. 사용자 응답은 `{"id":"1","nickname":"데모 다람쥐"}`로 제한하며 이메일·로그인 ID·비밀번호 해시를 반환하지 않습니다. 일정/테이블 ID는 정수, 사용자 ID와 WebSocket `schedule_id`는 문자열입니다. 닉네임은 프로필에 저장하며 현재 편집/회원가입 API는 없습니다. 채팅에는 작성 시 닉네임을 스냅샷으로 저장합니다.

| 상태 | 예시 오류 코드 | 의미 |
| --- | --- | --- |
| 400 | `invalid_parameter`, `invalid_datetime`, `invalid_interval`, `invalid_fields` | 입력·필드 검증 |
| 401 | `authentication_required`, `invalid_credentials` | 미인증, 잘못된 로그인 또는 비활성 사용자 |
| 403 | `csrf_failed`, `permission_denied` | CSRF 또는 작성자 권한 |
| 404 | `not_found` | 없는 일정/테이블, 잘못된 ID |
| 409 | `schedule_overlap`, `schedule_cancelled`, `schedule_closed` | 일정 상태/겹침 충돌 |
| 409 | `table_full`, `already_using_table` | 정원 초과·다른 테이블 이용 중 |
| 409 | `recruitment_disabled`, `recruitment_full`, `capacity_below_count` | 모집 미설정·정원 충돌 |
| 405 / 413 / 415 | `method_not_allowed` / `body_too_large` / `invalid_content_type` | 메서드·본문 크기·콘텐츠 타입 |

기본 오류 형태는 B와 같습니다. 겹침 오류만 선택적인 `error.details`를 추가합니다.

```json
{"error":{"code":"permission_denied","message":"일정 작성자만 변경할 수 있습니다."}}
```

## 로그인·내 정보

| 메서드 | 경로 | 요청 | 성공 |
| --- | --- | --- | --- |
| POST | `/api/auth/login/` | `{"username":"demo-room-a","password":"<직접 설정한 비밀번호>"}` | 200: `user`, 회전한 `csrf_token` |
| POST | `/api/auth/logout/` | 본문 없음 | 200: `{"logged_out":true}` |
| GET | `/api/auth/me/` | 없음 | 200: `{"user":{"id":"1","nickname":"데모 다람쥐"}}` |

최초 로그인 전에도 `/api/csrf/`를 호출하고 `X-CSRFToken`을 보내야 합니다. 로그인 성공은 Django 비밀번호 검증과 세션 로그인으로 처리합니다. 비활성 사용자와 잘못된 비밀번호는 같은 `401 invalid_credentials`입니다. 우회 로그인은 없습니다. 로그인 성공 시 CSRF 쿠키가 회전하므로 로그인 응답의 토큰으로 교체합니다. 기존 토큰은 다음 변경 요청에서 `403`이 됩니다. 로그아웃은 로그인 필요이며 반복 로그아웃은 `401`입니다.

## 일정

| 메서드 | 경로 | 동작 |
| --- | --- | --- |
| GET | `/api/schedules/?start=<ISO>&end=<ISO>&limit=100&offset=0` | 조회 기간과 겹치는 일정(취소 포함) |
| POST | `/api/schedules/` | 생성, 201 |
| GET | `/api/schedules/{id}/` | 상세, 200 |
| PATCH | `/api/schedules/{id}/` | 작성자 부분 수정, 200 |
| POST | `/api/schedules/{id}/cancel/` | 작성자 취소, `{}`, 200 |

조회는 `start`, `end` 필수, 최대 366일, `start < end`입니다. 구간은 `[start,end)`이며 `starts_at < end && ends_at > start`인 항목을 시작 시각·ID 순서로 제공합니다. `limit` 1~100(기본 100), `offset` 0~100000(기본 0). 응답은 `{"schedules":[...],"next_offset":null}`이며 다음 페이지가 있으면 정수 offset입니다. 목록은 조회 시점 데이터이며 동시에 일정이 바뀌면 처음부터 다시 조회하세요. 쿼리의 `+09:00`은 URL 인코딩하거나 `URLSearchParams`를 사용합니다.

생성 예시(예시 날짜가 지났다면 바꾸세요):

```json
{
  "title":"프로젝트 모임",
  "description":"데모 진행 상황 공유",
  "category":"study",
  "starts_at":"2026-11-05T18:00:00+09:00",
  "ends_at":"2026-11-05T19:00:00+09:00",
  "confirm_overlap":false
}
```

`title` 필수 1~120자, `description` 선택 0~4000자(기본 빈 문자열), `category` 선택 1~80자(기본 `general`). 원문 길이 검증 후 양 끝 공백을 제거합니다. Unicode code point 기준이며 NUL/잘못된 Unicode는 거부합니다. `starts_at`, `ends_at`은 필수이며 `YYYY-MM-DDTHH:mm:ss[.ffffff]Z` 또는 `±HH:mm` 오프셋을 사용합니다. UTC 변환 기준 연도 2~9998, 시작은 종료보다 빨라야 합니다. 과거 일정 저장은 가능하지만 종료된 일정에 신규 참여/모집 변경은 불가합니다. 분류는 데모에서 자유 문자열입니다.

생성·상세·수정 응답:

```json
{
  "schedule": {
    "id":1,"title":"프로젝트 모임","description":"데모 진행 상황 공유","category":"study",
    "starts_at":"2026-11-05T09:00:00+00:00","ends_at":"2026-11-05T10:00:00+00:00",
    "author":{"id":"1","nickname":"데모 다람쥐"},"is_cancelled":false,
    "created_at":"2026-11-04T01:00:00+00:00","updated_at":"2026-11-04T01:00:00+00:00",
    "recruitment":{"capacity":null,"participant_count":0,"is_participating":false}
  }
}
```

취소는 `{"schedule":{...},"changed":true}`이며 반복 취소는 `changed:false`입니다. 취소된 일정은 수정/복구할 수 없습니다. 일반 사용자·staff/superuser 모두 작성자만 수정/취소/모집 설정할 수 있으며 관리자 우회 권한은 추가하지 않았습니다.

### 일정 겹침 확인

취소되지 않은 일정에 대해 `[시작,종료)`가 겹치면 생성·수정 모두 거부합니다. 수정 시 자기 자신은 제외하고 끝과 시작이 같은 경계는 허용합니다. 제목만 수정하더라도 현재 다른 일정과 겹치면 확인이 필요합니다.

```json
{
  "error": {
    "code":"schedule_overlap",
    "message":"겹치는 일정을 확인한 뒤 confirm_overlap=true로 다시 요청하세요.",
    "details":{
      "conflicts":[{"id":1,"title":"프로젝트 모임","starts_at":"2026-11-05T09:00:00+00:00","ends_at":"2026-11-05T10:00:00+00:00"}],
      "has_more":false
    }
  }
}
```

프론트는 충돌 일정을 표시하고 사용자가 확인하면 같은 요청에 **boolean** `confirm_overlap:true`를 붙여 재요청합니다. 최대 100개 충돌을 제공하며 이후 항목이 있으면 `has_more:true`입니다. 확인 플래그는 재요청 시점의 모든 겹침을 허용하며 특정 충돌 버전/ID에 묶인 승인 토큰은 아닙니다. 생성 API 자체는 멱등하지 않으므로 네트워크 응답 유실 시 목록 확인 없이 자동 재생성하지 않습니다.

일정 저장/취소/모집 설정/참여 변경은 해당 트랜잭션에서 `notify_schedule_change`를 호출합니다. 일정 생성은 `created`, 취소는 `cancelled`, 수정·모집/참여 변경은 `updated`. 커밋 이후 전달되며 롤백하면 이벤트가 없습니다. 반복 참여/취소/같은 모집 설정에는 추가 이벤트가 없습니다. 프론트는 이벤트를 받은 뒤 상세/목록을 다시 조회합니다.

## 일정 참여 모집

| 메서드 | 경로 | 요청 / 응답 |
| --- | --- | --- |
| GET | `/api/schedules/{id}/recruitment/` | `{"recruitment":{"capacity":4,"participant_count":0,"is_participating":false}}` |
| PUT | `/api/schedules/{id}/recruitment/` | 작성자만 `{"capacity":4}` |
| POST | `/api/schedules/{id}/participation/` | 본인 참여, `{}` |
| DELETE | `/api/schedules/{id}/participation/` | 본인 참여 취소, `{}` |

모집 정원은 1~10000 정수입니다. `capacity:null`은 모집을 끄며 참여자가 0명일 때만 가능합니다. 최초 일정은 모집 미설정 상태입니다. 설정·참여·취소 성공은 모두 200:

```json
{"recruitment":{"capacity":4,"participant_count":1,"is_participating":true},"changed":true}
```

반복 참여/미참여자의 취소는 `changed:false`. 작성자도 직접 참여할 때만 인원에 포함됩니다. 정원 축소는 현재 인원 이상이어야 합니다. 취소되었거나 종료 시각에 도달한 일정은 신규 참여를 거부합니다. 기존 참여자의 재시도는 취소·종료 후에도 멱등 성공하며 본인 참여 취소도 허용합니다. 일정 취소가 기존 참여 기록을 삭제하지 않습니다. 일정 시간 수정도 기존 참여를 유지합니다. 참여 명단/개인정보 공개 API는 없습니다.

## 물리적 테이블

| 메서드 | 경로 | 동작 |
| --- | --- | --- |
| GET | `/api/tables/` | 전체 테이블 ID순 목록 |
| POST | `/api/tables/{id}/use/` | `{}`: 본인 이용 시작 |
| DELETE | `/api/tables/{id}/use/` | `{}`: 해당 테이블의 본인 이용 종료 |

목록 예시:

```json
{"tables":[{"id":1,"name":"테이블 1","capacity":4,"current_count":1,"is_using":true}]}
```

시작/종료는 200 `{"table":{...},"changed":true}`. 같은 테이블의 시작 재시도, 이미 종료한 이용의 종료 재시도는 `changed:false`이며 중복 기록을 만들지 않습니다. 다른 테이블로 이동하려면 먼저 기존 이용을 종료해야 합니다. 이용 중인 테이블과 다른 테이블에 종료 요청을 보내면 현재 이용은 유지하고 `changed:false`입니다. 다른 사용자 ID를 넣은 JSON은 거부합니다.

한 사용자는 동시에 한 테이블만 이용합니다. 정원 초과는 `409 table_full`. 테이블/정원 생성·편집 API는 이번 범위에 없고 `seed_demo`로 준비합니다. 브라우저 종료·로그아웃은 이용 종료가 아닙니다. 명시적 시작/종료가 기준이며 실제 입퇴실 인원과 완전히 독립적입니다. 테이블 전용 실시간 이벤트는 없으므로 변경 후/탭 복귀/주기적으로 목록을 조회합니다.
