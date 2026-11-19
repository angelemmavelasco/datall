import io
from datetime import date
from decimal import Decimal
import openpyxl
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.customers.models import Customer, CustomerType
from apps.products.models import (
    Product,
    ProductCategory,
    ProductClass,
    Stock,
    PurchaseOrder,
    PurchaseOrderItem,
)
from apps.sales.models import Warehouse, SaleTransaction
from apps.products.services.products import ProductsService, ProductsStats
from apps.products.services.purchase_orders import PurchaseOrdersService, PurchaseOrderExports

User = get_user_model()

class ProductsStatsTest(TestCase):
    def test_products_stats(self):
        user = User.objects.create_user(username='u', password='p')
        cat = ProductCategory.objects.create(id='C1', name='Cat1')
        pclass = ProductClass.objects.create(id='CL1', name='Class1', product_category=cat)
        p1 = Product.objects.create(id='P1', name='Prod1', product_class=pclass, price=Decimal('10.00'), is_active=True)
        p2 = Product.objects.create(id='P2', name='Prod2', product_class=pclass, price=Decimal('20.00'), is_active=True)
        w1 = Warehouse.objects.create(id='w1', name='Wh1', warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE)
        w2 = Warehouse.objects.create(id='w2', name='Wh2', warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE)

        Stock.objects.create(product=p1, warehouse=w1, quantity=Decimal('10.00'), lot_number='L1')
        Stock.objects.create(product=p1, warehouse=w2, quantity=Decimal('20.00'), lot_number='L2')
        Stock.objects.create(product=p2, warehouse=w1, quantity=Decimal('30.00'), lot_number='L3')

        ps = ProductsService(user=user)
        qs = ps.read_products()
        stats_svc = ProductsStats(products_service=ps)
        kpis = stats_svc.stats(qs=qs)

        self.assertEqual(kpis['total_stock'], Decimal('60.00'))
        self.assertEqual(kpis['avg_price'], Decimal('15.00'))
        self.assertEqual(kpis['products_count'], 2)

    def test_products_stats_with_distinct_filtered_and_identical_lots(self):
        user = User.objects.create_user(username='u2', password='p')
        cat = ProductCategory.objects.create(id='C2', name='Cat2')
        pclass = ProductClass.objects.create(id='CL2', name='Class2', product_category=cat)
        p = Product.objects.create(id='P3', name='Prod3', product_class=pclass, price=Decimal('50.00'), is_active=True)
        w = Warehouse.objects.create(id='w3', name='Wh3', warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE)

        # Two different lots with identical quantity (10.00 each)
        Stock.objects.create(product=p, warehouse=w, quantity=Decimal('10.00'), lot_number='LOTA')
        Stock.objects.create(product=p, warehouse=w, quantity=Decimal('10.00'), lot_number='LOTB')

        ps = ProductsService(user=user)
        # Apply distinct to simulate filtering through relationships
        qs = ps.read_products().filter(product_class__product_category=cat).distinct()
        stats_svc = ProductsStats(products_service=ps)
        kpis = stats_svc.stats(qs=qs)

        # Should be 20.00, not collapsed to 10.00
        self.assertEqual(kpis['total_stock'], Decimal('20.00'))


class PurchaseOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='po_admin', password='password123', email='po@test.com')
        self.client = Client()
        self.client.force_login(self.user)

        self.cat = ProductCategory.objects.create(id='CAT1', name='Consumibles')
        self.pclass = ProductClass.objects.create(id='dmd', name='Diamond', product_category=self.cat)
        self.product = Product.objects.create(
            id='SKU100',
            name='Guante Nitrilo',
            product_class=self.pclass,
            weight=Decimal('2.5000'),
            pieces_per_box=10,
            boxes_per_pallet=5,
            is_active=True,
        )

        self.wh_gdl = Warehouse.objects.create(
            id='gdl',
            name='Guadalajara',
            warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE,
        )
        self.wh_mty = Warehouse.objects.create(
            id='mty',
            name='Monterrey',
            warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE,
        )
        self.wh_t_mty = Warehouse.objects.create(
            id='t_mty',
            name='Tránsito MTY',
            warehouse_type=Warehouse.WarehouseTypeChoices.TRANSFER,
        )

        self.cust_type = CustomerType.objects.create(id='CT1', name='Distribuidor')
        self.customer = Customer.objects.create(
            id='CUST1',
            name='Cliente Test',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )

        # 2 months evaluation window (2026-08 to 2026-09):
        # GDL sold 20 (avg 10/mo), physical stock 100 (90 surplus vs 1 mo target)
        # MTY sold 100 (avg 50/mo), physical stock 10 + transit 10 = 20 (30 deficit vs 1 mo target)
        # Separated suggestion: GDL=0, MTY=30 -> 30
        # Accumulated suggestion: total_avg=60, total_stock=110, total_transit=10 -> max(60-120, 0)=0 (or for 3 mos: 180-120=60)
        SaleTransaction.objects.create(
            doc_id='D1',
            sale_date=date(2026, 8, 15),
            quantity=Decimal('20.00'),
            customer=self.customer,
            warehouse=self.wh_gdl,
            product_class=self.pclass,
            product=self.product,
        )
        SaleTransaction.objects.create(
            doc_id='D2',
            sale_date=date(2026, 9, 15),
            quantity=Decimal('100.00'),
            customer=self.customer,
            warehouse=self.wh_mty,
            product_class=self.pclass,
            product=self.product,
        )
        Stock.objects.create(product=self.product, warehouse=self.wh_gdl, quantity=Decimal('100.00'), lot_number='L1')
        Stock.objects.create(product=self.product, warehouse=self.wh_mty, quantity=Decimal('10.00'), lot_number='L2')
        Stock.objects.create(product=self.product, warehouse=self.wh_t_mty, quantity=Decimal('10.00'), lot_number='L3')

        self.service = PurchaseOrdersService(user=self.user)

    def test_accumulated_order_saves_empty_breakdown_and_recalculates_product_coverage(self):
        order = self.service.create_purchase_order(
            origin_type=PurchaseOrder.OriginChoices.IMPORTACION,
            grouping_mode=PurchaseOrder.GroupingModeChoices.ACCUMULATED,
            warehouse_ids=['gdl', 'mty'],
            start_date_str='2026-08',
            end_date_str='2026-09',
            coverage_months=Decimal('3.0'),
            requested_quantities={'SKU100': Decimal('75')},
            product_coverages={'SKU100': Decimal('4.0')},
            custom_folio='PO-ACC-01',
        )

        item = order.items.get(product=self.product)
        self.assertEqual(item.warehouse_breakdown, {})
        self.assertEqual(item.requested_units, Decimal('75.00'))
        # 60 avg/mo * 4.0 mos - 110 stock - 10 transit = 120
        self.assertEqual(item.suggested_units, Decimal('120.00'))
        # 75 requested / 50 units_per_pallet = 2 pallets = 100 ordered units
        self.assertEqual(item.pallets_ordered, 2)
        self.assertEqual(item.ordered_units, 100)

    def test_accumulated_excel_export_omits_cedis_columns_and_preserves_requested_units(self):
        order = self.service.create_purchase_order(
            origin_type=PurchaseOrder.OriginChoices.IMPORTACION,
            grouping_mode=PurchaseOrder.GroupingModeChoices.ACCUMULATED,
            warehouse_ids=['gdl', 'mty'],
            start_date_str='2026-08',
            end_date_str='2026-09',
            coverage_months=Decimal('3.0'),
            requested_quantities={'SKU100': Decimal('75')},
            custom_folio='PO-ACC-EXP',
        )
        # Simulate legacy DB row that still had stale per-CEDIS breakdown stored
        item = order.items.get(product=self.product)
        item.warehouse_breakdown = {'gdl': 20, 'mty': 130}
        item.save(update_fields=['warehouse_breakdown'])

        xlsx_bytes = PurchaseOrderExports.export_order_excel(
            order=order,
            logistics_params=self.service.get_logistics_parameters(),
        )
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
        self.assertEqual(
            wb.sheetnames,
            [PurchaseOrderExports.ORDER_SHEET_TITLE, PurchaseOrderExports.FORECAST_SHEET_TITLE],
        )

        ws_order = wb[PurchaseOrderExports.ORDER_SHEET_TITLE]
        ws_forecast = wb[PurchaseOrderExports.FORECAST_SHEET_TITLE]

        # Find SKU100 row in sheet 1
        s1_sku_row = None
        for r in range(1, ws_order.max_row + 1):
            if ws_order.cell(row=r, column=1).value == 'SKU100':
                s1_sku_row = r
                break
        self.assertIsNotNone(s1_sku_row)

        # Super-header uses Product Attributes (not Static Specs) and no CEDIS Breakdown in accumulated mode
        super_header_row = s1_sku_row - 3
        self.assertEqual(
            ws_order.cell(row=super_header_row, column=1).value,
            'Atributos del Producto / Product Attributes',
        )
        self.assertEqual(
            ws_order.cell(row=super_header_row, column=8).value,
            'Consolidado de la Orden / Order Consolidation',
        )

        es_header_row = s1_sku_row - 2
        es_headers = [ws_order.cell(row=es_header_row, column=c).value for c in range(1, 13)]
        self.assertFalse(any(h and str(h).startswith('Pedido ') for h in es_headers))

        # Col 8 (H) must be exact requested_units (75.0), NOT =SUM(...)
        self.assertEqual(ws_order.cell(row=s1_sku_row, column=8).value, 75.0)
        self.assertEqual(ws_order.cell(row=s1_sku_row, column=9).value, f'=IF(H{s1_sku_row}>0, CEILING(H{s1_sku_row}/G{s1_sku_row}, 1), 0)')
        self.assertEqual(ws_order.cell(row=s1_sku_row, column=11).value, f'=I{s1_sku_row}*G{s1_sku_row}')

        sub_row = s1_sku_row + 1
        self.assertEqual(ws_order.cell(row=sub_row, column=8).value, f'=SUM(H{s1_sku_row}:H{s1_sku_row})')
        self.assertEqual(ws_order.cell(row=sub_row, column=12).value, f'=SUM(L{s1_sku_row}:L{s1_sku_row})')

        sum_head_row = sub_row + 2
        self.assertEqual(ws_order.cell(row=sum_head_row, column=1).value, 'RESUMEN DE ORDEN / ORDER SUMMARY')
        self.assertEqual(ws_order.cell(row=sum_head_row + 1, column=3).value, f'=L{sub_row}')
        self.assertEqual(ws_order.cell(row=sum_head_row + 2, column=3).value, f'=I{sub_row}')
        self.assertEqual(ws_order.cell(row=sum_head_row + 3, column=3).value, f'=C{sum_head_row + 2}*75.0')
        self.assertEqual(ws_order.cell(row=sum_head_row + 4, column=3).value, f'=L{sub_row}+C{sum_head_row + 3}')
        self.assertEqual(ws_order.cell(row=sum_head_row + 5, column=3).value, f'=C{sum_head_row + 4}/44000.0')

        # Sheet 2 links live to Sheet 1 Col H (requested) and Col K (ordered)
        s2_sku_row = None
        for r in range(1, ws_forecast.max_row + 1):
            if ws_forecast.cell(row=r, column=1).value == 'SKU100':
                s2_sku_row = r
                break
        self.assertIsNotNone(s2_sku_row)
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=4).value, 110.0)
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=5).value, 10.0)
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=6).value, 120.0)
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=7).value, 60.0)
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=8).value, 3.0)
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=9).value, 60.0)
        self.assertEqual(
            ws_forecast.cell(row=s2_sku_row, column=10).value,
            f"='{PurchaseOrderExports.ORDER_SHEET_TITLE}'!H{s1_sku_row}",
        )
        self.assertEqual(ws_forecast.cell(row=s2_sku_row, column=11).value, f'=J{s2_sku_row}-I{s2_sku_row}')
        self.assertEqual(
            ws_forecast.cell(row=s2_sku_row, column=12).value,
            f"='{PurchaseOrderExports.ORDER_SHEET_TITLE}'!K{s1_sku_row}",
        )

    def test_separated_excel_export_keeps_cedis_breakdown_and_sum_formula(self):
        order = self.service.create_purchase_order(
            origin_type=PurchaseOrder.OriginChoices.LOCAL,
            grouping_mode=PurchaseOrder.GroupingModeChoices.SEPARATED,
            warehouse_ids=['gdl', 'mty'],
            start_date_str='2026-08',
            end_date_str='2026-09',
            coverage_months=Decimal('2.0'),
            warehouse_quantities={'SKU100': {'gdl': Decimal('5'), 'mty': Decimal('80')}},
            custom_folio='PO-SEP-EXP',
        )
        xlsx_bytes = PurchaseOrderExports.export_order_excel(
            order=order,
            logistics_params=self.service.get_logistics_parameters(),
        )
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
        ws_order = wb[PurchaseOrderExports.ORDER_SHEET_TITLE]

        s1_sku_row = None
        for r in range(1, ws_order.max_row + 1):
            if ws_order.cell(row=r, column=1).value == 'SKU100':
                s1_sku_row = r
                break
        self.assertIsNotNone(s1_sku_row)

        super_header_row = s1_sku_row - 3
        self.assertEqual(
            ws_order.cell(row=super_header_row, column=8).value,
            'Desglose por CEDIS / CEDIS Breakdown',
        )
        self.assertEqual(
            ws_order.cell(row=super_header_row, column=10).value,
            'Consolidado de la Orden / Order Consolidation',
        )
        self.assertEqual(ws_order.cell(row=s1_sku_row, column=8).value, 5.0)
        self.assertEqual(ws_order.cell(row=s1_sku_row, column=9).value, 80.0)
        self.assertEqual(ws_order.cell(row=s1_sku_row, column=10).value, f'=SUM(H{s1_sku_row}:I{s1_sku_row})')

    def test_detail_view_hides_cedis_breakdown_for_accumulated_orders(self):
        acc_order = self.service.create_purchase_order(
            origin_type=PurchaseOrder.OriginChoices.IMPORTACION,
            grouping_mode=PurchaseOrder.GroupingModeChoices.ACCUMULATED,
            warehouse_ids=['gdl', 'mty'],
            start_date_str='2026-08',
            end_date_str='2026-09',
            coverage_months=Decimal('3.0'),
            requested_quantities={'SKU100': Decimal('75')},
            custom_folio='PO-ACC-VIEW',
        )
        sep_order = self.service.create_purchase_order(
            origin_type=PurchaseOrder.OriginChoices.LOCAL,
            grouping_mode=PurchaseOrder.GroupingModeChoices.SEPARATED,
            warehouse_ids=['gdl', 'mty'],
            start_date_str='2026-08',
            end_date_str='2026-09',
            coverage_months=Decimal('2.0'),
            warehouse_quantities={'SKU100': {'gdl': Decimal('5'), 'mty': Decimal('80')}},
            custom_folio='PO-SEP-VIEW',
        )

        acc_resp = self.client.get(reverse('products:purchase_order_detail_view', kwargs={'pk': acc_order.pk}))
        self.assertEqual(acc_resp.status_code, 200)
        self.assertNotContains(acc_resp, 'Requerimiento por CEDIS')

        sep_resp = self.client.get(reverse('products:purchase_order_detail_view', kwargs={'pk': sep_order.pk}))
        self.assertEqual(sep_resp.status_code, 200)
        self.assertContains(sep_resp, 'Requerimiento por CEDIS')

