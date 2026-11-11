from unicodedata import category

from django.http import JsonResponse

from common.http import ApiError, api, json_body


@api(["GET", "PATCH"])
def me(request):
    user = request.user

    if request.method == "PATCH":
        nickname = json_body(request).get("nickname")

        if not isinstance(nickname, str):
            raise ApiError("invalid_nickname", "닉네임을 문자열로 입력하세요.")

        if any(category(char) in {"Cc", "Cs"} for char in nickname):
            raise ApiError("invalid_nickname", "닉네임에 제어 문자를 사용할 수 없습니다.")

        nickname = nickname.strip()
        if not 1 <= len(nickname) <= 30:
            raise ApiError("invalid_nickname", "닉네임은 1~30자로 입력하세요.")

        user.nickname = nickname
        user.save(update_fields=["nickname"])

    return JsonResponse({
        "id": str(user.pk),
        "email": user.email,
        "nickname": user.nickname,
    })