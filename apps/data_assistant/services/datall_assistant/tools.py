import datetime
from .sales_analytics_service import SalesAnalyticsService

def obtener_hora_actual(**kwargs):
    """
    Returns the current system time.
    """
    ahora = datetime.datetime.now()
    return f"The current system time is: {ahora.strftime('%Y-%m-%d %H:%M:%S')}"

def analyze_sales_data(user, dimensions=None, metrics=None, start_date=None, end_date=None, filters=None, **kwargs):
    """
    Aggregate and filter sales data based on the provided dimensions, metrics, and filters dynamically.
    """
    service = SalesAnalyticsService(user)
    try:
        data = service.get_aggregated_data(dimensions, metrics, start_date, end_date, filters)
        return data
    except Exception as e:
        return {"error": str(e)}

def search_catalog(user, entity_type, search_term, **kwargs):
    """
    Search for entities in the catalogs to get their IDs.
    """
    service = SalesAnalyticsService(user)
    try:
        data = service.search_catalog(entity_type, search_term)
        return data
    except Exception as e:
        return {"error": str(e)}
