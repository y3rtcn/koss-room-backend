from django.http import JsonResponse
from common.http import api, json_body
from common.validation import fields, resource_id
from .services import list_tables, set_use


@api(["GET"])
def tables(request):
    return JsonResponse(list_tables(request.user))


@api(["POST", "DELETE"])
def use(request, table_id):
    fields(json_body(request), set())
    return JsonResponse(set_use(request.user, resource_id(table_id), start=request.method == "POST"))
