import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import User, Module, Submodule

# 1. Crear / Actualizar Usuario
username = "a.velasco"
password = "datall1234"
first_name = "Angel Emmanuel"
last_name = "Moreno"
second_last_name = "Velasco"

user, created = User.objects.get_or_create(username=username)
user.first_name = first_name
user.last_name = last_name
user.second_last_name = second_last_name
user.is_staff = True
user.is_superuser = True
user.set_password(password)
user.save()

print(f"Usuario '{username}' {'creado' if created else 'actualizado'} exitosamente.")

# 2. Definición de Módulos y Submódulos
modules_data = [
    {
        "name": "business intelligence",
        "order": 1,
        "submodules": [
            {"name": "análisis avanzado", "url_name": "core:hello_world", "order": 1},
            {"name": "reportes especiales", "url_name": "core:hello_world", "order": 2},
            {"name": "ventas", "url_name": "core:hello_world", "order": 3},
            {"name": "clientes", "url_name": "core:hello_world", "order": 4},
            {"name": "productos", "url_name": "core:hello_world", "order": 5},
        ],
    },
    {
        "name": "recursos humanos",
        "order": 2,
        "submodules": [
            {"name": "departamentos", "url_name": "human_resources:department_list_view", "order": 1},
            {"name": "gerencias", "url_name": "human_resources:business_unit_list_view", "order": 2},
            {"name": "puestos y perfiles", "url_name": "human_resources:position_list_view", "order": 3},
            {"name": "desempeño y evaluaciones", "url_name": "human_resources:monitoring_form_submission_list_view", "order": 4},
        ],
    },
    {
        "name": "cuenta",
        "order": 3,
        "submodules": [
            {"name": "mi perfil", "url_name": "core:user_list_view", "order": 1},
            {"name": "reestablecimiento de contraseña", "url_name": "core:password_change", "order": 2},
        ],
    },
    {
        "name": "gestion datall",
        "order": 4,
        "submodules": [
            {"name": "usuarios", "url_name": "core:user_list_view", "order": 1},
        ],
    },
    {
        "name": "mas",
        "order": 5,
        "submodules": [],
    },
]

for mod_info in modules_data:
    module_obj, _ = Module.objects.update_or_create(
        name=mod_info["name"],
        defaults={"order": mod_info["order"], "is_active": True}
    )
    for sub_info in mod_info["submodules"]:
        sub_obj, _ = Submodule.objects.update_or_create(
            name=sub_info["name"],
            module=module_obj,
            defaults={
                "url_name": sub_info["url_name"],
                "order": sub_info["order"],
                "is_active": True,
            }
        )

print("Módulos y submódulos cargados exitosamente.")
