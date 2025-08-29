from django.contrib import admin, messages
from django.http import HttpResponse
from django import forms
from django.contrib.admin.helpers import ActionForm
import csv

from drivers.models import Driver
from .models import Package, Warehouse


# --- Actions ---
@admin.action(description="Asignar por ZIP a driver")
def assign_by_zip(modeladmin, request, queryset):
    # Campo proveniente del ActionForm (abajo)
    zip_driver = request.POST.get("_zip_driver")
    if not zip_driver:
        messages.error(request, "Debes indicar driver_id en el campo ‘Driver ID’.")
        return
    try:
        driver = Driver.objects.get(pk=int(zip_driver))
    except (ValueError, Driver.DoesNotExist):
        messages.error(request, f"Driver {zip_driver} no existe.")
        return
    updated = queryset.update(assigned_driver=driver)
    messages.success(request, f"Asignados {updated} paquetes a {driver}.")


@admin.action(description="Marcar Out for delivery")
def mark_ofd(modeladmin, request, queryset):
    updated = queryset.update(status="out_for_delivery")
    messages.success(request, f"{updated} paquetes marcados OFD.")


@admin.action(description="Marcar Delivered")
def mark_delivered(modeladmin, request, queryset):
    updated = queryset.update(status="delivered")
    messages.success(request, f"{updated} paquetes entregados.")


@admin.action(description="Exportar CSV (básico)")
def export_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=packages.csv"
    writer = csv.writer(response)
    writer.writerow(["tracking_number", "status", "assigned_driver", "addr_city", "addr_zip", "created_at"])
    for p in queryset.select_related("assigned_driver"):
        writer.writerow([
            getattr(p, "tracking_number", ""),
            getattr(p, "status", ""),
            getattr(p.assigned_driver, "name", "") if getattr(p, "assigned_driver", None) else "",
            getattr(p, "addr_city", ""),
            getattr(p, "addr_zip", ""),
            getattr(p, "created_at", ""),
        ])
    return response


# --- ActionForm para meter el Driver ID sin templates personalizados ---
class AssignActionForm(ActionForm):
    _zip_driver = forms.IntegerField(required=False, label="Driver ID (para asignación)")


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    actions = [assign_by_zip, mark_ofd, mark_delivered, export_csv]
    action_form = AssignActionForm  # añade el campo _zip_driver al formulario de acciones

    list_display = ("tracking_number", "status", "assigned_driver", "addr_city", "addr_zip", "promised_date", "created_at")
    list_filter = ("status", "assigned_driver", "addr_city", "addr_zip", "promised_date", "created_at")
    search_fields = ("tracking_number", "recipient_name", "addr_street", "addr_city", "addr_zip", "customer_phone")
    date_hierarchy = "created_at"
    autocomplete_fields = ("assigned_driver", "warehouse")
    ordering = ("-created_at",)
    list_per_page = 50


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "created_at")
    search_fields = ("name", "address")
    ordering = ("name",)