from dataclasses import dataclass


@dataclass(frozen=True)
class RouteStation:
    station_id: int
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    retail_price: float
    latitude: float
    longitude: float
    route_mile: float
    detour_miles: float
    geocode_precision: str
