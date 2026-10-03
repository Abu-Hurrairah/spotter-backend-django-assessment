from django.urls import path
from . import views

urlpatterns = [
    path("api/v1/health/", views.health, name="health"),
    path("api/v1/data/status/", views.data_status, name="data-status"),
    path("api/v1/route/", views.route_api, name="route-api"),
    path("api/v1/routes/<uuid:route_id>/map/", views.route_map, name="route-map"),
]
