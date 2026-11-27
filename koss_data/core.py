"""Explainable registered-participant estimates; no backend imports or writes."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil
import re
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone offset required')
    return result.astimezone(KST)


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid integer')
    return value


@dataclass(frozen=True)
class Config:
    slot_minutes: int = 60
    low: float = .3
    high: float = .6
    min_history_days: int = 4
    freshness_minutes: int = 15
    use_chat: bool = False

    def __post_init__(self):
        if (type(self.slot_minutes) is not int or self.slot_minutes <= 0
                or 1440 % self.slot_minutes or not 0 <= self.low < self.high <= 1
                or self.min_history_days < 2 or self.freshness_minutes <= 0):
            raise ValueError('Invalid configuration')


def normalize(snapshot, space_ids):
    """Drop cancelled rows. A failed participant fetch makes overlapping slots unknown."""
    rows, seen, issues = [], {}, list(snapshot.get('issues', []))
    raw = snapshot.get('schedules')
    if raw is None:
        return [], issues + ['schedules_unavailable'], False
    for row in raw:
        sid = row.get('id')
        if sid in seen:
            if seen[sid] != row:
                raise ValueError('Conflicting duplicate schedule')
            continue
        seen[sid] = row
        try:
            integer(sid, 1)
            integer(row['space_id'], 1)
            if type(row['is_cancelled']) is not bool:
                raise ValueError('Invalid cancellation flag')
            if row['is_cancelled'] or row['space_id'] not in space_ids:
                continue
            left, right = instant(row['starts_at']), instant(row['ends_at'])
            if left >= right:
                raise ValueError('Invalid interval')
            integer(row['expected_count'], 1)  # recruitment limit, never occupancy
        except (KeyError, TypeError, ValueError):
            # Unknown interval may affect any slot: do not silently skip it.
            issues.append('invalid_schedule')
            return [], issues, False
        payload = snapshot.get('participants', {}).get(str(sid))
        users = None
        try:
            if payload is None or payload['schedule_id'] != sid:
                raise ValueError('Missing participants')
            integer(payload['participant_count'])
            users = {p['user_id'] for p in payload['participants']}
            if any(not isinstance(u, str) or not u for u in users):
                raise ValueError('Invalid user ID')
            if len(users) != payload['participant_count']:
                raise ValueError('Participant count mismatch')
            if len(users) > row['expected_count']:
                raise ValueError('Participants exceed recruitment limit')
        except (KeyError, TypeError, ValueError):
            users = None
            issues.append(f'participants_unavailable:{sid}')
        rows.append((left, right, users, sid))
    return rows, issues, True


def slot_count(rows, start, end, complete):
    active = [r for r in rows if r[0] < end and r[1] > start]
    if not complete or any(r[2] is None for r in active):
        return None, len(active)
    # Peak concurrent unique users, rather than union over a whole hour.
    points = {start} | {r[0] for r in active if start < r[0] < end}
    peak = max((len(set().union(*(r[2] for r in active if r[0] <= t < r[1])))
                for t in points), default=0)
    return peak, len(active)


def chat_evidence(messages, now, config):
    result, seen = [], set()
    # Whole-message matching deliberately rejects questions, future plans, tables,
    # subjective language and ambiguous counts such as '우리 3명'. Unverified report.
    pattern = r'지금 동방 전체 인원은 ([0-9]{1,3})명입니다[.!]?'
    for m in messages:
        if m.get('id') in seen:
            continue
        seen.add(m.get('id'))
        try:
            t = instant(m['created_at'])
            match = re.fullmatch(pattern, m['content'].strip())
            if match and 0 <= (now-t).total_seconds() <= config.freshness_minutes*60:
                result.append((t, m['id'], int(match[1])))
        except (ValueError, KeyError, TypeError):
            continue
    return max(result, default=None)


def analyze(snapshot, day, *, capacity, space_ids, room_scope=False,
            history_start=None, now=None, config=None):
    """Return JSON-safe contract. history_start asserts complete historical retention."""
    config = config or Config()
    day = date.fromisoformat(day) if isinstance(day, str) else day
    now = instant(now) if isinstance(now, str) else (now or datetime.now(KST))
    if now.tzinfo is None:
        raise ValueError('now must be timezone aware')
    now = now.astimezone(KST)
    if not space_ids or any(type(s) is not int or s <= 0 for s in space_ids):
        raise ValueError('Explicit space IDs required')
    if capacity is not None:
        integer(capacity, 1)
    rows, issues, complete = normalize(snapshot, set(space_ids))
    spaces = snapshot.get('spaces')
    if spaces is None or not set(space_ids) <= {s['id'] for s in spaces}:
        raise ValueError('Selected spaces must be present in spaces API')
    if history_start is not None:
        history_start = date.fromisoformat(history_start)
        if history_start >= min(day, now.date()):
            raise ValueError('History start must precede target and today')
    # Both target and future dates are excluded to avoid leakage.
    history_days = []
    if history_start:
        d = history_start
        while d < min(day, now.date()):
            if d.weekday() == day.weekday():
                history_days.append(d)
            d += timedelta(days=1)
    attendance = None
    if room_scope and snapshot.get('attendance') is not None:
        try:
            a = snapshot['attendance']
            age = (now-instant(a['observed_at'])).total_seconds()
            if 0 <= age <= config.freshness_minutes*60:
                attendance = integer(a['current_count'])
        except (KeyError, ValueError, TypeError):
            issues.append('invalid_attendance')
    chat = chat_evidence(snapshot.get('messages', []), now, config) if room_scope else None
    output = []
    start = datetime.combine(day, time.min, KST)
    for minute in range(0, 1440, config.slot_minutes):
        left = start + timedelta(minutes=minute)
        right = left + timedelta(minutes=config.slot_minutes)
        reserved, schedule_count = slot_count(rows, left, right, complete)
        samples = []
        for d in history_days:
            hl = datetime.combine(d, left.timetz())
            value, count = slot_count(rows, hl, hl+timedelta(minutes=config.slot_minutes), complete)
            if value is not None:
                samples.append((d, value, count))
        n = len(samples)
        mean = sum(v for _, v, _ in samples)/n if n else None
        recent = [v for _, v, _ in samples[-4:]]
        previous = [v for _, v, _ in samples[-8:-4]]
        trend = (sum(recent)/len(recent)-sum(previous)/len(previous)) if previous and len(recent)==4 else None
        sources = ['timetable'] if reserved is not None else []
        reasons = ['신청자 ID를 중복 제거한 시간대 내 최대 동시 참여 인원입니다.'] if reserved is not None else ['예약 데이터가 불완전하여 인원을 확정할 수 없습니다.']
        # Zero reservations does not establish zero physical occupants.
        estimate = reserved if reserved else None
        if reserved == 0:
            reasons.append('예약 신청자가 없다는 사실은 실제 상주 인원 0명을 의미하지 않습니다.')
        confidence = 'LOW'
        if n >= config.min_history_days and reserved is not None:
            estimate = max(reserved, ceil(mean)) if mean > 0 or reserved > 0 else None
            sources.append('timetable_history')
            confidence = 'MEDIUM' if estimate is not None else 'LOW'
            reasons.append('동일 요일 과거 평균과 현재 신청 인원 중 큰 값을 사용했습니다.')
        current = left <= now < right
        a_count = attendance if current else None
        c_count = chat[2] if current and chat else None
        if a_count is not None:
            estimate = max(estimate or 0, a_count)
            sources.append('attendance')
            reasons.append('현재 입퇴실 버튼 기록과 예약 추정 중 큰 값이며 합산하지 않았습니다.')
            # Button reporting completeness is unvalidated; never high confidence.
            confidence = 'LOW'
        elif config.use_chat and c_count is not None:
            estimate = max(estimate or 0, c_count)
            sources.append('chat_explicit_report')
            confidence = 'LOW'
            reasons.append('최근 명시적 전체 인원 제보를 반영했으나 진위는 미검증입니다.')
        if estimate == 0:
            estimate = None
        ratio = estimate/capacity if estimate is not None and capacity else None
        level = None if ratio is None else ('LOW' if ratio <= config.low else 'MEDIUM' if ratio <= config.high else 'HIGH')
        recommended = level == 'LOW' and confidence == 'MEDIUM' and left >= now
        if estimate is not None and capacity and estimate > capacity:
            confidence, recommended = 'LOW', False
            reasons.append('정원 초과: 예약 중복 또는 기록 오류 확인이 필요합니다.')
        output.append(dict(start_time=left.strftime('%H:%M'), end_time=right.strftime('%H:%M') if right.date()==day else '24:00',
            starts_at=left.isoformat(), ends_at=right.isoformat(), reservation_count=reserved,
            schedule_count=schedule_count, chat_count=c_count, attendance_count=a_count,
            estimated_count=estimate, congestion_ratio=ratio, congestion_level=level,
            recommended=recommended, data_source=sources, confidence=confidence,
            reasons=reasons, history=dict(sample_days=n, mean_count=mean,
                max_count=max((v for _,v,_ in samples), default=None),
                reservation_frequency=sum(c>0 for _,_,c in samples)/n if n else None,
                recent_mean=sum(recent)/len(recent) if recent else None, trend_delta=trend)))
    return dict(schema_version='1.0', date=day.isoformat(), timezone='Asia/Seoul',
        generated_at=now.isoformat(), capacity=capacity, space_ids=sorted(space_ids),
        estimate_basis='registered_participants_proxy', recommendations=output,
        issues=sorted(set(issues)), limitations=['실제 상주 인원 예측 정확도는 검증되지 않았습니다.',
        '과거 신청 내역은 현재 조회 상태이며 당시 취소 전 상태를 복원하지 않습니다.'])
