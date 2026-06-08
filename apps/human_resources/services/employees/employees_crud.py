from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from apps.core.models import Employee

User = get_user_model()

class EmployeesCRUD:

    def get_employees(self, search_query: str = None):
        """
        Retrieves users who have at least one Employee record.
        Prefetches only their currently active employee record.
        """
        
        # Prefetch the active employee record (termination_date is null)
        active_employee_prefetch = Prefetch(
            'employees',
            queryset=Employee.objects.filter(termination_date__isnull=True).select_related('position', 'warehouse', 'manager', 'manager__user'),
            to_attr='active_employee_records'
        )
        
        queryset = User.objects.filter(employees__isnull=False).distinct().prefetch_related(active_employee_prefetch)
        
        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(username__icontains=search_query) |
                Q(email__icontains=search_query)
            )
            
        return queryset

    def get_user_with_employee_history(self, user_id: int):
        """
        Retrieves a user and their full employment history (all Employee records).
        """
        if not user_id:
            return None

        employee_prefetch = Prefetch(
            'employees',
            queryset=Employee.objects.select_related(
                'position', 'warehouse', 'manager', 'manager__user', 
                'payroll_type', 'payroll_periodicity', 'tax_system'
            ).order_by('-hire_date')
        )

        return User.objects.prefetch_related(employee_prefetch).filter(id=user_id).first()

    def process_employee_create(self, raw_data: dict):
        """
        Process the raw data from a dict and create a new Employee record.
        """
        if not raw_data:
            return False

        user_id = raw_data.get('user_id')
        position_id = raw_data.get('position_id')
        warehouse_id = raw_data.get('warehouse_id')
        hire_date = raw_data.get('hire_date')
        
        if not user_id or not position_id or not warehouse_id or not hire_date:
            return False

        cleaned_data = {}
        fields_to_null = [
            'termination_date', 'manager_id', 'payroll_type_id', 
            'payroll_amount', 'payroll_periodicity_id', 'tax_system_id'
        ]

        for key, value in raw_data.items():
            if key == 'csrfmiddlewaretoken':
                continue
                
            if value == "":
                if key in fields_to_null:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = ""
            else:
                cleaned_data[key] = value

        new_employee = Employee(**cleaned_data)
        new_employee.save()
        
        return new_employee

    def get_org_chart_employees(self, search_query: str = None):
        queryset = Employee.objects.select_related(
            'user', 'position', 'warehouse', 'manager'
        ).prefetch_related(
            'managed_regions'
        ).filter(termination_date__isnull=True)
        
        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )
        return queryset
