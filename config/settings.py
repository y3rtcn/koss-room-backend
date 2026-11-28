"""B 앱 실행을 위한 최소 제안 설정. A와 사용자/인증/루트 URL 합의 후 통합."""
import os
from pathlib import Path
from dotenv import load_dotenv

from django.core.exceptions import ImproperlyConfigured

from config.database_url import parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# 기본값은 운영 모드입니다. 로컬 개발은 .env에 DJANGO_DEBUG=1을 넣습니다.
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-development-only-change-before-deploying")
if not DEBUG and SECRET_KEY == "local-development-only-change-before-deploying":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set outside local development")
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
# Render가 자동으로 넣어 주는 서비스 주소(예: koss-room-backend.onrender.com).
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
INSTALLED_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "attendance",
    "chat",
    "accounts",
    "django.contrib.messages",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "spaces",
    "schedules",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True
LANGUAGE_CODE = "ko-kr"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    # 배포(Neon 등): 연결 문자열 하나로 설정합니다. PG* 변수보다 우선합니다.
    DATABASES = {"default": parse_database_url(DATABASE_URL)}
elif DB_ENGINE == "postgresql":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["PGDATABASE"],
        "USER": os.environ["PGUSER"],
        "PASSWORD": os.getenv("PGPASSWORD", ""),
        "HOST": os.getenv("PGHOST", "127.0.0.1"),
        "PORT": os.getenv("PGPORT", "5432"),
        "OPTIONS": {"sslmode": os.getenv("PGSSLMODE", "prefer")},
        "CONN_MAX_AGE": 0,
    }}
elif DB_ENGINE == "sqlite" and DEBUG:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ImproperlyConfigured("Use DB_ENGINE=postgresql outside local development")

# 무료 로컬 MVP: HTTP + WebSocket을 같은 Daphne 프로세스 하나에서 실행해야 합니다.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
WS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "WS_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if origin.strip()
]
if RENDER_EXTERNAL_HOSTNAME:
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in WS_ALLOWED_ORIGINS:
        WS_ALLOWED_ORIGINS.append(render_origin)
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if os.getenv("CSRF_TRUSTED_ORIGINS") else []
CSRF_FAILURE_VIEW = "common.http.csrf_failure"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# 운영(DEBUG=0): HTTPS를 처리하는 프록시(Render 등) 뒤에서 실행한다고 가정합니다.
# 프록시가 X-Forwarded-Proto를 설정해야 Django와 Google 로그인 콜백이 https로 동작합니다.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http" if DEBUG else "https"
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024
# A의 User.nickname 확정 전 임시 표시 필드. 이메일/로그인 ID를 대체 표시하지 않습니다.
ROOM_NICKNAME_FIELD = "nickname"
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # templates/: 프론트가 준비한 로그인 화면(allauth) 템플릿. 앱 기본 템플릿보다 우선합니다.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "OAUTH_PKCE_ENABLED": True,
    },
}

# 로그인·로그아웃 후 프론트 홈으로 돌아갑니다.
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
# 프론트 빌드 결과(npm run build의 dist/ 내용)를 두는 곳. config/frontend.py가 제공합니다.
FRONTEND_DIST_DIR = BASE_DIR / "frontend_dist"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.KookminSocialAccountAdapter"
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_AUTO_SIGNUP = True

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_EMAIL_VERIFICATION = "none"