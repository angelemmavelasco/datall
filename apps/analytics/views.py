from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def sales_dashboard_view(request):
    template = 'analytics/sales_dashboard/sales_dashboard.html'

    return render(request, template)

@login_required
def customer_kpis_view(request):
    pass

@login_required
def product_kpis_view(request):
    pass

@login_required
def route_kpis_view(request):
    pass

@login_required
def collections_dashboard_view(request):
    pass

@login_required
def commercial_risk_view(request):
    pass

@login_required
def target_achievement_view(request):
    pass

@login_required
def annual_sale_breakdown_view(request):
    pass

@login_required
def monthly_sale_breakdown_view(request):
    '''at this moment, this is not added'''
    pass

@login_required
def business_unit_sale_breakdown_view(request):
    pass

@login_required
def unique_customer_count_view(request):
    pass
