from django.http import JsonResponse

from common.http import api
from .models import Schedule


def schedule_data(schedule):
    return {
        "id": schedule.pk,
        "title": schedule.title,
        "creator_id": str(schedule.creator_id),
        "space_id": schedule.space_id,
        "space_name": schedule.space.name,
        "starts_at": schedule.starts_at.isoformat(),
        "ends_at": schedule.ends_at.isoformat(),
        "expected_count": schedule.expected_count,
        "purpose": schedule.purpose,
        "is_cancelled": schedule.is_cancelled,
    }


@api(["GET"])
def schedule_list(request):
    schedules = (
        Schedule.objects
        .filter(is_cancelled=False)
        .select_related("space")
    )

    return JsonResponse({
        "schedules": [schedule_data(schedule) for schedule in schedules]
    })

# Create your views here.
