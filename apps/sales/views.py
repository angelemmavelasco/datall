from django.contrib import messages
from django.shortcuts import render, redirect
from apps.sales.services.products.products_crud import ProductsCRUD
from django.contrib.auth.decorators import login_required
from apps.core.models import Reference


@login_required
def products(request):
    TEMPLATE = 'sales/products/products.html'
    products_service = ProductsCRUD()
    products = products_service.get_products()

    context = {
        'products': products
    }

    return render(request, TEMPLATE, context)

@login_required
def product(request, product_id: str):
    TEMPLATE = 'sales/products/product.html'
    products_service = ProductsCRUD()
    product = products_service.get_product(product_id=product_id)

    context = {
        'product': product
    }

    return render(request, TEMPLATE, context)

@login_required
def product_import(request):
    TEMPLATE_REDIRECT = 'sales:products'

    if request.method == 'POST':
        file = request.FILES.get('file')

        if not file:
            messages.error(request, "No se adjuntó ningún archivo.")
            return redirect(TEMPLATE_REDIRECT)

        if not (file.name.endswith('.csv') or file.name.endswith('.xlsx')):
            messages.error(request, "El archivo debe ser un CSV o Excel (.xlsx).")
            return redirect(TEMPLATE_REDIRECT)

        column_ref = Reference.objects.filter(
            model=Reference.Model.COLUMNS,
            description='product_cleaning'
        )
        product_class_ref = Reference.objects.filter(
            model=Reference.Model.PRODUCT_CLASS,
            description='product_cleaning'
        )

        if not column_ref.exists():
            messages.error(request, "No existen reglas de mapeo de configuradas para la importación de productos.")
            return redirect(TEMPLATE_REDIRECT)

        column_mappers = {ref.key: ref.reference for ref in column_ref}
        products_service = ProductsCRUD()
        success = products_service.products_create(file=file, column_mappers=column_mappers)

        if success:
            messages.success(request, "El archivo se importó y procesó correctamente.")
        else:
            messages.error(request, "Ocurrió un error al procesar el archivo. Verifica el formato de los datos.")

    return redirect(TEMPLATE_REDIRECT)


