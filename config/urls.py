from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.analytics.views import(
    sales_dashboard_view
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('human_resources/', include('apps.human_resources.urls')),
    path('sales/', include('apps.sales.urls')),
    path('customers/', include('apps.customers.urls')),
    path('products/', include('apps.products.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('mapser/', include('apps.mapser.urls')),
    
    #legacy urls
    path('business_intelligence/sales_dashboard', sales_dashboard_view, name='sales_dashboard_view'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = 'apps.core.views.error_400_view'
handler403 = 'apps.core.views.error_403_view'
handler404 = 'apps.core.views.error_404_view'
handler500 = 'apps.core.views.error_500_view'