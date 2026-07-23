from django.db import models

# Create your models here.
class ProductCategory(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(max_length=500, default='', blank=True)

    class Meta:
        verbose_name = 'Categoría de producto'
        verbose_name_plural = 'Categorías de producto'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class ProductClass(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(max_length=255, null=True, blank=True)
    product_category = models.ForeignKey('ProductCategory', on_delete=models.PROTECT, related_name='product_classes', null=True, blank=True)

    class Meta:
        verbose_name = 'Clase de producto'
        verbose_name_plural = 'Clases de producto'

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().lower()

        super().save(*args, **kwargs)

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    barcode = models.CharField(blank=True, null=True, max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)
    product_class = models.ForeignKey('ProductClass', on_delete=models.PROTECT, related_name='products', null=True, blank=True)
    cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    unit_of_measure = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

