from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError

User = get_user_model()

PACKAGE_STATUS = (
    ("received", "Received"),
    ("in_warehouse", "In warehouse"),
    ("out_for_delivery", "Out for delivery"),
    ("delivered", "Delivered"),
    ("failed_attempt", "Failed attempt"),
    ("returned", "Returned"),
    ("cancelled", "Cancelled"),
)

DELIVERY_RESULT = (
    ("delivered", "Delivered"),
    ("failed", "Failed"),
)

EVENT_TYPE = (
    ("created", "Created"),
    ("updated", "Updated"),
    ("assigned", "Assigned"),
    ("ofd", "Out for delivery"),
    ("delivered", "Delivered"),
    ("failed", "Failed"),
    ("returned", "Returned"),
)

# Allowed next states for finite-state machine of Package.status
VALID_NEXT_STATUS = {
    "received": {"in_warehouse", "cancelled"},
    "in_warehouse": {"out_for_delivery", "returned"},
    "out_for_delivery": {"delivered", "failed_attempt", "returned"},
    "failed_attempt": {"out_for_delivery", "returned"},
    "delivered": set(),
    "returned": set(),
    "cancelled": set(),
}


class Warehouse(models.Model):
    name = models.CharField(max_length=80)
    address = models.CharField(max_length=180, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "name")
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Warehouse"
        verbose_name_plural = "Warehouses"

    def __str__(self):
        return self.name


class Package(models.Model):
    tracking_number = models.CharField(max_length=64, unique=True)
    speedx_id = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=32, choices=PACKAGE_STATUS, default="received", db_index=True)
    priority = models.IntegerField(default=0)

    recipient_name = models.CharField(max_length=128)
    customer_phone = models.CharField(max_length=32, blank=True)
    addr_street = models.CharField(max_length=160)
    addr_city = models.CharField(max_length=80, db_index=True)
    addr_state = models.CharField(max_length=40, blank=True)
    addr_zip = models.CharField(max_length=16, db_index=True)

    dest_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dest_lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    note = models.CharField(max_length=240, blank=True)
    weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    cod_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    warehouse = models.ForeignKey(
        "packages.Warehouse", on_delete=models.SET_NULL, null=True, blank=True, related_name="packages"
    )
    promised_date = models.DateField(null=True, blank=True)

    assigned_driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_packages"
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    out_for_delivery_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    attempt_count = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Validate that the new status is reachable from the previous one."""
        # If this is an update (has pk), enforce finite-state transition rules
        if self.pk:
            try:
                previous_status = type(self).objects.only("status").get(pk=self.pk).status
            except type(self).DoesNotExist:
                previous_status = None
            # Only validate when the status actually changes
            if previous_status and self.status != previous_status:
                allowed = VALID_NEXT_STATUS.get(previous_status, set())
                if self.status not in allowed:
                    raise ValidationError({
                        "status": f"Transición no permitida: {previous_status} → {self.status}. Permitidos: {sorted(allowed)}"
                    })
        else:
            # New records must start in a consistent state
            if self.status not in {s for s, _ in PACKAGE_STATUS}:
                raise ValidationError({"status": "Estado inválido para nuevo paquete."})

    def allowed_next_statuses(self):
        """Return a sorted list of allowed next statuses from current state."""
        return sorted(VALID_NEXT_STATUS.get(self.status, set()))

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["assigned_driver", "status"]),
            models.Index(fields=["promised_date"]),
            models.Index(fields=["addr_zip"]),
            models.Index(fields=["addr_city"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(attempt_count__gte=0), name="packages_attempt_count_gte_0"),
        ]

    def __str__(self):
        return self.tracking_number


class PackageEvent(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=40, choices=EVENT_TYPE)
    status_from = models.CharField(max_length=32, blank=True)
    status_to = models.CharField(max_length=32)
    at_ts = models.DateTimeField(auto_now_add=True)
    driver = models.ForeignKey("drivers.Driver", null=True, blank=True, on_delete=models.SET_NULL)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-at_ts", "id")
        indexes = [
            models.Index(fields=["package", "-at_ts"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self):
        return f"{self.package.tracking_number} • {self.type} → {self.status_to} @ {self.at_ts:%Y-%m-%d %H:%M}"


class DeliveryAttempt(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="attempts")
    driver = models.ForeignKey("drivers.Driver", on_delete=models.SET_NULL, null=True)
    attempt_no = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    result = models.CharField(max_length=16, choices=DELIVERY_RESULT)
    reason_code = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    at_ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("package", "attempt_no")
        constraints = [
            models.UniqueConstraint(fields=["package", "attempt_no"], name="unique_package_attempt_no"),
        ]
        indexes = [
            models.Index(fields=["package", "attempt_no"]),
            models.Index(fields=["result"]),
        ]

    def __str__(self):
        return f"{self.package.tracking_number} • attempt {self.attempt_no} • {self.result}"


class PodPhoto(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="pod_photos")
    attempt = models.ForeignKey(DeliveryAttempt, on_delete=models.CASCADE, related_name="photos")
    path_local = models.CharField(max_length=255)  # MEDIA_ROOT relative path
    mime_type = models.CharField(max_length=64, blank=True)
    size_bytes = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    checksum = models.CharField(max_length=64, blank=True)
    taken_at = models.DateTimeField(null=True, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lon = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ("-taken_at", "id")
        indexes = [
            models.Index(fields=["package"]),
            models.Index(fields=["attempt"]),
            models.Index(fields=["taken_at"]),
        ]

    def __str__(self):
        return f"POD {self.package.tracking_number} • {self.path_local}"