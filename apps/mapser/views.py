from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required



@login_required
def mapser_view(request):
    return render(request, 'mapser/mapser.html', {})
