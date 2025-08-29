from django.db.models import Count
from packages.models import Package

def inventory_by_status():
    return Package.objects.values("status").annotate(n=Count("id")).order_by("-n")

def inventory_by_zip():
    return Package.objects.values("addr_zip","status").annotate(n=Count("id")).order_by("addr_zip","status")

def inventory_by_city():
    return Package.objects.values("addr_city","status").annotate(n=Count("id")).order_by("addr_city","status")