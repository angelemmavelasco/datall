# Sistema de Comisiones

El motor de comisiones está estructurado utilizando Programación Orientada a Objetos en la capa de servicios y se apoya en modelos relacionales jerárquicos para garantizar la trazabilidad en el tiempo y el rendimiento de la base de datos.
commit 1360b3b9cf194f28c518a34305c5dd5d5d8adf8f (HEAD -> etl, origin/etl)
Author: Angel Velasco <angelvelasco@Angels-MacBook-Air.local>
Date:   Fri Jul 24 15:02:52 2026 -0600

    feat: implement stock transfer calculation and export service with database models and UI integration
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
*El uso de bulk_create garantiza que la creación de decenas o cientos de excepciones para una lista de rutas no sature la red ni la base de datos, despachando la instrucción completa en una única transacción.*

### Motor de calculo y tolerancias
La generacion de calculos mensuales se orquesta en el metodo *create_multiple*. Se implemento una estrategia de separacion entre el alcance de metas reales y las reglas de negocio de compensacion.

```python
effective_scope = settlement.snapshot_global_scope
if exception:
    effective_scope += exception.scope_tolerance_pct

applied_tier = tiers.filter(
    min_global_scope_pct__lte=effective_scope,
    min_completed_classes__lte=settlement.snapshot_completed_classes
).first()
```
*Este fragmento de codigo del detalle de liquidacion ilustra como el sistema respeta y almacena permanentemente el rendimiento bruto del colaborador en la propiedad snapshot_global_scope. No obstante, al determinar que peldaño o multiplicador le corresponde, utiliza la variable calculada effective_scope, sumando asi la excepcion otorgada. Esto asegura integridad en reportes comerciales y equidad en el pago salarial.*

### Controladores de vista multiplexados (views)
En lugar de crear un endpoint y un controlador para cada accion individual sobre las comisiones, el archivo *apps/human_resources/views.py* consolida el manejo de formularios mediante un solo controlador.

```python
@login_required
@require_POST
def commissions_action(request):
    action = request.POST.get('action')
    selected_routes = request.POST.getlist('selected_routes')

    if action == 'recalculate':
        # Delega al servicio para calculo
    elif action == 'close':
        # Delega al servicio para cierre
    elif action == 'export_data':
        # Retorna el response CSV
    elif action == 'send_closed':
        # Envia correo electronico
```
*Esta arquitectura permite agregar nuevas herramientas de gestion de multiples rutas (como aprobaciones o rechazos) simplemente agregando condiciones al enrutador, reduciendo la redundancia de consultas de seguridad y permisos de usuario.*

### Exportacion de archivos
La clase *CommissionsReport* procesa el armado y entrega de datos sin comprometer almacenamiento en servidor.

```python
def export_report_data(self, route_ids, month, year):
    count, csv_content = self._generate_csv_data(route_ids, month, year)
    response = HttpResponse(
        csv_content.encode('utf-8-sig'), 
        content_type='text/csv; charset=utf-8-sig'
    )
    response['Content-Disposition'] = f'attachment; filename="comisiones_{month}_{year}.csv"'
    return response
```
*Este fragmento explica como se inyecta el contenido de un buffer en memoria hacia una respuesta web directa. La codificacion utf-8-sig es critica, pues inserta la marca de orden de bytes (BOM) requerida por hojas de calculo populares para leer correctamente acentos y caracteres especiales sin alteraciones.*
