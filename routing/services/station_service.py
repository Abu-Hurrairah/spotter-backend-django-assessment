from __future__ import annotations

from django.conf import settings
from pyproj import Transformer
from shapely.geometry import LineString, Point

from routing.models import FuelStation

MILES_PER_METER = 1 / 1609.344


from routing.domain import RouteStation

class StationLocator:

    def __init__(self, corridor_miles: float | None = None):
        self.corridor_miles = corridor_miles or settings.ROUTE_CORRIDOR_MILES
        self.transformer = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)

    def locate(self, route_geometry: dict, route_distance_miles: float) -> list[RouteStation]:
        coordinates = route_geometry.get("coordinates") or []
        if len(coordinates) < 2:
            return []

        route_xy = [self.transformer.transform(lon, lat) for lon, lat in coordinates]
        line = LineString(route_xy)
        projected_length = line.length
        if projected_length <= 0:
            return []

        corridor_meters = self.corridor_miles * 1609.344
        allow_city = settings.ALLOW_CITY_FALLBACK

        query = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        if not allow_city:
            query = query.exclude(geocode_precision="city")

        raw: list[RouteStation] = []
        for row in query.iterator(chunk_size=1000):
            x, y = self.transformer.transform(row.longitude, row.latitude)
            point = Point(x, y)
            perpendicular = line.distance(point)
            if perpendicular > corridor_meters:
                continue
            projected = line.project(point)
            route_mile = (projected / projected_length) * route_distance_miles
            detour_miles = perpendicular * MILES_PER_METER * 2.0
            raw.append(
                RouteStation(
                    station_id=row.id,
                    opis_id=row.opis_id,
                    name=row.truckstop_name,
                    address=row.address,
                    city=row.city,
                    state=row.state,
                    retail_price=float(row.retail_price),
                    latitude=row.latitude,
                    longitude=row.longitude,
                    route_mile=max(0.0, min(route_distance_miles, route_mile)),
                    detour_miles=detour_miles,
                    geocode_precision=row.geocode_precision,
                )
            )

        deduped: dict[tuple, RouteStation] = {}
        for station in raw:
            key = (
                station.opis_id,
                station.name.lower(),
                station.city.lower(),
                station.state,
                round(station.route_mile, 1),
            )
            current = deduped.get(key)
            if current is None or station.retail_price < current.retail_price:
                deduped[key] = station

        return sorted(deduped.values(), key=lambda s: (s.route_mile, s.retail_price))
