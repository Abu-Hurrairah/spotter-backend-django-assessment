import uuid
from django.db import models

class FuelStation(models.Model):
    PRECISION_CHOICES = [
        ("exact", "Exact/Address"),
        ("city", "City centroid fallback"),
        ("unknown", "Unknown"),
    ]

    opis_id = models.IntegerField(db_index=True)
    truckstop_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.IntegerField(null=True, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
    geocode_precision = models.CharField(max_length=16, choices=PRECISION_CHOICES, default="unknown")
    geocode_source = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["state", "city"]),
            models.Index(fields=["latitude", "longitude"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["opis_id", "truckstop_name", "address", "city", "state", "rack_id"],
                name="unique_fuel_station_price_row",
            )
        ]

    def __str__(self):
        return f"{self.truckstop_name} - {self.city}, {self.state}"


class GeocodeCache(models.Model):
    query = models.CharField(max_length=500, unique=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    display_name = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class RouteRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    start_text = models.CharField(max_length=500)
    finish_text = models.CharField(max_length=500)
    distance_miles = models.FloatField()
    duration_seconds = models.FloatField(default=0)
    route_geojson = models.JSONField()
    result_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
