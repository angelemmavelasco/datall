# Sistema de Comisiones

El motor de comisiones está estructurado utilizando Programación Orientada a Objetos en la capa de servicios y se apoya en modelos relacionales jerárquicos para garantizar la trazabilidad en el tiempo y el rendimiento de la base de datos.

## Arquitectura de Modelos

El sistema se divide en los siguientes modelos clave dentro de `apps/core/models.py`:

* `CommissionProfile`: Entidad base. Agrupa las reglas generales y sirve como identificador del esquema.
* `CommissionTier`: Define los rangos o escalones de comisión para un perfil.
* `RouteCommissionSetup`: Relaciona una Ruta con un Perfil en un rango de fechas. Permite el historial de asignaciones.
* `RouteCommissionException`: Maneja casos atípicos temporales (como la curva de aprendizaje de nuevos ingresos o permisos especiales).
* `CommissionSettlement`: Almacena la liquidación final inmutable, tomando una "fotografía" (snapshot) de los datos al momento del cálculo para prevenir alteraciones históricas si los esquemas cambian.

## Lógica de Servicios (Service Layer)

Toda la lógica de negocio para la configuración de comisiones reside en `apps/human_resources/services/comissions/comissions.py`.

### Creación de Perfiles y Asignación Masiva

El método `commission_profile_create` maneja la creación atómica del perfil, sus umbrales y la asignación a múltiples rutas.

```python
@transaction.atomic
def commission_profile_create(self, profile_data, tiers_data, configs_data):
    # 1. Crea el CommissionProfile base
    # 2. Crea los CommissionTier en bulk (lote) para mejor rendimiento
    # 3. Itera sobre las configuraciones de rutas (configs_data)
    for config in configs_data:
        self.configure_profile_to_route(profile, config)
    return profile
```

### Prevención de Solapamiento (Overlaps)

La validación más crítica ocurre en `configure_profile_to_route`. Antes de insertar un nuevo `RouteCommissionSetup`, el sistema verifica que la ruta no tenga ya un perfil activo que se empalme temporalmente con las nuevas fechas propuestas.

```python
active_setups = RouteCommissionSetup.objects.filter(route_id=route_id).select_related('profile')

for setup in active_setups:
    error_msg = f"La ruta {route_id} cuenta con un perfil activo ('{setup.profile.name}'). Finaliza el perfil actual o elimínala de esta configuración."

    if not setup.end_date:
        # Si el setup actual es indefinido (no tiene fecha de fin), 
        # genera conflicto si la nueva configuración tampoco tiene fin o si cruza el inicio actual.
        if not end_date or start_date >= setup.start_date or end_date >= setup.start_date:
            raise ValueError(error_msg)
    else:
        # Lógica de intersección de rangos de fecha cuando ambas tienen límite
        if not end_date:
            if start_date <= setup.end_date:
                raise ValueError(error_msg)
        else:
            if start_date <= setup.end_date and end_date >= setup.start_date:
                raise ValueError(error_msg)
```
*Si se detecta un solapamiento, se levanta un `ValueError` que aborta la transacción completa en la base de datos gracias al decorador `@transaction.atomic`.*

### Motor de Lectura y Rendimiento

El método `commissions_read` genera el queryset base para el listado de perfiles. Para evitar el problema común de N+1 consultas (N+1 queries problem), se utilizan subconsultas (`Subquery`) y agregaciones a nivel de base de datos (`OuterRef`, `Count`, `Sum`, `Coalesce`).

```python
# Ejemplo de conteo de rutas activas asociadas al perfil
active_routes_sq = RouteCommissionSetup.objects.filter(
    profile=OuterRef('pk'),
    route__in=self.allowed_routes
).filter(
    Q(end_date__isnull=True) | Q(end_date__gte=today)
).values('profile').annotate(
    count=Count('id')
).values('count')

qs = qs.annotate(
    associated_routes_count=Coalesce(Subquery(active_routes_sq, output_field=IntegerField()), 0),
    # ...
)
```
*Esto permite que métricas pesadas como "Rutas activas", "Monto pagado" o "Reportes generados" se calculen directamente en PostgreSQL de forma altamente optimizada durante la consulta inicial.*

### Evaluación Escalonada (Tiers)

El modelo `CommissionTier` define un ordenamiento predeterminado vital para el cálculo de pagos. Esto asegura que Python siempre evalúe de mayor a menor rendimiento:

```python
class Meta:
    ordering = ['-min_global_scope_pct', '-min_completed_classes']
```
*Al evaluar las comisiones de un vendedor, el motor iterará sobre el queryset ordenado. El primer registro que cumpla con las condiciones de alcance del vendedor será el "Tier" aplicado. Esto elimina la necesidad de programar de forma manual la evaluación de rangos condicionales ("si es mayor a X pero menor a Y") en el código de cálculo.*

### Gestión de Excepciones (CommissionExceptions)

La clase `CommissionExceptions` sigue los mismos principios de rendimiento y responsabilidad única.

#### Obtención de Datos y Concatenación Dinámica

El método `get_data` se encarga de obtener las excepciones y, en lugar de iterar cada registro para buscar el nombre del vendedor actual (lo que generaría un problema grave de consultas N+1), inyecta los datos usando subconsultas sobre la tabla de asignaciones (`RouteAssignment`):

```python
assignments = RouteAssignment.objects.filter(
    route=OuterRef('route'),
    start_date__lte=OuterRef('end_date')
).filter(
    Q(end_date__isnull=True) | Q(end_date__gte=OuterRef('start_date'))
).order_by('-start_date')

first_name_sq = assignments.values('employee__user__first_name')[:1]
last_name_sq = assignments.values('employee__user__last_name')[:1]

qs = qs.annotate(
    first_name=Subquery(first_name_sq),
    last_name=Subquery(last_name_sq)
).annotate(
    employee=Concat('first_name', Value(' '), 'last_name', output_field=CharField())
)
```
*Esta técnica permite extraer el nombre y apellido del vendedor asignado exactamente en el rango de fechas de la excepción, concatenarlo a nivel de base de datos (`Concat`) y devolver el campo `employee` ya construido, mejorando drásticamente el tiempo de respuesta.*

#### Creación Masiva (Bulk Create)

Para la asignación masiva desde la interfaz de usuario, el método `create_multiple` itera sobre las rutas permitidas, instancia los modelos en memoria y ejecuta un solo llamado a la base de datos:

```python
def create_multiple(self, route_ids, exception_data):
    valid_routes = self.allowed_routes.filter(id__in=route_ids)
    
    exceptions_to_create = [
        RouteCommissionException(route=route, **exception_data)
        for route in valid_routes
    ]
    
    if exceptions_to_create:
        RouteCommissionException.objects.bulk_create(exceptions_to_create)
```
*El uso de `bulk_create` garantiza que la creación de decenas o cientos de excepciones para una lista de rutas no sature la red ni la base de datos, despachando la instrucción completa en una única transacción.*
