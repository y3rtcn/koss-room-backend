"""Small same-origin demo UI. Only explicitly listed public assets are served."""
from pathlib import Path

from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

ASSETS = Path(__file__).resolve().parent / "assets"
PUBLIC_FILES = {"app.css": "text/css", "app.js": "text/javascript"}


@require_safe
@never_cache
def index(request):
    return FileResponse((ASSETS / "index.html").open("rb"), content_type="text/html; charset=utf-8")


@require_safe
@never_cache
def asset(request, name):
    if name not in PUBLIC_FILES:
        raise Http404
    return FileResponse((ASSETS / name).open("rb"), content_type=PUBLIC_FILES[name] + "; charset=utf-8")
