"""프론트 빌드 결과(frontend_dist/)를 같은 주소에서 제공합니다.

- `/`            → frontend_dist/index.html (매번 새로 확인하도록 no-cache)
- `/assets/...`  → frontend_dist/assets/ (Vite가 파일명에 해시를 붙이므로 1년 캐시)
- `/favicon.svg` 같은 루트의 정적 파일 → frontend_dist/ 바로 아래 파일

API·로그인·웹소켓 경로는 건드리지 않으며, 없는 경로를 index.html로 돌려주는
전체 경로 가로채기는 하지 않습니다.
"""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_safe
from django.views.static import serve

NOT_BUILT_HTML = (
    "<!doctype html><meta charset='utf-8'><title>KOSS ROOM</title>"
    "<p>프론트 빌드 파일이 아직 없습니다. frontend_dist/index.html을 추가하세요.</p>"
)


def dist_dir():
    return Path(settings.FRONTEND_DIST_DIR)


@require_safe
def index(request):
    path = dist_dir() / "index.html"
    if not path.is_file():
        return HttpResponse(NOT_BUILT_HTML, status=404)
    response = FileResponse(path.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response


@require_safe
def asset(request, path):
    response = serve(request, path, document_root=dist_dir() / "assets")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@require_safe
def root_file(request, path):
    if path == "index.html":
        raise Http404
    response = serve(request, path, document_root=dist_dir())
    response["Cache-Control"] = "public, max-age=3600"
    return response
