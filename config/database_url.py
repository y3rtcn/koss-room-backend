"""DATABASE_URL(예: Neon 연결 문자열)을 Django DATABASES 항목으로 변환합니다.

외부 패키지 없이 postgres:// / postgresql:// 형식만 지원합니다.
"""
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

POSTGRES_SCHEMES = {"postgres", "postgresql"}


def parse_database_url(url):
    parts = urlsplit(url.strip())
    if parts.scheme not in POSTGRES_SCHEMES:
        raise ImproperlyConfigured("DATABASE_URL must start with postgresql://")
    name = unquote(parts.path.lstrip("/"))
    if not parts.hostname or not name:
        raise ImproperlyConfigured("DATABASE_URL needs a host and a database name")

    options = dict(parse_qsl(parts.query))
    options.setdefault("sslmode", "require")
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname,
        "PORT": str(parts.port or 5432),
        "OPTIONS": options,
        "CONN_MAX_AGE": 0,
    }
    # Neon 풀러(PgBouncer 트랜잭션 모드) 주소에서는 서버 측 커서를 쓸 수 없습니다.
    if "-pooler." in parts.hostname:
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
    return config
