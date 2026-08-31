from django.contrib import admin
from django.contrib.admin.apps import AdminConfig


class CustomAdminConfig(AdminConfig):
    default_site = 'apps.core.admin_site.ThemedAdminSite'


class ThemedAdminSite(admin.AdminSite):
    site_header = "Panel de administración Datall"
    site_title = "Datall Admin"
    index_title = "Panel de Administración"

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        all_models = {}
        for app in app_list:
            for model in app['models']:
                all_models[model['object_name']] = model

        themed_groups = [
            {
                'name': 'Estructura Organizacional',
                'app_label': 'hr_estructura_organizacional',
                'models': [
                    'Department',
                    'Position',
                    'PositionKPI',
                    'Skill',
                    'PositionSkill',
                    'BusinessUnit',
                    'Employee',
                ]
            },
            {
                'name': 'Reportes de desempeño » Formatos',
                'app_label': 'hr_formatos_desempeno',
                'models': [
                    'MonitoringForm',
                    'MonitoringFormField',
                    'MonitoringFormQuestion',
                    'MonitoringPeriod',
                ]
            },
            {
                'name': 'Reportes de desempeño » Envíos',
                'app_label': 'hr_envios_desempeno',
                'models': [
                    'MonitoringFormSubmission',
                    'MonitoringFormAnswer',
                ]
            },
            {
                'name': 'Inventario',
                'app_label': 'sales_inventario',
                'models': [
                    'Warehouse',
                    'Product',
                    'ProductCategory',
                    'ProductClass',
                    'ProductProperty',
                    'ProductPropertyValue',
                    'Stock',
                ]
            },
            {
                'name': 'Rutas',
                'app_label': 'sales_rutas',
                'models': [
                    'Route',
                    'RouteType',
                    'SaleChannel',
                    'RouteAssignment',
                    'UserRouteAccess',
                ]
            },
            {
                'name': 'Ventas',
                'app_label': 'sales_ventas',
                'models': [
                    'SaleTransaction',
                    'SaleTarget',
                ]
            },
            {
                'name': 'Clientes',
                'app_label': 'customers_clientes',
                'models': [
                    'Customer',
                    'CustomerType',
                    'CustomerAssignment',
                    'CustomerClassMargin',
                    'AccountsReceivable',
                ]
            },
            {
                'name': 'Convenios',
                'app_label': 'customers_convenios',
                'models': []
            },
            {
                'name': 'Configuración del Sistema',
                'app_label': 'core_configuracion',
                'models': [
                    'Module',
                    'Submodule',
                    'Reference',
                    'AppVersion',
                    'User',
                    'Group',
                ]
            }
        ]

        new_app_list = []
        used_models = set()

        for group in themed_groups:
            group_models = []
            for model_name in group['models']:
                if model_name in all_models:
                    group_models.append(all_models[model_name])
                    used_models.add(model_name)

            if group_models:
                new_app_list.append({
                    'name': group['name'],
                    'app_label': group['app_label'],
                    'app_url': '',
                    'has_module_perms': True,
                    'models': group_models,
                })
        for app in app_list:
            remaining_models = [m for m in app['models'] if m['object_name'] not in used_models]
            if remaining_models:
                new_app_list.append({
                    'name': app['name'],
                    'app_label': app['app_label'],
                    'app_url': app['app_url'],
                    'has_module_perms': app['has_module_perms'],
                    'models': remaining_models,
                })

        return new_app_list
