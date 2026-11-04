from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist


def display_nickname(user):
    """Profile first, legacy configured field second; never expose login identifiers."""
    try:
        value = user.room_profile.nickname
    except (ObjectDoesNotExist, AttributeError):
        value = None
    if not isinstance(value, str) or not value.strip():
        field = getattr(settings, "ROOM_NICKNAME_FIELD", "nickname")
        value = "" if field in {"username", "email", "password", "USERNAME_FIELD"} else getattr(user, field, "")
    return value.strip()[:150] if isinstance(value, str) and value.strip() else "동아리원"
