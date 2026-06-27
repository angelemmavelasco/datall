from django.urls import path
from apps.data_admin.views import *
app_name = 'data_admin'

urlpatterns = [
    path('users/', users, name='users'),
    path('users/<int:user_id>/', user, name='user'),
    path('users/create/', user_create, name='user_create'),
    path('groups/', groups, name='groups'),
    path('groups/<int:group_id>/', group, name='group'),
    path('groups/create/', group_create, name='group_create'),
    path('uploads/', uploads, name='uploads'),
    path('uploads/create/', upload_create, name='upload_create'),


    path('activity/', activity, name='activity'),

    path('references/', references, name='references'),
]