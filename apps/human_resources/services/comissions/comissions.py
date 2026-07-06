from django.db import transaction
from apps.core.models import (
    CommissionProfile,
    CommissionTier,
    RouteCommissionSetup,
    CommissionSettlement,
    RouteCommissionException,
    RouteAssignment,
    SaleTarget,
    SaleTransaction,
    )

from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from datetime import datetime
from django.db.models import (
    Q, F,
    Count, Sum, Avg,
    Subquery, OuterRef,
    Case, When, Value,
    CharField, IntegerField, DecimalField,
    ExpressionWrapper
)


from django.db.models.functions import (
    Coalesce,
    Concat,
    Cast,
)
from decimal import Decimal
import calendar
from datetime import date, datetime
import csv
import io


from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404


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

    @transaction.atomic
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


class CommissionsReport(SaleTransactionCRUD, SaleTargetCRUD):
    def __init__(self, allowed_routes=None, *args, **kwargs):
        self.allowed_routes = allowed_routes
        super().__init__()

    def read(self, **kwargs):
        qs = CommissionSettlement.objects.filter(route__in=self.allowed_routes)
        
        month = kwargs.get('month')
        year = kwargs.get('year')
        if month:
            qs = qs.filter(period_start__month=int(month))
        if year:
            qs = qs.filter(period_start__year=int(year))
            
        status = kwargs.get('status')
        if status:
            qs = qs.filter(status__in=status)
            
        warehouses = kwargs.get('warehouses')
        if warehouses:
            qs = qs.filter(route__warehouse_id__in=warehouses)
            
        regions = kwargs.get('regions')
        if regions:
            qs = qs.filter(route__warehouse__region_id__in=regions)
            
        routes = kwargs.get('routes')
        if routes:
            qs = qs.filter(route_id__in=routes)
            
        query_text = kwargs.get('query_text')
        if query_text:
            qs = qs.filter(
                Q(route__id__icontains=query_text) | 
                Q(employee__user__first_name__icontains=query_text) |
                Q(employee__user__last_name__icontains=query_text)
            )
            
        return qs.select_related('route', 'employee__user')

    def _calculate_kpis(self, qs):
        qs = qs.annotate(
            potential_bonus=Case(
                When(bonus_type='v', then=ExpressionWrapper(
                    F('snapshot_base_bonus') * F('snapshot_net_sales') / Value(100.0),
                    output_field=DecimalField()
                )),
                When(bonus_type='f', then=F('snapshot_base_bonus')),
                default=Value(0.0),
                output_field=DecimalField()
            )
        )
        kpis = qs.aggregate(
            avg_scope=Avg('snapshot_global_scope'),
            avg_product_classes_scope=Avg('snapshot_completed_classes'),
            total_paid=Sum('final_calculated_bonus'),
            total_potential=Sum('potential_bonus')
        )
        total_paid = kpis['total_paid'] or 0
        total_potential = kpis['total_potential'] or 0
        return {
            'avg_scope': kpis['avg_scope'] or 0,
            'avg_product_classes_scope': kpis['avg_product_classes_scope'] or 0,
            'total_paid': total_paid,
            'total_potential': total_potential,
            'savings_difference': total_potential - total_paid,
        }

    def get_data(self, **kwargs):
        """Prepara el diccionario para inyectarlo directo al template"""
        qs = self.read(**kwargs)
        
        setup_sq = RouteCommissionSetup.objects.filter(
            route=OuterRef('route'),
            start_date__lte=OuterRef('period_end')
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=OuterRef('period_start'))
        ).order_by('-start_date')

        qs = qs.annotate(
            bonus_type=Subquery(setup_sq.values('bonus_type')[:1]),
            profile_id=Subquery(setup_sq.values('profile_id')[:1])
        )
        print(qs)
        
        return {
            'report': qs,
            **self._calculate_kpis(qs)
        }

    def create_multiple(self, route_ids, month, year):
        month = int(month)
        year = int(year)
        period_start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        period_end = date(year, month, last_day)

        valid_routes = self.allowed_routes.filter(id__in=route_ids)
        print('--------------')
        print(valid_routes)
        print('--------------')
        calculated_count = 0

        for route in valid_routes:

            settlement = CommissionSettlement.objects.filter(route=route, period_start=period_start).first()
            if settlement and settlement.status == 'closed':
                continue 

            print('setup')
            setup = RouteCommissionSetup.objects.filter(
                route=route, start_date__lte=period_end
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=period_start)
            ).order_by('-start_date').first()
            print(setup)
            
            if not setup:
                continue 
            profile = setup.profile

            assignment = RouteAssignment.objects.filter(
                route=route, start_date__lte=period_end
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=period_start)
            ).order_by('-start_date').first()

            print(f'route: {route} assignment: {assignment}')
            
            if not assignment or not assignment.employee:
                print('no assignmet or employee')
                continue

            targets_qs = SaleTargetCRUD.read(self, self.allowed_routes, routes=[route.id], period=period_start)
            tx_qs = SaleTransactionCRUD.read(self, self.allowed_routes, routes=[route.id], sale_date_start=period_start, sale_date_end=period_end)

            target_total = targets_qs.aggregate(t=Sum('target_amount'))['t'] or Decimal('0.00')
            sales_total = tx_qs.aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')

            scope = (sales_total / target_total * 100) if target_total > 0 else Decimal('0.00')

            valid_targets = targets_qs.filter(is_valid_for_comission=True)
            completed_classes = 0
            for tgt in valid_targets:
                cls_sales = tx_qs.filter(product_class=tgt.product_class).aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')
                if cls_sales >= tgt.target_amount:
                    completed_classes += 1

            exception = RouteCommissionException.objects.filter(
                route=route, start_date__lte=period_end, end_date__gte=period_start
            ).order_by('-start_date').first()

            if exception:
                scope += exception.scope_tolerance_pct

            tiers = profile.commission_tiers.all().order_by('-min_global_scope_pct', '-min_completed_classes')
            applied_tier = None
            for tier in tiers:
                if scope >= tier.min_global_scope_pct and completed_classes >= tier.min_completed_classes:
                    applied_tier = tier
                    break

            multiplier = applied_tier.bonus_multiplier_pct if applied_tier else Decimal('0.00')
            
            if exception and exception.guaranteed_flat_bonus is not None:
                extra_flat = exception.guaranteed_flat_bonus
            else:
                extra_flat = applied_tier.extra_flat_bonus if applied_tier else Decimal('0.00')

            base_bonus = setup.base_bonus_amount
            if setup.bonus_type == 'v':
                potential = (base_bonus * sales_total / Decimal('100.00'))
                calculated = (potential * multiplier / Decimal('100.00')) + extra_flat
            else:
                calculated = (base_bonus * multiplier / Decimal('100.00')) + extra_flat

            manual_adj = settlement.manual_adjustment if settlement else Decimal('0.00')
            final_bonus = calculated + manual_adj

            if not settlement:
                settlement = CommissionSettlement(
                    period_start=period_start,
                    period_end=period_end,
                    route=route,
                )
            
            # Siempre actualizamos el empleado en base a la asignación actual
            # por si hubo un cambio de personal después del primer cálculo
            settlement.employee = assignment.employee
            
            settlement.snapshot_profile_name = profile.name
            settlement.snapshot_target = target_total
            settlement.snapshot_net_sales = sales_total
            settlement.snapshot_global_scope = scope
            settlement.snapshot_completed_classes = completed_classes
            settlement.snapshot_base_bonus = base_bonus
            settlement.final_calculated_bonus = final_bonus
            settlement.manual_adjustment = manual_adj
            settlement.save()

            print('calculated')

            print(calculated_count)
            
            calculated_count += 1
            
        return calculated_count

    def close_settlements(self, route_ids, month, year):
        month = int(month)
        year = int(year)
        
        valid_routes = self.allowed_routes.filter(id__in=route_ids)
        
        settlements_to_close = CommissionSettlement.objects.filter(
            route__in=valid_routes,
            period_start__year=year,
            period_start__month=month,
            status='draft'
        )
        
        updated_count = settlements_to_close.update(status='closed')
        
        return updated_count

    def get_settlement_detail(self, pk):

        settlement = get_object_or_404(
            CommissionSettlement.objects.select_related('route', 'employee__user'),
            pk=pk,
            route__in=self.allowed_routes
        )

        period_start = settlement.period_start
        period_end = settlement.period_end
        route = settlement.route

        setup = RouteCommissionSetup.objects.filter(
            route=route, start_date__lte=period_end
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=period_start)
        ).order_by('-start_date').first()

        bonus_type = setup.bonus_type if setup else 'v'

        exception = RouteCommissionException.objects.filter(
            route=route, start_date__lte=period_end, end_date__gte=period_start
        ).order_by('-start_date').first()
        targets_qs = SaleTarget.objects.filter(route=route, period=period_start).select_related('product_class')
        tx_qs = SaleTransaction.objects.filter(route=route, sale_date__range=(period_start, period_end))

        sales_breakdown = []
        for tgt in targets_qs:
            cls_sales = tx_qs.filter(product_class=tgt.product_class).aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')
            scope = (cls_sales / tgt.target_amount * 100) if tgt.target_amount > 0 else Decimal('0.00')
            sales_breakdown.append({
                'class_name': str(tgt.product_class.name).title(),
                'is_valid': tgt.is_valid_for_comission,
                'target': tgt.target_amount,
                'sales': cls_sales,
                'scope': scope,
                'completed': cls_sales >= tgt.target_amount
            })

        tiers = CommissionTier.objects.filter(
            commission_profile__name=settlement.snapshot_profile_name
        ).order_by('-min_global_scope_pct', '-min_completed_classes')
        applied_tier = tiers.filter(
            min_global_scope_pct__lte=settlement.snapshot_global_scope,
            min_completed_classes__lte=settlement.snapshot_completed_classes
        ).first()

        if bonus_type == 'v':
            potential_bonus = (settlement.snapshot_base_bonus * settlement.snapshot_net_sales) / Decimal('100.0')
            formatted_base_bonus = f"{settlement.snapshot_base_bonus} %"
        else:
            potential_bonus = settlement.snapshot_base_bonus
            formatted_base_bonus = f"$ {settlement.snapshot_base_bonus:,.2f}"
            
        multiplier = applied_tier.bonus_multiplier_pct if applied_tier else Decimal('0.00')
        extra_flat = applied_tier.extra_flat_bonus if applied_tier else Decimal('0.00')
        
        obtained_bonus = settlement.final_calculated_bonus - settlement.manual_adjustment

        return {
            'settlement': settlement,
            'bonus_type': bonus_type,
            'formatted_base_bonus': formatted_base_bonus,
            'sales_breakdown': sales_breakdown,
            'tiers': tiers,
            'applied_tier': applied_tier,
            'exception': exception,
            'potential_bonus': potential_bonus,
            'obtained_bonus': obtained_bonus,
            'multiplier': multiplier,
            'extra_flat': extra_flat,
        }

    def _generate_csv_data(self, route_ids, month, year, status_filter=None):
        month = int(month)
        year = int(year)
        
        valid_routes = self.allowed_routes.filter(id__in=route_ids)
        settlements_qs = CommissionSettlement.objects.filter(
            route__in=valid_routes,
            period_start__year=year,
            period_start__month=month
        ).select_related('route', 'employee__user')

        if status_filter:
            settlements_qs = settlements_qs.filter(status=status_filter)

        if not settlements_qs.exists():
            return 0, None

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        
        writer.writerow([
            'Ruta', 'Colaborador', 'Estado', 'Periodo calculado', 'Fecha de cálculo', 
            'Perfil de cálculo', 'Objetivo de venta', 'Venta neta', 'Alcance', 
            'Clases completadas', 'Bono base', 'Multiplicador', 'Bono potencial', 
            'Ajustes manuales', 'Conversión final', 'Diferencia (Potencial - Conversión)'
        ])
        
        count = 0
        for settlement in settlements_qs:
            setup = RouteCommissionSetup.objects.filter(
                route=settlement.route, start_date__lte=settlement.period_end
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=settlement.period_start)
            ).order_by('-start_date').first()
            
            bonus_type = setup.bonus_type if setup else 'v'
            
            if bonus_type == 'v':
                potential = (settlement.snapshot_base_bonus * settlement.snapshot_net_sales) / Decimal('100.0')
                base_str = f"{settlement.snapshot_base_bonus} %"
            else:
                potential = settlement.snapshot_base_bonus
                base_str = f"$ {settlement.snapshot_base_bonus:.2f}"

            tier = CommissionTier.objects.filter(
                commission_profile__name=settlement.snapshot_profile_name,
                min_global_scope_pct__lte=settlement.snapshot_global_scope,
                min_completed_classes__lte=settlement.snapshot_completed_classes
            ).first()
            
            multiplier = tier.bonus_multiplier_pct if tier else Decimal('0.00')
            difference = potential - settlement.final_calculated_bonus
            
            writer.writerow([
                str(settlement.route.id).upper(),
                f"{settlement.employee.user.first_name} {settlement.employee.user.last_name}".title(),
                'Borrador' if settlement.status == 'draft' else 'Cerrado',
                f"{settlement.period_start.strftime('%d/%m/%Y')} - {settlement.period_end.strftime('%d/%m/%Y')}",
                settlement.calculated_at.strftime('%d/%m/%Y %H:%M'),
                settlement.snapshot_profile_name.title(),
                f"$ {settlement.snapshot_target:.2f}",
                f"$ {settlement.snapshot_net_sales:.2f}",
                f"{settlement.snapshot_global_scope} %",
                settlement.snapshot_completed_classes,
                base_str, f"{multiplier} %", f"$ {potential:.2f}",
                f"$ {settlement.manual_adjustment:.2f}",
                f"$ {settlement.final_calculated_bonus:.2f}", f"$ {difference:.2f}"
            ])
            count += 1
            
        return count, csv_buffer.getvalue()

    def export_report_data(self, route_ids, month, year):
        count, csv_content = self._generate_csv_data(route_ids, month, year)
        
        if count == 0:
            return None
            
        response = HttpResponse(
            csv_content.encode('utf-8-sig'), 
            content_type='text/csv; charset=utf-8-sig'
        )
        response['Content-Disposition'] = f'attachment; filename="comisiones_{month}_{year}.csv"'
        return response

    def send_commission_report(self, route_ids, month, year, report_type: str ='draft', emails: list[str] = None):
        month = int(month)
        year = int(year)
        
        count, csv_content = self._generate_csv_data(route_ids, month, year, status_filter=report_type)
        
        if count == 0:
            return 0

        if report_type == 'draft':
            next_month = 1 if month == 12 else month + 1
            next_year = year + 1 if month == 12 else year
            close_date = f"06/{next_month:02d}/{next_year}"
            subject = f'Borrador de Reporte de Comisiones - Periodo {month:02d}/{year}'
            body = (
                f"Buen día equipo,\n\n"
                f"Se adjunta a este correo el borrador del reporte de comisiones correspondiente "
                f"al periodo {month:02d}/{year} para su revisión.\n\n"
                f"Por favor, les solicitamos validar la información. Les recordamos que el "
                f"cierre definitivo de este periodo se llevará a cabo el día {close_date}.\n\n"
                f"Cualquier aclaración o ajuste deberá reportarse antes de la fecha mencionada al equipo de análisis.\n\n"
                f"Este correo fue enviado automáticamente desde la plataforma Datall.\n"
                f"Saludos cordiales."
            )

            filename = f'reporte_comisiones_borrador_{month:02d}_{year}.csv'

        else:
            subject = f'Reporte de Comisiones Cerrado - Periodo {month:02d}/{year}'

            body = (
                f"Buen día equipo,\n\n"
                f"Se adjunta el reporte de comisiones correspondiente "
                f"al periodo {month:02d}/{year}.\n\n"
                f"Este correo fue enviado automáticamente desde la plataforma Datall.\n"
                f"Saludos cordiales."
            )

            filename = f'reporte_comisiones_cerrado_{month:02d}_{year}.csv'

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL, 
            to=emails if emails else ['angel.emma.velasco@gmail.com'], 
        )

        email.attach(filename, csv_content.encode('utf-8-sig'), 'text/csv')
        email.send(fail_silently=False)

        return count

    def send_commission_report_draft(self, month, year):
        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year

        close_date = f"06/{next_month:02d}/{next_year}"

        subject = f'Borrador de Reporte de Comisiones - Periodo: {month:02d}/{year}'

        body = (
            f"Buen día equipo,\n\n"
            f"Se adjunta a este correo el borrador del reporte de comisiones correspondiente "
            f"al periodo {month:02d}/{year} para su revisión.\n\n"
            f"Por favor, les solicitamos validar la información. Les recordamos que el "
            f"cierre definitivo de este periodo se llevará a cabo el día {close_date}.\n\n"
            f"Cualquier aclaración o ajuste deberá reportarse antes de la fecha mencionada al equipo de análisis.\n\n"
            f"Este correo fue enviado automáticamente desde la plataforma Datall.\n"
            f"Saludos cordiales."
        )

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DATA_ANALYST_FROM_EMAIL,
            to=['angel.emma.velasco@gmail.com'],
        )

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        
        writer.writerow(['Empleado', 'Comision', 'Estatus'])
        writer.writerow(['Angel Velasco', '1500.00', 'Borrador']) 

        email.attach(
            f'borrador_comisiones_{month:02d}_{year}.csv',
            csv_buffer.getvalue(),
            'text/csv'
        )

        email.send(fail_silently=False)

    def send_commission_report_closed(self, month, year):
        subject = f'Reporte de Comisiones - Periodo: {month:02d}/{year}'

        body = (
            f"Buen día equipo,\n\n"
            f"Se adjunta el reporte de comisiones correspondiente "
            f"al periodo {month:02d}/{year}.\n\n"
            f"Este correo fue enviado automáticamente desde la plataforma Datall.\n"
            f"Saludos cordiales."
        )

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DATA_ANALYST_FROM_EMAIL,
            to=['angel.emma.velasco@gmail.com'],
        )

        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        
        writer.writerow(['Empleado', 'Comision', 'Estatus'])
        writer.writerow(['Angel Velasco', '1500.00', 'Cerrado']) 

        email.attach(
            f'reporte_comisiones_{month:02d}_{year}.csv',
            csv_buffer.getvalue(),
            'text/csv'
        )

        email.send(fail_silently=False)
        
