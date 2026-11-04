from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from common.http import ApiError
from .models import Table, TableUse


def serialize(table, user):
    count = getattr(table, "current_count", None)
    mine = getattr(table, "used_by_me", None)
    return {"id": table.pk, "name": table.name, "capacity": table.capacity,
            "current_count": count if count is not None else table.uses.filter(ended_at__isnull=True).count(),
            "is_using": mine if mine is not None else table.uses.filter(user=user, ended_at__isnull=True).exists()}


def list_tables(user):
    query = Table.objects.annotate(current_count=Count("uses", filter=Q(uses__ended_at__isnull=True)),
        used_by_me=Exists(TableUse.objects.filter(table_id=OuterRef("pk"), user=user, ended_at__isnull=True)))
    return {"tables": [serialize(table, user) for table in query.order_by("id")]}


@transaction.atomic
def set_use(user, pk, *, start):
    # All writers lock user -> target table, in this order. User lock serializes
    # requests to different tables; table lock serializes competing occupants.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    try:
        table = Table.objects.select_for_update().get(pk=pk)
    except Table.DoesNotExist:
        raise ApiError("not_found", "테이블을 찾을 수 없습니다.", 404)
    active = TableUse.objects.filter(user=user, ended_at__isnull=True).first()
    changed = False
    if start:
        if active and active.table_id != table.pk:
            raise ApiError("already_using_table", "기존 테이블 이용을 먼저 종료하세요.", 409)
        if active is None:
            if table.uses.filter(ended_at__isnull=True).count() >= table.capacity:
                raise ApiError("table_full", "테이블 정원이 찼습니다.", 409)
            TableUse.objects.create(table=table, user=user, started_at=timezone.now())
            changed = True
    elif active and active.table_id == table.pk:
        active.ended_at = timezone.now()
        active.save(update_fields=["ended_at"])
        changed = True
    return {"table": serialize(table, user), "changed": changed}
