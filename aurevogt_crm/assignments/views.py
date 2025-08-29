# Create your views here.
# Complete implementation of assignment views
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.urls import reverse
from django.utils import timezone
from django import forms
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.http import HttpResponse
from django.db.models import Q, OuterRef, Subquery
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db import transaction


def get_assignment_model():
    """
    Resuelve el modelo de asignaciones sin romper el arranque del proyecto.
    - Si settings.ASSIGNMENTS_MODEL_NAME está definido, se usa ese.
    - Si no, intenta con una lista de nombres comunes.
    - Si tampoco, devuelve None (las vistas mostrarán un mensaje útil).
    """
    # 1) Nombre forzado por settings, por ejemplo: 'Assignment' o 'DailyAssignment'
    forced_name = getattr(settings, 'ASSIGNMENTS_MODEL_NAME', None)
    candidates = []
    if forced_name:
        candidates.append(str(forced_name))
    # 2) candidatos por defecto
    candidates.extend(["Assignment", "RouteAssignment", "DailyAssignment", "DriverAssignment"])

    for name in candidates:
        try:
            model = apps.get_model("assignments", name)
            if model is not None:
                return model
        except Exception:
            continue
    return None


Assignment = get_assignment_model()

try:
    from drivers.models import Driver
except Exception:
    Driver = None

try:
    from packages.models import Package
except Exception:
    Package = None


def _is_staff(user):
    return user.is_staff or user.is_superuser


# ---------------------------
# Helpers para paquetes
# ---------------------------
def _filtered_unassigned_packages(request, *, limit: int | None = 500):
    """
    Devuelve paquetes NO asignados con filtros opcionales:
      - zipcode: filtra por Package.addr_zip (exact o prefijo)
      - city: filtra por Package.addr_city (icontains)
    Solo estados que tengan sentido para asignar: received / in_warehouse

    Si `limit` es un entero, limita la cantidad devuelta para listados en UI.
    Si `limit` es None, no aplica límite (útil para conteos/commit).
    """
    if Package is None:
        return Package  # None => el template puede manejarlo como []

    zipcode = (request.GET.get('zipcode') or '').strip()
    city = (request.GET.get('city') or '').strip()

    allowed_status = ['received', 'in_warehouse']
    qs = Package.objects.filter(
        assigned_driver__isnull=True,
        status__in=allowed_status
    )

    if zipcode:
        # permite prefijo (e.g., 331 para 331xx)
        qs = qs.filter(addr_zip__startswith=zipcode)
    if city:
        qs = qs.filter(addr_city__icontains=city)

    qs = qs.select_related('assigned_driver').order_by('-created_at')
    if isinstance(limit, int):
        qs = qs[:limit]
    return qs


@login_required
@require_GET
def auto_assign_preview(request, pk):
    """
    Devuelve un fragmento con el conteo de paquetes coincidentes y un botón
    para confirmar la auto-asignación (usando filtros zipcode/city).
    """
    if Assignment is None:
        return HttpResponse("Modelo no disponible", status=500)

    assignment = get_object_or_404(Assignment, pk=pk)
    qs = _filtered_unassigned_packages(request, limit=None)
    count = qs.count()
    context = {
        "assignment": assignment,
        "count": count,
        "zipcode": (request.GET.get("zipcode") or "").strip(),
        "city": (request.GET.get("city") or "").strip(),
    }
    return render(request, "assignments/fragments/auto_preview.html", context)


