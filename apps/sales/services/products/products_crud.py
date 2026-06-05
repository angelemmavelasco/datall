from django.db.models import Q
from apps.core.models import Product
import pandas as pd
from django.db import transaction

class ProductsCRUD:

    def __init__(self):
        self.model = Product

    def get_products(
            self, *,
            product_classes: list[str] = None,
            search_query: str = None,
            **kwargs
    ):
        """
        Retrieves products based on flexible filtering criteria.

        :param product_classes: List of ProductClass IDs (str)
        :param search_query: Global string to search across id, barcode, and name
        :param kwargs: Fallback for any other exact match filters
        :return: QuerySet of Products
        """
        queryset = self.model.objects.select_related('product_class__product_category').all()

        if product_classes:
            queryset = queryset.filter(product_class_id__in=product_classes)

        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(id__icontains=search_query) |
                Q(barcode__icontains=search_query) |
                Q(name__icontains=search_query)
            )

        if kwargs:
            queryset = queryset.filter(**kwargs)

        return queryset.distinct()

    def get_product(self, *, product_id: str = None):
        """
        Retrieves a single product instance by its primary key (ID).

        :param product_id: The string primary key of the product.
        :return: The Product instance if found, or None.
        """
        if not product_id:
             return None

        return self.model.objects.select_related('product_class__product_category').filter(id=product_id).first()

    def process_product_update(self, product_id: str, raw_data: dict):
        """
        Process the raw data from a dict and update the product's attributes.

        :param product_id: String ID of the product
        :param raw_data: Dictionary from request.POST
        :return: Product instance or False
        """
        if not product_id or not raw_data:
            return False

        raw_data.pop('csrfmiddlewaretoken', None)

        name = raw_data.get('name')
        if not name or str(name).strip() == "":
            return False

        cleaned_data = {}
        fields_to_null = ['product_class_id', 'cost', 'price']

        for key, value in raw_data.items():
            if value == "":
                if key in fields_to_null:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = ""
            else:
                cleaned_data[key] = value

        return self.update_product(product_id=product_id, **cleaned_data)

    def update_product(
            self, *,
            product_id: str = None,
            **kwargs
    ):
        """
        Updates an existing product's attributes dynamically.

        :param product_id: The string primary key of the product.
        :param kwargs: Keyword arguments representing the fields and their new values.
        :return: The updated Product instance, or None.
        """
        if not product_id or not kwargs:
            return None

        product = self.model.objects.filter(id=product_id).first()
        if not product:
            return None

        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)

        product.save()

        return product

    def delete_product(self, *, product_id: str = None):
        """
        Permanently deletes a product from the database (Hard Delete).
        Note: If you add an 'is_active' boolean to the model later,
        change this to a Soft Delete.

        :param product_id: The string primary key of the product.
        :return: The deleted Product instance, or None if not found.
        """
        if not product_id:
            return None

        product = self.model.objects.filter(id=product_id).first()
        if not product:
            return None

        product.delete()

        return product

    def product_create(self, raw_data: dict):
        """
        Process the raw data from a dict and create a new product.

        :param raw_data: The dictionary containing product data.
        :return: Product instance or False
        """
        if not raw_data:
            return False

        raw_data.pop('csrfmiddlewaretoken', None)

        product_id = raw_data.get('id')
        name = raw_data.get('name')

        # Regla estricta: Al no tener AutoField, el ID debe venir en el form
        if not product_id or str(product_id).strip() == "" or not name or str(name).strip() == "":
            return False

        # Evitar crash de IntegrityError si el ID (SKU) ya existe
        if self.model.objects.filter(id=product_id).exists():
            return False

        cleaned_data = {}
        fields_to_null = ['product_class_id', 'cost', 'price']

        for key, value in raw_data.items():
            if value == "":
                if key in fields_to_null:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = ""
            else:
                cleaned_data[key] = value

        new_product = self.model(**cleaned_data)
        new_product.save()

        return new_product

    def products_create(self, *, file, column_mappers: dict):
        """
        Process the raw data from a file and create multiple new products.

        :param file: The InMemoryUploadedFile object.
        :param column_mappers: Dictionary mapping raw column names to model field names.
        :return: Boolean indicating success.
        """
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)

            df.columns = df.columns.str.strip()

            keys_in_df = [key for key in column_mappers.keys() if key in df.columns]
            if not keys_in_df:
                return False

            df = df[keys_in_df]
            df.rename(columns=column_mappers, inplace=True)

            df = df.replace({pd.NA: None})
            df = df.where(pd.notnull(df), None)

            products_to_create = []
            products_to_update = []

            existing_ids = set(self.model.objects.values_list('id', flat=True))

            for index, row in df.iterrows():
                row_data = row.to_dict()

                product_id = str(row_data.get('id', '')).strip()
                if not product_id or product_id == 'None':
                    continue

                product_instance = self.model(
                    id=product_id,
                    barcode=row_data.get('barcode', None),
                    name=row_data.get('name', None),
                    cost=row_data.get('cost', None),
                    price=row_data.get('price', None),
                    unit_of_measure=row_data.get('unit_of_measure', None)
                )

                if product_id in existing_ids:
                    products_to_update.append(product_instance)
                else:
                    products_to_create.append(product_instance)

            with transaction.atomic():
                if products_to_create:
                    self.model.objects.bulk_create(products_to_create, batch_size=1000)

                if products_to_update:
                    fields_to_update = ['barcode', 'name', 'cost', 'price', 'unit_of_measure']
                    self.model.objects.bulk_update(products_to_update, fields_to_update, batch_size=1000)

            return True

        except Exception as e:
            return False

