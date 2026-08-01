from django.urls import path
from . import views

urlpatterns = [
    path('', views.labs_list_create, name='labs-list-create'),
    path('disponibles/', views.labs_disponibles, name='labs-disponibles'),
    path('<int:pk>/', views.labs_update, name='labs-update'),
]