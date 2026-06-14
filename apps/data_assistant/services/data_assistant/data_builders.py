from datetime import datetime
from apps.business_intelligence.services.commercial_risk.commercial_risk import CommercialRisk

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

def build_sales_dashboard_data(params):
    """Extrae los datos específicos para el Dashboard de Ventas"""
    
    pass