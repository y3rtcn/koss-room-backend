from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from attendance.models import OccupancyState
from common.http import ApiError
from realtime.events import publish_after_commit

from .models import Message

KST = ZoneInfo("Asia/Seoul")


def serialize_message(message):
    return {"id": message.pk, "user_id": str(message.user_id), "nickname": message.nickname,
            "content": message.content, "client_id": str(message.client_id),
            "created_at": message.created_at.isoformat()}


@transaction.atomic
def save_message(user, data):
    content, client_id = data.get("content"), data.get("client_id")
    if not isinstance(content, str) or not content.strip() or len(content) > 500:
        raise ApiError("invalid_content", "메시지는 공백만 제외한 1~500자입니다.")
    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        raise ApiError("invalid_content", "유효한 Unicode 문자를 사용하세요.")
    if "\x00" in content:
        raise ApiError("invalid_content", "NUL 문자는 사용할 수 없습니다.")
    if not isinstance(client_id, str):
        raise ApiError("invalid_client_id", "client_id는 UUID 문자열입니다.")
    try:
        client_id = UUID(client_id)
    except ValueError:
        raise ApiError("invalid_client_id", "client_id는 UUID 문자열입니다.")
    nickname = getattr(user, getattr(settings, "ROOM_NICKNAME_FIELD", "nickname"), "")
    nickname = str(nickname).strip()[:150] if nickname else "동아리원"
    content = content.strip()
    # 한 방의 쓰기를 직렬화해 ID 순서와 커밋 순서를 맞춥니다.
    # 그렇지 않으면 after_id 복구 도중 늦게 커밋된 작은 ID를 놓칠 수 있습니다.
    OccupancyState.objects.select_for_update().get(pk=1)
    message, created = Message.objects.get_or_create(
        user=user, client_id=client_id,
        defaults={"content": content, "nickname": nickname, "created_at": timezone.now()},
    )
    if message.content != content:
        raise ApiError("client_id_conflict", "같은 client_id를 다른 메시지에 재사용할 수 없습니다.", 409)
    result = serialize_message(message)
    if created:
        publish_after_commit("chat.message", {"message": result})
    return result, created


def list_messages(day, *, limit=50, before_id=None, after_id=None):
    start = datetime.combine(day, time.min, KST)
    end = start + timedelta(days=1)
    messages = Message.objects.filter(created_at__gte=start, created_at__lt=end)
    if before_id is not None:
        messages = messages.filter(pk__lt=before_id)
    if after_id is not None:
        messages = messages.filter(pk__gt=after_id)
    forward = after_id is not None
    rows = list(messages.order_by("id" if forward else "-id")[:limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    if not forward:
        rows.reverse()
    return {"date": day.isoformat(), "timezone": "Asia/Seoul",
            "messages": [serialize_message(row) for row in rows], "has_more": has_more,
            "next_before_id": rows[0].pk if rows and has_more and not forward else None,
            "next_after_id": rows[-1].pk if rows and has_more and forward else None}
