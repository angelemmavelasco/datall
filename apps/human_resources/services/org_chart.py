from dataclasses import dataclass
from collections import defaultdict
from typing import ClassVar

from django.utils import timezone
from django.db.models import Q

from apps.core.services.users import UsersService
from apps.human_resources.models import Employee


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


@dataclass
class OrgChartService(UsersService):
    employee_model: type = Employee
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_colaboradores',
        'recursos_humanos',
    )

    def get_employees_queryset(self):
        """
        returns the complete employees qs, all users can view all org chart with no restriction
        """
        today = timezone.now().date()
        return self.employee_model.objects.filter(
            Q(hire_date__lte=today) & (Q(termination_date__isnull=True) | Q(termination_date__gte=today))
        ).select_related(
            'user',
            'position',
            'position__department',
            'business_unit',
            'manager',
            'manager__user',
            'manager__position'
        )

    def format_node_label(self, emp: Employee, html: bool = False) -> str:
        pos = emp.position.name.title() if emp.position else 'Sin Posición'
        dept = emp.position.department.name.title() if (emp.position and emp.position.department) else 'Sin Departamento'
        bu = emp.business_unit.name.title() if emp.business_unit else 'Sin Gerencia'
        full_name = f"{emp.user.first_name} {emp.user.last_name}".strip().title() if emp.user else ''
        if not full_name and emp.user:
            full_name = emp.user.username
        if not full_name:
            full_name = 'Sin Usuario'

        if html:
            return f'<strong class="font-bold text-title">{pos}</strong> » {bu}, dpto. {dept}: <span class="text-blue-500">{full_name}</span>'
        return f"{pos}, {dept} (gerencia: {bu}): {full_name}"

    def render_tree_nodes(self, nodes: list[dict], prefix: str = "", html: bool = False) -> list[str]:
        lines = []
        num_nodes = len(nodes)
        for idx, node in enumerate(nodes):
            is_last = (idx == num_nodes - 1)
            connector = "└── " if is_last else "├── "

            node_text = node['html_text'] if html else node['text']
            if html:
                conn_prefix = f'<span class="text-muted select-none">{prefix}{connector}</span>'
                lines.append(f"{conn_prefix}{node_text}")
            else:
                lines.append(f"{prefix}{connector}{node_text}")

            if node['children']:
                child_prefix = prefix + ("    " if is_last else "│   ")
                spacer_str = prefix + ("    │" if is_last else "│   │")
                if html:
                    lines.append(f'<span class="text-muted select-none">{spacer_str}</span>')
                else:
                    lines.append(spacer_str)
                lines.extend(self.render_tree_nodes(node['children'], child_prefix, html=html))

            if not is_last:
                sibling_spacer = prefix + "│"
                if html:
                    lines.append(f'<span class="text-muted select-none">{sibling_spacer}</span>')
                else:
                    lines.append(sibling_spacer)

        return lines

    def generate_tree_data(self) -> dict[str, str]:
        """
        generates the complete organizational hierarchy and returns both plain text
        and styled HTML representations with unix tree style connectors.
        """
        employees = list(self.get_employees_queryset())
        empty_msg = "No se encontraron colaboradores registrados o activos en la jerarquía."
        if not employees:
            return {'tree_text': empty_msg, 'tree_html': empty_msg}

        emp_dict = {emp.id: emp for emp in employees}
        children_map = defaultdict(list)
        roots = []

        for emp in employees:
            if emp.manager_id and emp.manager_id in emp_dict:
                children_map[emp.manager_id].append(emp)
            else:
                roots.append(emp)

        def sort_key(e):
            h_level = e.position.hierarchy_level if (e.position and e.position.hierarchy_level) else '9'
            pos_name = e.position.name if e.position else ''
            first_name = e.user.first_name if e.user else ''
            last_name = e.user.last_name if e.user else ''
            return (h_level, pos_name, first_name, last_name)

        roots.sort(key=sort_key)
        for m_id in children_map:
            children_map[m_id].sort(key=sort_key)

        def build_subtree(emp, depth=0):
            direct_children = children_map.get(emp.id, [])
            child_nodes = [build_subtree(child, depth + 1) for child in direct_children]
            return {
                'text': self.format_node_label(emp, html=False),
                'html_text': self.format_node_label(emp, html=True),
                'depth': depth,
                'children': child_nodes,
            }

        tree_hierarchy = [build_subtree(root, depth=0) for root in roots]

        if not tree_hierarchy:
            return {'tree_text': empty_msg, 'tree_html': empty_msg}

        plain_lines = []
        for i, root_node in enumerate(tree_hierarchy):
            plain_lines.append(root_node['text'])
            if root_node['children']:
                plain_lines.append("│")
                plain_lines.extend(self.render_tree_nodes(root_node['children'], prefix="", html=False))
            if i < len(tree_hierarchy) - 1:
                plain_lines.append("")

        html_lines = []
        for i, root_node in enumerate(tree_hierarchy):
            html_lines.append(root_node['html_text'])
            if root_node['children']:
                html_lines.append('<span class="text-muted select-none">│</span>')
                html_lines.extend(self.render_tree_nodes(root_node['children'], prefix="", html=True))
            if i < len(tree_hierarchy) - 1:
                html_lines.append("")

        return {
            'tree_text': "\n".join(plain_lines),
            'tree_html': "\n".join(html_lines),
        }

    def generate_tree_text(self) -> str:
        return self.generate_tree_data()['tree_text']
