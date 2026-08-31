from django.urls import path
from .views import mapser_view

app_name = 'mapser'

urlpatterns = [
    path('', mapser_view, name='mapser_view'),
]