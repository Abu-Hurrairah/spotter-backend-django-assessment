from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

from routing.models import GeocodeCache
from .exceptions import GeocodingError, RouteProviderError

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_BASE_URL = "https://router.project-osrm.org"


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float
    label: str


@dataclass(frozen=True)
class RouteData:
    start: Coordinate
    finish: Coordinate
    distance_miles: float
    duration_seconds: float
    geometry: dict[str, Any]


class FreeRoutingClient:

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "spotter-backend-assessment/1.0 (backend coding assessment)",
                "Accept": "application/json",
            }
        )

    @staticmethod
    def _normalize_location(value: str) -> str:
        return " ".join(value.strip().split())

    def geocode_us(self, text: str) -> Coordinate:
        text = self._normalize_location(text)
        if not text:
            raise GeocodingError("Location cannot be empty.")

        cache_key = f"free:geocode:us:{text.lower()}"
        cached = cache.get(cache_key)
        if cached:
            return Coordinate(**cached)

        db_cached = GeocodeCache.objects.filter(query__iexact=text).first()
        if db_cached:
            value = {
                "latitude": db_cached.latitude,
                "longitude": db_cached.longitude,
                "label": db_cached.display_name or text,
            }
            cache.set(cache_key, value, settings.ROUTE_CACHE_SECONDS)
            return Coordinate(**value)

        params = {
            "q": text,
            "countrycodes": "us",
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        try:
            response = self.session.get(NOMINATIM_URL, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GeocodingError(f"Unable to geocode '{text}': {exc}") from exc

        if not payload:
            raise GeocodingError(f"No USA location found for '{text}'.")

        row = payload[0]
        result = Coordinate(
            latitude=float(row["lat"]),
            longitude=float(row["lon"]),
            label=row.get("display_name", text),
        )
        GeocodeCache.objects.update_or_create(
            query=text,
            defaults={
                "latitude": result.latitude,
                "longitude": result.longitude,
                "display_name": result.label,
            },
        )
        cache.set(cache_key, result.__dict__, settings.ROUTE_CACHE_SECONDS)
        time.sleep(1.05)
        return result

    def directions(self, start_text: str, finish_text: str) -> RouteData:
        start = self.geocode_us(start_text)
        finish = self.geocode_us(finish_text)

        route_hash = hashlib.sha256(
            f"{start.longitude:.6f},{start.latitude:.6f}|{finish.longitude:.6f},{finish.latitude:.6f}".encode()
        ).hexdigest()[:24]
        cache_key = f"osrm:route:{route_hash}"
        cached = cache.get(cache_key)
        if cached:
            return RouteData(
                start=start,
                finish=finish,
                distance_miles=cached["distance_miles"],
                duration_seconds=cached["duration_seconds"],
                geometry=cached["geometry"],
            )

        coordinates = (
            f"{start.longitude:.6f},{start.latitude:.6f};"
            f"{finish.longitude:.6f},{finish.latitude:.6f}"
        )
        url = f"{OSRM_BASE_URL}/route/v1/driving/{coordinates}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        }
        try:
            response = self.session.get(url, params=params, timeout=25)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RouteProviderError(f"Routing provider failed: {exc}") from exc

        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise RouteProviderError(
                f"Routing provider returned no route: {payload.get('message') or payload.get('code') or 'unknown error'}"
            )

        route = payload["routes"][0]
        distance_meters = float(route.get("distance", 0))
        if distance_meters <= 0:
            raise RouteProviderError("Routing provider returned an invalid route distance.")

        data = {
            "distance_miles": distance_meters / 1609.344,
            "duration_seconds": float(route.get("duration", 0)),
            "geometry": route["geometry"],
        }
        cache.set(cache_key, data, settings.ROUTE_CACHE_SECONDS)
        return RouteData(start=start, finish=finish, **data)

OpenRouteServiceClient = FreeRoutingClient
