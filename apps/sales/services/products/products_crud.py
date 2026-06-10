from apps.core.models import Product

class ProductsCrud:
    """
    Servicio encargado de la lógica CRUD y consultas complejas para el modelo Product.
    """

    def read(self, **filters):
        """
        Retorna un QuerySet de productos aplicando los filtros proporcionados.
        Mantiene el mismo patrón de diseño que CustomersCrud.
        """
        qs = Product.objects.select_related('product_class').all()

        product_classes = filters.get('product_classes')
        if product_classes:
            qs = qs.filter(product_class_id__in=product_classes)

        query_text = filters.get('query_text')
        if query_text:
            qs = qs.filter(id__icontains=query_text) | qs.filter(name__icontains=query_text) | qs.filter(barcode__icontains=query_text)
        qs = qs.order_by('id')
        
        return qs

    def get_by_id(self, product_id):
        try:
            return Product.objects.select_related('product_class').get(id=product_id)
        except Product.DoesNotExist:
            return None
