from dataclasses import dataclass
from typing import ClassVar

from django.db.models.aggregates import Sum
from apps.human_resources.models import BusinessUnit
from apps.core.services.users import UsersService
from django.db.models import QuerySet, Count, Q
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from apps.human_resources.services.employees import EmployeesService
from django.utils import timezone

class ServiceError(Exception):
    pass

class BusinessUnitNotFound(ServiceError):
    pass

class PermissionsError(ServiceError):
    pass

def _format_validation_error(e: ValidationError) -> str:
    if hasattr(e, 'message_dict'):
        messages = []
        for field, errs in e.message_dict.items():
            field_name = field if field != '__all__' else ''
            prefix = f"{field_name}: " if field_name else ""
            messages.append(f"{prefix}{', '.join(errs)}")
        return "; ".join(messages)
    return ", ".join(e.messages)

@dataclass
class BusinessUnitsService(UsersService):
    business_unit_model: type = BusinessUnit
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_unidades_negocio',
        'recursos_humanos',
    )

    def read_business_units(self) -> QuerySet:
        today = timezone.now().date()

        is_active_emp = Q(
            employees__hire_date__lte=today,
        ) & (
            Q(employees__termination_date__isnull=True) |
            Q(employees__termination_date__gte=today)
        )

        is_inactive_emp = Q(
            employees__termination_date__lt=today
        ) | Q(
            employees__hire_date__gt=today
        )

        if self._is_full_access:
            base_qs = self.business_unit_model.objects.select_related('parent', 'manager', 'manager__user').all()
            active_employees_filter = is_active_emp
            inactive_employees_filter = is_inactive_emp
        else:
            employees_service = EmployeesService(user=self.user)
            accessible_employees = employees_service.read_employees()

            base_qs = self.business_unit_model.objects.select_related('parent', 'manager', 'manager__user').filter(
                Q(employees__in=accessible_employees) | Q(manager__user=self.user)
            ).distinct()

            active_employees_filter = is_active_emp & Q(employees__in=accessible_employees)
            inactive_employees_filter = is_inactive_emp & Q(employees__in=accessible_employees)

        return base_qs.annotate(
            sub_units_count=Count('sub_units', distinct=True),
            associated_active_employees_count=Count('employees__pk', filter=active_employees_filter, distinct=True),
            associated_inactive_employees_count=Count('employees__pk', filter=inactive_employees_filter, distinct=True),
        )

    def read_business_unit(self, *, pk: str) -> BusinessUnit:
        business_unit = self.read_business_units().filter(pk=pk).first()
        if business_unit:
            return business_unit

        if self.business_unit_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la unidad de negocio con ID "{pk}".')

        raise BusinessUnitNotFound(f'No se encontró ninguna unidad de negocio con el ID "{pk}".')

    def read_regions(self) -> QuerySet:
        '''returns only region type business units'''
        return self.read_business_units().filter(
            business_unit_type=self.business_unit_model.BusinessUnitTypeChoices.REGION
        )

    def read_units(self) -> QuerySet:
        '''returns only operational type business units'''
        return self.read_business_units().filter(
            business_unit_type=self.business_unit_model.BusinessUnitTypeChoices.UNIT
        )

    def read_sub_units(self, business_unit: BusinessUnit) -> QuerySet:
        '''returns direct child units of a given business unit'''
        return self.read_business_units().filter(parent=business_unit)

    def read_ancestors(self, business_unit: BusinessUnit) -> list[BusinessUnit]:
        '''returns the ancestors chain in ascending order (parent, grandparent, etc.)'''
        ancestors = []
        curr = business_unit.parent
        visited = {business_unit.pk}
        while curr and curr.pk not in visited:
            ancestors.append(curr)
            visited.add(curr.pk)
            curr = curr.parent
        return ancestors

    def read_business_unit_employees(self, business_unit: BusinessUnit, active: bool | None = True) -> QuerySet:
        '''returns a list of the associated employees (objects) to a given business unit (filtered by active/inactive)'''
        today = timezone.now().date()
        employees_service = EmployeesService(user=self.user)
        base_qs = employees_service.read_employees().filter(business_unit=business_unit)
        is_active_filter = Q(hire_date__lte=today) & (
            Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        )
        if active is True:
            return base_qs.filter(is_active_filter)
        elif active is False:
            return base_qs.exclude(is_active_filter)
        return base_qs

    def create_business_unit(self, **data) -> BusinessUnit:
        '''
        Create a new business unit based on provided data.
        Only allowed users (full access) can do it.
        '''
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear unidades de negocio.')

        bu_type = data.get('business_unit_type')
        if bu_type and bu_type not in self.business_unit_model.BusinessUnitTypeChoices.values:
            raise ServiceError(f"Tipo de unidad de negocio '{bu_type}' no es válido.")

        try:
            with transaction.atomic():
                new_bu = self.business_unit_model(**data)
                new_bu.full_clean()
                new_bu.save()

            return new_bu
        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {_format_validation_error(e)}")
        except IntegrityError:
            raise ServiceError("Ya existe una unidad de negocio con esos datos únicos (ej. ID).")
        except Exception as e:
            raise ServiceError(f"Error al crear la unidad de negocio: {str(e)}")

    def update_business_unit(self, *, pk: str, **data) -> BusinessUnit:
        bu_to_update = self.read_business_unit(pk=pk)

        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar unidades de negocio.')

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        if 'business_unit_type' in data:
            bu_type = data['business_unit_type']
            if bu_type and bu_type not in self.business_unit_model.BusinessUnitTypeChoices.values:
                raise ServiceError(f"Tipo de unidad de negocio '{bu_type}' no es válido.")

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(bu_to_update, attr, value)

                bu_to_update.full_clean()
                bu_to_update.save()

            return bu_to_update

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {_format_validation_error(e)}")
        except IntegrityError:
            raise ServiceError("Ya existe una unidad de negocio con esos datos únicos.")
        except Exception as e:
            raise ServiceError(f"Error al actualizar la unidad de negocio: {str(e)}")

    def delete_business_unit(self, *, pk: str) -> None:
        '''
        deletes a business unit if it has no dependencies
        '''
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para eliminar unidades de negocio.')

        bu_to_delete = self.read_business_unit(pk=pk)

        if bu_to_delete.sub_units.exists():
            raise ServiceError('No se puede eliminar la unidad de negocio porque tiene sub-unidades asociadas. Reasigna o elimina las sub-unidades primero.')

        if bu_to_delete.employees.exists():
            raise ServiceError('No se puede eliminar la unidad de negocio porque tiene colaboradores asignados.')

        if hasattr(bu_to_delete, 'routes') and bu_to_delete.routes.exists():
            raise ServiceError('No se puede eliminar la unidad de negocio porque tiene rutas asociadas.')

        if hasattr(bu_to_delete, 'sale_targets') and bu_to_delete.sale_targets.exists():
            raise ServiceError('No se puede eliminar la unidad de negocio porque tiene objetivos de venta asociados.')

        try:
            with transaction.atomic():
                bu_to_delete.delete()
        except Exception as e:
            raise ServiceError(f"Error al eliminar la unidad de negocio: {str(e)}")

@dataclass
class BusinessUnitsStats:
    business_units_service: BusinessUnitsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.business_units_service.read_business_units()

    def stats(self, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs
        return base_qs.aggregate(
            business_units_count=Count('pk'),
            regions_count=Count(
                'pk', 
                filter=Q(business_unit_type=self.business_units_service.business_unit_model.BusinessUnitTypeChoices.REGION)
            ),
            units_count=Count(
                'pk', 
                filter=Q(business_unit_type=self.business_units_service.business_unit_model.BusinessUnitTypeChoices.UNIT)
            ),
            active_employees_count=Sum('associated_active_employees_count'),
            inactive_employees_count=Sum('associated_inactive_employees_count'),
        )
