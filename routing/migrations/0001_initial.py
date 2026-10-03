import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opis_id", models.IntegerField(db_index=True)),
                ("truckstop_name", models.CharField(max_length=255)),
                ("address", models.CharField(max_length=255)),
                ("city", models.CharField(db_index=True, max_length=120)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("rack_id", models.IntegerField(blank=True, null=True)),
                ("retail_price", models.DecimalField(decimal_places=4, max_digits=8)),
                ("latitude", models.FloatField(blank=True, db_index=True, null=True)),
                ("longitude", models.FloatField(blank=True, db_index=True, null=True)),
                ("geocode_precision", models.CharField(choices=[("exact", "Exact/Address"), ("city", "City centroid fallback"), ("unknown", "Unknown")], default="unknown", max_length=16)),
                ("geocode_source", models.CharField(blank=True, default="", max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name="GeocodeCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(max_length=500, unique=True)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("display_name", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="RouteRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("start_text", models.CharField(max_length=500)),
                ("finish_text", models.CharField(max_length=500)),
                ("distance_miles", models.FloatField()),
                ("duration_seconds", models.FloatField(default=0)),
                ("route_geojson", models.JSONField()),
                ("result_json", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(fields=["state", "city"], name="routing_fue_state_eea59c_idx"),
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(fields=["latitude", "longitude"], name="routing_fue_latitud_98952a_idx"),
        ),
        migrations.AddConstraint(
            model_name="fuelstation",
            constraint=models.UniqueConstraint(fields=("opis_id", "truckstop_name", "address", "city", "state", "rack_id"), name="unique_fuel_station_price_row"),
        ),
    ]
