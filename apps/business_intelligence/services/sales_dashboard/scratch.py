import calendar
from datetime import datetime, date
from decimal import Decimal

def calculate_prorated_target(target_amount, period_date, date_start=None, date_end=None):
    if not date_start and not date_end:
        return target_amount
        
    month_start = period_date
    _, last_day = calendar.monthrange(month_start.year, month_start.month)
    month_end = date(month_start.year, month_start.month, last_day)
    
    start = date_start if date_start else month_start
    end = date_end if date_end else month_end
    
    # Calculate intersection
    overlap_start = max(month_start, start)
    overlap_end = min(month_end, end)
    
    if overlap_start > overlap_end:
        return Decimal('0.00')
        
    overlap_days = (overlap_end - overlap_start).days + 1
    total_days = (month_end - month_start).days + 1
    
    return Decimal(target_amount) * Decimal(overlap_days) / Decimal(total_days)

print(calculate_prorated_target(31000, date(2024, 5, 1), date(2024, 5, 10), date(2024, 5, 20)))
