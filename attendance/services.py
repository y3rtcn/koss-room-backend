from django.db import transaction
from django.utils import timezone

from realtime.events import publish_after_commit

from .models import OccupancyState, Visit


def serialize_visit(visit):
    if visit is None:
        return None
    return {"id": visit.pk, "entered_at": visit.entered_at.isoformat(),
            "exited_at": visit.exited_at.isoformat() if visit.exited_at else None}


def _snapshot(state, user):
    active = Visit.objects.filter(exited_at__isnull=True)
    visit = active.filter(user=user).first()
    return {"is_inside": visit is not None, "active_visit": serialize_visit(visit),
            "current_count": active.count(), "revision": state.revision}


@transaction.atomic
def status(user):
    state = OccupancyState.objects.select_for_update().get(pk=1)
    return _snapshot(state, user)


@transaction.atomic
def set_presence(user, *, inside):
    # PostgreSQL에서 전체 입퇴실을 직렬화합니다. 사용자별 잠금만으로는
    # 서로 다른 사용자의 동시 변경 시 인원/순번을 일관되게 만들 수 없습니다.
    state = OccupancyState.objects.select_for_update().get(pk=1)
    visit = Visit.objects.filter(user=user, exited_at__isnull=True).first()
    changed = (visit is None) if inside else (visit is not None)
    if changed:
        now = timezone.now()
        if inside:
            Visit.objects.create(user=user, entered_at=now)
        else:
            visit.exited_at = max(now, visit.entered_at)
            visit.save(update_fields=["exited_at"])
        state.revision += 1
        state.save(update_fields=["revision"])
    result = _snapshot(state, user)
    if changed:
        publish_after_commit("attendance.updated", {
            "current_count": result["current_count"], "revision": state.revision,
        })
    return {**result, "changed": changed}
