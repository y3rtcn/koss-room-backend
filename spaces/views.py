from django.http import JsonResponse

from common.http import api
from .models import Space


@api(["GET"])
def space_list(request):
    spaces = Space.objects.filter(is_active=True)

    return JsonResponse({
        "spaces": [
            {
                "id": space.pk,
                "name": space.name,
                "capacity": space.capacity,
            }
            for space in spaces
        ]
    })

# Create your views here.
