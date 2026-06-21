from django.db import transaction
from apps.core.models import (
    CommissionProfile,
    CommissionTier,
    RouteCommissionSetup,
    CommissionSettlement,
    RouteCommissionException,
    RouteAssignment)
from datetime import datetime
from django.db.models import Count, Sum, Q, Subquery, OuterRef, IntegerField, DecimalField, CharField, Value
from decimal import Decimal
from django.db.models.functions import Coalesce, Concat


class Comissions:
    def __init__(self, allowed_routes=None, *args, **kwargs):
        self.allowed_routes = allowed_routes

    @transaction.atomic
    def commission_profile_create(self, profile_data, tiers_data, configs_data):
        """
        Create the profile, assign the thresholds (bulk) and delegate multiple blocks
        of route configuration, ensuring database integrity.
        """
        if not profile_data.get('name'):
            raise ValueError("El nombre del perfil es obligatorio.")

        #base profile
        profile = CommissionProfile.objects.create(
            name=profile_data['name'],
            description=profile_data['description'],
            is_active=profile_data['is_active']
        )

        #tiers creations
        tiers_to_create = [
            CommissionTier(
                commission_profile=profile,
                min_global_scope_pct=tier['min_global_scope_pct'],
                min_completed_classes=tier['min_completed_classes'],
                bonus_multiplier_pct=tier['bonus_multiplier_pct'],
                extra_flat_bonus=tier['extra_flat_bonus']
            ) for tier in tiers_data
        ]
        
        if not tiers_to_create:
            raise ValueError("Debes agregar por lo menos un umbral de comisión.")
            
        CommissionTier.objects.bulk_create(tiers_to_create)

        #process route configurations 
        #while iterating, validate overlaps
        for config in configs_data:
            if not config.get('start_date') or not config.get('bonus_type'):
                raise ValueError("En las configuraciones asignadas, la fecha de inicio y el tipo de comisión son obligatorios.")
            
            self.configure_profile_to_route(profile, config)

        return profile

    def configure_profile_to_route(self, profile, config_data):
        """
        Assigns the profile to the routes within a specific block, validating overlaps.
        """
        start_date_str = config_data['start_date']
        end_date_str = config_data.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

        if end_date and start_date > end_date:
            raise ValueError("La fecha de inicio no puede ser posterior a la fecha de fin.")

        setups_to_create = []

        for route_id in config_data['routes']:
            #validate there are no existing profiles for route  at that moment
            active_setups = RouteCommissionSetup.objects.filter(route_id=route_id).select_related('profile')

            for setup in active_setups:
                error_msg = f"La ruta {route_id} cuenta con un perfil activo ('{setup.profile.name}'). Finaliza el perfil actual o elimínala de esta configuración."

                if not setup.end_date:
                    if not end_date or start_date >= setup.start_date or end_date >= setup.start_date:
                        raise ValueError(error_msg)
                else:
                    if not end_date:
                        if start_date <= setup.end_date:
                            raise ValueError(error_msg)
                    else:
                        if start_date <= setup.end_date and end_date >= setup.start_date:
                            raise ValueError(error_msg)

            setups_to_create.append(
                RouteCommissionSetup(
                    route_id=route_id,
                    profile=profile,
                    start_date=start_date,
                    end_date=end_date,
                    bonus_type=config_data['bonus_type'],
                    base_bonus_amount=config_data['base_bonus_amount'] or 0
                )
            )

        RouteCommissionSetup.objects.bulk_create(setups_to_create)

    def commissions_read(self, filters):
        
        today = datetime.now().date()
        qs = CommissionProfile.objects.all()

        if filters.get('q'):
            qs = qs.filter(name__icontains=filters['q'])
            
        if filters.get('status') in ['1', '0']:
            is_active = filters['status'] == '1'
            qs = qs.filter(is_active=is_active)
            
        if filters.get('min_classes'):
            qs = qs.filter(commission_tiers__min_completed_classes=filters['min_classes']).distinct()
        
        
        active_routes_sq = RouteCommissionSetup.objects.filter(
            profile=OuterRef('pk'),
            route__in=self.allowed_routes
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).values('profile').annotate(
            count=Count('id')
        ).values('count')


        tiers_sq = CommissionTier.objects.filter(
            commission_profile=OuterRef('pk')
        ).values('commission_profile').annotate(
            count=Count('id')
        ).values('count')

        reports_sq = CommissionSettlement.objects.filter(
            snapshot_profile_name=OuterRef('name')
        ).values('snapshot_profile_name').annotate(
            count=Count('id')
        ).values('count')

        paid_sq = CommissionSettlement.objects.filter(
            snapshot_profile_name=OuterRef('name')
        ).values('snapshot_profile_name').annotate(
            total=Sum('final_calculated_bonus')
        ).values('total')

        qs = qs.annotate(
            associated_routes_count=Coalesce(Subquery(active_routes_sq, output_field=IntegerField()), 0),
            applicable_tiers_count=Coalesce(Subquery(tiers_sq, output_field=IntegerField()), 0),
            generated_reports_count=Coalesce(Subquery(reports_sq, output_field=IntegerField()), 0),
            total_paid_sum=Coalesce(Subquery(paid_sq, output_field=DecimalField()), Decimal('0.00'))
        ).order_by('-is_active', 'name') 

        return qs

    @transaction.atomic
    def commission_profile_update(self, profile_id, profile_data, tiers_data, configs_data):
        """
        Update general profile and recreate the tiers and configs.
        """
        profile = CommissionProfile.objects.get(id=profile_id)
        
        #update general data
        profile.name = profile_data['name']
        profile.description = profile_data['description']
        profile.is_active = profile_data['is_active']
        profile.save()
        
        #recreate tiers
        profile.commission_tiers.all().delete()
        
        tiers_to_create = [
            CommissionTier(
                commission_profile=profile,
                min_global_scope_pct=tier['min_global_scope_pct'],
                min_completed_classes=tier['min_completed_classes'],
                bonus_multiplier_pct=tier['bonus_multiplier_pct'],
                extra_flat_bonus=tier['extra_flat_bonus']
            ) for tier in tiers_data
        ]
        
        if not tiers_to_create:
            raise ValueError("Debes agregar por lo menos un umbral de comisión.")
        
        CommissionTier.objects.bulk_create(tiers_to_create)
        
        #delete old configurations
        profile.routecommissionsetup_set.all().delete()
        
        for config in configs_data:
            if not config.get('start_date') or not config.get('bonus_type'):
                raise ValueError("En las configuraciones asignadas, la fecha de inicio y el tipo de comisión son obligatorios.")
            
            self.configure_profile_to_route(profile, config)
            
        return profile





