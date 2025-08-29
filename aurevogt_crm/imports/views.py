from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import ImportBatch, ImportErrorRow
import csv
from io import TextIOWrapper
from django import forms
from django.views.decorators.http import require_POST

class ImportBatchForm(forms.ModelForm):
    """
    Edición conservadora de un batch: permitimos cambiar file_name y status.
    No se permite modificar source ni created_by desde el formulario.
    """
    class Meta:
        from .models import ImportBatch  # import local para evitar recursión en evaluaciones
        model = ImportBatch
        fields = ['file_name', 'status']


def _can_manage_imports(user):
    """
    Sólo superusuarios, miembros del grupo 'ImportsManagers',
    o usuarios listados en settings.ALLOWED_IMPORT_USERS pueden crear/importar.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.groups.filter(name='ImportsManagers').exists():
        return True
    allowed = getattr(settings, 'ALLOWED_IMPORT_USERS', [])
    return user.username in allowed


@login_required
def import_list(request):
    batches = ImportBatch.objects.all().order_by('-imported_at', '-id')
    return render(request, 'imports/import_list.html', {'batches': batches})


@login_required
def import_detail(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk)
    errors_qs = ImportErrorRow.objects.filter(batch=batch).order_by('row_number')

    # Paginación de errores (por si son muchos)
    page_number = request.GET.get('page', 1)
    paginator = Paginator(errors_qs, 50)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'imports/import_detail.html',
        {
            'batch': batch,
            'errors': page_obj,  # iteración en template: for e in errors
            'paginator': paginator,
            'page_obj': page_obj,
        },
    )


@user_passes_test(_can_manage_imports, login_url='login', redirect_field_name=None)
def import_edit(request, pk):
    """
    Edita ligeramente un ImportBatch (file_name y status).
    """
    batch = get_object_or_404(ImportBatch, pk=pk)

    if request.method == 'POST':
        form = ImportBatchForm(request.POST, instance=batch)
        if form.is_valid():
            form.save()
            messages.success(request, 'Import batch actualizado correctamente.')
            return redirect('imports:detail', pk=batch.pk)
        else:
            messages.error(request, 'Revisa los errores del formulario.')
    else:
        form = ImportBatchForm(instance=batch)

    return render(
        request,
        'imports/import_edit.html',
        {
            'batch': batch,
            'form': form,
        },
    )


@user_passes_test(_can_manage_imports, login_url='login', redirect_field_name=None)
@require_POST
def import_delete(request, pk):
    """
    Elimina un ImportBatch. Requiere POST con CSRF.
    """
    batch = get_object_or_404(ImportBatch, pk=pk)
    batch.delete()
    messages.success(request, 'Import batch eliminado.')
    return redirect('imports:list')



@user_passes_test(_can_manage_imports, login_url='login', redirect_field_name=None)
def import_form(request):
    """
    Vista para subir CSV (source='speedx_csv') o disparar importación por API (source='speedx_api').
    No depende del admin. Deja mensajes de estado y redirige a la lista.
    """
    if request.method == 'POST':
        source = (request.POST.get('source') or '').strip()
        upload = request.FILES.get('upload')

        if source not in ('speedx_csv', 'speedx_api'):
            messages.error(request, 'Fuente inválida. Usa CSV de SpeedX o API.')
            return redirect('imports:form')

        # Creamos el batch en estado 'processing'
        batch = ImportBatch.objects.create(
            source=source,
            file_name=getattr(upload, 'name', '') or '',
            created_by=request.user,
            status='processing',
        )

        total = success = errors = 0

        try:
            if source == 'speedx_csv':
                if not upload:
                    messages.error(request, 'Debes adjuntar un archivo CSV.')
                    batch.status = 'failed'
                    batch.save(update_fields=['status'])
                    return redirect('imports:form')

                # Lectura en streaming del CSV
                wrapped = TextIOWrapper(upload.file, encoding='utf-8', newline='')
                # Espera columnas: tracking_number, recipient_name, addr_street, addr_city, addr_state, addr_zip (mínimo)
                reader = csv.DictReader(wrapped)

                # ---------- helpers locales ----------
                from decimal import Decimal, InvalidOperation
                from datetime import datetime

                def _d(n):
                    if n is None:
                        return None
                    s = str(n).strip()
                    if not s:
                        return None
                    try:
                        return Decimal(s)
                    except InvalidOperation:
                        return None

                def _date(v):
                    if not v:
                        return None
                    s = str(v).strip()
                    if not s:
                        return None
                    # intenta YYYY-MM-DD, luego MM/DD/YYYY
                    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                        try:
                            return datetime.strptime(s, fmt).date()
                        except ValueError:
                            pass
                    return None
                # -------------------------------------

                with transaction.atomic():
                    for idx, row in enumerate(reader, start=1):
                        total += 1
                        try:
                            # Validaciones mínimas + creación/actualización de Package
                            tracking = (row.get('tracking_number') or row.get('tracking') or '').strip()
                            if not tracking:
                                raise ValueError('Falta número de tracking (tracking_number)')

                            # Importaciones locales para evitar ciclos
                            from packages.models import Package, Warehouse
                            from drivers.models import Driver

                            recipient_name = (row.get('recipient_name') or '').strip()
                            addr_street    = (row.get('addr_street') or '').strip()
                            addr_city      = (row.get('addr_city') or '').strip()
                            addr_state     = (row.get('addr_state') or '').strip()
                            addr_zip       = (row.get('addr_zip') or '').strip()

                            if not recipient_name or not addr_street or not addr_city or not addr_zip:
                                raise ValueError('Faltan columnas mínimas: recipient_name, addr_street, addr_city, addr_zip')

                            note        = (row.get('note') or '').strip()
                            weight      = _d(row.get('weight'))
                            cod_amount  = _d(row.get('cod_amount'))
                            dest_lat    = _d(row.get('dest_lat'))
                            dest_lon    = _d(row.get('dest_lon'))
                            promised    = _date(row.get('promised_date'))
                            priority    = int(str(row.get('priority') or '0').strip() or 0)

                            # Warehouse por nombre (opcional)
                            wh = None
                            wh_name = (row.get('warehouse') or '').strip()
                            if wh_name:
                                wh, _ = Warehouse.objects.get_or_create(name=wh_name)

                            # Preasignación opcional por username
                            assigned_driver = None
                            drv_username = (row.get('driver_username') or '').strip()
                            if drv_username:
                                try:
                                    assigned_driver = Driver.objects.select_related('user').get(user__username=drv_username)
                                except Driver.DoesNotExist:
                                    assigned_driver = None  # lo ignoramos si no existe

                            # Construye defaults
                            pkg_defaults = {
                                'status': 'in_warehouse',
                                'priority': priority,
                                'recipient_name': recipient_name,
                                'customer_phone': (row.get('customer_phone') or '').strip(),
                                'addr_street': addr_street,
                                'addr_city': addr_city,
                                'addr_state': addr_state,
                                'addr_zip': addr_zip,
                                'note': note,
                                'weight': weight,
                                'cod_amount': cod_amount,
                                'dest_lat': dest_lat,
                                'dest_lon': dest_lon,
                                'warehouse': wh,
                                'promised_date': promised,
                                'assigned_driver': assigned_driver,
                            }

                            Package.objects.update_or_create(
                                tracking_number=tracking,
                                defaults=pkg_defaults,
                            )

                            success += 1
                        except Exception as e:
                            ImportErrorRow.objects.create(
                                batch=batch,
                                row_number=idx,
                                payload=row,
                                error=str(e),
                            )
                            errors += 1

            elif source == 'speedx_api':
                # Placeholder para llamada a API externa (SpeedX).
                # Aquí deberías implementar el fetch y el parseo.
                # Por ahora no hace nada, sólo marca el batch como sin cambios.
                messages.info(request, 'Importación por API aún no implementada.')
                total = success = errors = 0

            # Actualizamos el batch
            batch.total_records = total
            batch.success_count = success
            batch.error_count = errors
            batch.status = 'done' if errors == 0 else 'completed_with_errors'
            batch.save()

            if errors:
                messages.warning(
                    request,
                    f'Importación finalizada con {errors} errores. Revisa el detalle.'
                )
                return redirect('imports:detail', pk=batch.pk)

            messages.success(
                request,
                f'Importación completada. Registros: {total}, exitosos: {success}.'
            )
            return redirect('imports:list')

        except Exception as e:
            # Falla no controlada
            batch.status = 'failed'
            batch.save(update_fields=['status'])
            messages.error(request, f'Fallo en importación: {e}')
            return redirect('imports:list')

    # GET
    return render(request, 'imports/import_form.html')


@user_passes_test(_can_manage_imports, login_url='login', redirect_field_name=None)
def truck_receipt(request):
    """
    Render simple de recibo de camión. Puedes ajustar el contexto según tu dominio.
    """
    context = {}
    return render(request, 'imports/truck_receipt.html', context)