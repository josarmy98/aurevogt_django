from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS, BasePermission
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from .models import Package, DeliveryAttempt, PodPhoto, PackageEvent
from .serializers import PackageSerializer, DeliveryAttemptSerializer

class CanEditPackages(BasePermission):
    """Allow writes only to staff/superuser or users with packages change permission."""
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user and request.user.is_authenticated
        # For mutating requests require specific permission or staff
        return (
            request.user and request.user.is_authenticated and (
                getattr(request.user, 'is_staff', False) or
                getattr(request.user, 'is_superuser', False) or
                request.user.has_perm('packages.change_package')
            )
        )

class PackageViewSet(viewsets.ModelViewSet):
    queryset = Package.objects.all().order_by('-created_at')
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status','assigned_driver','addr_zip','addr_city','warehouse']
    search_fields = ['tracking_number','recipient_name','customer_phone']
    ordering_fields = ['created_at','promised_date','priority']
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    def get_permissions(self):
        # Only privileged users can modify or assign
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'assign', 'assign_by_area']:
            return [IsAuthenticated(), CanEditPackages()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def assign(self, request):
        """
        Body: { driver_id: int, package_ids: [int, ...] }
        """
        from drivers.models import Driver
        driver_id = request.data.get('driver_id')
        ids = request.data.get('package_ids', [])
        if not driver_id or not isinstance(ids, list) or not ids:
            return Response({'detail': 'driver_id y package_ids[] son requeridos.'}, status=status.HTTP_400_BAD_REQUEST)
        driver = get_object_or_404(Driver, id=driver_id)
        now = timezone.now()
        qs = Package.objects.filter(id__in=ids)
        updated = qs.update(assigned_driver=driver, assigned_at=now)
        for p in qs:
            PackageEvent.objects.create(package=p, type='assigned', status_from=p.status, status_to=p.status, driver=driver)
        return Response({'assigned': updated})

    @action(detail=False, methods=['post'])
    def assign_by_area(self, request):
        """
        Body: { driver_id: int, zipcode: '33101' }  ó  { driver_id: int, city: 'Miami' }
        Asigna paquetes no asignados por zipcode o ciudad.
        """
        from drivers.models import Driver
        driver_id = request.data.get('driver_id')
        zipcode = request.data.get('zipcode')
        city = request.data.get('city')
        if not driver_id or (not zipcode and not city):
            return Response({'detail': 'driver_id y zipcode o city son requeridos.'}, status=status.HTTP_400_BAD_REQUEST)
        driver = get_object_or_404(Driver, id=driver_id)
        qs = Package.objects.filter(assigned_driver__isnull=True, status__in=['received','in_warehouse'])
        if zipcode:
            qs = qs.filter(addr_zip=zipcode)
        if city:
            qs = qs.filter(addr_city__iexact=city)
        now = timezone.now()
        ids = list(qs.values_list('id', flat=True))
        if not ids:
            return Response({'assigned_count': 0})
        qs.update(assigned_driver=driver, assigned_at=now)
        for p in Package.objects.filter(id__in=ids):
            PackageEvent.objects.create(package=p, type='assigned', status_from=p.status, status_to=p.status, driver=driver)
        return Response({'assigned_count': len(ids)})

class DeliveryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Only privileged users can mutate delivery state
        if self.action in ['start_route', 'confirm', 'fail']:
            return [IsAuthenticated(), CanEditPackages()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def start_route(self, request):
        # marca OFD para todos los paquetes asignados a un driver en fecha
        from drivers.models import Driver
        driver = get_object_or_404(Driver, id=request.data.get('driver_id'))
        now = timezone.now()
        qs = driver.assigned_packages.filter(status__in=['in_warehouse','received'])
        if not qs.exists():
            return Response({'ofded': 0})
        for p in qs:
            PackageEvent.objects.create(package=p, type='ofd', status_from=p.status, status_to='out_for_delivery', driver=driver)
        qs.update(status='out_for_delivery', out_for_delivery_at=now)
        return Response({'ofded': qs.count()})

    @action(detail=False, methods=['post'])
    def confirm(self, request):
        """
        Body: { package_id, photos:[{path_local, checksum}], gps:{lat,lon}, notes }
        """
        p = get_object_or_404(Package, id=request.data.get('package_id'))
        from drivers.models import Driver
        driver = get_object_or_404(Driver, id=request.data.get('driver_id'))
        # Solo el conductor asignado o un usuario con permiso puede confirmar
        if p.assigned_driver_id != driver.id and not request.user.has_perm('packages.change_package'):
            return Response({'detail': 'Solo el conductor asignado o un usuario con permiso puede confirmar.'}, status=status.HTTP_403_FORBIDDEN)
        gps = request.data.get('gps') or {}
        if 'lat' not in gps or 'lon' not in gps:
            return Response({'detail': 'gps.lat y gps.lon son requeridos'}, status=status.HTTP_400_BAD_REQUEST)
        attempt_no = p.attempt_count + 1
        att = DeliveryAttempt.objects.create(
            package=p, driver=driver, attempt_no=attempt_no,
            result='delivered', lat=gps['lat'], lon=gps['lon']
        )
        for ph in request.data.get('photos', []):
            PodPhoto.objects.create(package=p, attempt=att, path_local=ph['path_local'], checksum=ph.get('checksum',''))
        p.status = 'delivered'
        p.delivered_at = timezone.now()
        p.attempt_count = attempt_no
        p.last_event_at = timezone.now()
        p.save(update_fields=['status','delivered_at','attempt_count','last_event_at'])
        PackageEvent.objects.create(package=p, type='delivered', status_from='out_for_delivery', status_to='delivered', driver=driver,
                                    lat=att.lat, lon=att.lon, notes=request.data.get('notes',''))
        return Response({'ok': True})

    @action(detail=False, methods=['post'])
    def fail(self, request):
        """
        Body: { package_id, reason_code, gps:{lat,lon}, photos:[{path_local}] }
        """
        p = get_object_or_404(Package, id=request.data.get('package_id'))
        from drivers.models import Driver
        driver = get_object_or_404(Driver, id=request.data.get('driver_id'))
        # Solo el conductor asignado o un usuario con permiso puede marcar fallo
        if p.assigned_driver_id != driver.id and not request.user.has_perm('packages.change_package'):
            return Response({'detail': 'Solo el conductor asignado o un usuario con permiso puede marcar el intento como fallido.'}, status=status.HTTP_403_FORBIDDEN)
        gps = request.data.get('gps') or {}
        if 'lat' not in gps or 'lon' not in gps:
            return Response({'detail': 'gps.lat y gps.lon son requeridos'}, status=status.HTTP_400_BAD_REQUEST)
        reason_code = request.data.get('reason_code')
        if not reason_code:
            return Response({'detail': 'reason_code es requerido'}, status=status.HTTP_400_BAD_REQUEST)
        attempt_no = p.attempt_count + 1
        att = DeliveryAttempt.objects.create(
            package=p, driver=driver, attempt_no=attempt_no,
            result='failed', reason_code=reason_code,
            lat=gps['lat'], lon=gps['lon']
        )
        for ph in request.data.get('photos', []):
            PodPhoto.objects.create(package=p, attempt=att, path_local=ph['path_local'])
        p.status = 'failed_attempt'
        p.attempt_count = attempt_no
        p.last_event_at = timezone.now()
        p.save(update_fields=['status','attempt_count','last_event_at'])
        PackageEvent.objects.create(package=p, type='failed', status_from='out_for_delivery', status_to='failed_attempt', driver=driver,
                                    lat=att.lat, lon=att.lon, notes=request.data.get('notes',''))
        return Response({'ok': True})

# =========  Vistas HTML (CBV) =========
class PackageListView(LoginRequiredMixin, ListView):
    model = Package
    template_name = 'packages/package_list.html'
    context_object_name = 'packages'
    paginate_by = 25

    def get_queryset(self):
        qs = Package.objects.all().select_related('assigned_driver', 'warehouse').order_by('-created_at')
        q = self.request.GET.get('q')
        status_f = self.request.GET.get('status')
        zip_f = self.request.GET.get('zip')
        city_f = self.request.GET.get('city')
        if q:
            qs = qs.filter(
                Q(tracking_number__icontains=q)
                | Q(recipient_name__icontains=q)
                | Q(customer_phone__icontains=q)
            )
        if status_f:
            qs = qs.filter(status=status_f)
        if zip_f:
            qs = qs.filter(addr_zip=zip_f)
        if city_f:
            qs = qs.filter(addr_city__icontains=city_f)
        return qs

class PackageDetailView(LoginRequiredMixin, DetailView):
    model = Package
    template_name = 'packages/package_detail.html'
    context_object_name = 'package'

class PackageCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Package
    permission_required = 'packages.add_package'
    template_name = 'packages/package_form.html'
    fields = [
        'tracking_number', 'recipient_name', 'customer_phone',
        'addr_line1', 'addr_line2', 'addr_city', 'addr_state', 'addr_zip',
        'promised_date', 'warehouse', 'priority', 'status', 'assigned_driver'
    ]
    success_url = reverse_lazy('packages:list')

class PackageUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Package
    permission_required = 'packages.change_package'
    template_name = 'packages/package_form.html'
    fields = [
        'tracking_number', 'recipient_name', 'customer_phone',
        'addr_line1', 'addr_line2', 'addr_city', 'addr_state', 'addr_zip',
        'promised_date', 'warehouse', 'priority', 'status', 'assigned_driver'
    ]
    success_url = reverse_lazy('packages:list')

class PackageDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Package
    permission_required = 'packages.delete_package'
    template_name = 'packages/package_confirm_delete.html'
    success_url = reverse_lazy('packages:list')