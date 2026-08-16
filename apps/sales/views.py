from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

@login_required
def warehouse_list_view(request):
    template = 'sales/warehouses/warehouse_list.html'
    return render(request, template)

@login_required
def warehouse_detail_view(request):
    pass

@login_required
def warehouse_create_view(request):
    pass

@login_required
def warehouse_update_view(request):
    pass

@login_required
def route_type_list_view(request):
    pass

@login_required
def route_type_detail_view(request):
    pass

@login_required
def route_type_create_view(request):
    pass

@login_required
def route_type_update_view(request):
    pass

@login_required
def route_type_delete_view(request):
    pass

@login_required
def sale_channel_list_view(request):
    pass

@login_required
def sale_channel_detail_view(request):
    pass

@login_required
def sale_channel_create_view(request):
    pass

@login_required
def sale_channel_update_view(request):
    pass

@login_required
def sale_channel_delete_view(request):
    pass

@login_required
def route_list_view(request):
    pass

@login_required
def route_detail_view(request):
    pass

@login_required
def route_create_view(request):
    pass

@login_required
def route_update_view(request):
    pass

@login_required
def route_delete_view(request):
    pass

@login_required
def route_assignment_list_view(request):
    pass

@login_required
def route_assignment_detail_view(request):
    pass

@login_required
def route_assignment_create_view(request):
    pass

@login_required
def route_assignment_update_view(request):
    pass

@login_required
def route_assignment_delete_view(request):
    pass

@login_required
def user_route_access_list_view(request):
    pass

@login_required
def user_route_access_detail_view(request):
    pass

@login_required
def user_route_access_create_view(request):
    pass

@login_required
def user_route_access_update_view(request):
    pass

@login_required
def user_route_access_delete_view(request):
    pass