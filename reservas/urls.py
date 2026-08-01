from django.urls import path
from . import views

urlpatterns = [
    path('', views.reservas_list_create, name='reservas-list-create'),
    path('<int:pk>/', views.reservas_detalle, name='reservas-detalle'),
    path('<int:pk>/cancelar/', views.reservas_cancelar, name='reservas-cancelar'),
    path('<int:pk>/modificar/', views.reservas_modificar, name='reservas-modificar'),
]