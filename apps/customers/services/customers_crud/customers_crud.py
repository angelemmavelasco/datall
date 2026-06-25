from django.db.models import Q
from django.core.exceptions import PermissionDenied
from apps.core.models import Customer

class CustomerCrud:
    def read(self, allowed_routes, **filters):
        """
        Read and filter customers ensuring they are in allowed routes.
        """
        if not allowed_routes:
            return Customer.objects.none()

        qs = Customer.objects.filter(
            route__in=allowed_routes
        ).select_related('route', 'route__warehouse', 'customer_type')

        #searching by id or name
        query_text = filters.get('query_text')
        if query_text:
            qs = qs.filter(
                Q(id__icontains=query_text) | Q(name__icontains=query_text)
            )

        #specific filters
        route = filters.get('routes')
        if route:
            qs = qs.filter(route__in=route)

        warehouse = filters.get('warehouses')
        if warehouse:
            qs = qs.filter(route__warehouse__in=warehouse)

        region = filters.get('regions')
        if region:
            qs = qs.filter(route__warehouse__region__in=region)

        customer_type = filters.get('customer_types')
        if customer_type:
            qs = qs.filter(customer_type__in=customer_type)

        opinion_leader = filters.get('opinion_leader')
        if opinion_leader in ['true', 'false', '1', '0', True, False]:
            val = str(opinion_leader).lower() in ['true', '1', 't', 'y', 'yes']
            qs = qs.filter(opinion_leader=val)

        # date range
        start_date = filters.get('start_registration_date')
        if start_date:
            qs = qs.filter(registration_date__gte=start_date)

        end_date = filters.get('end_registration_date')
        if end_date:
            qs = qs.filter(registration_date__lte=end_date)

        return qs

    def create(self, allowed_routes, **data):
        """
        Create a customer ensuring the route is allowed.
        """
        if not allowed_routes:
            raise PermissionDenied("No tienes rutas asignadas para crear clientes.")

        route = data.get('route')
        #verify the route is allowed for this user
        if route and route not in allowed_routes and getattr(route, 'id', route) not in [r.id if hasattr(r, 'id') else r for r in allowed_routes]:
            raise PermissionDenied("No tienes permisos para crear un cliente en esta ruta.")

        return Customer.objects.create(**data)

    def update(self, customer_id, allowed_routes, **data):
        """
        Update a customer ensuring the route is allowed.
        """
        if not allowed_routes:
            raise PermissionDenied("No tienes permisos para actualizar clientes.")

        # Get customer and verify that the route is allowed for this user
        customer = Customer.objects.filter(id=customer_id, route__in=allowed_routes).first()
        if not customer:
            raise Customer.DoesNotExist("El cliente no existe o no tienes permiso para editarlo.")

        # verify the new route is allowed for this user
        new_route = data.get('route')
        if new_route:
            route_id = new_route.id if hasattr(new_route, 'id') else new_route
            allowed_ids = [r.id if hasattr(r, 'id') else r for r in allowed_routes]
            if route_id not in allowed_ids:
                raise PermissionDenied("No tienes permisos para mover el cliente a esta ruta.")

        # Update fields
        for field, value in data.items():
            setattr(customer, field, value)
        
        customer.save()
        return customer

    def delete(self, customer_id, allowed_routes):
        """
        Delete a customer ensuring the route is allowed for this user
        """
        if not allowed_routes:
            raise PermissionDenied("No tienes permisos para eliminar clientes.")

        customer = Customer.objects.filter(id=customer_id, route__in=allowed_routes).first()
        if not customer:
            raise Customer.DoesNotExist("El cliente no existe o no tienes permiso para eliminarlo.")

        customer.delete()
        return True