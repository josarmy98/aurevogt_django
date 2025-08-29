import csv, os
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from packages.models import Package
from imports.models import ImportBatch

class Command(BaseCommand):
    help = "Importa paquetes desde CSV (cabeceras: tracking_number,recipient_name,addr_street,addr_city,addr_state,addr_zip,customer_phone)"

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    def handle(self, *args, **opts):
        path = opts['csv_path']
        if not os.path.exists(path):
            raise CommandError(f'No existe {path}')
        ib = ImportBatch.objects.create(source='csv', file_name=os.path.basename(path), status='running')
        total = ok = err = 0
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                try:
                    Package.objects.update_or_create(
                        tracking_number=row['tracking_number'],
                        defaults=dict(
                            recipient_name=row.get('recipient_name',''),
                            addr_street=row.get('addr_street',''),
                            addr_city=row.get('addr_city',''),
                            addr_state=row.get('addr_state',''),
                            addr_zip=row.get('addr_zip',''),
                            customer_phone=row.get('customer_phone',''),
                            status='received',
                        )
                    )
                    ok += 1
                except Exception as e:
                    err += 1
                    self.stderr.write(f'Error fila {total}: {e}')
        ib.total_records = total
        ib.success_count = ok
        ib.error_count = err
        ib.status = 'done'
        ib.save()
        self.stdout.write(self.style.SUCCESS(f'Importados OK={ok} ERR={err}'))