class CommissionExceptions:
    def __init__(self, allowed_routes=None, *args, **kwargs):
        self.allowed_routes = allowed_routes

    def read(self, **kwargs):
        qs = RouteCommissionException.objects.filter(route__in=self.allowed_routes)
        
        if 'q' in kwargs and kwargs['q']:
            qs = qs.filter(route__id__icontains=kwargs['q'])
            
        if 'status' in kwargs and kwargs['status'] in ['1', '0']:
            is_active = kwargs['status'] == '1'
            qs = qs.filter(route__is_active=is_active)
            
        if 'min_tolerance' in kwargs and kwargs['min_tolerance']:
            qs = qs.filter(scope_tolerance_pct__gte=kwargs['min_tolerance'])
            
        if 'start_date' in kwargs and kwargs['start_date']:
            qs = qs.filter(start_date__gte=kwargs['start_date'])
            
        if 'end_date' in kwargs and kwargs['end_date']:
            qs = qs.filter(end_date__lte=kwargs['end_date'])
            
        return qs

    def get_data(self, **kwargs):
        qs = self.read(**kwargs)

        assignments = RouteAssignment.objects.filter(
            route=OuterRef('route'),
            start_date__lte=OuterRef('end_date')
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=OuterRef('start_date'))
        ).order_by('-start_date')

        first_name_sq = assignments.values('employee__user__first_name')[:1]
        last_name_sq = assignments.values('employee__user__last_name')[:1]

        qs = qs.annotate(
            first_name=Subquery(first_name_sq),
            last_name=Subquery(last_name_sq)
        ).annotate(
            employee=Concat('first_name', Value(' '), 'last_name', output_field=CharField())
        ).order_by('-start_date', 'route__id')

        return qs

    def create(self, **kwargs):
        return RouteCommissionException.objects.create(**kwargs)

    def create_multiple(self, route_ids, exception_data):
        valid_routes = self.allowed_routes.filter(id__in=route_ids)
        
        exceptions_to_create = []
        for route in valid_routes:
            exceptions_to_create.append(
                RouteCommissionException(
                    route=route,
                    **exception_data
                )
            )
        
        if exceptions_to_create:
            RouteCommissionException.objects.bulk_create(exceptions_to_create)
            
        return len(exceptions_to_create)

    def update(self, exception_id, **kwargs):
        exception = RouteCommissionException.objects.get(id=exception_id, route__in=self.allowed_routes)
        for key, value in kwargs.items():
            setattr(exception, key, value)
        exception.save()
        return exception

    def delete(self, exception_id):
        exception = RouteCommissionException.objects.get(id=exception_id, route__in=self.allowed_routes)
        exception.delete()
        return True