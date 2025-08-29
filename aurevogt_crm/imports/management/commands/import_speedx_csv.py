import csv
from django.core.management.base import BaseCommand
from django.db import transaction
from packages.models import Package, Warehouse
from imports.models import ImportBatch, ImportErrorRow

CHUNK = 1000  # tamaño de lote

class Command(BaseCommand):
    help = "Importa paquetes desde un CSV de SpeedX"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--warehouse-id", type=int, required=True)

    def handle(self, *args, **opts):
        csv_path = opts["csv_path"]
        wh = Warehouse.objects.get(id=opts["warehouse_id"])

        batch = ImportBatch.objects.create(source="speedx_csv", file_name=csv_path, status="processing")
        to_create = []
        successes = errors = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):  # header = 1
                try:
                    pkg = Package(
                        tracking_number=row["tracking_number"].strip(),
                        speedx_id=row.get("speedx_id") or None,
                        recipient_name=row["recipient_name"].strip(),
                        customer_phone=row.get("customer_phone",""),
                        addr_street=row["addr_street"].strip(),
                        addr_city=(row.get("addr_city") or "").strip(),
                        addr_state=(row.get("addr_state") or "").strip(),
                        addr_zip=(row.get("addr_zip") or "").strip(),
                        warehouse=wh,
                        status="received",
                    )
                    to_create.append(pkg)
                    if len(to_create) >= CHUNK:
                        Package.objects.bulk_create(to_create, ignore_conflicts=True)
                        successes += len(to_create)
                        to_create = []
                except Exception as e:
                    errors += 1
                    ImportErrorRow.objects.create(batch=batch, row_number=i, payload=row, error=str(e))

        if to_create:
            Package.objects.bulk_create(to_create, ignore_conflicts=True)
            successes += len(to_create)

        batch.total_records = successes + errors
        batch.success_count = successes
        batch.error_count = errors
        batch.status = "done" if errors == 0 else "failed"
        batch.save()

        self.stdout.write(self.style.SUCCESS(f"Import OK: {successes}, errors: {errors}"))