from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar
import traceback

try:
    import pandas as pd
except ImportError:
    pd = None

from django.db import transaction, IntegrityError
from django.db.models import QuerySet
from django.utils import timezone
from apps.core.services.uploads import BaseETLHelper

from apps.core.services.users import UsersService
from apps.products.models import Product, Stock
from apps.sales.models import Warehouse


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class StockNotFound(ServiceError):
    pass


@dataclass
class StocksService(UsersService):
    stock_model: type = Stock
    product_model: type = Product
    warehouse_model: type = Warehouse

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_inventario',
        'inventario',
        'acceso_total_productos',
        'acceso_total',
    )

    def read_stocks(self) -> QuerySet:
        """
        returns the queryset of stocks with product and warehouse select_related.
        """
        return self.stock_model.objects.select_related(
            'product',
            'product__product_class',
            'product__product_class__product_category',
            'warehouse'
        ).order_by('product__name', 'warehouse__name', 'lot_number')

    def read_stock(self, *, pk: int) -> Stock:
        """
        returns a single stock record by primary key.
        """
        stock = self.read_stocks().filter(pk=pk).first()
        if stock:
            return stock

        if self.stock_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la existencia con ID "{pk}".')

        raise StockNotFound(f'No se encontró ninguna existencia con el ID "{pk}".')

    def _clean_stocks(self, file_obj) -> tuple[bool, str | object]:
        """
        cleans and normalizes tabular data for Stock imports.
        supports Reference mappings and default fallback column names:
        - cve_prod / cve_producto / producto -> product_id
        - lote -> lot_number
        - lugar / almacen / cedis -> warehouse_id
        - existencia / cantidad -> quantity
        - fech_venc / fecha_caducidad -> expiration_date
        """
        print(f"\n[STOCKS-ETL] initializing etl stock process", flush=True)

        if pd is None:
            err = "La librería 'pandas' no está instalada en el entorno."
            print(f"[STOCKS-ETL ERROR] {err}", flush=True)
            return False, err

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            print(f"[STOCKS-ETL ERROR] failed to load dataframe from file", flush=True)
            return False, df_or_err

        df = df_or_err
        print(f"[STOCKS-ETL] original columns read from file: {list(df.columns)}", flush=True)

        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.stock_model,
            submodule_url_name='core:upload_options_list_view',
            context='columna'
        )

        fallback_map = {
            'cve_prod': 'product_id',
            'cve_producto': 'product_id',
            'cve_art': 'product_id',
            'producto': 'product_id',
            'product': 'product_id',
            'lote': 'lot_number',
            'num_lote': 'lot_number',
            'lugar': 'warehouse_id',
            'almacen': 'warehouse_id',
            'cedis': 'warehouse_id',
            'warehouse': 'warehouse_id',
            'existencia': 'quantity',
            'existencias': 'quantity',
            'cantidad': 'quantity',
            'stock': 'quantity',
            'fech_venc': 'expiration_date',
            'f_venc': 'expiration_date',
            'fecha_venc': 'expiration_date',
            'fecha_vencimiento': 'expiration_date',
            'fecha_caducidad': 'expiration_date',
            'caducidad': 'expiration_date',
            'vencimiento': 'expiration_date',
        }

        rename_dict = {}
        for col in df.columns:
            clean_col = str(col).strip().lower()
            if clean_col in fallback_map and fallback_map[clean_col] not in df.columns:
                rename_dict[col] = fallback_map[clean_col]

        if rename_dict:
            df.rename(columns=rename_dict, inplace=True)
            print(f"[STOCKS-ETL] fallback renamed columns: {rename_dict}", flush=True)

        df = BaseETLHelper.resolve_foreign_key_columns(df, self.stock_model)
        print(f"[STOCKS-ETL] columns after fallback map and resolve: {list(df.columns)}", flush=True)

        is_req_valid, req_msg = BaseETLHelper.validate_required_columns(
            df,
            {
                'product_id': 'Producto (cve_prod / product_id)',
                'warehouse_id': 'Centro de Distribución / Almacén (lugar / warehouse_id)',
                'quantity': 'Existencia / Cantidad (existencia / quantity)',
            }
        )
        if not is_req_valid:
            print(f"[STOCKS-ETL ERROR] required columns validation failed: {req_msg}", flush=True)
            return False, req_msg

        if 'warehouse_id' in df.columns:
            df = BaseETLHelper.apply_reference_value_mappings(
                df,
                column='warehouse_id',
                target_model=self.warehouse_model,
                context='valor_cedis',
                submodule_url_name='core:upload_options_list_view'
            )

        str_cols = ['product_id', 'warehouse_id', 'lot_number']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': None, 'NaN': None, 'None': None, 'none': None, 'null': None, 'NULL': None, '': None})

        if 'lot_number' in df.columns:
            df['lot_number'] = df['lot_number'].fillna('')
        else:
            df['lot_number'] = ''
        df = df.dropna(subset=['product_id', 'warehouse_id'])
        if df.empty:
            err = "The file does not contain valid stock after discarding rows without product or warehouse."
            print(f"[STOCKS-ETL ERROR] {err}", flush=True)
            return False, err

        if 'quantity' in df.columns:
            df['quantity'] = pd.to_numeric(
                df['quantity'].astype(str).str.replace(r'[$, ]', '', regex=True),
                errors='coerce'
            ).fillna(0.0).round(2)
        else:
            df['quantity'] = 0.0

        if 'expiration_date' in df.columns:
            fechas_str = df['expiration_date'].astype(str).str.strip().str.replace(' 00:00:00', '', regex=False)
            fechas_str = fechas_str.replace({'nan': None, 'NaN': None, 'None': None, 'none': None, 'null': None, '': None})

            dates_iso = pd.to_datetime(fechas_str, format='%Y-%m-%d', errors='coerce')
            dates_mx = pd.to_datetime(fechas_str, format='%d/%m/%Y', errors='coerce')
            dates_mx_short = pd.to_datetime(fechas_str, format='%d/%m/%y', errors='coerce')

            parsed_dates = dates_iso.fillna(dates_mx).fillna(dates_mx_short).fillna(pd.to_datetime(fechas_str, errors='coerce'))
            df['expiration_date'] = parsed_dates.dt.date
            df['expiration_date'] = df['expiration_date'].where(df['expiration_date'].notnull(), None)
        else:
            df['expiration_date'] = None

        is_fk_valid, fk_msg = BaseETLHelper.validate_foreign_keys(df, self.stock_model)
        if not is_fk_valid:
            print(f"[STOCKS-ETL ERROR] foreign key validation failed: {fk_msg}", flush=True)
            return False, fk_msg
        initial_count = len(df)
        df = df.groupby(['product_id', 'warehouse_id', 'lot_number'], as_index=False).agg({
            'quantity': 'sum',
            'expiration_date': 'first',
        })
        if len(df) < initial_count:
            print(f"[STOCKS-ETL] consolidated {initial_count - len(df)} duplicate records grouping by Product, Warehouse and Lot.", flush=True)

        df = df.where(pd.notnull(df), None)
        print(f"[STOCKS-ETL SUCCESS] Cleaning completed. {len(df)} stock records ready to process.\n", flush=True)

        return True, df

    def bulk_create_stocks(self, file_obj) -> object:
        """
        Executes bulk import/upsert of Stock records into the database.
        Respects the unique constraint on (product, warehouse, lot_number).
        """
        from apps.core.services.uploads import ImportResult, PermissionsError, BaseETLHelper

        print(f"\n[STOCKS-BULK] initializing bulk_create_stocks", flush=True)

        if not self.has_full_access:
            err_msg = 'No tienes permisos suficientes para realizar cargas masivas de existencias.'
            print(f"[STOCKS-BULK PERMISSIONS ERROR] {err_msg}", flush=True)
            raise PermissionsError(err_msg)

        is_valid, df_or_err = self._clean_stocks(file_obj)
        if not is_valid:
            print(f"[STOCKS-BULK VALIDATION ERROR] {df_or_err}", flush=True)
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        if df is None or df.empty:
            return ImportResult(success=False, message="El archivo no contiene existencias para procesar.")

        product_ids = set(df['product_id'].dropna().unique())
        warehouse_ids = set(df['warehouse_id'].dropna().unique())

        print(f"[STOCKS-BULK] Productos únicos: {len(product_ids)} | Almacenes únicos: {len(warehouse_ids)}", flush=True)

        # Lookup existing stocks for the matching products and warehouses
        existing_stocks_qs = self.stock_model.objects.filter(
            product_id__in=product_ids,
            warehouse_id__in=warehouse_ids
        )
        existing_stocks_map = {
            (str(s.product_id).strip(), str(s.warehouse_id).strip(), (s.lot_number or '').strip()): s
            for s in existing_stocks_qs
        }
        print(f"[STOCKS-BULK] Existencias coincidentes en BD: {len(existing_stocks_map)}", flush=True)

        stocks_to_create = []
        stocks_to_update = []
        total_processed = 0

        for _, row in df.iterrows():
            pid = str(row['product_id']).strip()
            wid = str(row['warehouse_id']).strip()
            lot = str(row.get('lot_number', '') or '').strip()
            qty = row['quantity']
            exp_date = row.get('expiration_date')
            if pd.isna(exp_date) or str(exp_date).strip() in ('', 'None', 'nan', 'NaN', 'NaT'):
                exp_date = None

            key = (pid, wid, lot)
            total_processed += 1

            if key in existing_stocks_map:
                stock_instance = existing_stocks_map[key]
                stock_instance.quantity = qty
                stock_instance.expiration_date = exp_date
                stock_instance.updated_at = timezone.now()
                stocks_to_update.append(stock_instance)
            else:
                stocks_to_create.append(
                    self.stock_model(
                        product_id=pid,
                        warehouse_id=wid,
                        lot_number=lot,
                        quantity=qty,
                        expiration_date=exp_date
                    )
                )

        print(
            f"[STOCKS-BULK PLAN] Nuevos a crear: {len(stocks_to_create)} | "
            f"A actualizar: {len(stocks_to_update)}",
            flush=True
        )

        try:
            with transaction.atomic():
                if stocks_to_create:
                    print(f"[STOCKS-BULK DB] Creando {len(stocks_to_create)} existencias...", flush=True)
                    self.stock_model.objects.bulk_create(stocks_to_create, batch_size=1000)

                if stocks_to_update:
                    print(f"[STOCKS-BULK DB] Actualizando {len(stocks_to_update)} existencias...", flush=True)
                    self.stock_model.objects.bulk_update(
                        stocks_to_update,
                        ['quantity', 'expiration_date', 'updated_at'],
                        batch_size=1000
                    )

            success_msg = f"Importación exitosa. Se crearon {len(stocks_to_create)} existencias y se actualizaron {len(stocks_to_update)}."
            print(f"[STOCKS-BULK SUCCESS] {success_msg}\n", flush=True)
            return ImportResult(
                success=True,
                message=success_msg,
                total_processed=total_processed,
                created_count=len(stocks_to_create),
                updated_count=len(stocks_to_update)
            )

        except Exception as e:
            print(f"\n[STOCKS-BULK DATABASE EXCEPTION] Error al ejecutar transacción en base de datos: {str(e)}", flush=True)
            traceback.print_exc()
            humanized_msg = BaseETLHelper.humanize_database_error(e)
            print(f"[STOCKS-BULK HUMANIZED MESSAGE] {humanized_msg}\n", flush=True)
            return ImportResult(
                success=False,
                message=humanized_msg,
                total_processed=total_processed,
                errors=[str(e)]
            )

    class StockTransfersService:
        pass
