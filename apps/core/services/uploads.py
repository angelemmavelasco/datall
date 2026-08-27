from __future__ import annotations

import io
try:
    import pandas as pd
except ImportError:
    pd = None

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Callable, Optional, Any
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

        file_size = getattr(file_obj, 'size', None)
        if file_size is None and hasattr(file_obj, 'getbuffer'):
            file_size = file_obj.getbuffer().nbytes
        elif file_size is None and hasattr(file_obj, 'seek') and hasattr(file_obj, 'tell'):
            file_obj.seek(0, io.SEEK_END)
            file_size = file_obj.tell()
            file_obj.seek(0)

        if file_size is not None and file_size <= 0:
            return False, "El archivo proporcionado se encuentra vacío o no contiene datos."

        return True, ""

    @classmethod
    def read_file_to_dataframe(cls, file_obj) -> tuple[bool, Optional[object] | str]:
        """
        reads a CSV or Excel file safely into a pandas DataFrame with string dtypes to preserve raw values.
        """
        if pd is None:
            return False, "La librería 'pandas' no está instalada en el entorno."

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
        submodule_name: str = 'importacion',
        context: str = 'columna'
    ) -> pd.DataFrame:
        """
        renames DataFrame columns according to the Reference mapping rules for the target model (case-insensitive).
        """
        ctype = ContentType.objects.get_for_model(model)

        references = Reference.objects.filter(content_type=ctype)
        if context:
            references = references.filter(context__icontains=context)

        if submodule_name:
            submodule_refs = references.filter(submodule__name__icontains=submodule_name)
            if submodule_refs.exists():
                references = submodule_refs

        column_map = {}
        for ref in references:
            raw_key = str(ref.key).strip().lower()
            target_val = str(ref.value).strip() if hasattr(ref, 'value') and ref.value else str(getattr(ref, 'reference', '')).strip()
            if raw_key and target_val:
                column_map[raw_key] = target_val

        new_columns = {}
        for col in df.columns:
            cleaned_col = str(col).strip().lower()
            if cleaned_col in column_map:
                new_columns[col] = column_map[cleaned_col]

        if new_columns:
            df.rename(columns=new_columns, inplace=True)

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

    @classmethod
    def validate_required_columns(
            cls,
            df: pd.DataFrame,
            required_columns: list[str] | dict[str, str]
        ) -> tuple[bool, str]:
        """
        Validates that required columns exist in the DataFrame after mapping.
        required_columns can be a list of column names or a dict of {col_name: human_label}.
        """
        detected_cols = list(df.columns)
        if isinstance(required_columns, dict):
            missing = [f"'{col}' ({label})" for col, label in required_columns.items() if col not in df.columns]
        else:
            missing = [f"'{col}'" for col in required_columns if col not in df.columns]

        if missing:
            missing_str = ', '.join(missing)
            detected_str = ', '.join([f"'{c}'" for c in detected_cols]) if detected_cols else '(ninguna)'
            return False, (
                f"El archivo no contiene la(s) columna(s) obligatoria(s): {missing_str}. "
                f"Columnas detectadas en el archivo: [{detected_str}]. "
                f"Por favor asegúrate de incluir las columnas requeridas o definir las Referencias correspondientes."
            )

        return True, ""

    @classmethod
    def validate_foreign_keys(
            cls,
            df: pd.DataFrame,
            model: type[models.Model],
            fields: list[str] | None = None,
            ignore_fields: list[str] | None = None
        ) -> tuple[bool, str]:
        """
        Universally validates that all Foreign Key values present in df exist in the related database tables.
        Returns (True, '') if valid, or (False, error_message) with detailed missing IDs and content type.
        """
        ignore_set = set(ignore_fields or [])
        fk_fields = [
            f for f in model._meta.get_fields()
            if f.is_relation and f.many_to_one and hasattr(f, 'attname')
        ]

        if fields:
            field_set = set(fields)
            fk_fields = [f for f in fk_fields if f.name in field_set or f.attname in field_set]

        for fk in fk_fields:
            col_name = fk.attname
            if col_name in ignore_set or fk.name in ignore_set:
                continue

            target_col = col_name if col_name in df.columns else (fk.name if fk.name in df.columns else None)
            if not target_col:
                continue

            related_model = fk.related_model
            model_verbose_name = getattr(related_model._meta, 'verbose_name', related_model.__name__).title()

            raw_values = df[target_col].dropna().astype(str).str.strip().unique()
            df_ids = {v for v in raw_values if v and v.lower() not in ('none', 'nan', 'null', '')}

            if not df_ids:
                continue

            if not related_model.objects.exists():
                return False, (
                    f"Error de clave foránea en la columna '{target_col}': "
                    f"No existen registros en el catálogo de {model_verbose_name} ({related_model.__name__}). "
                    f"Debes registrar al menos un registro en dicho catálogo antes de continuar."
                )

            db_pks = set(
                str(pk).strip() for pk in related_model.objects.filter(pk__in=df_ids).values_list('pk', flat=True)
            )

            missing_ids = df_ids - db_pks
            if missing_ids:
                missing_list = sorted(list(missing_ids))
                sample = missing_list[:10]
                suffix = f" ...y {len(missing_list) - 10} más" if len(missing_list) > 10 else ""
                return False, (
                    f"Error de clave foránea en la columna '{target_col}': "
                    f"Los siguientes IDs deben ser registrados en el catálogo de {model_verbose_name} ({related_model.__name__}): "
                    f"{sample}{suffix}. "
                    f"Por favor registra estos datos primero en el sistema o agrega su equivalencia en Referencias."
                )

        return True, ""

    @classmethod
    def humanize_database_error(cls, error: Exception) -> str:
        """
        parses raw database exceptions and converts them into friendly, readable spanish diagnostic messages.
        """
        err_msg = str(error)
        err_lower = err_msg.lower()

        if "violates foreign key constraint" in err_lower:
            import re
            detail_match = re.search(r"Key \((.*?)\)=\((.*?)\) is not present in table \"(.*?)\"", err_msg)
            if detail_match:
                col, val, table = detail_match.groups()
                return (
                    f"Error de integridad referencial: El valor '{val}' para el campo '{col}' "
                    f"no existe en la tabla '{table}'. Por favor regístralo antes de continuar."
                )
            return f"Error de clave foránea: Uno o más registros hacen referencia a datos inexistentes en el sistema. Detalle: {err_msg}"

        if "violates unique constraint" in err_lower or "duplicate key" in err_lower:
            import re
            detail_match = re.search(r"Key \((.*?)\)=\((.*?)\) already exists", err_msg)
            if detail_match:
                col, val = detail_match.groups()
                return f"Error de registro duplicado: Ya existe un registro con '{col}' = '{val}'."
            return f"Error de registro duplicado: Ya existe un registro con los mismos identificadores únicos."

        if "violates not-null constraint" in err_lower:
            import re
            match = re.search(r"column \"(.*?)\"", err_msg)
            col = match.group(1) if match else "desconocida"
            return f"Error de campo obligatorio: La columna '{col}' no puede estar vacía."

        return f"Error durante la inserción/actualización en base de datos: {err_msg}"


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
        try:
            self.validate_permission()
        except PermissionsError as e:
            return ImportResult(success=False, message=str(e))

        if not model_key:
            return ImportResult(success=False, message="No se especificó la entidad o catálogo a importar.")

        # validation
        is_valid, validation_msg = BaseETLHelper.validate_file(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=validation_msg)

        # registry lookup
        importers = self.get_registered_importers()
        normalized_key = model_key.lower().strip()
        importer = importers.get(normalized_key)

        if not importer:
            return ImportResult(
                success=False,
                message=f'No se encontró un procesador de importación registrado para la entidad "{model_key}".'
            )

        # exec
        try:
            return importer(file_obj)
        except Exception as e:
            return ImportResult(
                success=False,
                message=f'Ocurrió un error durante la ejecución de la importación: {str(e)}',
                errors=[str(e)]
            )
