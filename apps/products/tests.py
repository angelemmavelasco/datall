from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.products.models import Product, ProductCategory, ProductClass, Stock
from apps.sales.models import Warehouse
from apps.products.services.products import ProductsService, ProductsStats

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

