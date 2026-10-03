from __future__ import annotations

import csv
import io
import time
from collections import defaultdict

import requests
from django.core.management.base import BaseCommand, CommandError
from routing.models import FuelStation

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class Command(BaseCommand):
    help = "Geocode fuel stations once, using US Census exact matches plus an optional cached city-centroid fallback."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10000)
        parser.add_argument("--skip-census", action="store_true", help="Skip Census and run only the city fallback on remaining rows.")
        parser.add_argument("--city-fallback", action="store_true", help="Use Nominatim for unmatched unique city/state pairs (rate-limited to ~1 request/sec).")
        parser.add_argument("--max-city-fallback", type=int, default=100)

    def handle(self, *args, **options):
        rows = list(FuelStation.objects.filter(latitude__isnull=True)[: options["limit"]])
        if not rows:
            self.stdout.write(self.style.SUCCESS("All fuel station rows already have coordinates."))
            return

        if not options["skip_census"]:
            self.stdout.write(f"Submitting {len(rows)} rows to the US Census batch geocoder...")
            input_buffer = io.StringIO()
            writer = csv.writer(input_buffer, lineterminator="\n")
            for row in rows:
                writer.writerow([row.id, row.address, row.city, row.state, ""])
            input_bytes = input_buffer.getvalue().encode("utf-8")

            try:
                response = requests.post(
                    CENSUS_BATCH_URL,
                    files={"addressFile": ("fuel_stations.csv", input_bytes, "text/csv")},
                    data={"benchmark": "Public_AR_Current"},
                    timeout=180,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise CommandError(f"Census geocoder request failed: {exc}") from exc

            reader = csv.reader(io.StringIO(response.text))
            updated = 0
            for result in reader:
                if len(result) < 6:
                    continue
                try:
                    station_id = int(result[0].strip().strip('"'))
                except ValueError:
                    continue
                if result[2].strip().lower() != "match":
                    continue
                coords = result[5].strip()
                if "," not in coords:
                    continue
                try:
                    lon_s, lat_s = coords.split(",", 1)
                    lon, lat = float(lon_s), float(lat_s)
                except ValueError:
                    continue
                FuelStation.objects.filter(id=station_id).update(
                    longitude=lon,
                    latitude=lat,
                    geocode_precision="exact",
                    geocode_source="US Census batch geocoder",
                )
                updated += 1
            self.stdout.write(self.style.SUCCESS(f"Census exact/address matches: {updated}"))

        if options["city_fallback"]:
            unmatched = FuelStation.objects.filter(latitude__isnull=True)
            groups = defaultdict(list)
            for row in unmatched.iterator(chunk_size=1000):
                groups[(row.city.strip(), row.state.strip())].append(row.id)

            # Highest-value groups first so a small number of API calls geocodes
            # as many fuel-price rows as possible before a deadline.
            ordered_groups = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
            max_groups = options["max_city_fallback"]
            self.stdout.write(
                f"City fallback enabled; geocoding up to {max_groups} highest-frequency city/state pairs using Nominatim..."
            )
            session = requests.Session()
            session.headers.update({"User-Agent": "spotter-backend-assessment/1.0 (coding assessment)"})
            done_rows = 0
            done_groups = 0
            for (city, state), ids in ordered_groups[:max_groups]:
                try:
                    r = session.get(
                        NOMINATIM_URL,
                        params={"city": city, "state": state, "country": "USA", "format": "jsonv2", "limit": 1},
                        timeout=20,
                    )
                    r.raise_for_status()
                    payload = r.json()
                    if payload:
                        lat = float(payload[0]["lat"])
                        lon = float(payload[0]["lon"])
                        FuelStation.objects.filter(id__in=ids).update(
                            longitude=lon,
                            latitude=lat,
                            geocode_precision="city",
                            geocode_source="Nominatim city centroid fallback",
                        )
                        done_rows += len(ids)
                        done_groups += 1
                except (requests.RequestException, ValueError, KeyError):
                    pass
                time.sleep(1.05)
            self.stdout.write(self.style.SUCCESS(f"City-fallback groups matched: {done_groups}; rows updated: {done_rows}"))

        remaining = FuelStation.objects.filter(latitude__isnull=True).count()
        geocoded = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count()
        self.stdout.write(f"Geocoded rows now: {geocoded}; remaining ungeocoded rows: {remaining}")
