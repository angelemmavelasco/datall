from django.urls import path
from .views import *

app_name = 'data_assistant'

urlpatterns = [
    path('data_assistant/', data_assistant, name='data_assistant'),
    path('datall_assistant/', datall_assistant, name='datall_assistant'),
]
