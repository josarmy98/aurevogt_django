from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import Driver, LocationPing
from .serializers import DriverSerializer, LocationPingSerializer
from django import forms
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import OuterRef, Subquery
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from django.conf import settings
from django.utils.dateparse import parse_datetime

class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ["user", "license_number", "vehicle", "status"]
        widgets = {
            "license_number": forms.TextInput(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "status": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "user": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
            "vehicle": forms.Select(attrs={"class": "border rounded px-3 py-2 w-full"}),
        }

class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.all().select_related('user','vehicle')
    serializer_class = DriverSerializer
    filterset_fields = ['status']
    search_fields = ['user__email','license_number']

    @action(detail=True, methods=['get'])
    def assigned_packages(self, request, pk=None):
        d = self.get_object()
        qs = d.assigned_packages.all().values('id','tracking_number','status','addr_city','addr_zip')
        return Response(list(qs))

    @action(detail=True, methods=['get'])
    def last_ping(self, request, pk=None):
        d = self.get_object()
        ping = LocationPing.objects.filter(driver=d).order_by('-captured_at').values('lat', 'lon', 'captured_at').first()
        if ping:
            ping['lng'] = ping.pop('lon')
        return Response(ping or {})

class PingViewSet(viewsets.ModelViewSet):
    queryset = LocationPing.objects.all().order_by('-captured_at')
    serializer_class = LocationPingSerializer

@login_required
@permission_required("drivers.view_driver", raise_exception=True)
def api_driver_locations(request):
    """
    Devuelve JSON con la última ubicación conocida por cada driver que tenga pings.
    Formato:
    {
        "drivers": [
            {"id": 1, "name": "John Doe", "lat": 25.77, "lng": -80.19, "captured_at": "2025-08-28T21:10:00Z", "status": "active", "vehicle": "ABC123"},
            ...
        ]
    }
    """
    latest_ping_qs = LocationPing.objects.filter(driver=OuterRef('pk')).order_by('-captured_at')

    drivers_qs = (
        Driver.objects.select_related('user', 'vehicle')
        .annotate(
            latest_lat=Subquery(latest_ping_qs.values('lat')[:1]),
            latest_lng=Subquery(latest_ping_qs.values('lon')[:1]),
            latest_at=Subquery(latest_ping_qs.values('captured_at')[:1]),
        )
        .filter(latest_lat__isnull=False, latest_lng__isnull=False)
    )

    data = []
    for d in drivers_qs:
        name = (d.user.get_full_name() or d.user.username) if d.user_id else f"Driver #{d.pk}"
        vehicle_plate = d.vehicle.plate if getattr(d, 'vehicle_id', None) else None
        captured_iso = d.latest_at.isoformat() if d.latest_at else None
        data.append({
            'id': d.pk,
            'name': name,
            'lat': float(d.latest_lat),
            'lng': float(d.latest_lng),
            'captured_at': captured_iso,
            'status': getattr(d, 'status', None),
            'vehicle': vehicle_plate,
        })

    return JsonResponse({'drivers': data})


# --- API para ingesta de ubicación desde la app móvil ---
@csrf_exempt
@require_http_methods(["POST"])
def api_ingest_driver_location(request):
    # --- API key simple opcional (recomendado) ---
    api_key = request.headers.get("X-API-Key")
    expected = getattr(settings, "DRIVER_API_KEY", None)
    if expected and api_key != expected:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    driver_id = payload.get("driver_id")
    lat = payload.get("lat")
    lng = payload.get("lng")
    accuracy = payload.get("accuracy")
    heading = payload.get("heading")
    speed = payload.get("speed")
    captured_at = payload.get("captured_at")  # ISO8601 opcional

    if driver_id is None or lat is None or lng is None:
        return JsonResponse({"detail": "driver_id, lat y lng son obligatorios"}, status=400)

    # Validaciones básicas
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return JsonResponse({"detail": "lat/lng inválidos"}, status=400)

    if captured_at:
        dt = parse_datetime(captured_at)
    else:
        dt = timezone.now()

    driver = get_object_or_404(Driver, pk=driver_id)

    ping = LocationPing.objects.create(
        driver=driver,
        lat=lat,
        lon=lng,
        accuracy=accuracy,
        heading=heading,
        speed=speed,
        captured_at=dt,
    )

    return JsonResponse(
        {
            "status": "ok",
            "ping_id": ping.id,
            "driver_id": driver.id,
            "captured_at": ping.captured_at.isoformat(),
        },
        status=201,
    )

@login_required
@permission_required("drivers.view_driver", raise_exception=True)
def driver_list(request):
    drivers = Driver.objects.select_related("user", "vehicle").all()
    return render(request, "drivers/driver_list.html", {"drivers": drivers})

@login_required
@permission_required("drivers.add_driver", raise_exception=True)
def driver_create(request):
    if request.method == "POST":
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save()
            messages.success(request, "Conductor creado correctamente.")
            return redirect("drivers:detail", pk=driver.pk)
    else:
        form = DriverForm()
    return render(request, "drivers/driver_form.html", {"form": form, "mode": "create"})

@login_required
@permission_required("drivers.change_driver", raise_exception=True)
def driver_edit(request, pk):
    driver = get_object_or_404(Driver, pk=pk)
    if request.method == "POST":
        form = DriverForm(request.POST, instance=driver)
        if form.is_valid():
            form.save()
            messages.success(request, "Conductor actualizado.")
            return redirect("drivers:detail", pk=driver.pk)
    else:
        form = DriverForm(instance=driver)
    return render(request, "drivers/driver_form.html", {"form": form, "mode": "edit", "driver": driver})

@login_required
@permission_required("drivers.view_driver", raise_exception=True)
def driver_detail(request, pk):
    driver = get_object_or_404(Driver.objects.select_related("user", "vehicle"), pk=pk)
    return render(request, "drivers/driver_detail.html", {"driver": driver})