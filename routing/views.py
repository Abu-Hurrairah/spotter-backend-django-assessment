from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import FuelStation, RouteRun
from .services.exceptions import FuelOptimizationError, RoutingError
from .services.route_service import RouteFuelService

logger = logging.getLogger(__name__)


@require_GET
def health(request: HttpRequest):
    return JsonResponse({"status": "ok", "service": "spotter-fuel-route-api"})


@require_GET
def data_status(request: HttpRequest):
    total = FuelStation.objects.count()
    geocoded = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count()
    return JsonResponse(
        {
            "fuel_station_rows": total,
            "geocoded_rows": geocoded,
            "ungeocoded_rows": total - geocoded,
            "ready_for_route_optimization": geocoded > 0,
        }
    )


@csrf_exempt
def route_api(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

    start = str(payload.get("start", "")).strip()
    finish = str(payload.get("finish", "")).strip()
    if not start or not finish:
        return JsonResponse({"error": "Both 'start' and 'finish' are required."}, status=400)
    if len(start) > 500 or len(finish) > 500:
        return JsonResponse({"error": "Location fields must be 500 characters or fewer."}, status=400)

    try:
        result = RouteFuelService().build(start, finish, request=request)
        return JsonResponse(result, json_dumps_params={"indent": 2})
    except (RoutingError, FuelOptimizationError) as exc:
        logger.warning("Route request failed: %s", exc)
        return JsonResponse({"error": str(exc)}, status=422)
    except Exception:
        logger.exception("Unexpected route error")
        return JsonResponse({"error": "Unexpected server error. Check application logs."}, status=500)


@require_GET
def route_map(request: HttpRequest, route_id):
    run = get_object_or_404(RouteRun, id=route_id)
    return render(
        request,
        "routing/route_map.html",
        {
            "run": run,
            "result_json": json.dumps(run.result_json),
        },
    )
