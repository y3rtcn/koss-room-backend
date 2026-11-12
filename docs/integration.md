# A·프론트엔드 연동 계약

## 공통 기반 제안과 합의할 내용

작업 시작 시 원격 `main`은 `7143435` 초기 커밋이며 README와 `.gitignore`만 있었습니다. 기존 Django 공통 프로젝트·추가 원격 브랜치는 없었습니다. 팀원 초대 상태는 변경하지 않았습니다.

다음은 팀원과 확인할 **제안**입니다.

1. `config` 프로젝트 이름과 루트 URL 구성. A의 기반이 있으면 B 앱을 그 프로젝트로 옮겨 연결합니다.
2. `AUTH_USER_MODEL` 및 닉네임 필드. B는 `settings.AUTH_USER_MODEL`만 참조하며 사용자 모델을 정의하지 않습니다. `ROOM_NICKNAME_FIELD`는 기본 `nickname`; 누락·빈 값은 `동아리원`으로 표시합니다. 이메일·로그인 ID는 닉네임 대용으로 노출하지 않습니다. 닉네임은 메시지 작성 시 저장한 스냅샷입니다.
3. Django 세션 인증과 같은 사이트에서 프론트/API를 제공하는 구성. 현재 `SameSite=Lax`; 임의의 외부 데모 사이트와 바로 쿠키 연동된다는 뜻은 아닙니다. CORS를 전체 허용하지 않았습니다. 개발 프론트는 `/api/`, `/ws/` 프록시를 쓰는 방식을 먼저 협의합니다. 프론트 Origin을 `WS_ALLOWED_ORIGINS`, 필요시 `CSRF_TRUSTED_ORIGINS`에 정확히 등록합니다.
4. 배포 공동 담당·무료 단일 프로세스 구성, 일정 목적별 통계 담당.
5. 퇴실 누락 보정, 메시지/입퇴실 보존 기간, 회원 탈퇴 시 기록 처리. 현재 자동 퇴실·자동 삭제가 없습니다. 사용자 삭제는 `PROTECT`로 기록을 보호합니다. 이 개발안을 최종 보존 정책으로 간주하지 않습니다.

## A 프로젝트에 B 앱 설치

`attendance`, `chat`, `realtime`, `analytics`, `common` 패키지를 사용합니다. `INSTALLED_APPS`에 `daphne`(맨 앞), `attendance`, `chat`, Django auth/contenttypes/sessions를 포함합니다. 기존 `SessionMiddleware`, `CsrfViewMiddleware`, `AuthenticationMiddleware`와 `USE_TZ=True`를 유지합니다. `TIME_ZONE="Asia/Seoul"`로 설정합니다.

`config/settings.py`, `config/urls.py`, `config/asgi.py`는 최소 예시입니다. A 설정을 덮어쓰지 않고 URL include와 ASGI 라우팅을 합칩니다. `CSRF_FAILURE_VIEW`, `CHANNEL_LAYERS`, `WS_ALLOWED_ORIGINS` 등도 확인합니다. 닉네임 필드 설정을 생략해도 기본 `nickname`을 찾습니다.

`python manage.py migrate`를 적용하면 방의 동시 쓰기를 잠그는 `OccupancyState(pk=1)`도 생성됩니다. 임의로 삭제하지 않습니다. 입퇴실 인원·순번은 이 행을 잠근 뒤 계산하고, 한 사용자당 열린 방문은 DB의 조건부 유일 제약으로 제한합니다. 채팅도 이 행 잠금을 사용해 메시지 ID와 커밋 순서가 뒤집혀 재접속 커서가 메시지를 놓치는 일을 방지합니다. 하루 약 50명, 방 하나에 맞춘 단순한 직렬화 방식입니다.

기록은 B 서비스 함수를 통해 수행합니다. 관리자 도구나 다른 코드에서 Visit/Message를 직접 쓰면 알림·순번·잠금 보장을 우회하게 됩니다. DB 유일 제약은 별도로 유지됩니다.

## 일정 변경 알림 호출

A가 일정 생성·수정·취소를 검증하고 저장하는 **같은 트랜잭션 안에서** 호출합니다.

```python
from django.db import transaction
from realtime.events import notify_schedule_change

with transaction.atomic():
    # A 담당: 권한 검사, 겹침 안내/확인 처리, 일정 저장
    schedule.save()
    notify_schedule_change(schedule_id=schedule.pk, action="updated")
```

`action`은 `created`, `updated`, `cancelled`입니다. 함수가 `transaction.on_commit`으로 등록하므로 롤백 시 알림이 나가지 않습니다. 이미 커밋한 뒤 호출해도 전송되지만, 커밋과 호출 사이 프로세스 종료 시 알림을 놓칠 수 있으므로 위 형태를 권장합니다.

B는 일정 모델·권한·시간 겹침 로직을 구현하지 않습니다. 이벤트에는 일정 ID와 작업만 포함하며 프론트는 A의 조회 API로 다시 읽습니다. 목적별 통계도 이번 입퇴실 통계와 별개입니다.

## 무료 MVP의 실시간 전달 제한

한 Daphne 프로세스의 메모리 채널을 사용합니다. 프로세스 재시작, 채널 용량 초과, 연결 단절로 이벤트를 놓칠 수 있으며 전달 보장은 없습니다. 별도 유료 큐나 Redis를 도입하지 않았습니다. 저장 데이터는 PostgreSQL이 기준입니다.

프론트는 연결 성공·재접속·탭 복귀 시 본인 상태/현재 인원/일정과 채팅을 다시 조회합니다. 활성 화면에서는 약 30초마다 상태·채팅을 다시 조회하여 연결이 유지된 상태의 유실도 복구합니다. 채팅은 마지막으로 연속 조회 완료한 ID 이후를 `after_id`로 페이지 끝까지 읽습니다. 단순히 가장 큰 실시간 이벤트 ID로 복구 커서를 올리면 중간에 놓친 메시지를 건너뛸 수 있습니다. 날짜가 바뀌거나 며칠 동안 연결이 끊겼다면 필요한 날짜별로 조회합니다. 메시지는 HTML로 삽입하지 않고 텍스트로 렌더링합니다.

입퇴실 이벤트의 `revision`이 이미 반영한 값 이하라면 무시합니다. 다른 탭에서 내 상태를 변경할 수 있으므로 해당 이벤트 수신 시 `/api/attendance/me/`도 다시 조회합니다. 채팅은 `message.id`로 중복 제거하고 ID 오름차순으로 표시합니다. `chat.ack`와 `chat.message` 도착 순서에는 의존하지 않습니다. 새 전송마다 UUID를 만들고 재시도 시 **같은 UUID와 내용**을 사용합니다.

로그아웃·만료 시 소켓은 다음 송신/이벤트 수신에서 `4401`로 닫힙니다. 프론트에서 약 30초마다 `ping`을 보내면 유휴 연결의 만료도 확인됩니다. 소켓 연결/종료는 입퇴실 기록을 만들거나 종료하지 않습니다.

## 확인한 공식 문서

- [Django 조건부 유일 제약](https://docs.djangoproject.com/en/5.2/ref/models/constraints/)
- [Channels WebSocket Origin 보안](https://channels.readthedocs.io/en/stable/topics/security.html)
- [Django 릴리스 메타데이터](https://pypi.org/pypi/Django/json)

프론트 데모 URL은 이번 도구에서 열리지 않았습니다. 데모를 변경하거나 화면 동작을 확정 요구사항으로 추가하지 않았습니다. 기존 로컬 데모의 모델·소켓·테스트는 읽기만 했으며 전체 복사는 하지 않았습니다.
