from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import *
from .services import CustomersService

@login_required
def customer_list_view(request):
    pass