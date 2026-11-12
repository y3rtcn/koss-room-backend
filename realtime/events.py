"""A의 저장 트랜잭션 안에서 notify_schedule_change()를 호출합니다."""
import logging
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
ROOM_GROUP = "koss.room"


def publish_after_commit(event_type, data):
    event = {"type": event_type, "event_id": str(uuid4()),
             "occurred_at": timezone.now().isoformat(), "data": data}

    def send():
        try:
            async_to_sync(get_channel_layer().group_send)(
                ROOM_GROUP, {"type": "room.event", "event": event}
            )
        except Exception:
            # DB 쓰기는 이미 성공했습니다. 알림 실패를 HTTP 저장 실패로 바꾸지 않습니다.
            logger.exception("Room notification failed: %s", event_type)

    transaction.on_commit(send)


def notify_schedule_change(*, schedule_id, action):
    if action not in {"created", "updated", "cancelled"}:
        raise ValueError("action must be created, updated, or cancelled")
    publish_after_commit("schedule.changed", {"schedule_id": str(schedule_id), "action": action})
