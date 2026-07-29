from dataclasses import dataclass, field
from apps.sales.models import Sale, SaleLine, SaleLineTax

class ServiceError(Exception):
    pass

class SaleNotFoundError(ServiceError):
    pass

class SalePermissionError(ServiceError):
    pass

class SaleAlreadyCanceledError(ServiceError):
    pass

class SaleAlreadyInvoicedError(ServiceError):
    pass

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object


@dataclass
class SalesService:
    '''
    focused on business logic operations related to sales and salelines.
    some of the main logic includes generates invoices, triggers related to inventory,
    and validations over the main user.
    '''
    user: 'UserModel'
    SaleModel: type[Sale] = Sale
    SaleLineModel: type[SaleLine] = SaleLine
    SaleLineTaxModel: type[SaleLineTax] = SaleLineTax
    _is_full_access: bool = field(init=False)
    
    def __post_init__(self) -> None:
        self._validate_access()
        self._is_full_access = self._checkout_full_access

    def _validate_access(self) -> None:
        '''
        validates if the user was provided, exists and is authenticated.
        '''
        if not self.user:
            raise PositionNotFoundError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise PositionAuthenticationError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise PositionPermissionError('El usuario se encuentra inactivo.')

    @property
    def _checkout_full_access(self) -> bool:
        '''
        validates if user has total access (or is superuser) or limited access.
        '''
        if getattr(self.user, 'is_superuser', False):
            return True
        return self.user.groups.filter(name__in=[
            'total', 'acceso total', 'admin', 'global', 
            'acceso global', 'ventas', 'sales', 'seller', 'vendedor'
        ]).exists()
