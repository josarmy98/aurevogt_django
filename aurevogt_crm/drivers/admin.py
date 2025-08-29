from django.contrib import admin
from .models import Driver, Vehicle, LocationPing

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("user", "license_number", "status", "last_location_at")
    list_filter = ("status",)
    # ← Necesario para que PackageAdmin.autocomplete_fields funcione
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "license_number",
    )

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate", "type", "capacity", "status")
    list_filter = ("status", "type")
    search_fields = ("plate",)

@admin.register(LocationPing)
class LocationPingAdmin(admin.ModelAdmin):
    list_display = ("driver", "lat", "lon", "captured_at", "speed", "battery")
    list_filter = ("captured_at",)
    search_fields = ("driver__user__email",)