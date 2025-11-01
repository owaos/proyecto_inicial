from django.urls import path, include 
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search, name='search'),
    path('search/productos/', views.productos, name='productos'),
    path("ml/health/", views.ml_health, name="ml_health"),
    path("api/ml/search/", views.ml_search_api, name="ml_search_api"),
    path('eco-tips/', views.eco_tips, name='eco_tips')
]
