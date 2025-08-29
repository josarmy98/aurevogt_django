"""
Vistas para administración y gestión de usuarios personalizados.
Incluye vistas para creación de usuarios por administradores y perfil de usuario,
con integración opcional de Driver y Vehicle.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.shortcuts import render, redirect
from drivers.models import Driver, Vehicle

from django.views.decorators.http import require_http_methods
from django.db import transaction

def _is_admin(user):
    return user.is_authenticated and user.is_superuser  # solo admins

@login_required
@user_passes_test(_is_admin)
@require_http_methods(["GET", "POST"])
def user_create(request):
    """
    Vista para creación de usuarios solo por administradores.
    Permite crear usuarios y, opcionalmente, asignarles rol de Driver y un Vehicle asociado.
    """
    if request.method == "POST":
        username   = (request.POST.get("username") or "").strip()
        password   = (request.POST.get("password") or "").strip()
        is_driver  = request.POST.get("is_driver") == "on"
        vehicle_id = request.POST.get("vehicle_id")

        if not username or not password:
            messages.error(request, "Usuario y contraseña son obligatorios.")
            return redirect("users:create")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Ese username ya existe.")
            return redirect("users:create")

        # Crear usuario y (opcionalmente) su Driver de forma atómica
        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password)

            if is_driver:
                drivers_group, _ = Group.objects.get_or_create(name="Drivers")
                user.groups.add(drivers_group)
                driver = Driver.objects.create(user=user)

                if vehicle_id:
                    v = Vehicle.objects.filter(pk=vehicle_id).first()
                    if v:
                        driver.active_vehicle = v
                        driver.save(update_fields=["active_vehicle"])
                    else:
                        messages.warning(
                            request,
                            "El vehículo seleccionado no existe; se creó el conductor sin vehículo activo."
                        )

        messages.success(request, "Usuario creado correctamente.")
        return redirect("drivers:list")

    vehicles = Vehicle.objects.all().order_by("plate")
    return render(request, "users/user_create.html", {"vehicles": vehicles})


@login_required
def user_profile(request):
    """Perfil del usuario actual con info de Driver/Vehicle si aplica."""
    # Si hay un Driver asociado (ya sea OneToOne o FK), tomamos el primero
    driver = Driver.objects.filter(user=request.user).select_related("active_vehicle").first()
    vehicle = driver.active_vehicle if driver else None

    if not driver:
        messages.info(request, "No tienes un vehículo asociado porque no eres conductor.")

    context = {
        "driver": driver,
        "vehicle": vehicle,
        "user_obj": request.user,
    }
    return render(request, "users/profile.html", context)