@login_required
@require_POST
@transaction.atomic
def auto_assign_commit(request, pk):
    """
    Asigna los paquetes filtrados al driver de la asignación y devuelve
    el fragmento de la lista de paquetes de la ruta.
    """
    if Assignment is None or Package is None:
        return HttpResponse("Modelo no disponible", status=500)

    assignment = get_object_or_404(Assignment, pk=pk)
    qs = _filtered_unassigned_packages(request, limit=None)

    pkg_ids = list(qs.values_list("id", flat=True))
    if pkg_ids:
        # Fijar driver y timestamp en bulk
        Package.objects.filter(id__in=pkg_ids).update(
            assigned_driver=assignment.driver,
            assigned_at=timezone.now(),
        )

    updated_qs = _route_packages_for(assignment)
    return render(request, "assignments/fragments/route_list.html", {
        "route_packages": updated_qs,
        "assignment": assignment,
    })


def _route_packages_for(assignment):
    """
    Intenta obtener los paquetes vinculados a la asignación, sin asumir el tipo de relación.
    - Si hay atributo 'packages' (M2M o FK related_name), lo usa.
    - Si existe 'package_set' (FK por defecto), lo usa.
    Devuelve queryset o lista vacía.
    """
    if assignment is None:
        return []
    if hasattr(assignment, 'packages'):
        try:
            return assignment.packages.all()
        except Exception:
            pass
    if hasattr(assignment, 'package_set'):
        try:
            return assignment.package_set.all()
        except Exception:
            pass
    return []

# --- Helpers para modificar paquetes en una asignación ---

def _relation_manager_for_packages(assignment):
    """
    Devuelve un manager para manipular paquetes en la asignación si existe
    una relación explícita. Soporta:
      - `assignment.packages` (M2M o related_name de FK)
      - `assignment.package_set` (FK inversa por defecto)
    Retorna tupla (manager, kind) donde kind ∈ {"m2m", "fk", "none"}.
    """
    # M2M o related_name explícito
    if hasattr(assignment, 'packages') and assignment.packages is not None:
        try:
            # Comprobamos que tenga los métodos típicos de manager M2M
            _ = assignment.packages.all()
            return assignment.packages, 'm2m'
        except Exception:
            pass
    # Relación inversa por FK
    if hasattr(assignment, 'package_set') and assignment.package_set is not None:
        try:
            _ = assignment.package_set.all()
            return assignment.package_set, 'fk'
        except Exception:
            pass
    return None, 'none'


def _attach_package_to_assignment(assignment, package):
    """
    Intenta vincular `package` a `assignment`.
    Si existe relación explícita (M2M/FK inversa) se usa. En su defecto,
    si el modelo Package tiene `assigned_driver`, se asigna al driver de la
    asignación (si existe) y se marca `assigned_at`.
    """
    manager, kind = _relation_manager_for_packages(assignment)
    if kind == 'm2m':
        manager.add(package)
        return True
    if kind == 'fk':
        # Para FK inversa necesitamos reasignar el FK en el paquete, si existe
        fk_field_name = getattr(manager, 'core_filters', {}).get(assignment._meta.model_name)
        # Si no podemos inferir el nombre del FK, intentamos atributo común
        try:
            package.assignment = assignment
            package.save(update_fields=['assignment'])
            return True
        except Exception:
            pass
    # Fallback por driver
    if hasattr(package, 'assigned_driver') and hasattr(assignment, 'driver'):
        package.assigned_driver = assignment.driver
        if hasattr(package, 'assigned_at'):
            package.assigned_at = timezone.now()
        package.save(update_fields=[fld for fld in ['assigned_driver', 'assigned_at'] if hasattr(package, fld)])
        return True
    return False


def _detach_package_from_assignment(assignment, package):
    """
    Quita `package` de `assignment` usando relación explícita si existe,
    o limpiando `assigned_driver` como fallback.
    """
    manager, kind = _relation_manager_for_packages(assignment)
    if kind == 'm2m':
        manager.remove(package)
        return True
    if kind == 'fk':
        try:
            # Intentamos limpiar el FK a la asignación
            if hasattr(package, 'assignment'):
                package.assignment = None
                package.save(update_fields=['assignment'])
                return True
        except Exception:
            pass
    if hasattr(package, 'assigned_driver'):
        package.assigned_driver = None
        # no tocamos assigned_at aquí
        package.save(update_fields=['assigned_driver'])
        return True
    return False


