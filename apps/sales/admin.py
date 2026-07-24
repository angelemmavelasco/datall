from django.contrib import admin
from .models import (
    RouteType, SaleChannel, Route, RouteAssignment,
    Sale, SaleLine, SaleLineTax
)

admin.site.register(RouteType)
admin.site.register(SaleChannel)
admin.site.register(Route)
admin.site.register(RouteAssignment)
admin.site.register(Sale)
admin.site.register(SaleLine)
admin.site.register(SaleLineTax)
