from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from routing.models import RouteRun
from .exceptions import FuelOptimizationError
from .fuel_optimizer import FuelOptimizer
from .routing_provider import FreeRoutingClient
from .station_service import StationLocator


class RouteFuelService:
    def __init__(self):
        self.router = FreeRoutingClient()
        self.optimizer = FuelOptimizer(
            mpg=settings.MPG,
            max_range_miles=settings.MAX_RANGE_MILES,
            start_window_miles=settings.START_PRICE_WINDOW_MILES,
        )

    def _locate_and_optimize(self, geometry: dict, distance_miles: float):
        tried = []
        last_error = None
        for corridor in (settings.ROUTE_CORRIDOR_MILES, 15.0, 30.0, 50.0, 75.0):
            if corridor in tried:
                continue
            tried.append(corridor)
            candidates = StationLocator(corridor_miles=corridor).locate(geometry, distance_miles)
            try:
                plan = self.optimizer.optimize(distance_miles, candidates)
                return candidates, plan, corridor
            except FuelOptimizationError as exc:
                last_error = exc
        raise last_error or FuelOptimizationError("No feasible fuel plan found for this route.")

    def build(self, start: str, finish: str, request=None) -> dict:
        cache_key = f"fuel-route:v2:{start.strip().lower()}::{finish.strip().lower()}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        route = self.router.directions(start, finish)
        candidates, plan, corridor_used = self._locate_and_optimize(route.geometry, route.distance_miles)

        result = {
            "start": {
                "input": start,
                "resolved": route.start.label,
                "latitude": route.start.latitude,
                "longitude": route.start.longitude,
            },
            "finish": {
                "input": finish,
                "resolved": route.finish.label,
                "latitude": route.finish.latitude,
                "longitude": route.finish.longitude,
            },
            "distance_miles": round(route.distance_miles, 2),
            "duration_hours": round(route.duration_seconds / 3600.0, 2),
            "vehicle": {
                "mpg": settings.MPG,
                "max_range_miles": settings.MAX_RANGE_MILES,
                "tank_capacity_gallons": round(settings.MAX_RANGE_MILES / settings.MPG, 2),
            },
            "fuel": {
                "estimated_total_cost": plan.total_cost,
                "estimated_gallons_purchased": plan.total_gallons,
                "origin_price_per_gallon": plan.origin_price_per_gallon,
                "origin_price_basis": plan.origin_price_basis,
                "selected_stops": plan.stops,
                "legs": plan.legs,
            },
            "station_candidates_considered": len(candidates),
            "route_corridor_miles_used": corridor_used,
            "routing_provider": "OSRM (one route call per uncached request)",
            "endpoint_geocoder": "OpenStreetMap Nominatim (cached)",
            "assumptions": [
                "Vehicle fuel economy is fixed at 10 MPG unless configured otherwise.",
                "Maximum driving range is fixed at 500 miles unless configured otherwise.",
                "Origin fuel price is estimated from the cheapest route-adjacent station near the start because the assignment does not provide starting fuel level or origin fuel price.",
                "Fuel optimization uses a cost-weighted shortest path over route-adjacent stations; each selected stop buys enough fuel to reach the next selected stop.",
                "Station detour mileage is approximated from perpendicular distance to the route; exact-address geocodes are preferred over city-centroid fallbacks.",
            ],
            "route_geojson": route.geometry,
        }

        run = RouteRun.objects.create(
            start_text=start,
            finish_text=finish,
            distance_miles=route.distance_miles,
            duration_seconds=route.duration_seconds,
            route_geojson=route.geometry,
            result_json=result,
        )
        map_path = reverse("route-map", kwargs={"route_id": run.id})
        result["route_id"] = str(run.id)
        result["map_url"] = request.build_absolute_uri(map_path) if request else map_path
        run.result_json = result
        run.save(update_fields=["result_json"])
        cache.set(cache_key, result, settings.ROUTE_CACHE_SECONDS)
        return result
