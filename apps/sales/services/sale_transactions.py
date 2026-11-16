from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from django.db.models import (
    Q,
    QuerySet,
    Count,
    Sum,
    Avg,
)
from django.utils import timezone

from apps.core.services.users import UsersService
from apps.customers.models import Customer, CustomerAssignment
from apps.products.models import ProductClass
from apps.sales.models import SaleTransaction, Route, Warehouse
from apps.sales.services.routes import RoutesService


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class SaleTransactionNotFound(ServiceError):
    pass


@dataclass
class SaleTransactionsService(UsersService):
    sale_transaction_model: type = SaleTransaction
    route_model: type = Route
    warehouse_model: type = Warehouse
    customer_model: type = Customer
    customer_assignment_model: type = CustomerAssignment
    product_class_model: type = ProductClass

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_ventas',
        'ventas',
        'acceso_total_rutas',
        'acceso_total',
    )

    def _get_allowed_routes_qs(self) -> QuerySet:
        """
        helper to get allowed routes for the current user using RoutesService
        """
        routes_service = RoutesService(user=self.user)
        return routes_service.get_allowed_routes(can_view=True, can_edit=False)

    def read_transactions_by_allowed_routes(self) -> QuerySet:
        """
        Returns transactions executed/emitted by routes to which the user has access.
        Independent of whether the customer currently belongs to those routes or not.
        """
        base_qs = self.sale_transaction_model.objects.select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'route__sale_channel',
            'warehouse',
            'product',
            'product_class',
            'product_class__product_category',
        )

        if self.has_full_access:
            return base_qs.order_by('-sale_date', '-id')

        allowed_routes = self._get_allowed_routes_qs()
        return base_qs.filter(route__in=allowed_routes).order_by('-sale_date', '-id')

    def read_transactions_by_allowed_customers(self) -> QuerySet:
        """
        Returns transactions corresponding to customers currently assigned to routes
        to which the user has access, regardless of which route historically emitted the transaction.
        """
        base_qs = self.sale_transaction_model.objects.select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'route__sale_channel',
            'warehouse',
            'product',
            'product_class',
            'product_class__product_category',
        )

        if self.has_full_access:
            return base_qs.order_by('-sale_date', '-id')

        today = timezone.localdate()
        allowed_routes = self._get_allowed_routes_qs()

        # Customers currently assigned to allowed routes
        allowed_customers_subquery = self.customer_assignment_model.objects.filter(
            route__in=allowed_routes
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).values('customer_id')

        return base_qs.filter(customer_id__in=allowed_customers_subquery).order_by('-sale_date', '-id')

    def read_transactions(self) -> QuerySet:
        """
        Default transaction listing perspective for general views: based on allowed routes.
        """
        return self.read_transactions_by_allowed_routes()

    def read_transaction(self, *, pk: str | int) -> SaleTransaction:
        """
        Returns a single transaction by ID, validated against allowed routes.
        """
        transaction_obj = self.read_transactions_by_allowed_routes().filter(pk=pk).first()
        if transaction_obj:
            return transaction_obj

        if self.sale_transaction_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la transacción con ID "{pk}".')

        raise SaleTransactionNotFound(f'No se encontró ninguna transacción con el ID "{pk}".')

    def _clean_transactions(self, file_obj) -> tuple[bool, str | object]:
        try:
            import pandas as pd
        except ImportError:
            return False, "La librería 'pandas' no está instalada en el entorno."

        from apps.core.services.uploads import BaseETLHelper

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            return False, df_or_err

        df = df_or_err
        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.sale_transaction_model,
            submodule_url_name='core:upload_options_list_view',
            context='columna'
        )
        df = BaseETLHelper.resolve_foreign_key_columns(df, self.sale_transaction_model)

        is_req_valid, req_msg = BaseETLHelper.validate_required_columns(
            df,
            {
                'sale_date': 'Fecha de Venta',
                'doc_id': 'Número de Documento / Factura',
                'customer_id': 'Cliente',
                'product_id': 'Producto',
            }
        )
        if not is_req_valid:
            return False, req_msg

        valid_classes_dict = {str(c.id).strip().lower(): c.id for c in self.product_class_model.objects.all()}
        default_class = valid_classes_dict.get('otr') or (next(iter(valid_classes_dict.values())) if valid_classes_dict else None)

        if 'product_class_id' in df.columns:
            df = BaseETLHelper.apply_reference_value_mappings(
                df,
                column='product_class_id',
                target_model=self.product_class_model,
                context='valor_clase_producto',
                submodule_url_name='core:upload_options_list_view'
            )
            df['product_class_id'] = df['product_class_id'].apply(
                lambda x: valid_classes_dict.get(str(x).strip().lower(), default_class) if x not in (None, 'None', 'nan', '') else default_class
            )
        elif default_class:
            df['product_class_id'] = default_class

        valid_warehouses_dict = {str(w.id).strip().lower(): w.id for w in self.warehouse_model.objects.all()}
        default_warehouse = valid_warehouses_dict.get('snc') or (next(iter(valid_warehouses_dict.values())) if valid_warehouses_dict else None)

        if 'warehouse_id' in df.columns:
            df = BaseETLHelper.apply_reference_value_mappings(
                df,
                column='warehouse_id',
                target_model=self.warehouse_model,
                context='valor_cedis',
                submodule_url_name='core:upload_options_list_view'
            )
            df['warehouse_id'] = df['warehouse_id'].apply(
                lambda x: valid_warehouses_dict.get(str(x).strip().lower(), default_warehouse) if x not in (None, 'None', 'nan', '') else default_warehouse
            )
        elif default_warehouse:
            df['warehouse_id'] = default_warehouse

        str_cols = ['customer_id', 'route_id', 'doc_id', 'product_id']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': None, '': None, 'None': None, 'none': None, 'null': None, 'NULL': None})

        fechas_str = df['sale_date'].astype(str).str.strip().str.replace(' 00:00:00', '', regex=False)
        
        dates_iso = pd.to_datetime(fechas_str, format='%Y-%m-%d', errors='coerce')
        dates_mx = pd.to_datetime(fechas_str, format='%d/%m/%Y', errors='coerce')
        dates_mx_short = pd.to_datetime(fechas_str, format='%d/%m/%y', errors='coerce')
        
        df['sale_date'] = dates_iso.fillna(dates_mx).fillna(dates_mx_short).fillna(pd.to_datetime(fechas_str, errors='coerce'))
        df['sale_date'] = df['sale_date'].ffill().bfill()

        if df['sale_date'].isnull().all():
            return False, "No se pudo interpretar ninguna fecha válida en la columna mapeada a 'sale_date'."

        num_cols = ['cost', 'net_amount', 'gross_amount', 'profit', 'quantity']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(
                    df[c].astype(str).str.replace(r'[$, ]', '', regex=True),
                    errors='coerce'
                ).fillna(0.0).round(6)

        df = df.dropna(subset=['customer_id', 'sale_date'])
        if df.empty:
            return False, "El archivo no contiene transacciones válidas después de descartar filas sin cliente o fecha."

        is_fk_valid, fk_msg = BaseETLHelper.validate_foreign_keys(df, self.sale_transaction_model)
        if not is_fk_valid:
            return False, fk_msg

        df = df.where(pd.notnull(df), None)
        df['sale_date'] = pd.to_datetime(df['sale_date']).dt.date

        return True, df

    def bulk_create_transactions(self, file_obj) -> object:
        from apps.core.services.uploads import ImportResult, PermissionsError, BaseETLHelper
        from django.db import transaction

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para realizar cargas masivas de transacciones de venta.')

        is_valid, df_or_err = self._clean_transactions(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        if df is None or df.empty:
            return ImportResult(success=False, message="El archivo no contiene transacciones para procesar.")

        min_date = df['sale_date'].min()
        max_date = df['sale_date'].max()

        model_fields = [f.name for f in self.sale_transaction_model._meta.get_fields() if not f.is_relation]
        model_fields.extend([f.attname for f in self.sale_transaction_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
        
        valid_columns = [col for col in df.columns if col in model_fields and col != 'id']

        transactions_to_create = []
        total_processed = 0

        for _, row in df.iterrows():
            data = {}
            for col in valid_columns:
                val = row[col]
                if val is not None and str(val).lower() not in ['nan', '', 'none']:
                    data[col] = val
            
            if 'sale_date' not in data or 'doc_id' not in data:
                continue

            transactions_to_create.append(self.sale_transaction_model(**data))
            total_processed += 1

        if not transactions_to_create:
            return ImportResult(success=False, message="No se encontraron transacciones válidas para importar.")

        try:
            with transaction.atomic():
                deleted_count, _ = self.sale_transaction_model.objects.filter(sale_date__range=[min_date, max_date]).delete()

                self.sale_transaction_model.objects.bulk_create(
                    transactions_to_create,
                    batch_size=5000
                )

            return ImportResult(
                success=True,
                message=f"Importación exitosa. Se eliminaron {deleted_count} registros antiguos y se crearon {len(transactions_to_create)} nuevos en el rango {min_date} al {max_date}.",
                total_processed=total_processed,
                created_count=len(transactions_to_create),
                updated_count=0
            )

        except Exception as e:
            humanized_msg = BaseETLHelper.humanize_database_error(e)
            return ImportResult(
                success=False,
                message=humanized_msg,
                total_processed=total_processed,
                errors=[str(e)]
            )


@dataclass
class SaleTransactionsStats:
    '''dedicated only to give general stats about sale transactions'''
    sale_transactions_service: SaleTransactionsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.sale_transactions_service.read_transactions()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            transactions_count=Count('pk', distinct=True),
            total_quantity=Sum('quantity'),
            total_net_amount=Sum('net_amount'),
            total_gross_amount=Sum('gross_amount'),
            total_profit=Sum('profit'),
            avg_ticket=Avg('net_amount'),
            unique_customers_count=Count('customer', distinct=True),
            unique_products_count=Count('product', distinct=True),
        )

        agg['total_quantity'] = agg['total_quantity'] or Decimal('0.0000')
        agg['total_net_amount'] = agg['total_net_amount'] or Decimal('0.00')
        agg['total_gross_amount'] = agg['total_gross_amount'] or Decimal('0.00')
        agg['total_profit'] = agg['total_profit'] or Decimal('0.00')
        agg['avg_ticket'] = agg['avg_ticket'] or Decimal('0.00')

        if agg['total_net_amount'] > 0:
            agg['total_margin'] = (agg['total_profit'] / agg['total_net_amount']) * Decimal('100.00')
        else:
            agg['total_margin'] = Decimal('0.00')

        return agg


class SaleTransactionsExports:
    def __init__(self, sale_transactions_service: SaleTransactionsService):
        self.sale_transactions_service = sale_transactions_service

    def _is_vendor(self) -> bool:
        user = self.sale_transactions_service.user
        if not user or not hasattr(user, 'groups'):
            return False
        return user.groups.filter(name='vendedor').exists()

    def _get_margin_status(self, margin: Decimal | float) -> str:
        val = float(margin or 0)
        if val >= 43:
            return 'Excelente'
        if val >= 40:
            return 'Óptimo'
        if val >= 37:
            return 'Regular'
        if val >= 35:
            return 'Malo'
        return 'Muy malo'

    def export_sale_transactions_report(
        self,
        *,
        qs: 'QuerySet | None' = None,
        date_start: str = '',
        date_end: str = '',
    ) -> 'io.BytesIO':
        import io
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from django.utils import timezone

        service = self.sale_transactions_service
        base_qs = qs if qs is not None else service.read_transactions()
        is_vendor = self._is_vendor()
        can_view_cost = service.has_full_access and not is_vendor
        stats = SaleTransactionsStats(sale_transactions_service=service).stats(qs=base_qs)

        wb = openpyxl.Workbook()

        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        section_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
        title_font = Font(name="Calibri", size=14, bold=True, color="0F172A")
        subtitle_font = Font(name="Calibri", size=9, italic=True, color="64748B")
        data_font = Font(name="Calibri", size=10, color="0F172A")
        bold_data_font = Font(name="Calibri", size=10, bold=True, color="0F172A")
        green_font = Font(name="Calibri", size=10, color="15803D")
        green_bold_font = Font(name="Calibri", size=10, bold=True, color="15803D")
        red_font = Font(name="Calibri", size=10, color="B91C1C")
        red_bold_font = Font(name="Calibri", size=10, bold=True, color="B91C1C")
        amber_font = Font(name="Calibri", size=10, bold=True, color="D97706")

        thin_border_side = Side(style='thin', color='CBD5E1')
        cell_border = Border(
            left=thin_border_side,
            right=thin_border_side,
            top=thin_border_side,
            bottom=thin_border_side,
        )

        left_align = Alignment(horizontal="left", vertical="center")
        center_align = Alignment(horizontal="center", vertical="center")
        right_align = Alignment(horizontal="right", vertical="center")

        currency_format = '"$"#,##0.00'
        pct_format = '0.00%'
        int_format = '#,##0'
        qty_format = '#,##0.00'

        def get_status_font(margin_val: Decimal | float):
            val = float(margin_val or 0)
            if val >= 40:
                return green_bold_font
            if val >= 37:
                return amber_font
            return red_bold_font

        now_str = timezone.localtime().strftime('%Y-%m-%d %H:%M')
        if date_start and date_end:
            period_label = f"Periodo: {date_start} al {date_end}"
        elif date_start:
            period_label = f"Desde: {date_start}"
        elif date_end:
            period_label = f"Hasta: {date_end}"
        else:
            period_label = "Periodo: Todos los registros"

        ws_summary = wb.active
        ws_summary.title = "Resumen General"
        ws_summary.views.sheetView[0].showGridLines = True

        ws_summary.cell(row=1, column=1, value="REPORTE DE TRANSACCIONES DE VENTA").font = title_font
        ws_summary.cell(row=2, column=1, value=f"Generado el: {now_str} | {period_label}").font = subtitle_font

        ws_summary.cell(row=4, column=1, value="1. Indicadores Generales (KPIs)").font = section_font
        summary_headers = ["Indicador", "Valor"]
        for col_num, h_text in enumerate(summary_headers, 1):
            c = ws_summary.cell(row=5, column=col_num, value=h_text)
            c.fill = header_fill
            c.font = header_font
            c.alignment = center_align if col_num > 1 else left_align
            c.border = cell_border

        total_net = float(stats.get('total_net_amount') or 0)
        total_profit = float(stats.get('total_profit') or 0)
        total_margin = float(stats.get('total_margin') or 0)

        kpi_rows = [
            ("Transacciones", int(stats.get('transactions_count') or 0), int_format, bold_data_font, right_align),
            ("Piezas Vendidas", float(stats.get('total_quantity') or 0), qty_format, bold_data_font, right_align),
            (
                "Venta Neta Total",
                total_net,
                currency_format,
                red_bold_font if total_net <= 0 else green_bold_font,
                right_align,
            ),
            ("Ticket Promedio", float(stats.get('avg_ticket') or 0), currency_format, bold_data_font, right_align),
        ]

        if can_view_cost:
            kpi_rows.append(
                (
                    "Utilidad Total",
                    total_profit,
                    currency_format,
                    red_bold_font if total_profit <= 0 else green_bold_font,
                    right_align,
                )
            )

        if is_vendor:
            kpi_rows.append(
                (
                    "Evaluación",
                    self._get_margin_status(total_margin),
                    None,
                    get_status_font(total_margin),
                    center_align,
                )
            )
        else:
            kpi_rows.append(
                (
                    "Margen Total (%)",
                    total_margin / 100.0,
                    pct_format,
                    bold_data_font,
                    right_align,
                )
            )

        kpi_rows.extend([
            ("Clientes Atendidos", int(stats.get('unique_customers_count') or 0), int_format, bold_data_font, right_align),
            ("Productos Vendidos", int(stats.get('unique_products_count') or 0), int_format, bold_data_font, right_align),
        ])

        for r_idx, (lbl, val, num_fmt, val_font, val_align) in enumerate(kpi_rows, 6):
            c_lbl = ws_summary.cell(row=r_idx, column=1, value=lbl)
            c_lbl.font = data_font
            c_lbl.alignment = left_align
            c_lbl.border = cell_border

            c_val = ws_summary.cell(row=r_idx, column=2, value=val)
            c_val.font = val_font
            c_val.alignment = val_align
            c_val.border = cell_border
            if num_fmt:
                c_val.number_format = num_fmt

        ws_summary.column_dimensions['A'].width = 32
        ws_summary.column_dimensions['B'].width = 24

        ws_detail = wb.create_sheet(title="Transacciones")
        ws_detail.views.sheetView[0].showGridLines = True
        ws_detail.freeze_panes = "A5"

        ws_detail.cell(row=1, column=1, value="LISTADO DETALLADO DE TRANSACCIONES").font = title_font
        ws_detail.cell(row=2, column=1, value=f"Generado el: {now_str} | {period_label}").font = subtitle_font

        detail_columns = [
            ("Documento", 18),
            ("Fecha", 14),
            ("ID Cliente", 14),
            ("Cliente", 36),
            ("Ruta", 28),
            ("Gerencia", 22),
            ("Centro de Distribución", 24),
            ("Clase de Producto", 22),
            ("ID Producto", 14),
            ("Producto", 36),
            ("Cantidad", 14),
            ("Importe Neto", 18),
        ]
        if can_view_cost:
            detail_columns.append(("Utilidad", 18))
        if not is_vendor:
            detail_columns.append(("Margen (%)", 14))
        detail_columns.append(("Evaluación", 16))

        for col_num, (h_text, col_width) in enumerate(detail_columns, 1):
            c = ws_detail.cell(row=4, column=col_num, value=h_text)
            c.fill = header_fill
            c.font = header_font
            c.alignment = center_align
            c.border = cell_border
            ws_detail.column_dimensions[get_column_letter(col_num)].width = col_width

        detail_qs = base_qs.select_related(
            'customer',
            'route',
            'route__business_unit',
            'warehouse',
            'product',
            'product_class',
        )

        row_idx = 5
        for tx in detail_qs.iterator(chunk_size=2000):
            net_val = float(tx.net_amount or 0)
            profit_val = float(tx.profit or 0)
            margin_val = float(tx.margin or 0)
            qty_val = float(tx.quantity or 0)

            doc_str = (tx.doc_id or '-').upper()
            date_str = tx.sale_date.strftime('%Y-%m-%d') if tx.sale_date else '-'
            cust_id_str = (tx.customer.id or '-').upper() if tx.customer and tx.customer.id else '-'
            cust_name_str = tx.customer.name.title() if tx.customer and tx.customer.name else '-'
            route_str = f"{tx.route.id.upper()} - {tx.route.name.title()}" if tx.route else 'Sin ruta'
            bu_str = tx.route.business_unit.name.title() if tx.route and tx.route.business_unit and tx.route.business_unit.name else '-'
            wh_str = tx.warehouse.name.title() if tx.warehouse and tx.warehouse.name else '-'
            pclass_str = tx.product_class.name.title() if tx.product_class and tx.product_class.name else '-'
            prod_id_str = (tx.product.id or '-').upper() if tx.product and tx.product.id else '-'
            prod_name_str = (
                tx.product.name.title()
                if tx.product and tx.product.name
                else (pclass_str if pclass_str != '-' else '-')
            )

            row_cells = [
                (doc_str, center_align, data_font, None),
                (date_str, center_align, data_font, None),
                (cust_id_str, center_align, data_font, None),
                (cust_name_str, left_align, data_font, None),
                (route_str, left_align, data_font, None),
                (bu_str, left_align, data_font, None),
                (wh_str, left_align, data_font, None),
                (pclass_str, left_align, data_font, None),
                (prod_id_str, center_align, data_font, None),
                (prod_name_str, left_align, data_font, None),
                (qty_val, right_align, data_font, qty_format),
                (net_val, right_align, red_font if net_val <= 0 else green_font, currency_format),
            ]

            if can_view_cost:
                row_cells.append(
                    (profit_val, right_align, red_font if profit_val <= 0 else green_font, currency_format)
                )

            if not is_vendor:
                row_cells.append((margin_val / 100.0, right_align, data_font, pct_format))

            row_cells.append((self._get_margin_status(margin_val), center_align, get_status_font(margin_val), None))

            for col_num, (val, align, font, num_fmt) in enumerate(row_cells, 1):
                c = ws_detail.cell(row=row_idx, column=col_num, value=val)
                c.alignment = align
                c.font = font
                c.border = cell_border
                if num_fmt:
                    c.number_format = num_fmt

            row_idx += 1

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer
