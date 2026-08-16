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
from .forms import (
    WarehouseForm,
    RouteForm,
    RouteAssignmentFormSet,
    UserRouteAccessFormSet,
)

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
        assignments_formset = RouteAssignmentFormSet(request.POST, prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(request.POST, prefix='accesses')

        if form.is_valid() and assignments_formset.is_valid() and accesses_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                accesses_data = [f.cleaned_data for f in accesses_formset if f.cleaned_data]

                new_route = service.create_route(
                    route_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    accesses_data=accesses_data,
                )
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
        assignments_formset = RouteAssignmentFormSet(prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(prefix='accesses')

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'accesses_formset': accesses_formset,
        'can_update_access': service.has_full_access,
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
        assignments_formset = RouteAssignmentFormSet(request.POST, instance=route_instance, prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(request.POST, instance=route_instance, prefix='accesses')

        if form.is_valid() and assignments_formset.is_valid() and accesses_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                accesses_data = [f.cleaned_data for f in accesses_formset if f.cleaned_data]

                updated_route = service.update_route(
                    pk=pk,
                    route_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    accesses_data=accesses_data,
                )
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
        assignments_formset = RouteAssignmentFormSet(instance=route_instance, prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(instance=route_instance, prefix='accesses')

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'accesses_formset': accesses_formset,
        'updating': route_instance,
        'can_update_access': service.has_full_access,
    }
    return render(request, template, context)