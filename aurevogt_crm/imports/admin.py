from django.contrib import admin
from .models import ImportBatch, ImportErrorRow, TruckReceipt, TruckReceiptItem

@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "created_by",        # <- antes decía imported_by, cámbialo por created_by
        "imported_at",
        "status",
        "total_records",
        "success_count",
        "error_count",
    )
    list_filter = ("status", "source", "imported_at")
    search_fields = ("file_name", "created_by__username", "created_by__email")
    date_hierarchy = "imported_at"
    readonly_fields = ("imported_at",)
    actions = ["quick_import"]

    @admin.action(description="Quick import selected batch")
    def quick_import(self, request, queryset):
        for batch in queryset:
            # lógica placeholder de quick import
            # aquí podrías llamar un servicio de procesamiento directo
            self.message_user(request, f"Quick import triggered for batch {batch.id}")

@admin.register(ImportErrorRow)
class ImportErrorRowAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "row_number", "short_error", "created_at")
    list_filter = ("created_at",)
    search_fields = ("error", "payload")
    date_hierarchy = "created_at"

    def short_error(self, obj):
        return (obj.error or "")[:80]
    short_error.short_description = "Error"

@admin.register(TruckReceipt)
class TruckReceiptAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "warehouse", "eta", "received_at", "total_packages", "created_at")
    list_filter = ("warehouse", "created_at")
    search_fields = ("code",)
    date_hierarchy = "created_at"

@admin.register(TruckReceiptItem)
class TruckReceiptItemAdmin(admin.ModelAdmin):
    list_display = ("id", "receipt", "tracking_number", "status", "notes")
    list_filter = ("status", "receipt")
    search_fields = ("tracking_number", "notes")