from dataclasses import dataclass, field
from collections import defaultdict
from typing import ClassVar

from django.utils import timezone
from django.db.models import Q

from apps.core.services.users import UsersService
from apps.human_resources.models import Employee
from apps.human_resources.services.employees import EmployeesService


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
    accessible_employee_ids: set = field(init=False)

    def __post_init__(self):
        super().__post_init__()
        emp_service = EmployeesService(user=self.user)
        self.accessible_employee_ids = set(emp_service.read_employees().values_list('id', flat=True))

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
            email = (emp.user.email or '').strip() if emp.user else ''
            phone = (emp.user.phone or '').strip() if emp.user else ''
            emp_id = emp.id
            can_view = "true" if emp.id in self.accessible_employee_ids else "false"
            return (
                f'<button type="button" '
                f'class="contact-node-btn font-bold text-title hover:text-hover hover:underline cursor-pointer transition-colors text-left bg-transparent border-0 font-mono" '
                f'data-pos="{pos}" '
                f'data-name="{full_name}" '
                f'data-dept="{dept}" '
                f'data-bu="{bu}" '
                f'data-email="{email}" '
                f'data-phone="{phone}" '
                f'data-empid="{emp_id}" '
                f'data-canview="{can_view}" '
                f'title="Ver contacto de {full_name}">{pos}</button> » {bu}, dpto. {dept}: <span class="text-blue-500 font-medium">{full_name}</span>'
            )
        return f"{pos}, {dept} (gerencia: {bu}): {full_name}"

    def render_tree_nodes_plain(self, nodes: list[dict], prefix: str = "") -> list[str]:
        lines = []
        num_nodes = len(nodes)
        for idx, node in enumerate(nodes):
            is_last = (idx == num_nodes - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{node['text']}")

            if node['children']:
                child_prefix = prefix + ("    " if is_last else "│   ")
                spacer_str = prefix + ("    │" if is_last else "│   │")
                lines.append(spacer_str)
                lines.extend(self.render_tree_nodes_plain(node['children'], child_prefix))

            if not is_last:
                sibling_spacer = prefix + "│"
                lines.append(sibling_spacer)

        return lines

    def render_collapsible_node(self, node: dict, default_expand_depth: int = 1) -> str:
        emp = node['emp']
        pos = emp.position.name.title() if emp.position else 'Sin Posición'
        dept = emp.position.department.name.title() if (emp.position and emp.position.department) else 'Sin Departamento'
        bu = emp.business_unit.name.title() if emp.business_unit else 'Sin Gerencia'
        full_name = f"{emp.user.first_name} {emp.user.last_name}".strip().title() if emp.user else ''
        if not full_name and emp.user:
            full_name = emp.user.username
        if not full_name:
            full_name = 'Sin Usuario'

        email = (emp.user.email or '').strip() if emp.user else ''
        phone = (emp.user.phone or '').strip() if emp.user else ''
        emp_id = emp.id
        can_view = "true" if emp.id in self.accessible_employee_ids else "false"

        depth = node['depth']
        children = node['children']
        num_children = len(children)
        has_children = num_children > 0

        is_open = (depth < default_expand_depth)
        search_text = f"{pos} {dept} {bu} {full_name} {email} {phone} {emp.user.username if emp.user else ''}".lower()

        if num_children == 1:
            child_badge_text = "1 colaborador"
        else:
            child_badge_text = f"{num_children} colaboradores"

        badge_html = (
            f'<span class="tree-badge text-[10px] font-sans px-1.5 py-0.5 rounded border border-border text-muted bg-page/80 group-hover:border-strong group-hover:text-title transition-colors ml-1 shrink-0">'
            f'{child_badge_text}'
            f'</span>'
        ) if has_children else ''

        if has_children:
            rotate_class = "rotate-90" if is_open else ""
            toggle_html = (
                f'<button type="button" class="tree-toggle-btn w-5 h-5 flex items-center justify-center rounded hover:bg-hover text-muted hover:text-title transition-colors cursor-pointer shrink-0" '
                f'onclick="toggleTreeNode(this.closest(\'.tree-node-row\'), event)" title="Expandir/Colapsar equipo">'
                f'<svg class="tree-toggle-icon w-3.5 h-3.5 transition-transform duration-200 {rotate_class}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                f'<path d="m9 18 6-6-6-6"/>'
                f'</svg>'
                f'</button>'
            )
        else:
            toggle_html = '<span class="w-5 h-5 flex items-center justify-center text-muted/30 shrink-0 select-none text-xs">•</span>'

        node_btn_html = (
            f'<button type="button" '
            f'class="contact-node-btn font-bold text-title hover:text-hover hover:underline cursor-pointer transition-colors text-left bg-transparent border-0 font-mono" '
            f'data-pos="{pos}" '
            f'data-name="{full_name}" '
            f'data-dept="{dept}" '
            f'data-bu="{bu}" '
            f'data-email="{email}" '
            f'data-phone="{phone}" '
            f'data-empid="{emp_id}" '
            f'data-canview="{can_view}" '
            f'title="Ver contacto de {full_name}">{pos}</button>'
        )

        cursor_class = "cursor-pointer" if has_children else "cursor-default"

        html_out = [
            f'<div class="tree-node flex flex-col w-full" data-node-id="{emp_id}" data-depth="{depth}" data-search-text="{search_text}">',
            f'  <div class="tree-node-row flex items-center flex-wrap gap-1.5 py-1 px-2 rounded hover:bg-hover/10 transition-colors font-mono text-xs select-none group {cursor_class}" onclick="toggleTreeNode(this, event)">',
            f'    {toggle_html}',
            f'    {node_btn_html}',
            f'    <span class="text-secondary text-[11px]">» {bu}, dpto. {dept}:</span>',
            f'    <span class="text-blue-500 font-medium">{full_name}</span>',
            f'    {badge_html}',
            f'  </div>',
        ]

        if has_children:
            container_hidden = "" if is_open else "hidden"
            html_out.append(f'  <div class="tree-children-container {container_hidden} flex flex-col ml-3.5 pl-3 border-l border-border/70 gap-0.5 mt-0.5">')
            for child in children:
                html_out.append(self.render_collapsible_node(child, default_expand_depth=default_expand_depth))
            html_out.append('  </div>')

        html_out.append('</div>')
        return "\n".join(html_out)

    def generate_tree_data(self) -> dict[str, str]:
        """
        generates the complete organizational hierarchy and returns both plain text
        and interactive collapsible HTML representations.
        """
        employees = list(self.get_employees_queryset())
        empty_msg = "No se encontraron colaboradores registrados o activos en la jerarquía."
        if not employees:
            return {'tree_text': empty_msg, 'tree_html': f'<div class="text-muted text-xs p-4">{empty_msg}</div>'}

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
                'emp': emp,
                'emp_id': emp.id,
                'text': self.format_node_label(emp, html=False),
                'depth': depth,
                'children': child_nodes,
            }

        tree_hierarchy = [build_subtree(root, depth=0) for root in roots]

        if not tree_hierarchy:
            return {'tree_text': empty_msg, 'tree_html': f'<div class="text-muted text-xs p-4">{empty_msg}</div>'}

        plain_lines = []
        for i, root_node in enumerate(tree_hierarchy):
            plain_lines.append(root_node['text'])
            if root_node['children']:
                plain_lines.append("│")
                plain_lines.extend(self.render_tree_nodes_plain(root_node['children'], prefix=""))
            if i < len(tree_hierarchy) - 1:
                plain_lines.append("")


        html_nodes = []
        for root_node in tree_hierarchy:
            html_nodes.append(self.render_collapsible_node(root_node, default_expand_depth=1))

        return {
            'tree_text': "\n".join(plain_lines),
            'tree_html': "\n".join(html_nodes),
        }

    def generate_tree_text(self) -> str:
        return self.generate_tree_data()['tree_text']
