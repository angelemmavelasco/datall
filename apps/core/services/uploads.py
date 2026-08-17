import io
import pandas as pd
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Callable, Optional
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import Reference
from apps.core.services.users import UsersService, ServiceError

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
    class UserType(AbstractBaseUser, PermissionsMixin):
        pass


class UploadServiceError(ServiceError):
    pass


class PermissionsError(UploadServiceError):
    pass


class FileValidationError(UploadServiceError):
    pass


@dataclass
class ImportResult:
    """
    Standard contract for ETL and bulk import results across services.
    """
    success: bool
    message: str
    total_processed: int = 0
    created_count: int = 0
    updated_count: int = 0
    errors: list[str] = field(default_factory=list)


class BaseETLHelper:
    """
    base utility helper for extracting, validating, and preparing tabular data from files.
    """
    ALLOWED_EXTENSIONS = ('.csv', '.xlsx', '.xls')
    CSV_ENCODINGS = ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1')

    @classmethod
    def validate_file(cls, file_obj) -> tuple[bool, str]:
        """
        validates basic file existence, non-empty size, and allowed extensions.
        """
        if not file_obj:
            return False, "No se proporcionó ningún archivo para procesar."

        filename = getattr(file_obj, 'name', '') or ''
        filename_lower = filename.lower()

        if not any(filename_lower.endswith(ext) for ext in cls.ALLOWED_EXTENSIONS):
            allowed = ', '.join(cls.ALLOWED_EXTENSIONS)
            return False, f"Formato de archivo no soportado. Debe ser uno de los siguientes: {allowed}"

        # Check if file has content
        file_size = getattr(file_obj, 'size', None)
        if file_size is not None and file_size <= 0:
            return False, "El archivo proporcionado está vacío."

        return True, ""

    @classmethod
    def read_file_to_dataframe(cls, file_obj) -> tuple[bool, pd.DataFrame | str]:
        """
        reads a CSV or Excel file safely into a pandas DataFrame with string dtypes to preserve raw values.
        """
        is_valid, validation_msg = cls.validate_file(file_obj)
        if not is_valid:
            return False, validation_msg

        filename = getattr(file_obj, 'name', '') or ''
        filename_lower = filename.lower()

        try:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)

            if filename_lower.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_obj, dtype=str)
            else:
                df = None
                read_errors = []
                for encoding in cls.CSV_ENCODINGS:
                    try:
                        if hasattr(file_obj, 'seek'):
                            file_obj.seek(0)
                        df = pd.read_csv(file_obj, dtype=str, encoding=encoding)
                        break
                    except (UnicodeDecodeError, pd.errors.ParserError) as err:
                        read_errors.append(f"{encoding}: {str(err)}")

                if df is None:
                    return False, f"No se pudo decodificar el archivo CSV. Verifique la codificación (UTF-8, Latin-1)."

            if df.empty:
                return False, "El archivo no contiene filas de datos."
            df = cls.clean_dataframe(df)

            return True, df

        except Exception as e:
            return False, f"Error al leer el archivo tabular: {str(e)}"

    @classmethod
    def clean_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Strips whitespace from column headers and string values, replacing null representations with None.
        """
        df.columns = [str(col).strip() for col in df.columns]
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({'nan': None, 'NaN': None, 'None': None, 'none': None, 'null': None, '': None})

        return df.where(pd.notnull(df), None)

    @classmethod
    def apply_reference_column_mappings(
        cls,
        df: pd.DataFrame,
        model: type[models.Model],
        submodule_name: str = 'importación de datos',
        context: str = 'columna'
    ) -> pd.DataFrame:
        """
        renames DataFrame columns according to the Reference mapping rules for the target model.
        """
        ctype = ContentType.objects.get_for_model(model)

        references = Reference.objects.filter(
            content_type=ctype
        )
        if submodule_name:
            references = references.filter(submodule__name__icontains=submodule_name)
        if context:
            references = references.filter(context__icontains=context)

        column_map = {}
        for ref in references:
            raw_key = str(ref.key).strip()
            target_val = str(ref.value).strip() if hasattr(ref, 'value') else str(getattr(ref, 'reference', '')).strip()
            if raw_key and target_val:
                column_map[raw_key] = target_val

        if column_map:
            df.rename(columns=column_map, inplace=True)

        return df

    @classmethod
    def resolve_foreign_key_columns(cls, df: pd.DataFrame, model: type[models.Model]) -> pd.DataFrame:
        """
        maps relationship field names to their underlying database column names (e.g. 'route' -> 'route_id').
        """
        fk_map = {}
        for f in model._meta.get_fields():
            if f.is_relation and hasattr(f, 'attname'):
                if f.name != f.attname:
                    fk_map[f.name] = f.attname

        if fk_map:
            df.rename(columns=fk_map, inplace=True)

        return df


@dataclass
class UploadsService(UsersService):
    """
    central orchestrator and dispatcher service for data imports.
    calidates user permissions and delegates cleaning and loading to specialized domain services.
    """
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_importaciones',
        'importaciones',
        'analista',
        'acceso_total',
    )

    def validate_permission(self) -> None:
        """
        validates that the user has full access, staff, superuser, or analyst role.
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para realizar cargas masivas de datos.')

    def get_registered_importers(self) -> dict[str, Callable]:
        """
        registry mapping entity identifiers to their domain service bulk_create methods.
        """
        importers: dict[str, Callable] = {}

        # Product
        try:
            from apps.products.services.products import ProductsService
            service = ProductsService(user=self.user)
            if hasattr(service, 'bulk_create_products'):
                importers['product'] = service.bulk_create_products
        except ImportError:
            pass

        # Customer
        try:
            from apps.customers.services.customers import CustomersService
            service = CustomersService(user=self.user)
            if hasattr(service, 'bulk_create_customers'):
                importers['customer'] = service.bulk_create_customers
        except ImportError:
            pass

        # SaleTransaction
        try:
            from apps.sales.services.sale_transactions import SaleTransactionsService
            service = SaleTransactionsService(user=self.user)
            if hasattr(service, 'bulk_create_transactions'):
                importers['saletransaction'] = service.bulk_create_transactions
        except ImportError:
            pass

        # AccountsReceivable
        try:
            from apps.customers.services.accounts_receivables import AccountsReceivablesService
            service = AccountsReceivablesService(user=self.user)
            if hasattr(service, 'bulk_create_ars'):
                importers['accountsreceivable'] = service.bulk_create_ars
        except ImportError:
            pass

        # Stock
        try:
            from apps.products.services.stocks import StocksService
            service = StocksService(user=self.user)
            if hasattr(service, 'bulk_create_stocks'):
                importers['stock'] = service.bulk_create_stocks
        except (ImportError, AttributeError):
            pass

        return importers

    def process_upload(self, *, model_key: str, file_obj) -> ImportResult:
        """
        validates permissions, verifies file integrity, and dispatches to the corresponding domain service.
        """
        self.validate_permission()

        #validation
        is_valid, validation_msg = BaseETLHelper.validate_file(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=validation_msg)

        #registry lookup
        importers = self.get_registered_importers()
        normalized_key = model_key.lower().strip()
        importer = importers.get(normalized_key)

        if not importer:
            return ImportResult(
                success=False,
                message=f'No se encontró un procesador de importación registrado para la entidad "{model_key}".'
            )

        #exec
        try:
            return importer(file_obj)
        except Exception as e:
            return ImportResult(
                success=False,
                message=f'Ocurrió un error durante la ejecución de la importación: {str(e)}'
            )
