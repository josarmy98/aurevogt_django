from django.core.management.base import BaseCommand
from django.db.models import Q
from packages.models import Package
from assignments.models import AssignmentRule, AssignmentBatch

class Command(BaseCommand):
    help = "Asigna paquetes según reglas por ZIP o ciudad"

    def add_arguments(self, parser):
        parser.add_argument("--status", default="in_warehouse")
        parser.add_argument("--service-date")  # opcional para filtros
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        qs = Package.objects.filter(status=opts["status"], assigned_driver__isnull=True)
        rules = AssignmentRule.objects.filter(enabled=True).order_by("-priority")

        assigned = 0
        for r in rules:
            if r.rule_type == "zip":
                q = qs.filter(addr_zip=r.pattern)
            else:
                q = qs.filter(addr_city__iexact=r.pattern)

            ids = list(q.values_list("id", flat=True)[:5000])  # limita por lote
            if not ids:
                continue
            if not opts["dry_run"]:
                Package.objects.filter(id__in=ids).update(assigned_driver=r.driver)
            assigned += len(ids)

        batch = AssignmentBatch.objects.create(
            filter_json={"status": opts["status"]},
            total=qs.count(),
            assigned=assigned,
            notes="auto-assign by rules",
        )
        self.stdout.write(self.style.SUCCESS(f"Assigned {assigned} packages • batch {batch.id}"))