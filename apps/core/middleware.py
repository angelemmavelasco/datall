import time
import logging
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from apps.core.models import ActivityLog, Submodule

logger = logging.getLogger(__name__)


class ActivityTrackingMiddleware:
    """
    registra la actividad de usuarios autenticados incluyendo rutas, parametros seguros y tiempos de respuesta.
    requiere el callable get_response de django y devuelve el objeto httpresponse procesado.
    """

    EXCLUDED_PREFIXES = (
        '/static/',
        '/media/',
        '/favicon.ico',
        '/__debug__/',
        '/admin/jsi18n/',
    )

    SENSITIVE_PARAMS = {
        'password',
        'csrfmiddlewaretoken',
        'token',
        'secret',
        'auth',
        'session_key',
    }

    OBJECT_ID_KWARGS = (
        'contact_id',
        'period_id',
        'pk',
        'id',
        'object_id',
    )

    VIEW_MODEL_MAP = {
        'core:user_list_view': ('core', 'user'),
        'core:user_detail_view': ('core', 'user'),
        'core:user_create_form_view': ('core', 'user'),
        'core:user_update_form_view': ('core', 'user'),
        'core:report_download_view': ('core', 'generatedreport'),
        'core:app_version_list_view': ('core', 'appversion'),
        'core:user_docs_view': ('core', 'supportarticle'),
        'core:activity_logs_view': ('core', 'activitylog'),
        'sales:warehouse_list_view': ('sales', 'warehouse'),
        'sales:warehouse_create_view': ('sales', 'warehouse'),
        'sales:warehouse_detail_view': ('sales', 'warehouse'),
        'sales:warehouse_update_view': ('sales', 'warehouse'),
        'sales:route_list_view': ('sales', 'route'),
        'sales:route_create_view': ('sales', 'route'),
        'sales:route_detail_view': ('sales', 'route'),
        'sales:route_update_view': ('sales', 'route'),
        'sales:sale_transaction_list_view': ('sales', 'saletransaction'),
        'sales:sale_transaction_export_view': ('sales', 'saletransaction'),
        'sales:sale_transaction_detail_view': ('sales', 'saletransaction'),
        'sales:sale_target_list_view': ('sales', 'saletarget'),
        'sales:sale_target_detail_view': ('sales', 'saletarget'),
        'sales:sale_target_update_view': ('sales', 'saletarget'),
        'customers:customer_list_view': ('customers', 'customer'),
        'customers:customer_create_view': ('customers', 'customer'),
        'customers:customer_detail_view': ('customers', 'customer'),
        'customers:customer_update_view': ('customers', 'customer'),
        'customers:customer_set_visit_schedule_view': ('customers', 'customer'),
        'customers:customer_add_note_view': ('customers', 'customer'),
        'customers:customer_add_contact_view': ('customers', 'customer'),
        'customers:customer_update_contact_view': ('customers', 'customercontact'),
        'customers:customer_delete_contact_view': ('customers', 'customercontact'),
        'customers:ar_list_view': ('customers', 'accountsreceivable'),
        'customers:export_ars_view': ('customers', 'accountsreceivable'),
        'customers:ar_detail_view': ('customers', 'accountsreceivable'),
        'customers:customer_agreement_list_view': ('customers', 'customeragreement'),
        'customers:customer_agreement_create_view': ('customers', 'customeragreement'),
        'customers:customer_agreement_detail_view': ('customers', 'customeragreement'),
        'customers:customer_agreement_update_document_view': ('customers', 'customeragreement'),
        'customers:customer_agreement_evaluate_action_view': ('customers', 'customeragreement'),
        'customers:commercial_benefit_list_view': ('customers', 'commercialbenefit'),
        'customers:commercial_benefit_create_view': ('customers', 'commercialbenefit'),
        'customers:commercial_benefit_update_view': ('customers', 'commercialbenefit'),
        'customers:commercial_benefit_toggle_active_view': ('customers', 'commercialbenefit'),
        'products:product_list_view': ('products', 'product'),
        'products:product_create_view': ('products', 'product'),
        'products:product_detail_view': ('products', 'product'),
        'products:product_update_view': ('products', 'product'),
        'products:stock_transfers_view': ('products', 'stock'),
        'products:export_stock_transfers_view': ('products', 'stock'),
        'products:purchase_order_list_view': ('products', 'purchaseorder'),
        'products:purchase_order_create_view': ('products', 'purchaseorder'),
        'products:purchase_order_detail_view': ('products', 'purchaseorder'),
        'products:purchase_order_status_update_view': ('products', 'purchaseorder'),
        'products:export_purchase_order_view': ('products', 'purchaseorder'),
        'human_resources:business_unit_list_view': ('human_resources', 'businessunit'),
        'human_resources:business_unit_detail_view': ('human_resources', 'businessunit'),
        'human_resources:business_unit_create_view': ('human_resources', 'businessunit'),
        'human_resources:business_unit_update_view': ('human_resources', 'businessunit'),
        'human_resources:department_list_view': ('human_resources', 'department'),
        'human_resources:department_detail_view': ('human_resources', 'department'),
        'human_resources:department_create_view': ('human_resources', 'department'),
        'human_resources:department_update_view': ('human_resources', 'department'),
        'human_resources:position_list_view': ('human_resources', 'position'),
        'human_resources:position_detail_view': ('human_resources', 'position'),
        'human_resources:position_create_view': ('human_resources', 'position'),
        'human_resources:position_update_view': ('human_resources', 'position'),
        'human_resources:position_skill_list_view': ('human_resources', 'positionskill'),
        'human_resources:position_skill_detail_view': ('human_resources', 'positionskill'),
        'human_resources:position_skill_create_view': ('human_resources', 'positionskill'),
        'human_resources:position_skill_update_view': ('human_resources', 'positionskill'),
        'human_resources:monitoring_form_field_list_view': ('human_resources', 'monitoringformfield'),
        'human_resources:monitoring_form_field_detail_view': ('human_resources', 'monitoringformfield'),
        'human_resources:monitoring_form_field_create_view': ('human_resources', 'monitoringformfield'),
        'human_resources:monitoring_form_field_update_view': ('human_resources', 'monitoringformfield'),
        'human_resources:monitoring_form_list_view': ('human_resources', 'monitoringform'),
        'human_resources:monitoring_form_detail_view': ('human_resources', 'monitoringform'),
        'human_resources:monitoring_form_create_view': ('human_resources', 'monitoringform'),
        'human_resources:monitoring_form_update_view': ('human_resources', 'monitoringform'),
        'human_resources:monitoring_form_submission_list_view': ('human_resources', 'monitoringformsubmission'),
        'human_resources:monitoring_form_submission_detail_view': ('human_resources', 'monitoringformsubmission'),
        'human_resources:monitoring_form_submission_create_view': ('human_resources', 'monitoringperiod'),
        'human_resources:monitoring_form_submission_update_view': ('human_resources', 'monitoringformsubmission'),
        'human_resources:monitoring_form_submission_delete_view': ('human_resources', 'monitoringformsubmission'),
        'human_resources:employee_list_view': ('human_resources', 'employee'),
        'human_resources:employee_detail_view': ('human_resources', 'employee'),
        'human_resources:employee_create_view': ('human_resources', 'employee'),
        'human_resources:employee_update_view': ('human_resources', 'employee'),
        'mapser:mapser_view': ('mapser', 'customergeoprofile'),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        start_time = time.perf_counter()
        response = self.get_response(request)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        if hasattr(request, 'user') and request.user.is_authenticated:
            self._log_activity(request, response, duration_ms)

        return response

    def _log_activity(self, request, response, duration_ms: int):
        try:
            resolver_match = getattr(request, 'resolver_match', None)
            view_name = resolver_match.view_name if resolver_match else ''
            path = request.path
            http_method = request.method
            params = {}
            if request.GET:
                for k, v in request.GET.lists():
                    if k.lower() not in self.SENSITIVE_PARAMS:
                        params[k] = v[0] if len(v) == 1 else v
            if request.method in ('POST', 'PUT', 'PATCH') and request.POST:
                post_params = {}
                for k, v in request.POST.lists():
                    if k.lower() not in self.SENSITIVE_PARAMS:
                        post_params[k] = v[0] if len(v) == 1 else v
                if post_params:
                    params['post_data'] = post_params
            if request.FILES:
                params['files'] = [f.name for f in request.FILES.values()]
            action = self._infer_action(request, view_name, params)
            status_code = response.status_code
            if status_code < 400:
                result = ActivityLog.Result.SUCCESS
            elif 400 <= status_code < 500:
                result = ActivityLog.Result.WARNING
            else:
                result = ActivityLog.Result.ERROR

            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

            submodule = None
            if view_name:
                submodule = Submodule.objects.filter(url_name=view_name).first()

            extra_log = getattr(request, 'activity_log_extra', None) or {}
            content_type, object_id = self._resolve_object_reference(resolver_match, extra_log)
            if extra_log.get('action'):
                action = extra_log['action']
            changes = extra_log.get('changes') if isinstance(extra_log.get('changes'), dict) else {}

            ActivityLog.objects.create(
                user=request.user,
                path=path,
                view_name=view_name,
                http_method=http_method,
                submodule=submodule,
                action=action,
                result=result,
                status_code=status_code,
                content_type=content_type,
                object_id=object_id,
                params=params,
                changes=changes,
                ip_address=ip_address,
                user_agent=user_agent,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning(f"error recording activity log: {e}")

    def _infer_action(self, request, view_name: str, params: dict) -> str:
        path_lower = request.path.lower()
        view_lower = view_name.lower() if view_name else ''
        method = request.method.upper()

        if 'export' in path_lower or 'export' in view_lower:
            return ActivityLog.Action.EXPORT
        if 'import' in path_lower or 'upload' in path_lower or 'import' in view_lower:
            return ActivityLog.Action.IMPORT
        if 'login' in path_lower or 'login' in view_lower:
            return ActivityLog.Action.LOGIN
        if 'logout' in path_lower or 'logout' in view_lower:
            return ActivityLog.Action.LOGOUT
        if method == 'POST':
            if 'delete' in path_lower or 'delete' in view_lower:
                return ActivityLog.Action.DELETE
            if any(term in path_lower or term in view_lower for term in ('create', 'add', 'new')):
                return ActivityLog.Action.CREATE
            return ActivityLog.Action.UPDATE
        if method == 'DELETE':
            return ActivityLog.Action.DELETE
        if method == 'GET' and params:
            return ActivityLog.Action.FILTER
        return ActivityLog.Action.VIEW

    def _resolve_object_reference(self, resolver_match, extra_log: dict):
        """
        resuelve el contenttype y el identificador de objeto desde metadatos de vista o parametros de url.
        requiere el resolver_match y diccionario extra y retorna la tupla content_type y object_id.
        """
        content_object = extra_log.get('content_object')
        if content_object is not None and getattr(content_object, 'pk', None) is not None:
            return ContentType.objects.get_for_model(content_object), str(content_object.pk)[:255]

        content_type = extra_log.get('content_type')
        object_id = extra_log.get('object_id')

        if object_id is None and resolver_match and resolver_match.kwargs:
            for kwarg_name in self.OBJECT_ID_KWARGS:
                val = resolver_match.kwargs.get(kwarg_name)
                if val is not None:
                    object_id = val
                    break

        if object_id is not None:
            object_id = str(object_id)[:255]

        if content_type is None and resolver_match and resolver_match.view_name:
            model_key = self.VIEW_MODEL_MAP.get(resolver_match.view_name)
            if model_key:
                try:
                    content_type = ContentType.objects.get_by_natural_key(*model_key)
                except ContentType.DoesNotExist:
                    content_type = None

        return content_type, object_id
