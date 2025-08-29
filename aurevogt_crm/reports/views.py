from django.db.models import Count, Avg, Min, Max, Q
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from datetime import datetime, time
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import IsAuthenticated

from packages.models import Package
from drivers.models import Driver

def _parse_date(value, default_start, is_end=False):
    """
    Admite YYYY-MM-DD o ISO8601 y devuelve datetime *aware* en tz actual.
    Si `is_end=True` y solo se recibe fecha, ajusta a fin de día (23:59:59.999999),
    de lo contrario a inicio de día (00:00:00).
    """
    if not value:
        return default_start

    # Primero intenta ISO8601 completo
    dt = parse_datetime(value)
    if dt is not None:
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

    # Fallback: solo fecha (YYYY-MM-DD)
    try:
        d = datetime.fromisoformat(value).date()
        if is_end:
            dt = datetime.combine(d, time(23, 59, 59, 999999))
        else:
            dt = datetime.combine(d, time.min)
        return timezone.make_aware(dt)
    except Exception:
        return default_start

@api_view(["GET"])
@permission_classes([IsAuthenticated])  # quita o cambia para pruebas si lo deseas
def productivity_by_driver(request):
    # Filtros
    now = timezone.now()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    date_from = _parse_date(request.query_params.get("date_from"), start_today, is_end=False)
    date_to   = _parse_date(request.query_params.get("date_to"),   end_today,  is_end=True)
    driver_id = request.query_params.get("driver_id")
    warehouse = request.query_params.get("warehouse_id")

    drivers = Driver.objects.select_related("user")
    if driver_id:
        drivers = drivers.filter(id=driver_id)

    data = []
    for driver in drivers:
        qs = Package.objects.filter(
            assigned_driver_id=driver.id,
            created_at__gte=date_from,
            created_at__lte=date_to,
        )
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)

        agg = qs.aggregate(
            total=Count("id"),
            delivered=Count("id", filter=Q(status="delivered")),
            failed=Count("id", filter=Q(status="failed_attempt")),
            ofd=Count("id", filter=Q(status="out_for_delivery")),
            avg_attempts=Avg("attempt_count"),
            first_ofd_at=Min("out_for_delivery_at"),
            last_event_at=Max("last_event_at"),
            last_delivered_at=Max("delivered_at"),
        )

        total = agg.get("total") or 0
        delivered = agg.get("delivered") or 0
        failed = agg.get("failed") or 0
        ofd = agg.get("ofd") or 0
        avg_attempts = agg.get("avg_attempts") or 0
        first = agg.get("first_ofd_at")
        last_event_at = agg.get("last_event_at")
        last_delivered_at = agg.get("last_delivered_at")

        last = last_delivered_at or last_event_at
        if first and last:
            hours = (last - first).total_seconds() / 3600.0
        else:
            hours = 0.0

        success_rate = (delivered / total) if total else 0.0
        delivered_per_hour = (delivered / hours) if hours > 0 else 0.0

        data.append({
            "driver_id": driver.id,
            "driver_first_name": getattr(driver.user, "first_name", ""),
            "driver_last_name": getattr(driver.user, "last_name", ""),
            "driver_license_number": driver.license_number,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "ofd": ofd,
            "success_rate": round(success_rate, 3),
            "avg_attempts": round(float(avg_attempts), 2) if avg_attempts is not None else 0.0,
            "first_ofd_at": first,
            "last_event_at": last_event_at,
            "productive_hours": round(hours, 2),
            "delivered_per_hour": round(delivered_per_hour, 2),
        })

    return Response(data)


