from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def sales_dashboard(request):
    return render(request, 'business_intelligence/sales_dashboard/sales_dashboard.html')


@login_required
def routes_kpis(request):
    context = {}
    return render(request, 'business_intelligence/routes_kpis/routes_kpis.html', context)


@login_required
def warehouses_kpis(request):
    context = {}
    return render(request, 'business_intelligence/warehouses_kpis/warehouses_kpis.html', context)



@login_required
def products_kpis(request):
    context = {}
    return render(request, 'business_intelligence/products_kpis/products_kpis.html', context)


@login_required
def customers_kpis(request):
    context = {}
    return render(request, 'business_intelligence/customers_kpis/customers_kpis.html', context)