import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.customers.services.customers import CustomersService
from .filters import MapserFilter
from .services.mapser import MapserService


@login_required
def mapser_view(request):
    '''
    renders mapser dashboard with customer geo profiles, denue points and interactive filters
    '''
    template = 'mapser/mapser.html'

    customers_service = CustomersService(user=request.user)
    base_customers_qs = customers_service.read_customers()

    filter_set = MapserFilter(request.GET, queryset=base_customers_qs, request=request)
    filtered_customers_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    selected_customer_ids = request.GET.getlist('customer')
    cust_selected = base_customers_qs.filter(pk__in=selected_customer_ids) if selected_customer_ids else base_customers_qs.none()
    cust_remaining = base_customers_qs.exclude(pk__in=selected_customer_ids).order_by('name', 'id')[:20]
    initial_customers = list(cust_selected) + list(cust_remaining)

    mapser_service = MapserService(
        user=request.user,
        customers_qs=filtered_customers_qs,
        cleaned_data=cleaned_data,
    )

    kpis = mapser_service.get_stats()
    geo_data = mapser_service.read_geo_profiles()
    denue_points = mapser_service.read_denues()

    context = {
        'filter': filter_set,
        'initial_customers': initial_customers,
        'selected_customer_ids': selected_customer_ids,
        'kpis': kpis,
        'geo_data_json': json.dumps(geo_data),
        'denue_points_json': json.dumps(denue_points),
        'default_center': list(mapser_service.default_center),
    }

    return render(request, template, context)
