from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from attendance.models import Visit

KST = ZoneInfo("Asia/Seoul")


def peak_count(intervals):
    changes = defaultdict(int)
    for start, end in intervals:
        changes[start] += 1
        changes[end] -= 1
    current = peak = 0
    for instant in sorted(changes):
        current += changes[instant]
        peak = max(peak, current)
    return peak


def daily_statistics(day, *, now=None):
    now = now or timezone.now()
    start = datetime.combine(day, time.min, KST)
    day_end = start + timedelta(days=1)
    observed_end = max(start, min(now, day_end))
    visits = Visit.objects.filter(entered_at__lt=observed_end).filter(
        Q(exited_at__isnull=True) | Q(exited_at__gt=start)
    ).values_list("user_id", "entered_at", "exited_at") if observed_end > start else []
    intervals, users = [], set()
    for user_id, entered_at, exited_at in visits:
        left, right = max(start, entered_at), min(observed_end, exited_at or observed_end)
        if right > left:
            intervals.append((left, right))
            users.add(user_id)
    hours = []
    total_person_seconds = 0
    for hour in range(24):
        left = start + timedelta(hours=hour)
        right = min(left + timedelta(hours=1), observed_end)
        seconds = max(0, (right - left).total_seconds())
        clipped = [(max(left, a), min(right, b)) for a, b in intervals if a < right and b > left and right > left]
        person_seconds = sum((b - a).total_seconds() for a, b in clipped)
        total_person_seconds += person_seconds
        hours.append({"hour": hour, "observed_seconds": seconds,
                      "average_count": round(person_seconds / seconds, 4) if seconds else None,
                      "peak_count": peak_count(clipped) if seconds else None})
    observed_seconds = (observed_end - start).total_seconds()
    return {"date": day.isoformat(), "timezone": "Asia/Seoul", "basis": "button_records",
            "as_of": now.isoformat(), "observed_seconds": observed_seconds,
            "visit_count": len(intervals), "unique_users": len(users),
            "person_seconds": total_person_seconds,
            "average_count": round(total_person_seconds / observed_seconds, 4) if observed_seconds else None,
            "peak_count": peak_count(intervals) if observed_seconds else None,
            "hourly": hours}
