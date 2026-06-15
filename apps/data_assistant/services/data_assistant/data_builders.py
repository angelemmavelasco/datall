from datetime import datetime, date
from apps.business_intelligence.services.commercial_risk.commercial_risk import CommercialRisk
from apps.business_intelligence.services.monthly_breakdown_by_warehouse.monthly_breakdown_by_warehouse import MonthlyBreakdownByWarehouse
from apps.core.utils import get_allowed_routes_for_user

def build_commercial_risk_data(params):
    """
    Extratcts the sepecific params for commercial risk view
    """
    route_id = params.get('route')
    
    date_start_str = params.get('date_start')
    date_start_obj = datetime.strptime(date_start_str, '%Y-%m-%d').date()

    date_end_str = params.get('date_end')
    date_end_obj = datetime.strptime(date_end_str, '%Y-%m-%d').date()

    risk_engine = CommercialRisk(
        date_start=date_start_obj, 
        date_end=date_end_obj, 
        route_id=route_id
    )
    
    summary = risk_engine.summary_for_assistant()
    summary['route'] = route_id
    return summary

def build_monthly_breakdown_by_warehouse(params):
    """
    Extracts the params for monthly breakdown by warehouse view
    """
    year_str = params.get('year', str(date.today().year))
    year = int(year_str)
    warehouse_id = params.get('warehouse')

    user = params.get('user')
    allowed_routes = get_allowed_routes_for_user(user)

    service = MonthlyBreakdownByWarehouse(
        year=year, 
        allowed_routes_qs=allowed_routes, 
        warehouse_id=warehouse_id
    )

    summary = service.summary_for_assistant()
    summary['warehouse'] = warehouse_id
    summary['year'] = year

    return summary