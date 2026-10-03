from django.contrib import admin
from .models import FuelStation, GeocodeCache, RouteRun

@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("truckstop_name", "city", "state", "retail_price", "geocode_precision")
    list_filter = ("state", "geocode_precision")
    search_fields = ("truckstop_name", "city", "address")

admin.site.register(GeocodeCache)
admin.site.register(RouteRun)
