from django.db import models
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db.models import Q

class CustomerType(models.Model):
    id = models.CharField(max_length=100, primary_key=True, help_text='Identificador unico del tipo de cliente')
    name = models.CharField(max_length=255, help_text='Tipo de cliente')
    description = models.TextField(blank=True, null=True, help_text='Descripción del tipo de cliente')

    class Meta:
        verbose_name = 'Tipo de cliente'
        verbose_name_plural = 'Tipos de cliente'

class Customer(models.Model):
    id = models.CharField(max_length=100, primary_key=True, help_text='Identificador unico del cliente')
    name = models.CharField(max_length=255, help_text='Nombre del cliente (nombre comercial o encargado de la cuenta)')
    registration_date = models.DateField(help_text='Fecha de registro del cliente')
    credit_limit = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Linea de credito del cliente')
    credit_days = models.IntegerField(default=0, help_text='Dias de credito del cliente')
    customer_type = models.ForeignKey('CustomerType', on_delete=models.PROTECT, related_name='%(app_label)s_customers', help_text='Tipo de cliente')
    opinion_leader = models.BooleanField(default=False, help_text='Indica si el cliente es un lider de opinion')

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        indexes = [models.Index(fields=["registration_date"])]

class CustomerAssignment(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='%(app_label)s_assignments', help_text='Cliente a asignar')
    route = models.ForeignKey('sales.Route', on_delete=models.PROTECT, related_name='%(app_label)s_assignments', help_text='Ruta a la que se asigna el cliente')
    start_date = models.DateField(help_text='Fecha de inicio de la asignación')
    end_date = models.DateField(null=True, blank=True, help_text='Fecha de fin de la asignación')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la asignación')
    
    class Meta:
        verbose_name = 'Asignación de cliente'
        verbose_name_plural = 'Asignaciones de clientes'
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "route", "start_date"],
                name="unique_customer_assignment"
            ),
            models.UniqueConstraint(
                fields=["customer"],
                condition=Q(end_date__isnull=True),
                name="unique_active_assignment_per_customer"
            ),
        ]

class CustomerClassMargin(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='%(app_label)s_class_margins')
    product_class = models.ForeignKey('inventory.ProductClass', on_delete=models.CASCADE, related_name='%(app_label)s_customer_margins')
    min_margin_percentage = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Margen por clase de producto'
        verbose_name_plural = 'Márgenes por clase de producto'
        unique_together = ('customer', 'product_class')


