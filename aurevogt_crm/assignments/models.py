from django.db import models

class AssignmentRule(models.Model):
    """Reglas automáticas de asignación -> driver por ZIP o ciudad."""
    RULE_TYPE = (("zip","ZIP"), ("city","City"))
    rule_type = models.CharField(max_length=10, choices=RULE_TYPE, db_index=True)
    pattern = models.CharField(max_length=40, db_index=True)  # ej '33166' o 'Doral'
    driver = models.ForeignKey("drivers.Driver", on_delete=models.PROTECT, related_name="assignment_rules")
    priority = models.IntegerField(default=0)  # mayor = se aplica primero
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("-priority","rule_type","pattern")
        indexes = [models.Index(fields=["rule_type","pattern","enabled"])]

class AssignmentBatch(models.Model):
    """Bitácora de ejecuciones de asignación masiva."""
    created_at = models.DateTimeField(auto_now_add=True)
    filter_json = models.JSONField(default=dict)  # ej {'status':'in_warehouse','zip':'33166'}
    total = models.IntegerField(default=0)
    assigned = models.IntegerField(default=0)
    notes = models.CharField(max_length=200, blank=True)

    service_date = models.DateField(null=True, blank=True, db_index=True)
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.PROTECT,
        related_name="assignment_batches",
        null=True,
        blank=True,
    )
    total_packages = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        d = self.service_date.isoformat() if self.service_date else self.created_at.date().isoformat()
        return f"Lote {d} - {self.driver or 'Sin conductor'} ({self.total_packages} pkgs)"

    class Meta:
        ordering = ("-service_date", "-created_at")