from django.urls import path
from . import views

app_name = "assignments"

urlpatterns = [
    path("", views.assignment_list, name="list"),
    path("<int:pk>/", views.assignment_detail, name="detail"),
    path("new/", views.assignment_create, name="create"),
    path("<int:pk>/edit/", views.assignment_update, name="edit"),
    path("<int:pk>/auto-assign/preview/", views.auto_assign_preview, name="auto_preview"),
    path("<int:pk>/auto-assign/", views.auto_assign_commit, name="auto_commit"),


    # Nuevos endpoints HTMX:
    path("<int:pk>/route/partial/", views.route_list_partial, name="route_list_partial"),
    path("<int:pk>/add-pkg/", views.add_pkg, name="add_pkg"),
    path("<int:pk>/remove-pkg/", views.remove_pkg, name="remove_pkg"),
]