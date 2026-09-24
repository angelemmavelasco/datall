from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from apps.core.models import User, PeriodicityChoices, Reference
from django.contrib.auth.models import Group
from apps.customers.models import (
    Customer,
    CustomerType,
    CustomerAssignment,
    CommercialBenefit,
    CommercialBenefitTypeChoices,
    CustomerAgreement,
    AgreementTypeChoices,
    AgreementClassTarget,
    AgreementEvaluationPeriod,
    PeriodStatusChoices,
    CustomerClassMargin,
)
from apps.customers.services.customer_agreements import (
    CustomerAgreementsService,
    CustomerAgreementsStats,
    CustomerAgreementNotFound,
    PermissionsError,
    parse_month_input,
)
from apps.customers.forms import CustomerAgreementCreateForm
from apps.customers.filters import CustomerAgreementFilter
from apps.products.models import ProductClass, ProductCategory
from apps.sales.models import Route, RouteType, SaleChannel, Warehouse


class CustomerAgreementModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', is_superuser=True)
        self.cust_type = CustomerType.objects.create(name='Veterinaria')
        self.customer = Customer.objects.create(
            id='CUST01',
            name='Clinica Veterinaria San Jose',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )
        self.route_type = RouteType.objects.create(id='rt01', name='Tipo 1')
        self.sale_channel = SaleChannel.objects.create(id='sc01', name='Canal 1')
        self.route = Route.objects.create(id='R01', name='Ruta Norte', route_type=self.route_type, sale_channel=self.sale_channel)
        CustomerAssignment.objects.create(customer=self.customer, route=self.route, start_date=date(2026, 1, 1))

        self.benefit = CommercialBenefit.objects.create(
            benefit_type=CommercialBenefitTypeChoices.PHYSICAL_ITEM,
            name='Nevera 400L',
            cost=Decimal('15000.00'),
            is_active=True,
        )

    def test_agreement_doc_id_autogeneration(self):
        agreement = CustomerAgreement.objects.create(
            customer=self.customer,
            route=self.route,
            benefit=self.benefit,
            agreement_type=AgreementTypeChoices.SHORT_TERM,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            global_target_amount=Decimal('50000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
            created_by=self.user,
        )
        self.assertTrue(bool(agreement.doc_id))
        self.assertEqual(len(agreement.doc_id), 5)

    def test_agreement_immutability(self):
        agreement = CustomerAgreement.objects.create(
            customer=self.customer,
            route=self.route,
            benefit=self.benefit,
            agreement_type=AgreementTypeChoices.SHORT_TERM,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            global_target_amount=Decimal('50000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
            created_by=self.user,
        )
        #modify immutable fields raises ValidationError
        agreement.global_target_amount = Decimal('80000.00')
        with self.assertRaises(ValidationError):
            agreement.save()


class CustomerAgreementServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_service', is_superuser=True)
        self.cust_type = CustomerType.objects.create(name='Farmacia')
        self.customer = Customer.objects.create(
            id='CUST02',
            name='Farmacia El Trebol',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )
        self.route_type = RouteType.objects.create(id='rt02', name='Tipo 2')
        self.sale_channel = SaleChannel.objects.create(id='sc02', name='Canal 2')
        self.route = Route.objects.create(id='R02', name='Ruta Sur', route_type=self.route_type, sale_channel=self.sale_channel)
        CustomerAssignment.objects.create(customer=self.customer, route=self.route, start_date=date(2026, 1, 1))

        self.benefit = CommercialBenefit.objects.create(
            benefit_type=CommercialBenefitTypeChoices.PHYSICAL_ITEM,
            name='Báscula Digital',
            cost=Decimal('6000.00'),
            is_active=True,
        )
        self.cat = ProductCategory.objects.create(name='Alimentos')
        self.pc_diamond = ProductClass.objects.create(id='dmd', name='Diamond', product_category=self.cat)
        self.pc_naturals = ProductClass.objects.create(id='nat', name='Naturals', product_category=self.cat)

        self.service = CustomerAgreementsService(user=self.user)

    def test_create_customer_agreement_with_periods(self):
        participating = [
            {'product_class_id': 'dmd', 'is_mandatory': True, 'required_target': Decimal('20000.00')},
            {'product_class_id': 'nat', 'is_mandatory': False, 'required_target': Decimal('0.00')},
        ]
        agreement = self.service.create_customer_agreement(
            customer_id='CUST02',
            benefit_id=self.benefit.id,
            agreement_type=AgreementTypeChoices.SHORT_TERM,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            global_target_amount=Decimal('50000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
            growth_value=Decimal('10.00'),
            growth_frequency=PeriodicityChoices.MONTHLY,
            penalty_amount=Decimal('2000.00'),
            participating_classes_data=participating,
            margin_warning_accepted=True,
        )

        self.assertIsNotNone(agreement.pk)
        self.assertEqual(agreement.evaluation_periods.count(), 3)
        self.assertEqual(agreement.class_targets.count(), 2)

        # compound growth across periods:
        p1, p2, p3 = agreement.evaluation_periods.order_by('period_number')
        self.assertEqual(p1.expected_global_target, Decimal('50000.00'))
        self.assertEqual(p2.expected_global_target, Decimal('55000.00'))
        self.assertEqual(p3.expected_global_target, Decimal('60500.00'))

    def test_generate_agreement_preview(self):
        participating = [
            {'product_class_id': 'dmd', 'is_mandatory': True, 'required_target': Decimal('20000.00')},
            {'product_class_id': 'nat', 'is_mandatory': False, 'required_target': Decimal('0.00')},
        ]
        preview = self.service.generate_agreement_preview(
            customer_id='CUST02',
            benefit_id=self.benefit.id,
            agreement_type=AgreementTypeChoices.SHORT_TERM,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            global_target_amount=Decimal('60000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
            growth_value=Decimal('5.00'),
            growth_frequency=PeriodicityChoices.BIMONTHLY,
            penalty_amount=Decimal('3000.00'),
            participating_classes_data=participating,
        )

        self.assertEqual(preview['total_periods'], 6)
        self.assertEqual(len(preview['clauses']), 7)
        self.assertEqual(len(preview['projection_matrix']['periods']), 6)
        self.assertEqual(len(preview['projection_matrix']['mandatory_rows']), 1)
        self.assertIsNotNone(preview['projection_matrix']['complementary_row'])

    def test_stats_service(self):
        stats_service = CustomerAgreementsStats(service=self.service)
        kpis = stats_service.stats()
        self.assertIn('total_agreements', kpis)
        self.assertIn('active_agreements', kpis)
        self.assertIn('overall_compliance_pct', kpis)


class CustomerAgreementViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='admin_views', is_superuser=True)
        self.client.force_login(self.user)

        self.cust_type = CustomerType.objects.create(name='Distribuidor')
        self.customer = Customer.objects.create(
            id='CUST03',
            name='Distribuidora Del Bajio',
            customer_type=self.cust_type,
            registration_date=date(2026, 1, 1),
        )
        self.route_type = RouteType.objects.create(id='rt03', name='Tipo 3')
        self.sale_channel = SaleChannel.objects.create(id='sc03', name='Canal 3')
        self.route = Route.objects.create(id='R03', name='Ruta Bajio', route_type=self.route_type, sale_channel=self.sale_channel)
        CustomerAssignment.objects.create(customer=self.customer, route=self.route, start_date=date(2026, 1, 1))

        self.benefit = CommercialBenefit.objects.create(
            benefit_type=CommercialBenefitTypeChoices.PHYSICAL_ITEM,
            name='Exhibidor Metalico',
            cost=Decimal('4500.00'),
            is_active=True,
        )

        self.service = CustomerAgreementsService(user=self.user)
        self.agreement = self.service.create_customer_agreement(
            customer_id='CUST03',
            benefit_id=self.benefit.id,
            agreement_type=AgreementTypeChoices.SHORT_TERM,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            global_target_amount=Decimal('40000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
            margin_warning_accepted=True,
        )

    def test_agreement_list_view_get(self):
        url = reverse('customers:customer_agreement_list_view')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.agreement.doc_id)

    def test_agreement_detail_view_get(self):
        url = reverse('customers:customer_agreement_detail_view', kwargs={'pk': self.agreement.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.agreement.doc_id)
        self.assertContains(response, 'Distribuidora Del Bajio')

    def test_agreement_create_view_get(self):
        url = reverse('customers:customer_agreement_create_view')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Información general')

    def test_vendedor_masking_in_detail_view(self):
        from apps.sales.models import UserRouteAccess
        vendedor_group, _ = Group.objects.get_or_create(name='vendedor')
        vendedor_user = User.objects.create_user(username='vendedor_test')
        vendedor_user.groups.add(vendedor_group)
        UserRouteAccess.objects.create(user=vendedor_user, route=self.route, can_view=True)
        self.client.force_login(vendedor_user)

        url = reverse('customers:customer_agreement_detail_view', kwargs={'pk': self.agreement.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Utilidad')
        self.assertNotContains(response, 'Margen')
        self.assertNotContains(response, 'Amort. beneficio')
        self.assertContains(response, 'Rentabilidad')


    def test_update_agreement_document_service(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile("contrato_firmado.pdf", b"%PDF-1.4 dummy content", content_type="application/pdf")
        updated = self.service.update_agreement_document(pk=self.agreement.pk, file_obj=fake_file)
        self.assertTrue(bool(updated.related_doc))
        self.assertTrue(updated.related_doc.name.endswith('.pdf'))

    def test_validate_margin_view(self):
        url = reverse('customers:customer_agreement_validate_margin_view')
        #missing data returns warning partial
        r_empty = self.client.post(url, {})
        self.assertEqual(r_empty.status_code, 200)
        self.assertContains(r_empty, 'Atención en simulación financiera')

        #complete data returns simulation result
        post_data = {
            'customer': self.customer.id,
            'benefit': self.benefit.id,
            'start_date': '2026-01-01',
            'end_date': '2026-06-30',
            'global_target_amount': '50000.00',
            'target_frequency': '1M',
        }
        r_full = self.client.post(url, post_data)
        content_lower = r_full.content.decode().lower()
        self.assertTrue('margen viable' in content_lower or 'margen financiero' in content_lower)

    def test_customer_search_view(self):
        url = reverse('customers:customer_agreement_search_customers_view')
        response = self.client.get(url, {'q': 'Bajio'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Distribuidora Del Bajio')

    def test_customer_options_view(self):
        url = reverse('customers:customer_options_view')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Distribuidora Del Bajio')
        response_q = self.client.get(url, {'q_customer': 'Bajio'})
        self.assertEqual(response_q.status_code, 200)
        self.assertContains(response_q, 'Distribuidora Del Bajio')
        response_none = self.client.get(url, {'q_customer': 'NonExistentXYZ'})
        self.assertEqual(response_none.status_code, 200)
        self.assertContains(response_none, 'No se encontraron clientes')

    def test_parse_month_input(self):
        #YYYY-MM format
        self.assertEqual(parse_month_input('2026-03', is_end=False), date(2026, 3, 1))
        self.assertEqual(parse_month_input('2026-03', is_end=True), date(2026, 3, 31))
        #leap year handling
        self.assertEqual(parse_month_input('2024-02', is_end=True), date(2024, 2, 29))
        self.assertEqual(parse_month_input('2025-02', is_end=True), date(2025, 2, 28))
        #snapping full date strings to month boundaries
        self.assertEqual(parse_month_input('2026-07-15', is_end=False), date(2026, 7, 1))
        self.assertEqual(parse_month_input('2026-07-15', is_end=True), date(2026, 7, 31))
        #invalid strings
        self.assertIsNone(parse_month_input('invalid-format'))
        self.assertIsNone(parse_month_input(''))

    def test_customer_agreement_create_form_months(self):
        form_data = {
            'customer': self.customer.id,
            'benefit': self.benefit.id,
            'agreement_type': AgreementTypeChoices.SHORT_TERM,
            'start_date': '2026-02',
            'end_date': '2026-08',
            'global_target_amount': '150000.00',
            'target_frequency': PeriodicityChoices.MONTHLY,
            'doc_id': 'TEST-FORM-01',
        }
        form = CustomerAgreementCreateForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['start_date'], date(2026, 2, 1))
        self.assertEqual(form.cleaned_data['end_date'], date(2026, 8, 31))

        #test inverted dates
        bad_data = form_data.copy()
        bad_data['start_date'] = '2026-08'
        bad_data['end_date'] = '2026-02'
        bad_form = CustomerAgreementCreateForm(data=bad_data)
        self.assertFalse(bad_form.is_valid())
        self.assertIn('end_date', bad_form.errors)

    def test_customer_agreement_filter_months(self):
        f_match = CustomerAgreementFilter(data={'start_date_gte': '2026-01', 'end_date_lte': '2026-06'}, queryset=CustomerAgreement.objects.all())
        self.assertIn(self.agreement, f_match.qs)
        f_no_match = CustomerAgreementFilter(data={'start_date_gte': '2026-03'}, queryset=CustomerAgreement.objects.all())
        self.assertNotIn(self.agreement, f_no_match.qs)

    def test_validate_margin_breakdown_mandatory_and_complementary(self):
        #setup classes and minimum margins
        cat = ProductCategory.objects.create(id='CAT_TEST', name='Test Category')
        class_mand = ProductClass.objects.create(id='CLASS_MAND', name='Alimento Premium', product_category=cat)
        class_comp1 = ProductClass.objects.create(id='CLASS_COMP1', name='Shampoo Canino', product_category=cat)
        class_comp2 = ProductClass.objects.create(id='CLASS_COMP2', name='Vacuna Triple', product_category=cat)

        CustomerClassMargin.objects.create(customer=self.customer, product_class=class_mand, min_margin_percentage=Decimal('35.00'))
        CustomerClassMargin.objects.create(customer=self.customer, product_class=class_comp1, min_margin_percentage=Decimal('20.00'))
        CustomerClassMargin.objects.create(customer=self.customer, product_class=class_comp2, min_margin_percentage=Decimal('42.00'))  # Most restrictive!

        # 2. Call validate_agreement_margin service directly
        participating_data = [
            {'product_class_id': 'CLASS_MAND', 'is_mandatory': True, 'required_target': Decimal('20000.00')},
            {'product_class_id': 'CLASS_COMP1', 'is_mandatory': False, 'required_target': Decimal('0.00')},
            {'product_class_id': 'CLASS_COMP2', 'is_mandatory': False, 'required_target': Decimal('0.00')},
        ]

        val_result = self.service.validate_agreement_margin(
            customer_id=self.customer.id,
            benefit_id=self.benefit.id,
            eval_start='2026-01',
            eval_end='2026-03',
            agreement_start_date='2026-04',
            agreement_end_date='2026-09',
            target_frequency='1M',
            global_target_amount=Decimal('50000.00'),
            participating_classes_data=participating_data,
        )

        is_valid, sim_margin, max_min_margin, vol_alert, res_dict = val_result
        self.assertTrue(res_dict['has_mandatory'])
        self.assertEqual(len(res_dict['mandatory_breakdown']), 1)
        self.assertEqual(res_dict['mandatory_breakdown'][0]['product_class_id'], 'CLASS_MAND')
        self.assertEqual(res_dict['mandatory_breakdown'][0]['min_margin'], Decimal('35.00'))

        self.assertTrue(res_dict['has_complementary'])
        self.assertEqual(res_dict['complementary_pool']['count'], 2)
        # Verify the most restrictive class is CLASS_COMP2 with 42%
        self.assertEqual(res_dict['most_restrictive_min_margin'], Decimal('42.00'))
        self.assertEqual(res_dict['most_restrictive_class_name'], 'Vacuna Triple')

        # 3. Test HTTP view response rendering the detailed table and explanation
        url = reverse('customers:customer_agreement_validate_margin_view')
        post_data = {
            'customer': self.customer.id,
            'benefit': self.benefit.id,
            'start_date': '2026-04',
            'end_date': '2026-09',
            'eval_start': '2026-01',
            'eval_end': '2026-03',
            'global_target_amount': '50000.00',
            'target_frequency': '1M',
            'participating_classes': ['CLASS_MAND', 'CLASS_COMP1', 'CLASS_COMP2'],
            'mandatory_classes': ['CLASS_MAND'],
            'mandatory_target_CLASS_MAND': '20000.00',
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Clases obligatorias (evaluación individual', content)
        self.assertIn('Alimento Premium', content)
        self.assertIn('Bolsa complementaria consolidada', content)
        self.assertIn('Vacuna Triple', content)
        self.assertIn('Más restrictiva', content)
        self.assertIn('Criterio de evaluación para clases complementarias', content)
        self.assertIn('42.00%', content)

    def test_agreement_preview_doc_id_autogeneration(self):
        preview = self.service.generate_agreement_preview(
            customer_id=self.customer.id,
            benefit_id=self.benefit.id,
            start_date='2026-01',
            end_date='2026-06',
            global_target_amount=Decimal('60000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
        )
        self.assertIsNotNone(preview['doc_id'])
        self.assertNotEqual(preview['doc_id'], 'PENDIENTE')
        self.assertEqual(len(preview['doc_id']), 5)
        self.assertTrue(preview['doc_id'].isalnum())
        self.assertEqual(preview['doc_id'], preview['doc_id'].upper())

    def test_customer_agreement_preview_view_generates_and_preserves_doc_id(self):
        url = reverse('customers:customer_agreement_preview_view')
        post_data = {
            'customer': self.customer.id,
            'benefit': self.benefit.id,
            'agreement_type': AgreementTypeChoices.SHORT_TERM,
            'start_date': '2026-01',
            'end_date': '2026-06',
            'global_target_amount': '60000.00',
            'target_frequency': '1M',
        }
        # 1. No doc_id provided: generates 5-char random folio
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('PENDIENTE', content)
        self.assertIn('id_doc_id', content)
        self.assertIn('Vista previa de contrato comercial', content)

        # 2. Provided custom doc_id: preserved
        post_data['doc_id'] = 'CUST5'
        response2 = self.client.post(url, post_data)
        self.assertEqual(response2.status_code, 200)
        self.assertContains(response2, 'CUST5')

    def test_agreement_preview_displays_assigned_collaborator_name(self):
        from apps.human_resources.models import Department, Position, Employee
        from apps.sales.models import RouteAssignment

        dept = Department.objects.create(id='VEN', name='Ventas')
        pos = Position.objects.create(id='ASESOR_V', name='Asesor de Ventas', department=dept)
        emp_user = User.objects.create_user(
            username='carlos_asesor',
            first_name='Carlos Alberto',
            last_name='Sánchez Mora',
        )
        emp = Employee.objects.create(
            id='EMP001',
            user=emp_user,
            position=pos,
            hire_date=date(2025, 1, 1),
        )
        RouteAssignment.objects.create(
            route=self.route,
            employee=emp,
            date_start=date(2025, 1, 1),
            date_end=None,
        )

        preview = self.service.generate_agreement_preview(
            customer_id=self.customer.id,
            benefit_id=self.benefit.id,
            start_date='2026-01',
            end_date='2026-06',
            global_target_amount=Decimal('40000.00'),
            target_frequency=PeriodicityChoices.MONTHLY,
        )
        self.assertEqual(preview['advisor_name'], 'Carlos Alberto Sánchez Mora')

        url = reverse('customers:customer_agreement_preview_view')
        post_data = {
            'customer': self.customer.id,
            'benefit': self.benefit.id,
            'agreement_type': AgreementTypeChoices.SHORT_TERM,
            'start_date': '2026-01',
            'end_date': '2026-06',
            'global_target_amount': '40000.00',
            'target_frequency': '1M',
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Carlos Alberto Sánchez Mora')
        self.assertContains(response, f'Ruta: {self.route.id}')

    def test_agreement_signed_and_benefit_fields_defaults(self):
        self.assertFalse(self.agreement.signed)
        self.assertFalse(self.agreement.benefit_already_provided)

    def test_agreement_clean_allows_updating_execution_fields(self):
        # Modifying execution fields (signed, benefit_already_provided, related_doc) is allowed by clean()
        self.agreement.signed = True
        self.agreement.benefit_already_provided = True
        try:
            self.agreement.clean()
        except ValidationError:
            self.fail("clean() should not raise ValidationError when updating signed or benefit_already_provided.")

        # Modifying immutable fields like doc_id raises ValidationError
        self.agreement.doc_id = 'DIFF1'
        with self.assertRaises(ValidationError):
            self.agreement.clean()

    def test_can_edit_agreement_reference_and_full_access(self):
        # 1. Superuser has full access -> True
        self.assertTrue(self.service.can_edit_agreement)

        # 2. Regular user without reference group -> False
        regular_user = User.objects.create_user(username='regular_test')
        regular_service = CustomerAgreementsService(user=regular_user)
        self.assertFalse(regular_service.can_edit_agreement)

        # 3. User in group configured via Reference(key='can_edit_customer_agreement') -> True
        cedis_group, _ = Group.objects.get_or_create(name='gerente_cedis')
        cedis_user = User.objects.create_user(username='cedis_manager')
        cedis_user.groups.add(cedis_group)

        Reference.objects.get_or_create(
            key='can_edit_customer_agreement',
            value='gerente_cedis',
        )

        cedis_service = CustomerAgreementsService(user=cedis_user)
        self.assertTrue(cedis_service.can_edit_agreement)

    def test_update_agreement_execution_service_permissions(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake_file = SimpleUploadedFile("contrato_firmado.pdf", b"%PDF-1.4 dummy", content_type="application/pdf")

        # Unauthorized user raises PermissionsError
        regular_user = User.objects.create_user(username='unauth_test')
        regular_service = CustomerAgreementsService(user=regular_user)
        with self.assertRaises(PermissionsError):
            regular_service.update_agreement_execution(
                pk=self.agreement.pk,
                signed=True,
                benefit_already_provided=True,
                file_obj=fake_file,
            )

        # Authorized user succeeds
        updated = self.service.update_agreement_execution(
            pk=self.agreement.pk,
            signed=True,
            benefit_already_provided=True,
            file_obj=fake_file,
        )
        self.assertTrue(updated.signed)
        self.assertTrue(updated.benefit_already_provided)
        self.assertTrue(bool(updated.related_doc))

    def test_agreement_detail_view_permissions_and_template(self):
        from apps.sales.models import UserRouteAccess
        # Create a seller user without can_edit_agreement
        seller_group, _ = Group.objects.get_or_create(name='vendedor')
        seller_user = User.objects.create_user(username='seller_view_test')
        seller_user.groups.add(seller_group)
        UserRouteAccess.objects.create(user=seller_user, route=self.route, can_view=True)

        self.client.force_login(seller_user)
        url = reverse('customers:customer_agreement_detail_view', kwargs={'pk': self.agreement.pk})
        resp_seller = self.client.get(url)
        self.assertEqual(resp_seller.status_code, 200)
        self.assertFalse(resp_seller.context['can_edit'])
        # The management form should not be present for seller
        self.assertNotContains(resp_seller, 'Gestión operativa del convenio')
        self.assertContains(resp_seller, 'Pendiente de firma')
        self.assertContains(resp_seller, 'Pendiente de entrega')

        # Create a manager user in gerente_cedis group
        cedis_group, _ = Group.objects.get_or_create(name='gerente_cedis')
        Reference.objects.get_or_create(
            key='can_edit_customer_agreement',
            value='gerente_cedis',
        )
        manager_user = User.objects.create_user(username='manager_view_test')
        manager_user.groups.add(cedis_group)
        UserRouteAccess.objects.create(user=manager_user, route=self.route, can_view=True)

        self.client.force_login(manager_user)
        resp_manager = self.client.get(url)
        self.assertEqual(resp_manager.status_code, 200)
        self.assertTrue(resp_manager.context['can_edit'])
        # The management form should be visible
        self.assertContains(resp_manager, 'Gestión operativa del convenio')
        self.assertContains(resp_manager, 'name="signed"')
        self.assertContains(resp_manager, 'name="benefit_already_provided"')

    def test_agreement_update_document_view_post_permissions(self):
        from apps.sales.models import UserRouteAccess
        from django.core.files.uploadedfile import SimpleUploadedFile

        post_url = reverse('customers:customer_agreement_update_document_view', kwargs={'pk': self.agreement.pk})

        # 1. Unauthorized user attempt
        seller_user = User.objects.create_user(username='unauth_post_user')
        UserRouteAccess.objects.create(user=seller_user, route=self.route, can_view=True)
        self.client.force_login(seller_user)

        r_unauth = self.client.post(post_url, {'signed': 'on', 'benefit_already_provided': 'on'})
        self.assertEqual(r_unauth.status_code, 302)
        self.agreement.refresh_from_db()
        self.assertFalse(self.agreement.signed)
        self.assertFalse(self.agreement.benefit_already_provided)

        # 2. Authorized user attempt (gerente_cedis via Reference)
        cedis_group, _ = Group.objects.get_or_create(name='gerente_cedis')
        Reference.objects.get_or_create(
            key='can_edit_customer_agreement',
            value='gerente_cedis',
        )
        manager_user = User.objects.create_user(username='auth_post_user')
        manager_user.groups.add(cedis_group)
        UserRouteAccess.objects.create(user=manager_user, route=self.route, can_view=True)
        self.client.force_login(manager_user)

        fake_pdf = SimpleUploadedFile("convenio_firmado.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r_auth = self.client.post(post_url, {
            'signed': 'on',
            'benefit_already_provided': 'on',
            'related_doc': fake_pdf,
        })
        self.assertEqual(r_auth.status_code, 302)
        self.agreement.refresh_from_db()
        self.assertTrue(self.agreement.signed)
        self.assertTrue(self.agreement.benefit_already_provided)
        self.assertTrue(bool(self.agreement.related_doc))









