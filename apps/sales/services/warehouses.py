from dataclasses import dataclass
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import QuerySet

from apps.core.services.users import UsersService
from apps.sales.models import Warehouse


class ServiceError(Exception):
    pass


class WarehouseNotFound(ServiceError):
    pass


class PermissionsError(ServiceError):
    pass


@dataclass
class WarehousesService(UsersService):
    warehouse_model: type = Warehouse
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_centros_distribucion',
    )

    def read_warehouses(self) -> QuerySet:
        """
        returns a queryset of warehouses based on user access
        """
        if not self._is_full_access:
            return self.warehouse_model.objects.none()

        return self.warehouse_model.objects.all().order_by('name')

    def read_warehouse(self, *, pk: str) -> Warehouse:
        """
        returns a warehouse by its primary key
        """
        warehouse = self.read_warehouses().filter(pk=pk).first()
        if warehouse:
            return warehouse

        if self.warehouse_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al centro de distribución con ID "{pk}".')

        raise WarehouseNotFound(f'No se encontró ningún centro de distribución con el ID "{pk}".')

    def create_warehouse(self, **data) -> Warehouse:
        """
        creates a warehouse
        """
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear centros de distribución.')

        try:
            with transaction.atomic():
                new_warehouse = self.warehouse_model(**data)
                new_warehouse.full_clean()
                new_warehouse.save()

            return new_warehouse

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un centro de distribución con esos datos únicos (ej. ID o Nombre).")
        except Exception as e:
            raise ServiceError(f"Error al crear el centro de distribución: {str(e)}")

    def update_warehouse(self, *, pk: str, **data) -> Warehouse:
        """
        updates a warehouse
        """
        warehouse_to_update = self.read_warehouse(pk=pk)

        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar centros de distribución.')

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(warehouse_to_update, attr, value)

                warehouse_to_update.full_clean()
                warehouse_to_update.save()

            return warehouse_to_update

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un centro de distribución con esos datos únicos (ej. Nombre).")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el centro de distribución: {str(e)}")

    def delete_warehouse(self, *, pk: str) -> None:
        """
        delete a warehouse by id and raise an error if the warehouse is not found or if the user does not have permissions to delete it 
        """
        warehouse_to_delete = self.read_warehouse(pk=pk)

        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para eliminar centros de distribución.')

        try:
            with transaction.atomic():
                warehouse_to_delete.delete()
        except IntegrityError:
            raise ServiceError("No se puede eliminar el centro de distribución porque tiene registros asociados.")
        except Exception as e:
            raise ServiceError(f"Error al eliminar el centro de distribución: {str(e)}")
