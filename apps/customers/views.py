from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.core.utils import get_allowed_routes_for_user, get_allowed_warehouses_for_user
from apps.core.models import Region

from datetime import datetime, date

@login_required
def customer_agreements(request):
    allowed_routes = get_allowed_routes_for_user(request.user)
    allowed_warehouses = get_allowed_warehouses_for_user(request.user)
    allowed_regions = Region.objects.filter(warehouses__in=allowed_warehouses).distinct()
    template = 'customers/customer_agreements/customer_agreements.html'

    # get filters
    today = date.today()
    if request.GET:
        status = request.GET.getlist('status', [])
    else:
        status = ['active']
        
    created_start = request.GET.get('created_start', '')
    created_end = request.GET.get('created_end', '')
    finished_start = request.GET.get('finished_start', '')
    finished_end = request.GET.get('finished_end', '')
    routes = request.GET.getlist('routes', [])
    warehouses = request.GET.getlist('warehouses', [])
    regions = request.GET.getlist('regions', [])
    
    
    

    filters = {}

    context = {
        'filter_routes': allowed_routes,
        'filter_warehouses': allowed_warehouses,
        'filter_regions': allowed_regions,

        # selected filters
        'selected_status': status,
        'selected_created_start': created_start,
        'selected_created_end': created_end,
        'selected_finished_start': finished_start,
        'selected_finished_end': finished_end,
        'selected_routes': routes,
        'selected_warehouses': warehouses,
        'selected_regions': regions,

    }
    return render(request, template, context)