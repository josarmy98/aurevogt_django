from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()

class Vehicle(models.Model):
    plate = models.CharField(max_length=16, unique=True)
    type = models.CharField(max_length=24, default='car')
    capacity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=24, default='active')
    def __str__(self): return self.plate

class Driver(models.Model):
    # Cada usuario puede ser como mucho un Driver
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='driver_profile')
    license_number = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=24, default='active')
    vehicle = models.OneToOneField(Vehicle,
        null=True, blank=True, on_delete=models.CASCADE, related_name="driver")
    device_os = models.CharField(max_length=24, blank=True)
    device_token = models.CharField(max_length=180, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    # cacheo de última posición para no hacer join a LocationPing en listados/mapa
    last_lat = models.FloatField(null=True, blank=True)
    last_lng = models.FloatField(null=True, blank=True)

    # --- helpers ---
    def latest_ping(self):
        return self.pings.order_by("-captured_at").first()

    def as_map_marker(self):
        return {
            "id": self.id,
            "name": str(self),
            "lat": self.last_lat,
            "lng": self.last_lng,
            "vehicle": self.vehicle.plate if self.vehicle else None,
            "status": self.status,
            "captured_at": self.last_location_at.isoformat() if self.last_location_at else None,
        }

    def __str__(self):
        return self.user.get_full_name() or self.user.username or self.user.email

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["last_location_at"]),
        ]

class LocationPing(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='pings')
    lat = models.FloatField()
    lon = models.FloatField()
    accuracy = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    heading = models.FloatField(null=True, blank=True)
    battery = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    captured_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Ping({self.driver_id}) {self.lat},{self.lon} @ {self.captured_at}"

    class Meta:
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["driver", "captured_at"]),
        ]

@receiver(post_save, sender=LocationPing)
def _update_driver_last_seen(sender, instance, created, **kwargs):
    if created:
        # Mantén timestamp y última posición en Driver para consultas rápidas
        Driver.objects.filter(pk=instance.driver_id).update(
            last_location_at=instance.captured_at or timezone.now(),
            last_lat=instance.lat,
            last_lng=instance.lon,
        )