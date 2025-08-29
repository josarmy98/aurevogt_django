from django.urls import path
from django.shortcuts import render
from .views import productivity_by_driver

app_name = 'reports'

urlpatterns = [
    path("api/productivity/", productivity_by_driver, name="productivity_by_driver"),
    path("dashboard/", lambda request: render(request, "reports/report_dashboard.html"), name="dashboard"),
]