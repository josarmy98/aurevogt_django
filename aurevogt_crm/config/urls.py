# """
# URL configuration for config project.

# The `urlpatterns` list routes URLs to views. For more information please see:
#     https://docs.djangoproject.com/en/5.2/topics/http/urls/
# Examples:
# Function views
#     1. Add an import:  from my_app import views
#     2. Add a URL to urlpatterns:  path('', views.home, name='home')
# Class-based views
#     1. Add an import:  from other_app.views import Home
#     2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
# Including another URLconf
#     1. Import the include() function: from django.urls import include, path
#     2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
# """
# from django.contrib import admin
# from django.urls import path, include
# from django.conf import settings
# from django.conf.urls.static import static
# from rest_framework.routers import DefaultRouter
# from drivers.views import DriverViewSet, PingViewSet
# from packages.views import PackageViewSet
# from reports.views import productivity_by_driver

# router = DefaultRouter()
# router.register('drivers', DriverViewSet, basename='drivers')
# router.register('pings', PingViewSet, basename='pings')
# router.register('packages', PackageViewSet, basename='packages')





# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path('api/', include(router.urls)),
#     path("api/reports/productivity/", productivity_by_driver, name="productivity-by-driver"),

# ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# """
# URL configuration for config project.

# The `urlpatterns` list routes URLs to views. For more information please see:
#     https://docs.djangoproject.com/en/5.2/topics/http/urls/
# """
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# DRF
from rest_framework.routers import DefaultRouter

# ViewSets existentes (API)
from drivers.views import DriverViewSet, PingViewSet
from packages.views import PackageViewSet

# Reports (FBV - función)
from reports.views import productivity_by_driver

# Vistas HTML globales (dashboard / auth simples)
from config.views import (
    dashboard_view,
    login_view,
    register_view,
    logout_view,
    profile_view,
)

# --------------------------------------------------------------------
# API v1 Router
# --------------------------------------------------------------------
router = DefaultRouter()
router.register('drivers', DriverViewSet, basename='drivers')
router.register('pings', PingViewSet, basename='pings')
router.register('packages', PackageViewSet, basename='packages')
# Nota: cuando tengas ViewSets para assignments e imports, descomenta:
# from assignments.views import AssignmentViewSet
# router.register('assignments', AssignmentViewSet, basename='assignments')
# from imports.views import ImportBatchViewSet
# router.register('imports', ImportBatchViewSet, basename='imports')

urlpatterns = [
    # ADMIN
    path('admin/', admin.site.urls),

    # ---------------- HTML (HTMX/Tailwind) ----------------
    path('', dashboard_view, name='dashboard'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile'),
    path('assignments/', include(('assignments.urls', 'assignments'), namespace='assignments')),
    path('packages/', include(('packages.urls', 'packages'), namespace='packages')),
    path("users/", include(("users.urls", "users"), namespace="users")),
    path('imports/', include(('imports.urls', 'imports'), namespace='imports')),
    path('reports/', include(('reports.urls', 'reports'), namespace='reports')),
    path("drivers/", include(("drivers.urls", "drivers"), namespace="drivers")),
    
    

    # ---------------- API (REST) ----------------
    path('api/', include(router.urls)),
    path('api/v1/', include(router.urls)),  # alias versionado
    path('api-auth/', include('rest_framework.urls')),  # login/logout DRF

    # Reports (funciones)
    path('api/reports/productivity/', productivity_by_driver, name='productivity-by-driver'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)