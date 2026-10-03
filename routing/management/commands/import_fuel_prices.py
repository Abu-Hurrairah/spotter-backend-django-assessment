from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from routing.models import FuelStation


class Command(BaseCommand):
    help = "Import the Spotter fuel-price CSV into the database."

    def add_arguments(self, parser):
        parser.add_argument("--csv", dest="csv_path", required=True)
        parser.add_argument("--replace", action="store_true", help="Delete existing fuel rows before importing")

    def handle(self, *args, **options):
        path = Path(options["csv_path"])
        if not path.exists():
            raise CommandError(f"CSV not found: {path}")
        if options["replace"]:
            FuelStation.objects.all().delete()

        created = 0
        skipped = 0
        batch = []
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            required = {"OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Rack ID", "Retail Price"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise CommandError(f"CSV is missing required columns. Found: {reader.fieldnames}")
            for row in reader:
                try:
                    price = Decimal(row["Retail Price"])
                    opis_id = int(float(row["OPIS Truckstop ID"]))
                    rack_raw = row.get("Rack ID", "").strip()
                    rack_id = int(float(rack_raw)) if rack_raw else None
                except (ValueError, InvalidOperation):
                    skipped += 1
                    continue
                batch.append(
                    FuelStation(
                        opis_id=opis_id,
                        truckstop_name=row["Truckstop Name"].strip(),
                        address=row["Address"].strip(),
                        city=row["City"].strip(),
                        state=row["State"].strip().upper()[:2],
                        rack_id=rack_id,
                        retail_price=price,
                    )
                )
                if len(batch) >= 1000:
                    result = FuelStation.objects.bulk_create(batch, ignore_conflicts=True)
                    created += len(result)
                    batch.clear()
            if batch:
                result = FuelStation.objects.bulk_create(batch, ignore_conflicts=True)
                created += len(result)

        self.stdout.write(self.style.SUCCESS(f"Import finished. Attempted/created batch rows: {created}; skipped malformed rows: {skipped}. Total DB rows: {FuelStation.objects.count()}"))