@login_required
def assignment_list(request):
    """
    Lista de asignaciones con filtros opcionales:
      - date=YYYY-MM-DD
      - driver=<id>
      - q=<texto>
    """
    if Assignment is None:
        available = [m.__name__ for m in apps.get_app_config("assignments").get_models()]
        msg = (
            "No se encontró un modelo de asignaciones. "
            "Define settings.ASSIGNMENTS_MODEL_NAME con el nombre correcto (p. ej. 'DailyAssignment'). "
            "Modelos disponibles en la app 'assignments': %s" % (", ".join(available) or "(ninguno)")
        )
        return HttpResponse(msg, status=500)

    qs = Assignment.objects.all().select_related('driver').order_by('-id')

    date_str = request.GET.get('date')
    driver_id = request.GET.get('driver')
    q = request.GET.get('q')

    if date_str:
        qs = qs.filter(date=date_str)
    if driver_id:
        qs = qs.filter(driver_id=driver_id)
    if q:
        qs = qs.filter(reference__icontains=q)

    context = {
        'assignments': qs,
        'drivers': Driver.objects.all() if Driver else [],
        'selected_date': date_str or timezone.localdate().isoformat(),
        'selected_driver': driver_id or '',
        'q': q or '',
    }
    return render(request, 'assignments/assignment_list.html', context)


@login_required
def assignment_detail(request, pk: int):
    if Assignment is None:
        available = [m.__name__ for m in apps.get_app_config("assignments").get_models()]
        msg = (
            "No se encontró un modelo de asignaciones. "
            "Define settings.ASSIGNMENTS_MODEL_NAME con el nombre correcto. "
            "Modelos disponibles: %s" % (", ".join(available) or "(ninguno)")
        )
        return HttpResponse(msg, status=500)

    obj = get_object_or_404(Assignment.objects.select_related('driver'), pk=pk)
    route_packages = _route_packages_for(obj)
    context = {
        'assignment': obj,
        'route_packages': route_packages,
    }
    return render(request, 'assignments/assignment_detail.html', context)


@login_required
@user_passes_test(_is_staff)
def assignment_create(request):
    if Assignment is None:
        available = [m.__name__ for m in apps.get_app_config("assignments").get_models()]
        msg = (
            "No se encontró un modelo de asignaciones. "
            "Define settings.ASSIGNMENTS_MODEL_NAME con el nombre correcto. "
            "Modelos disponibles: %s" % (", ".join(available) or "(ninguno)")
        )
        return HttpResponse(msg, status=500)

    # --- NUEVO: en GET creamos un borrador y redirigimos al edit para habilitar botones ---
    if request.method == "GET":
        # Intentamos crear una asignación mínima (borrador). Si el modelo
        # tiene campos requeridos conocidos, rellenamos valores sensatos.
        kwargs = {}
        try:
            field_names = {f.name for f in Assignment._meta.get_fields() if hasattr(f, "attname")}
        except Exception:
            field_names = set()
        # Rellena campos comunes si existen
        if "date" in field_names:
            kwargs["date"] = timezone.localdate()
        if "reference" in field_names:
            kwargs["reference"] = f"draft-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        if "status" in field_names and hasattr(Assignment, "_meta"):
            # si el modelo maneja estados y acepta 'draft', úsalo
            try:
                choices = dict(getattr(Assignment._meta.get_field("status"), "choices", [])).keys()
                if "draft" in choices:
                    kwargs["status"] = "draft"
            except Exception:
                pass
        try:
            obj = Assignment.objects.create(**kwargs)
            return redirect(reverse("assignments:edit", args=[obj.pk]))
        except Exception:
            # Si no se puede crear (campos obligatorios adicionales), caemos al flujo original
            pass

    class AssignmentForm(forms.ModelForm):
        class Meta:
            model = Assignment
            fields = '__all__'

    if request.method == 'POST':
        form = AssignmentForm(request.POST)
        if form.is_valid():
            obj = form.save()
            return redirect(reverse('assignments:edit', args=[obj.pk]))
    else:
        form = AssignmentForm()

    context = {
        'form': form,
        'mode': 'create',
        # filtros (eco en el formulario)
        'filter_zipcode': (request.GET.get('zipcode') or '').strip(),
        'filter_city': (request.GET.get('city') or '').strip(),
    }
    # paquetes sin asignar (con filtros)
    if Package:
        context['unassigned_packages'] = _filtered_unassigned_packages(request, limit=500)
    else:
        context['unassigned_packages'] = []
    # en creación no hay paquetes aún en la ruta
    context['route_packages'] = []
    return render(request, 'assignments/assignment_form.html', context)


