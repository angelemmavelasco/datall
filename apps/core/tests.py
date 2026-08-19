from django.test import TestCase
from apps.core.models import (
    Product,
    Customer,
    SaleTransaction,
    Stock,
    Route,
    Warehouse,
)
from apps.core.services.core_test_data_seeder_service import CoreTestDataSeederService


class CoreTestDataSeederServiceTest(TestCase):
    def test_seed_and_clear_test_data(self):
        seeder = CoreTestDataSeederService()
        
        # Test seeding
        result = seeder.seed_all()
        self.assertGreater(result["products"], 0)
        self.assertGreater(result["customers"], 0)
        self.assertGreater(result["sale_transactions"], 0)
        
        # Verify prefix on all seeded objects
        for product in Product.objects.filter(id__startswith="TEST"):
            self.assertTrue(product.name.startswith("TEST"))
            self.assertTrue(product.product_class_id.startswith("TEST"))
            
        for customer in Customer.objects.filter(id__startswith="TEST"):
            self.assertTrue(customer.name.startswith("TEST"))
            self.assertTrue(customer.customer_type_id.startswith("TEST"))
            
        for sale in SaleTransaction.objects.filter(doc_id__startswith="TEST"):
            self.assertTrue(sale.product_id.startswith("TEST"))
            self.assertTrue(sale.customer_id.startswith("TEST"))
            self.assertEqual(sale.profit, sale.net_amount - sale.cost)
            
        # Test clear
        clear_result = seeder.clear_test_data()
        self.assertEqual(Product.objects.filter(id__startswith="TEST").count(), 0)
        self.assertEqual(Customer.objects.filter(id__startswith="TEST").count(), 0)
        self.assertEqual(SaleTransaction.objects.filter(doc_id__startswith="TEST").count(), 0)
