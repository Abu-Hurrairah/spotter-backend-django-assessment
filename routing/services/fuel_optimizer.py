from __future__ import annotations

from dataclasses import dataclass
import math

from .exceptions import FuelOptimizationError
from routing.domain import RouteStation


@dataclass(frozen=True)
class FuelLeg:
    from_name: str
    to_name: str
    from_route_mile: float
    to_route_mile: float
    distance_miles: float
    gallons: float
    price_per_gallon: float
    fuel_cost: float


@dataclass(frozen=True)
class FuelPlan:
    total_cost: float
    total_gallons: float
    origin_price_per_gallon: float
    origin_price_basis: str
    stops: list[dict]
    legs: list[dict]


class FuelOptimizer:

    def __init__(self, mpg: float = 10.0, max_range_miles: float = 500.0, start_window_miles: float = 25.0):
        if mpg <= 0 or max_range_miles <= 0:
            raise ValueError("mpg and max_range_miles must be positive")
        self.mpg = mpg
        self.max_range_miles = max_range_miles
        self.start_window_miles = start_window_miles

    def _origin_price(self, stations: list[RouteStation]) -> tuple[float, str]:
        near = [s for s in stations if s.route_mile <= self.start_window_miles]
        if near:
            best = min(near, key=lambda s: s.retail_price)
            return best.retail_price, f"cheapest station within first {self.start_window_miles:g} route miles ({best.name})"
        broader = [s for s in stations if s.route_mile <= min(100.0, self.max_range_miles)]
        if broader:
            best = min(broader, key=lambda s: s.retail_price)
            return best.retail_price, f"fallback: cheapest station within first {min(100.0, self.max_range_miles):g} route miles ({best.name})"
        if stations:
            best = min(stations, key=lambda s: s.route_mile)
            return best.retail_price, f"fallback: first route-adjacent station ({best.name})"
        raise FuelOptimizationError("No geocoded fuel stations are available near this route.")

    def optimize(self, distance_miles: float, stations: list[RouteStation]) -> FuelPlan:
        if distance_miles <= 0:
            raise FuelOptimizationError("Route distance must be positive.")

        origin_price, basis = self._origin_price(stations)

        # Nodes: synthetic origin, every corridor station strictly inside route, synthetic destination.
        station_nodes = [s for s in stations if 0 < s.route_mile < distance_miles]
        station_nodes.sort(key=lambda s: (s.route_mile, s.retail_price))

        nodes = [
            {
                "type": "origin",
                "name": "Trip origin",
                "mile": 0.0,
                "price": origin_price,
                "station": None,
                "detour": 0.0,
            }
        ]
        for station in station_nodes:
            # Penalize city-centroid fallback slightly to prefer exact station geocodes.
            precision_penalty = 2.0 if station.geocode_precision == "city" else 0.0
            nodes.append(
                {
                    "type": "station",
                    "name": station.name,
                    "mile": station.route_mile,
                    "price": station.retail_price,
                    "station": station,
                    "detour": station.detour_miles + precision_penalty,
                }
            )
        nodes.append(
            {
                "type": "destination",
                "name": "Destination",
                "mile": distance_miles,
                "price": 0.0,
                "station": None,
                "detour": 0.0,
            }
        )

        n = len(nodes)
        inf = float("inf")
        best = [inf] * n
        prev: list[int | None] = [None] * n
        best[0] = 0.0
        for i in range(n - 1):
            if math.isinf(best[i]):
                continue
            source = nodes[i]
            for j in range(i + 1, n):
                target = nodes[j]
                road_distance = target["mile"] - source["mile"]
                if road_distance <= 0:
                    continue
                if road_distance > self.max_range_miles:
                    break
                paid_distance = road_distance + source["detour"]
                gallons = paid_distance / self.mpg
                edge_cost = gallons * source["price"]
                candidate = best[i] + edge_cost
                if candidate + 1e-9 < best[j]:
                    best[j] = candidate
                    prev[j] = i

        if math.isinf(best[-1]):
            raise FuelOptimizationError(
                f"No feasible fuel plan found: at least one route gap exceeds the {self.max_range_miles:g}-mile vehicle range. "
                "Geocode more stations or widen the route corridor."
            )

        path = []
        idx = n - 1
        while idx is not None:
            path.append(idx)
            idx = prev[idx]
        path.reverse()

        legs: list[FuelLeg] = []
        stop_payloads: list[dict] = []
        total_gallons = 0.0
        for a, b in zip(path, path[1:]):
            source = nodes[a]
            target = nodes[b]
            distance = target["mile"] - source["mile"]
            paid_distance = distance + source["detour"]
            gallons = paid_distance / self.mpg
            cost = gallons * source["price"]
            total_gallons += gallons
            legs.append(
                FuelLeg(
                    from_name=source["name"],
                    to_name=target["name"],
                    from_route_mile=source["mile"],
                    to_route_mile=target["mile"],
                    distance_miles=distance,
                    gallons=gallons,
                    price_per_gallon=source["price"],
                    fuel_cost=cost,
                )
            )
            if source["type"] == "station":
                s: RouteStation = source["station"]
                stop_payloads.append(
                    {
                        "station_id": s.station_id,
                        "opis_id": s.opis_id,
                        "name": s.name,
                        "address": s.address,
                        "city": s.city,
                        "state": s.state,
                        "latitude": round(s.latitude, 6),
                        "longitude": round(s.longitude, 6),
                        "route_mile": round(s.route_mile, 2),
                        "detour_miles": round(s.detour_miles, 2),
                        "price_per_gallon": round(s.retail_price, 4),
                        "geocode_precision": s.geocode_precision,
                    }
                )

        return FuelPlan(
            total_cost=round(best[-1], 2),
            total_gallons=round(total_gallons, 2),
            origin_price_per_gallon=round(origin_price, 4),
            origin_price_basis=basis,
            stops=stop_payloads,
            legs=[
                {
                    "from": leg.from_name,
                    "to": leg.to_name,
                    "from_route_mile": round(leg.from_route_mile, 2),
                    "to_route_mile": round(leg.to_route_mile, 2),
                    "distance_miles": round(leg.distance_miles, 2),
                    "gallons": round(leg.gallons, 2),
                    "price_per_gallon": round(leg.price_per_gallon, 4),
                    "fuel_cost": round(leg.fuel_cost, 2),
                }
                for leg in legs
            ],
        )