@login_required
@user_passes_test(_is_staff)
def assignment_update(request, pk: int):
    if Assignment is None:
        available = [m.__name__ for m in apps.get_app_config("assignments").get_models()]
        msg = (
            "No se encontró un modelo de asignaciones. "
            "Define settings.ASSIGNMENTS_MODEL_NAME con el nombre correcto. "
            "Modelos disponibles: %s" % (", ".join(available) or "(ninguno)")
        )
        return HttpResponse(msg, status=500)

    class AssignmentForm(forms.ModelForm):
        class Meta:
            model = Assignment
            fields = '__all__'

    obj = get_object_or_404(Assignment, pk=pk)

    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            return redirect(reverse('assignments:detail', args=[obj.pk]))
    else:
        form = AssignmentForm(instance=obj)

    context = {
        'form': form,
        'mode': 'edit',
        'assignment': obj,
        'filter_zipcode': (request.GET.get('zipcode') or '').strip(),
        'filter_city': (request.GET.get('city') or '').strip(),
    }
    if Package:
        context['unassigned_packages'] = _filtered_unassigned_packages(request, limit=500)
    else:
        context['unassigned_packages'] = []
    context['route_packages'] = _route_packages_for(obj)
    return render(request, 'assignments/assignment_form.html', context)


@login_required
@require_POST
def add_pkg(request, pk: int):
    if Assignment is None or Package is None:
        return HttpResponse("Modelo no disponible", status=500)

    assignment = get_object_or_404(Assignment, pk=pk)
    try:
        pkg_id = int(request.POST.get('package_id'))
    except (TypeError, ValueError):
        return HttpResponse("package_id inválido", status=400)

    package = get_object_or_404(Package, pk=pkg_id)
    _attach_package_to_assignment(assignment, package)

    updated_qs = _route_packages_for(assignment)
    return render(request, 'assignments/fragments/route_list.html', {
        'route_packages': updated_qs,
        'assignment': assignment,
    })


@login_required
@require_POST
def remove_pkg(request, pk: int):
    if Assignment is None or Package is None:
        return HttpResponse("Modelo no disponible", status=500)

    assignment = get_object_or_404(Assignment, pk=pk)
    try:
        pkg_id = int(request.POST.get('package_id'))
    except (TypeError, ValueError):
        return HttpResponse("package_id inválido", status=400)

    package = get_object_or_404(Package, pk=pkg_id)
    _detach_package_from_assignment(assignment, package)

    updated_qs = _route_packages_for(assignment)
    return render(request, 'assignments/fragments/route_list.html', {
        'route_packages': updated_qs,
        'assignment': assignment,
    })


@login_required
def route_list_partial(request, pk: int):
    if Assignment is None:
        return HttpResponse("Modelo no disponible", status=500)

    assignment = get_object_or_404(Assignment, pk=pk)
    updated_qs = _route_packages_for(assignment)
    return render(request, 'assignments/fragments/route_list.html', {
        'route_packages': updated_qs,
        'assignment': assignment,
    })