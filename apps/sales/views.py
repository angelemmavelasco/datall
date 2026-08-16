from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .services.warehouses import (
    WarehousesService,
    WarehouseNotFound,
    PermissionsError,
    ServiceError,
)
from .services.routes import (
    RoutesService,
    RouteNotFound,
    PermissionsError as RoutePermissionsError,
    ServiceError as RouteServiceError,
)
from .filters import WarehouseFilter, RouteFilter
from .forms import WarehouseForm, RouteForm


@login_required
def warehouse_list_view(request):
    template = 'sales/warehouses/warehouse_list.html'
    service = WarehousesService(user=request.user)

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/warehouses/partials/warehouse_list__actions.html'

    warehouses = service.read_warehouses()
    warehouse_filter = WarehouseFilter(request.GET, queryset=warehouses)
    warehouses = warehouse_filter.qs

    context = {
        'warehouses': warehouses,
        'filter': warehouse_filter,
        'available_actions': available_actions,
    }
    return render(request, template, context)


@login_required
def warehouse_detail_view(request, pk: str):
    template = 'sales/warehouses/warehouse_detail.html'
    service = WarehousesService(user=request.user)

    try:
        warehouse = service.read_warehouse(pk=pk)
    except Exception as e:
        messages.error(request, str(e))
        return redirect('sales:warehouse_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/warehouses/partials/warehouse_detail__actions.html'

    context = {
        'warehouse': warehouse,
        'available_actions': available_actions,
    }
    return render(request, template, context)


@login_required
def warehouse_create_view(request):
    template = 'sales/warehouses/warehouse_form.html'
    service = WarehousesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear centros de distribución.')
        return redirect('sales:warehouse_list_view')

    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            try:
                new_warehouse = service.create_warehouse(**form.cleaned_data)
                messages.success(request, f'Centro de distribución {new_warehouse.name} creado correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('sales:warehouse_detail_view', new_warehouse.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('sales:warehouse_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = WarehouseForm()

    context = {
        'form': form,
    }
    return render(request, template, context)


@login_required
def warehouse_update_view(request, pk: str):
    template = 'sales/warehouses/warehouse_form.html'
    service = WarehousesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar centros de distribución.')
        return redirect('sales:warehouse_list_view')

    try:
        warehouse_instance = service.read_warehouse(pk=pk)
    except WarehouseNotFound:
        messages.error(request, "El centro de distribución solicitado no existe.")
        return redirect('sales:warehouse_list_view')
    except PermissionsError:
        messages.error(request, "No tienes permisos para actualizar este centro de distribución.")
        return redirect('sales:warehouse_list_view')
    except ServiceError as e:
        messages.error(request, str(e))
        return redirect('sales:warehouse_list_view')

    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse_instance)
        if form.is_valid():
            try:
                updated_warehouse = service.update_warehouse(pk=pk, **form.cleaned_data)
                messages.success(request, "Centro de distribución actualizado correctamente.")
                return redirect('sales:warehouse_detail_view', updated_warehouse.pk)
            except (PermissionsError, WarehouseNotFound) as e:
                messages.error(request, str(e))
                return redirect('sales:warehouse_list_view')
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = WarehouseForm(instance=warehouse_instance)

    context = {
        'form': form,
        'updating': warehouse_instance,
    }
    return render(request, template, context)

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
    template = 'sales/routes/route_list.html'
    service = RoutesService(user=request.user)

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/routes/partials/route_list__actions.html'

    routes = service.read_routes()
    route_filter = RouteFilter(request.GET, queryset=routes, request=request)
    routes = route_filter.qs

    context = {
        'routes': routes,
        'filter': route_filter,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def route_detail_view(request, pk: str):
    template = 'sales/routes/route_detail.html'
    service = RoutesService(user=request.user)

    try:
        route = service.read_route(pk=pk)
    except RouteNotFound:
        messages.error(request, f"La ruta con ID '{pk}' no fue encontrada.")
        return redirect('sales:route_list_view')
    except (PermissionsError, RoutePermissionsError) as e:
        messages.error(request, str(e))
        return redirect('sales:route_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar la ruta: {str(e)}")
        return redirect('sales:route_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/routes/partials/route_detail__actions.html'

    context = {
        'route': route,
        'available_actions': available_actions,
    }
    return render(request, template, context)


@login_required
def route_create_view(request):
    template = 'sales/routes/route_form.html'
    service = RoutesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear rutas.')
        return redirect('sales:route_list_view')

    if request.method == 'POST':
        form = RouteForm(request.POST)
        if form.is_valid():
            try:
                new_route = service.create_route(**form.cleaned_data)
                messages.success(request, f'Ruta {new_route.id} creada correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('sales:route_detail_view', new_route.pk)

            except (RoutePermissionsError, PermissionsError) as e:
                messages.error(request, str(e))
                return redirect('sales:route_list_view')

            except (RouteServiceError, ServiceError) as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = RouteForm()

    context = {
        'form': form,
    }
    return render(request, template, context)


@login_required
def route_update_view(request, pk: str):
    template = 'sales/routes/route_form.html'
    service = RoutesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar rutas.')
        return redirect('sales:route_detail_view', pk=pk)

    try:
        route_instance = service.read_route(pk=pk)
    except RouteNotFound:
        messages.error(request, "La ruta solicitada no existe.")
        return redirect('sales:route_list_view')
    except (PermissionsError, RoutePermissionsError):
        messages.error(request, "No tienes permisos para actualizar esta ruta.")
        return redirect('sales:route_list_view')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('sales:route_list_view')

    if request.method == 'POST':
        form = RouteForm(request.POST, instance=route_instance)
        if form.is_valid():
            try:
                updated_route = service.update_route(pk=pk, **form.cleaned_data)
                messages.success(request, f"Ruta {updated_route.id} actualizada correctamente.")
                return redirect('sales:route_detail_view', updated_route.pk)

            except (RoutePermissionsError, PermissionsError) as e:
                messages.error(request, str(e))
                return redirect('sales:route_list_view')

            except (RouteServiceError, ServiceError) as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = RouteForm(instance=route_instance)

    context = {
        'form': form,
        'updating': route_instance,
    }
    return render(request, template, context)

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