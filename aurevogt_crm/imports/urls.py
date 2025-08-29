from django.urls import path
from . import views

app_name = 'imports'

urlpatterns = [
    path('', views.import_list, name='list'),
    path('new/', views.import_form, name='form'),
    path('<int:pk>/', views.import_detail, name='detail'),
    path('<int:pk>/edit/', views.import_edit, name='edit'),
    path('<int:pk>/delete/', views.import_delete, name='delete'),
]