from django.db import models
from django.conf import settings

class ImportBatch(models.Model):
    SOURCE_CHOICES = (("speedx_csv","SpeedX CSV"),
                      ("speedx_api","SpeedX API"),
                      ("manual","Manual"))
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    file_name = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    imported_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="processing")  # processing|done|failed
    total_records = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    report_path = models.CharField(max_length=255, blank=True)  # CSV con errores

    class Meta:
        ordering = ("-imported_at",)
        indexes = [models.Index(fields=["imported_at"]), models.Index(fields=["status"])]

    def __str__(self):
        return f"Import {self.id} {self.source} {self.file_name}"

class ImportErrorRow(models.Model):
    batch = models.ForeignKey(ImportBatch, related_name="errors", on_delete=models.CASCADE)
    row_number = models.IntegerField()
    payload = models.JSONField(default=dict)
    error = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class TruckReceipt(models.Model):
    """Recibo de camión con un código/QR para identificar la descarga."""
    code = models.CharField(max_length=40, unique=True)  # ej: TRK-2024-08-27-XYZ
    warehouse = models.ForeignKey("packages.Warehouse", on_delete=models.PROTECT, related_name="truck_receipts")
    eta = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    total_packages = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

class TruckReceiptItem(models.Model):
    receipt = models.ForeignKey(TruckReceipt, related_name="items", on_delete=models.CASCADE)
    tracking_number = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, default="staged")  # staged|received|missing
    notes = models.CharField(max_length=200, blank=True)