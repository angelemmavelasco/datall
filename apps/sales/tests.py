import io
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
import openpyxl
from django.contrib.auth.models import Group
from django.test import TestCase, Client
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.core.models import User, GeneratedReport
from apps.customers.models import Customer, CustomerType, CustomerAssignment
from apps.products.models import ProductClass, ProductCategory, Product
from apps.human_resources.models import BusinessUnit, Department, Position, Employee
from apps.sales.models import Route, RouteType, SaleChannel, SaleTransaction, RouteAssignment, UserRouteAccess
from apps.sales.services.routes import RoutesService
from apps.sales.filters import SaleTransactionFilter, RouteFilter


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


class RouteAssignmentAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(id='DEP', name='Ventas')
        self.pos = Position.objects.create(id='POS01', name='Vendedor', department=self.dept)

        self.user_regular = User.objects.create_user(
            username='seller1',
            password='password123',
            email='seller1@test.com',
            first_name='Luis',
            last_name='Borrego'
        )
        self.emp = Employee.objects.create(
            id='EMP01',
            user=self.user_regular,
            position=self.pos,
            hire_date=date(2025, 1, 1),
        )

        self.route_type = RouteType.objects.create(id='RT01', name='Ruta Local')
        self.channel = SaleChannel.objects.create(id='SC01', name='Canal Tradicional')
        self.route = Route.objects.create(
            id='R_TEST',
            name='Ruta Prueba',
            route_type=self.route_type,
            sale_channel=self.channel,
            is_active=True,
        )

    def test_route_assignment_properties(self):
        today = timezone.localdate()

        # Past assignment
        past_assign = RouteAssignment(
            route=self.route,
            employee=self.emp,
            date_start=today - timedelta(days=60),
            date_end=today - timedelta(days=10),
        )
        self.assertFalse(past_assign.is_active)
        self.assertFalse(past_assign.is_future)
        self.assertTrue(past_assign.is_ended)
        self.assertEqual(past_assign.status_label, 'Finalizada')

        # Active assignment (ongoing, no date_end)
        active_assign = RouteAssignment(
            route=self.route,
            employee=self.emp,
            date_start=today - timedelta(days=5),
            date_end=None,
        )
        self.assertTrue(active_assign.is_active)
        self.assertFalse(active_assign.is_future)
        self.assertFalse(active_assign.is_ended)
        self.assertEqual(active_assign.status_label, 'Activa actualmente')

        # Active assignment (with future date_end)
        active_with_end = RouteAssignment(
            route=self.route,
            employee=self.emp,
            date_start=today - timedelta(days=5),
            date_end=today + timedelta(days=20),
        )
        self.assertTrue(active_with_end.is_active)
        self.assertFalse(active_with_end.is_future)
        self.assertFalse(active_with_end.is_ended)
        self.assertEqual(active_with_end.status_label, 'Activa actualmente')

        # Future assignment
        future_assign = RouteAssignment(
            route=self.route,
            employee=self.emp,
            date_start=today + timedelta(days=10),
            date_end=None,
        )
        self.assertFalse(future_assign.is_active)
        self.assertTrue(future_assign.is_future)
        self.assertFalse(future_assign.is_ended)
        self.assertEqual(future_assign.status_label, 'Programada')

    def test_route_assignment_clean_validation(self):
        today = timezone.localdate()
        invalid_assign = RouteAssignment(
            route=self.route,
            employee=self.emp,
            date_start=today,
            date_end=today - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            invalid_assign.clean()

    def test_future_assignment_without_specific_access_denies_view(self):
        today = timezone.localdate()
        # Assignment starting in the future
        RouteAssignment.objects.create(
            route=self.route,
            employee=self.emp,
            date_start=today + timedelta(days=5),
            date_end=None,
        )

        service = RoutesService(user=self.user_regular)
        allowed_routes = service.get_allowed_routes(can_view=True)
        self.assertNotIn(self.route, allowed_routes)

    def test_future_assignment_with_specific_access_grants_view(self):
        today = timezone.localdate()
        # Assignment starting in the future
        RouteAssignment.objects.create(
            route=self.route,
            employee=self.emp,
            date_start=today + timedelta(days=5),
            date_end=None,
        )
        # Specific access granted
        UserRouteAccess.objects.create(
            user=self.user_regular,
            route=self.route,
            can_view=True,
            can_edit=False,
        )

        service = RoutesService(user=self.user_regular)
        allowed_routes = service.get_allowed_routes(can_view=True)
        self.assertIn(self.route, allowed_routes)

    def test_active_assignment_grants_view_without_specific_access(self):
        today = timezone.localdate()
        # Assignment active today
        RouteAssignment.objects.create(
            route=self.route,
            employee=self.emp,
            date_start=today - timedelta(days=1),
            date_end=None,
        )

        service = RoutesService(user=self.user_regular)
        allowed_routes = service.get_allowed_routes(can_view=True)
        self.assertIn(self.route, allowed_routes)

    def test_read_routes_annotation_active_vs_future(self):
        today = timezone.localdate()
        admin_user = User.objects.create_superuser(
            username='admin_test',
            password='password123',
            email='admin_test@test.com'
        )

        # Route 1 has only future assignment
        RouteAssignment.objects.create(
            route=self.route,
            employee=self.emp,
            date_start=today + timedelta(days=7),
            date_end=None,
        )

        # Route 2 has active assignment
        route2 = Route.objects.create(
            id='R_ACTIVE',
            name='Ruta Activa',
            route_type=self.route_type,
            sale_channel=self.channel,
            is_active=True,
        )
        RouteAssignment.objects.create(
            route=route2,
            employee=self.emp,
            date_start=today - timedelta(days=7),
            date_end=None,
        )

        service = RoutesService(user=admin_user)
        routes_annotated = {r.id: r for r in service.read_routes()}

        self.assertIsNone(routes_annotated[self.route.id].current_employee_id)
        self.assertEqual(routes_annotated[route2.id].current_employee_id, self.emp.id)

    def test_route_detail_template_badges(self):
        today = timezone.localdate()
        # Past assignment
        past_emp_user = User.objects.create_user(username='past_emp', password='password123')
        past_emp = Employee.objects.create(
            id='EMP02', user=past_emp_user, position=self.pos, hire_date=date(2024, 1, 1)
        )
        RouteAssignment.objects.create(
            route=self.route,
            employee=past_emp,
            date_start=today - timedelta(days=60),
            date_end=today - timedelta(days=10),
        )
        # Future assignment
        RouteAssignment.objects.create(
            route=self.route,
            employee=self.emp,
            date_start=today + timedelta(days=5),
            date_end=None,
        )

        admin_user = User.objects.create_superuser(username='adm2', password='123', email='adm2@t.com')
        client = Client()
        client.force_login(admin_user)
        response = client.get(reverse('sales:route_detail_view', args=[self.route.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Programada')
        self.assertContains(response, 'Finalizada')
        self.assertNotContains(response, 'Activa actualmente')


class SaleTransactionExportTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin_export',
            password='password123',
            email='admin_export@test.com',
        )
        self.client = Client()
        self.client.force_login(self.admin_user)

        self.cust_type = CustomerType.objects.create(name='Clinica')
        self.customer = Customer.objects.create(
            id='CUST200',
            name='Clinica Norte',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )

        self.region = BusinessUnit.objects.create(
            id='REG02',
            name='Region Norte',
            business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION,
        )
        self.unit = BusinessUnit.objects.create(
            id='BU02',
            name='Gerencia Norte',
            business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT,
            parent=self.region,
        )

        self.route_type = RouteType.objects.create(id='RT02', name='Ruta Urbana')
        self.channel = SaleChannel.objects.create(id='SC02', name='Canal Directo')
        self.route = Route.objects.create(
            id='R202',
            name='Ruta Norte 1',
            route_type=self.route_type,
            sale_channel=self.channel,
            business_unit=self.unit,
        )
        CustomerAssignment.objects.create(customer=self.customer, route=self.route, start_date=date(2026, 1, 1))

        self.category = ProductCategory.objects.create(id='CAT02', name='Suplementos')
        self.product_class = ProductClass.objects.create(id='PC02', name='Vitaminas', product_category=self.category)
        self.product = Product.objects.create(id='PRD02', name='Complejo B', product_class=self.product_class)

        self.tx_pos = SaleTransaction.objects.create(
            doc_id='FAC-200',
            sale_date=date(2026, 3, 10),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('5.00'),
            net_amount=Decimal('500.00'),
            gross_amount=Decimal('550.00'),
            cost=Decimal('300.00'),
            profit=Decimal('200.00'),
        )
        self.tx_neg = SaleTransaction.objects.create(
            doc_id='NC-200',
            sale_date=date(2026, 3, 15),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('-1.00'),
            net_amount=Decimal('-100.00'),
            gross_amount=Decimal('-110.00'),
            cost=Decimal('-60.00'),
            profit=Decimal('-40.00'),
        )
        self.tx_zero = SaleTransaction.objects.create(
            doc_id='BON-200',
            sale_date=date(2026, 3, 20),
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

    def _create_user_with_route_assignment(self, username: str, is_vendor: bool = False):
        user = User.objects.create_user(username=username, password='password123', email=f'{username}@test.com')
        if is_vendor:
            vendor_group, _ = Group.objects.get_or_create(name='vendedor')
            user.groups.add(vendor_group)
        dept = Department.objects.create(id=f'DEP_{username[:6]}', name='Ventas')
        pos = Position.objects.create(id=f'POS_{username[:6]}', name='Agente', department=dept)
        emp = Employee.objects.create(
            id=f'EMP_{username[:6]}',
            user=user,
            position=pos,
            hire_date=date(2025, 1, 1),
        )
        RouteAssignment.objects.create(
            route=self.route,
            employee=emp,
            date_start=timezone.localdate() - timedelta(days=30),
            date_end=None,
        )
        return user

    @patch('apps.sales.exports.async_task')
    def test_export_view_admin_colors_kpis_and_report_record(self, mock_async_task):
        url = reverse('sales:sale_transaction_export_view')
        response = self.client.get(url, {'date_from': '2026-03-01', 'date_to': '2026-03-31'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment; filename="transacciones_venta_', response['Content-Disposition'])
        self.assertEqual(GeneratedReport.objects.filter(module_name='sale_transactions').count(), 1)
        mock_async_task.assert_called_once()

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        self.assertEqual(wb.sheetnames, ['Resumen General', 'Transacciones'])

        ws_summary = wb['Resumen General']
        kpis = {
            ws_summary.cell(row=r, column=1).value: ws_summary.cell(row=r, column=2)
            for r in range(6, ws_summary.max_row + 1)
        }
        self.assertEqual(kpis['Transacciones'].value, 3)
        self.assertEqual(kpis['Venta Neta Total'].value, 400.0)
        self.assertTrue(kpis['Venta Neta Total'].font.color.rgb.endswith('15803D'))
        self.assertEqual(kpis['Utilidad Total'].value, 110.0)
        self.assertTrue(kpis['Utilidad Total'].font.color.rgb.endswith('15803D'))
        self.assertIn('Margen Total (%)', kpis)

        ws_detail = wb['Transacciones']
        headers = [ws_detail.cell(row=4, column=c).value for c in range(1, ws_detail.max_column + 1)]
        self.assertIn('Importe Neto', headers)
        self.assertIn('Utilidad', headers)
        self.assertIn('Margen (%)', headers)

        net_col = headers.index('Importe Neto') + 1
        profit_col = headers.index('Utilidad') + 1
        rows_by_doc = {
            ws_detail.cell(row=r, column=1).value: r
            for r in range(5, ws_detail.max_row + 1)
        }

        self.assertTrue(ws_detail.cell(row=rows_by_doc['FAC-200'], column=net_col).font.color.rgb.endswith('15803D'))
        self.assertTrue(ws_detail.cell(row=rows_by_doc['FAC-200'], column=profit_col).font.color.rgb.endswith('15803D'))

        self.assertTrue(ws_detail.cell(row=rows_by_doc['NC-200'], column=net_col).font.color.rgb.endswith('B91C1C'))
        self.assertTrue(ws_detail.cell(row=rows_by_doc['NC-200'], column=profit_col).font.color.rgb.endswith('B91C1C'))

        self.assertTrue(ws_detail.cell(row=rows_by_doc['BON-200'], column=net_col).font.color.rgb.endswith('B91C1C'))
        self.assertTrue(ws_detail.cell(row=rows_by_doc['BON-200'], column=profit_col).font.color.rgb.endswith('B91C1C'))

    @patch('apps.sales.exports.async_task')
    def test_export_view_negative_kpi_totals_are_red(self, mock_async_task):
        url = reverse('sales:sale_transaction_export_view')
        response = self.client.get(
            url,
            {'search': 'NC-200', 'date_from': '2026-03-01', 'date_to': '2026-03-31'},
        )
        self.assertEqual(response.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws_summary = wb['Resumen General']
        kpis = {
            ws_summary.cell(row=r, column=1).value: ws_summary.cell(row=r, column=2)
            for r in range(6, ws_summary.max_row + 1)
        }
        self.assertEqual(kpis['Venta Neta Total'].value, -100.0)
        self.assertTrue(kpis['Venta Neta Total'].font.color.rgb.endswith('B91C1C'))
        self.assertEqual(kpis['Utilidad Total'].value, -40.0)
        self.assertTrue(kpis['Utilidad Total'].font.color.rgb.endswith('B91C1C'))

    @patch('apps.sales.exports.async_task')
    def test_export_view_default_current_month(self, mock_async_task):
        today = timezone.localdate()
        SaleTransaction.objects.create(
            doc_id='CURR-200',
            sale_date=today,
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('2.00'),
            net_amount=Decimal('250.00'),
            gross_amount=Decimal('275.00'),
            cost=Decimal('120.00'),
            profit=Decimal('130.00'),
        )
        url = reverse('sales:sale_transaction_export_view')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws_detail = wb['Transacciones']
        docs = [ws_detail.cell(row=r, column=1).value for r in range(5, ws_detail.max_row + 1)]
        self.assertEqual(docs, ['CURR-200'])

    @patch('apps.sales.exports.async_task')
    def test_export_view_hides_profit_and_margin_percentage_from_vendor(self, mock_async_task):
        vendor = self._create_user_with_route_assignment('vendor1', is_vendor=True)
        vendor_client = Client()
        vendor_client.force_login(vendor)

        url = reverse('sales:sale_transaction_export_view')
        response = vendor_client.get(url, {'date_from': '2026-03-01', 'date_to': '2026-03-31'})
        self.assertEqual(response.status_code, 200)

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws_summary = wb['Resumen General']
        kpi_labels = [ws_summary.cell(row=r, column=1).value for r in range(6, ws_summary.max_row + 1)]
        self.assertNotIn('Utilidad Total', kpi_labels)
        self.assertNotIn('Margen Total (%)', kpi_labels)
        self.assertIn('Evaluación', kpi_labels)

        ws_detail = wb['Transacciones']
        headers = [ws_detail.cell(row=4, column=c).value for c in range(1, ws_detail.max_column + 1)]
        self.assertNotIn('Utilidad', headers)
        self.assertNotIn('Margen (%)', headers)
        self.assertIn('Evaluación', headers)

    @patch('apps.sales.exports.async_task')
    def test_export_view_restricted_non_vendor_hides_profit_only(self, mock_async_task):
        regular_user = self._create_user_with_route_assignment('regular1', is_vendor=False)
        regular_client = Client()
        regular_client.force_login(regular_user)

        url = reverse('sales:sale_transaction_export_view')
        response = regular_client.get(url, {'date_from': '2026-03-01', 'date_to': '2026-03-31'})
        self.assertEqual(response.status_code, 200)

        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws_summary = wb['Resumen General']
        kpi_labels = [ws_summary.cell(row=r, column=1).value for r in range(6, ws_summary.max_row + 1)]
        self.assertNotIn('Utilidad Total', kpi_labels)
        self.assertIn('Margen Total (%)', kpi_labels)

        ws_detail = wb['Transacciones']
        headers = [ws_detail.cell(row=4, column=c).value for c in range(1, ws_detail.max_column + 1)]
        self.assertNotIn('Utilidad', headers)
        self.assertIn('Margen (%)', headers)

    def test_transaction_list_view_renders_export_button(self):
        response = self.client.get(reverse('sales:sale_transaction_list_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('sales:sale_transaction_export_view'))
        self.assertContains(response, 'Exportar')


class SaleTransactionRangeFilterTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin_rng',
            password='password123',
            email='admin_rng@test.com',
        )
        self.client = Client()
        self.client.force_login(self.admin_user)

        self.cust_type = CustomerType.objects.create(name='Clinica')
        self.customer = Customer.objects.create(
            id='CUST300',
            name='Clinica Sur',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )
        self.route_type = RouteType.objects.create(id='RT03', name='Ruta Sur')
        self.channel = SaleChannel.objects.create(id='SC03', name='Canal Directo')
        self.route = Route.objects.create(
            id='R303',
            name='Ruta Sur 1',
            route_type=self.route_type,
            sale_channel=self.channel,
        )
        self.category = ProductCategory.objects.create(id='CAT03', name='Vacunas')
        self.product_class = ProductClass.objects.create(id='PC03', name='Biologicos', product_category=self.category)
        self.product = Product.objects.create(id='PRD03', name='Vacuna Triple', product_class=self.product_class)

        self.tx_pos = SaleTransaction.objects.create(
            doc_id='FAC-300',
            sale_date=date(2026, 3, 10),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('5.00'),
            net_amount=Decimal('500.00'),
            gross_amount=Decimal('550.00'),
            cost=Decimal('300.00'),
            profit=Decimal('200.00'),
        )
        self.tx_discount = SaleTransaction.objects.create(
            doc_id='FAC-301',
            sale_date=date(2026, 3, 11),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('2.00'),
            net_amount=Decimal('50.00'),
            gross_amount=Decimal('200.00'),
            cost=Decimal('80.00'),
            profit=Decimal('-30.00'),
        )
        self.tx_gift = SaleTransaction.objects.create(
            doc_id='BON-300',
            sale_date=date(2026, 3, 12),
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
        self.tx_credit_note = SaleTransaction.objects.create(
            doc_id='NC-300',
            sale_date=date(2026, 3, 13),
            customer=self.customer,
            route=self.route,
            product=self.product,
            product_class=self.product_class,
            quantity=Decimal('-1.00'),
            net_amount=Decimal('-100.00'),
            gross_amount=Decimal('-110.00'),
            cost=Decimal('-60.00'),
            profit=Decimal('-40.00'),
        )

    def test_net_amount_range_filter_credit_notes_and_gifts(self):
        qs = SaleTransaction.objects.all()

        credit_notes = SaleTransactionFilter(
            {'net_amount_max_op': 'lt', 'net_amount_max': '0'},
            queryset=qs,
        ).qs
        self.assertEqual(list(credit_notes.values_list('doc_id', flat=True)), ['NC-300'])

        gifts = SaleTransactionFilter(
            {
                'net_amount_min_op': 'gte',
                'net_amount_min': '0',
                'net_amount_max_op': 'lte',
                'net_amount_max': '0',
            },
            queryset=qs,
        ).qs
        self.assertEqual(list(gifts.values_list('doc_id', flat=True)), ['BON-300'])

        strict_positive = SaleTransactionFilter(
            {'net_amount_min_op': 'gt', 'net_amount_min': '50'},
            queryset=qs,
        ).qs
        self.assertEqual(list(strict_positive.values_list('doc_id', flat=True)), ['FAC-300'])

    def test_profit_range_filter_discounts_and_combined_bounds(self):
        qs = SaleTransaction.objects.all()

        loss_sales = SaleTransactionFilter(
            {'profit_max_op': 'lt', 'profit_max': '0'},
            queryset=qs,
        ).qs
        self.assertEqual(
            set(loss_sales.values_list('doc_id', flat=True)),
            {'FAC-301', 'BON-300', 'NC-300'},
        )

        positive_net_with_negative_profit = SaleTransactionFilter(
            {
                'net_amount_min_op': 'gt',
                'net_amount_min': '0',
                'profit_max_op': 'lt',
                'profit_max': '0',
            },
            queryset=qs,
        ).qs
        self.assertEqual(
            list(positive_net_with_negative_profit.values_list('doc_id', flat=True)),
            ['FAC-301'],
        )

    def test_list_view_renders_top_date_and_range_filters_in_order(self):
        response = self.client.get(
            reverse('sales:sale_transaction_list_view'),
            {
                'date_from': '2026-03-01',
                'date_to': '2026-03-31',
                'net_amount_min_op': 'gte',
                'net_amount_min': '0',
                'profit_max_op': 'lt',
                'profit_max': '0',
            },
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        pos_date_from = html.index('name="date_from"')
        pos_date_to = html.index('name="date_to"')
        pos_net_min = html.index('name="net_amount_min"')
        pos_net_max = html.index('name="net_amount_max"')
        pos_profit_min = html.index('name="profit_min"')
        pos_profit_max = html.index('name="profit_max"')
        pos_search = html.index('name="search"')

        self.assertLess(pos_date_from, pos_date_to)
        self.assertLess(pos_date_to, pos_net_min)
        self.assertLess(pos_net_min, pos_net_max)
        self.assertLess(pos_net_max, pos_profit_min)
        self.assertLess(pos_profit_min, pos_profit_max)
        self.assertLess(pos_profit_max, pos_search)

        self.assertEqual(
            set(t.doc_id for t in response.context['transactions']),
            {'FAC-301', 'BON-300'},
        )
        self.assertEqual(response.context['kpis']['total_net_amount'], Decimal('50.00'))
        self.assertEqual(response.context['kpis']['total_profit'], Decimal('-80.00'))
        self.assertIn('net_amount_min=0', response.context['query_string'])
        self.assertIn('profit_max=0', response.context['query_string'])

    def test_vendor_cannot_see_or_apply_profit_range_filter(self):
        vendor = User.objects.create_user(username='vendor_rng', password='password123', email='vrng@test.com')
        vendor_group, _ = Group.objects.get_or_create(name='vendedor')
        vendor.groups.add(vendor_group)
        dept = Department.objects.create(id='DEP_RNG', name='Ventas')
        pos = Position.objects.create(id='POS_RNG', name='Agente', department=dept)
        emp = Employee.objects.create(id='EMP_RNG', user=vendor, position=pos, hire_date=date(2025, 1, 1))
        RouteAssignment.objects.create(
            route=self.route,
            employee=emp,
            date_start=timezone.localdate() - timedelta(days=30),
            date_end=None,
        )

        vendor_client = Client()
        vendor_client.force_login(vendor)

        response = vendor_client.get(
            reverse('sales:sale_transaction_list_view'),
            {
                'date_from': '2026-03-01',
                'date_to': '2026-03-31',
                'profit_min': '100',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="profit_min"')
        self.assertNotContains(response, 'name="profit_max"')
        self.assertContains(response, 'name="net_amount_min"')
        self.assertEqual(
            set(t.doc_id for t in response.context['transactions']),
            {'FAC-300', 'FAC-301', 'BON-300', 'NC-300'},
        )

        net_filtered = vendor_client.get(
            reverse('sales:sale_transaction_list_view'),
            {
                'date_from': '2026-03-01',
                'date_to': '2026-03-31',
                'net_amount_max_op': 'lt',
                'net_amount_max': '0',
            },
        )
        self.assertEqual(
            list(t.doc_id for t in net_filtered.context['transactions']),
            ['NC-300'],
        )

    @patch('apps.sales.exports.async_task')
    def test_export_view_respects_net_amount_and_profit_range_filters(self, mock_async_task):
        response = self.client.get(
            reverse('sales:sale_transaction_export_view'),
            {
                'date_from': '2026-03-01',
                'date_to': '2026-03-31',
                'net_amount_max_op': 'lt',
                'net_amount_max': '0',
            },
        )
        self.assertEqual(response.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        ws_detail = wb['Transacciones']
        docs = [ws_detail.cell(row=r, column=1).value for r in range(5, ws_detail.max_row + 1)]
        self.assertEqual(docs, ['NC-300'])
