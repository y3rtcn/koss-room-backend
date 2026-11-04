import re
from datetime import datetime, timezone as datetime_timezone

from .http import ApiError


def fields(data, allowed):
    if set(data) - set(allowed):
        raise ApiError("invalid_fields", "허용되지 않은 필드가 있습니다.")


def text(value, name, maximum, *, blank=False):
    if not isinstance(value, str) or len(value) > maximum or (not blank and not value.strip()):
        raise ApiError("invalid_parameter", f"{name}: {'0' if blank else '1'}~{maximum}자 문자열이 필요합니다.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ApiError("invalid_parameter", f"{name}: 유효한 Unicode 문자가 필요합니다.")
    if "\x00" in value:
        raise ApiError("invalid_parameter", f"{name}: NUL 문자는 허용하지 않습니다.")
    return value.strip()


def integer(value, name, minimum=1, maximum=10000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ApiError("invalid_parameter", f"{name}: {minimum}~{maximum} 정수가 필요합니다.")
    return value


def timestamp(value, name):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value
    ):
        raise ApiError("invalid_datetime", f"{name}: 오프셋 포함 ISO 8601 날짜·시간이 필요합니다.")
    try:
        parsed = datetime.fromisoformat(value).astimezone(datetime_timezone.utc)
        if not 2 <= parsed.year <= 9998:
            raise ValueError
        return parsed
    except (ValueError, OverflowError):
        raise ApiError("invalid_datetime", f"{name}: 유효한 날짜·시간이 필요합니다.")


def interval(start, end):
    if start >= end:
        raise ApiError("invalid_interval", "시작 시각은 종료 시각보다 빨라야 합니다.")


def resource_id(value):
    # Bound before passing URL strings to the database's bigint field.
    if not value.isascii() or not value.isdecimal() or len(value) > 19 or not 1 <= int(value) <= 9223372036854775807:
        raise ApiError("not_found", "대상을 찾을 수 없습니다.", 404)
    return int(value)
