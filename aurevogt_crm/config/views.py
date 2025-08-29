# config/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.db.models import OuterRef, Subquery, Value, F
from django.db.models.functions import Coalesce
from drivers.models import Driver, LocationPing

# Dashboard principal
@login_required
def dashboard_view(request):
    last_location = (
        LocationPing.objects
        .filter(driver=OuterRef('pk'))
        .order_by('-captured_at')
    )

    # Avoid clashing with existing Driver.last_lat / Driver.last_lng fields
    drivers_qs = (
        Driver.objects
        .annotate(
            latest_lat=Subquery(last_location.values('lat')[:1]),
            latest_lng=Subquery(last_location.values('lon')[:1]),
        )
        .annotate(
            map_lat=Coalesce('latest_lat', F('last_lat')),
            map_lng=Coalesce('latest_lng', F('last_lng')),
        )
        .filter(map_lat__isnull=False, map_lng__isnull=False)
    )

    # Use the map_* aliases when sending data to the template
    drivers_points = list(
        drivers_qs.values('id', 'user__username', 'map_lat', 'map_lng')
    )

    context = {
        "kpi": {
            "today_total": 10,
            "today_delivered": 8,
            "today_failed": 2,
        },
        "admin_assignments_url": reverse("admin:index") + "assignments/assignment/",
        "admin_imports_url": reverse("admin:index") + "imports/importbatch/",
        "admin_packages_url": reverse("admin:index") + "packages/package/",
        "admin_drivers_url": reverse("admin:index") + "drivers/driver/",
        "drivers_points": drivers_points,
        "drivers_points_url": reverse("drivers:api_driver_locations"),
    }
    return render(request, "dashboard.html", context)


# Login
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("dashboard")
    else:
        form = AuthenticationForm()
    return render(request, "login.html", {"form": form})


# Register
def register_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("dashboard")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})


# Logout
def logout_view(request):
    logout(request)
    return redirect("login")


# Profile (simple, se puede extender luego)
@login_required
def profile_view(request):
    return render(request, "profile.html", {"user": request.user})