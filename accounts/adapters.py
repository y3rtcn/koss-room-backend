from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import JsonResponse


class KookminSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        data = sociallogin.account.extra_data
        email = str(data.get("email", "")).strip().lower()

        verified = (
            data.get("email_verified") is True
            or data.get("verified_email") is True
        )

        allowed = (
            sociallogin.account.provider == "google"
            and verified
            and email.endswith("@kookmin.ac.kr")
            and data.get("hd") == "kookmin.ac.kr"
        )

        if not allowed:
            raise ImmediateHttpResponse(
                JsonResponse(
                    {"error": "국민대학교 Google 계정만 사용할 수 있습니다."},
                    status=403,
                )
            )