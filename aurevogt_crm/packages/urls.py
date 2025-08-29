from django.urls import path
from . import views

app_name = 'packages'

urlpatterns = [
    path('', views.PackageListView.as_view(), name='list'),
    path('<int:pk>/', views.PackageDetailView.as_view(), name='detail'),
    path('create/', views.PackageCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', views.PackageUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.PackageDeleteView.as_view(), name='delete'),
]