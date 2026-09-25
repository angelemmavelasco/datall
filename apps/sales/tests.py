from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.template.loader import render_to_string

from apps.core.models import User
from apps.customers.models import Customer, CustomerType, CustomerAssignment
from apps.products.models import ProductClass, ProductCategory, Product
from apps.human_resources.models import BusinessUnit
from apps.sales.models import Route, RouteType, SaleChannel, SaleTransaction
from apps.sales.filters import SaleTransactionFilter


class SaleTransactionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin_sales', password='password123', email='admin@test.com')
        self.client = Client()
        self.client.force_login(self.user)

        self.cust_type = CustomerType.objects.create(name='Clinica')
        self.customer = Customer.objects.create(
            id='CUST100',
            name='Hospital Veterinario',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )

        self.region = BusinessUnit.objects.create(
            id='REG01',
            name='Region Centro',
            business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION,
        )
        self.unit = BusinessUnit.objects.create(
            id='BU01',
            name='Gerencia Centro',
            business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT,
            parent=self.region,
        )

        self.route_type = RouteType.objects.create(id='RT1', name='Ruta Foranea')
        self.channel = SaleChannel.objects.create(id='SC1', name='Canal Directo')
        self.route = Route.objects.create(
            id='R101',
            name='Ruta Centro 1',
            route_type=self.route_type,
            sale_channel=self.channel,
            business_unit=self.unit,
        )
        CustomerAssignment.objects.create(customer=self.customer, route=self.route, start_date=date(2026, 1, 1))

        self.category = ProductCategory.objects.create(id='CAT01', name='Medicamentos')
        self.product_class = ProductClass.objects.create(id='PC01', name='Antibioticos', product_category=self.category)
        self.product = Product.objects.create(id='PRD01', name='Amoxicilina', product_class=self.product_class)

        self.tx1 = SaleTransaction.objects.create(
            doc_id='FAC-001',
            sale_date=date(2026, 3, 15),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('10.00'),
            net_amount=Decimal('500.00'),
            gross_amount=Decimal('550.00'),
            cost=Decimal('300.00'),
            profit=Decimal('200.00'),
        )
        self.tx_negative = SaleTransaction.objects.create(
            doc_id='NC-001',
            sale_date=date(2026, 3, 20),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('-2.00'),
            net_amount=Decimal('-100.00'),
            gross_amount=Decimal('-110.00'),
            cost=Decimal('-60.00'),
            profit=Decimal('-40.00'),
        )
        self.tx_zero = SaleTransaction.objects.create(
            doc_id='BON-001',
            sale_date=date(2026, 3, 25),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('1.00'),
            net_amount=Decimal('0.00'),
            gross_amount=Decimal('0.00'),
            cost=Decimal('50.00'),
            profit=Decimal('-50.00'),
        )

    def test_sale_transaction_filter_by_customer_and_dates(self):
        f = SaleTransactionFilter(
            {'customer': [self.customer.pk], 'date_from': '2026-03-01', 'date_to': '2026-03-31'},
            queryset=SaleTransaction.objects.all(),
        )
        self.assertEqual(f.qs.count(), 3)

    def test_sale_transaction_filter_date_aliases(self):
        f = SaleTransactionFilter(
            {'customer': [self.customer.pk], 'date_start': '2026-03-18', 'date_end': '2026-03-31'},
            queryset=SaleTransaction.objects.all(),
        )
        self.assertEqual(f.qs.count(), 2)

    def test_sale_transaction_filter_by_product_class_and_category(self):
        f = SaleTransactionFilter(
            {'product_class': [self.product_class.pk], 'product_category': [self.category.pk]},
            queryset=SaleTransaction.objects.all(),
        )
        self.assertEqual(f.qs.count(), 3)

    def test_sale_transaction_filter_by_region(self):
        f = SaleTransactionFilter(
            {'region': [self.region.pk]},
            queryset=SaleTransaction.objects.all(),
        )
        self.assertEqual(f.qs.count(), 3)

    def test_customer_detail_view_provides_transactions_url(self):
        url = reverse('customers:customer_detail_view', args=[self.customer.pk])
        response = self.client.get(url, {
            'date_start': '2026-01-01',
            'date_end': '2026-03-31',
            'product_class': [self.product_class.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('transactions_url', response.context)
        tx_url = response.context['transactions_url']
        self.assertIn('customer=CUST100', tx_url)
        self.assertIn('date_from=2026-01-01', tx_url)
        self.assertIn('date_to=2026-03-31', tx_url)
        self.assertIn('product_class=PC01', tx_url)
        self.assertContains(response, 'Ver transacciones')
        self.assertContains(response, tx_url.replace('&', '&amp;'))

    def test_sale_transaction_amount_and_profit_color_conditionals(self):
        rendered_positive = render_to_string(
            'sales/sale_transactions/partials/sale_transaction_list_rows.html',
            {'transactions': [self.tx1], 'can_view_cost': True}
        )
        self.assertIn('$500.00', rendered_positive)
        self.assertIn('text-teal-500', rendered_positive)

        rendered_negative = render_to_string(
            'sales/sale_transactions/partials/sale_transaction_list_rows.html',
            {'transactions': [self.tx_negative], 'can_view_cost': True}
        )
        self.assertIn('text-red-500', rendered_negative)
        self.assertIn('$-100.00', rendered_negative)

        rendered_zero = render_to_string(
            'sales/sale_transactions/partials/sale_transaction_list_rows.html',
            {'transactions': [self.tx_zero], 'can_view_cost': True}
        )
        self.assertIn('text-red-500', rendered_zero)
        self.assertIn('$0.00', rendered_zero)
