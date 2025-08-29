from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

app_name = "drivers"

urlpatterns = [
    # CRUD de drivers
    path("", login_required(views.driver_list), name="list"),
    path("<int:pk>/", login_required(views.driver_detail), name="detail"),
    path("new/", login_required(views.driver_create), name="create"),
    path("<int:pk>/edit/", login_required(views.driver_edit), name="edit"),

    # APIs de geolocalización
    path("api/driver-locations/", views.api_driver_locations, name="api_driver_locations"),
    path("api/driver-locations/ingest/", views.api_ingest_driver_location, name="api_ingest_driver_location"),
]