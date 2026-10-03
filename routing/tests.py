from unittest import TestCase

from routing.services.fuel_optimizer import FuelOptimizer
from routing.domain import RouteStation


def station(mile, price, name):
    return RouteStation(
        station_id=int(mile * 10 + price * 100),
        opis_id=int(mile * 10),
        name=name,
        address="US Highway",
        city="Test",
        state="TX",
        retail_price=price,
        latitude=32.0,
        longitude=-97.0,
        route_mile=mile,
        detour_miles=0,
        geocode_precision="exact",
    )


class FuelOptimizerTests(TestCase):
    def test_short_route_needs_no_midroute_stop(self):
        opt = FuelOptimizer(mpg=10, max_range_miles=500, start_window_miles=25)
        plan = opt.optimize(300, [station(10, 3.0, "Near origin")])
        self.assertEqual(plan.stops, [])
        self.assertAlmostEqual(plan.total_gallons, 30.0)
        self.assertAlmostEqual(plan.total_cost, 90.0)

    def test_long_route_selects_feasible_stops(self):
        opt = FuelOptimizer(mpg=10, max_range_miles=500, start_window_miles=25)
        stations = [
            station(10, 3.00, "Origin price source"),
            station(450, 3.50, "A"),
            station(490, 2.50, "B"),
            station(850, 2.70, "C"),
        ]
        plan = opt.optimize(1000, stations)
        names = [s["name"] for s in plan.stops]
        self.assertIn("B", names)
        self.assertLessEqual(max(leg["distance_miles"] for leg in plan.legs), 500)

    def test_raises_when_gap_exceeds_range(self):
        opt = FuelOptimizer(mpg=10, max_range_miles=500, start_window_miles=25)
        with self.assertRaises(Exception):
            opt.optimize(1200, [station(10, 3.0, "Start"), station(600, 3.0, "Too far")])
