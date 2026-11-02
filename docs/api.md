# 백엔드 B API / WebSocket v1 제안

Base path: `/api/`. WebSocket: `/ws/room/`. 경로 끝 `/`를 포함합니다. 로그인은 A 담당입니다. 모든 기능 API와 소켓은 활성 로그인 사용자의 Django 세션 쿠키가 필요합니다. `/api/csrf/`만 비로그인 접근을 허용합니다.

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

닉네임은 A의 사용자 필드 연동 후 실제 값이 들어갑니다. 현재는 필드가 없으면 `동아리원`. 프론트는 모든 메시지를 텍스트로 렌더링해야 합니다.

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
