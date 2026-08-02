# Datall

> Plataforma ETL + Business Intelligence para el consumo masivo de información comercial y su conversión en insights accionables (dashboards, reportes y un asistente IA).

Datall **no es un ERP en producción**: aunque el repositorio contiene modelos detallados de ventas, productos con variantes/lotes, clientes con convenios, etc., la gran mayoría de esos módulos están definidos a nivel de esquema como una **base de conocimiento/roadmap** del dominio comercial. El sistema funciona hoy como una **plataforma de inteligencia de negocios alimentada por cargas masivas de datos** (ETL) que transforma archivos crudos (CSV/Excel) en registros limpios y los expone mediante dashboards, reportes descargables, cálculo de comisiones y un asistente conversacional con IA.

---

## ¿Qué resuelve?

El núcleo del problema es responder, para una red de distribución con rutas, gerencias (CEDIS) y clientes:

- ¿Cómo van las ventas hoy vs. la meta, por ruta, gerencia, línea, producto y cliente?
- ¿Qué clientes están en riesgo comercial (concentración, churn, inactividad)?
- ¿Cuál es la salud de la cartera por cobrar?
- ¿Qué tan desviada está la cuota por línea de producto?
- ¿Cuánto y cómo se le paga a un vendedor (cálculo de comisiones)?
- ¿Cómo transfiero stock entre CEDIS para mantener la cobertura?

Todo esto respetando la **visibilidad por jerarquía**: cada usuario solo ve la información de su equipo de trabajo (árbol de reportes del `Employee`).

---

## Arquitectura

### Stack técnico

| Capa            | Tecnología                                                                 |
|-----------------|----------------------------------------------------------------------------|
| Backend         | **Django 6.0.5** + **Python 3.12**                                         |
| Frontend        | **Tailwind CSS** (compilado) + **HTMX** + **ECharts** + **Lucide Icons**  |
| Base de datos   | **PostgreSQL 15** (prod) / **SQLite** (dev `DEBUG=True`)                  |
| Async / canales | **Django Channels** + **Daphne** + **Redis 7**                             |
| Almacenamiento  | **Cloudflare R2** (S3) en prod, **FileSystem** en dev                     |
| ETL             | **pandas** + **openpyxl** + modelo `Reference` (mapeo configurable)       |
| IA              | **DeepSeek API** (vía `openai` client compatible)                         |
| Despliegue      | **Docker** + **docker-compose** + **gunicorn** + **uvicorn workers**       |
| Email           | **Resend SMTP**                                                            |

### Principios de arquitectura (estrictos)

Definidos en `agents.md` y aplicados consistentemente en el código:

1. **Apps en `apps/`**, configuración global en `config/`. Cada app encapsula su dominio.
2. **Servicios orientados a objetos en `services/`**: toda la lógica de negocio vive en clases (no funciones sueltas), con **una responsabilidad por archivo** (SRP). Ej.: `SaleTransactionCRUD`, `CustomerBulk`, `CommercialRisk`, `SalesDashboard`.
3. **Visibilidad BI por jerarquía de empleados**: el filtro base de toda consulta es `Employee.get_reporting_tree_ids()`. Nunca se exponen datos fuera de ese árbol.
4. **ETL con `Reference`**: cualquier mapeo de un valor crudo del archivo a un valor válido en la BD pasa por la tabla `Reference` (modelo `module + field_context + key → reference`). Cero hardcodeos en transformaciones.

### Patrón de vistas

Las vistas (`views.py`) son **delgadas**: leen query params, llaman a un servicio, y devuelven un template (con render parcial HTMX si aplica). Toda la lógica está en `services/`.

```python
# Patrón típico de vista BI
@login_required
def sales_dashboard(request):
    allowed_routes = get_allowed_routes_for_user(request.user)
    transactions = SaleTransactionCRUD().read(allowed_routes, **filters)
    data = SalesDashboard(transactions, targets, ...).calculate_kpis()
    return render(request, template, context)
```

---

## Apps del proyecto

El proyecto se divide en **10 apps Django** con responsabilidades bien delimitadas:

### 1. `core` — Núcleo, auth, catálogos y motor ETL

Concentra el grueso del modelo de datos y la configuración transversal:

- **Auth/RBAC:** `User` (extiende `AbstractUser`), `Group`, `MenuSection`, `SystemModule` (menú dinámico por grupo).
- **Auditoría:** `DataHistory` (log genérico con `ContentType` + `Action` + `Result` + `metadata` JSON), `ActivityLogger` (service que escribe en él desde casi cualquier vista).
- **Configuración:** `Reference` (lookup table para mapeos ETL), `AppVersion`, `Novelty`.

**Utils críticos** (`apps/core/utils.py`):
- `get_reference(module, field_context, key, default)` → el ÚNICO punto de acceso a `Reference`.
- `get_allowed_routes_for_user(user)` → el ÚNICO punto de acceso al árbol de rutas del usuario.

**Context processors** (`apps/core/context_processors.py`):
- `module_permissions` → inyecta `sections` con módulos accesibles al usuario (alimenta el sidebar).
- `last_update` → muestra la fecha de la última carga de datos.
- `get_app_version`, `recent_novelties`.

> **Importante:** además de los modelos en `core/`, existen modelos "gemelos" con más detalle ERP en `sales/` y `customers/`. Ver la sección "Migración dual" más abajo.

### 2. `data_admin` — Centro de mando de ETL y gobierno de datos

Es la app desde donde se **orquesta la ingesta de datos** y se gobierna la plataforma.

- **Carga masiva genérica** (`upload_create`): recibe un archivo y un `ContentType` (modelo destino), y delega al servicio de bulk correspondiente.
- **Modelos soportados en carga masiva:**
  - `customer` → `apps/customers/services/customers_crud/customer_bulk.py` (`CustomersBulk`)
  - `product` → `apps/sales/services/products/products_bulk.py` (`ProductsBulk`, `StocksBulk`)
  - `saletransaction` → `apps/sales/services/sale_transactions/sales_transactions_bulk.py` (`SalesTransactionsBulk`)
  - `saletarget` → `apps/sales/services/sale_targets/sale_targets_bulk.py` (`SaleTargetsBulk`)
  - `accountsreceivable` → `apps/customers/services/accounts_receivable/accounts_receivable_crud.py` (`AR_bulk`)
- **Pipeline ETL estándar** (cada `*Bulk.clean()` y `*Bulk.create()`):
  1. Lee `.csv` o `.xlsx` con `pandas`.
  2. Renombra columnas según `Reference` (`field_context='column'`, `module='importaciones'`).
  3. Resuelve FKs dinámicamente.
  4. Mapea valores de catálogo (clase de producto, CEDIS) vía `Reference` (`field_context='value_*'`).
  5. Limpia strings, normaliza fechas (soporta `YYYY-MM-DD`, `DD/MM/YYYY`, `DD/MM/YY`), hace `ffill/bfill` si hay nulos.
  6. Inserta en `SaleTransaction`/`Customer`/etc. dentro de una `transaction.atomic()`.
  7. Devuelve `(ok, mensaje)`; el resultado se loguea en `DataHistory`.
- **Gobernanza:** `users` (gestión de usuarios y grupos), `groups` (asignación de módulos del sidebar a grupos), `activity` (consulta de `DataHistory`), `references` (administración de las reglas de mapeo), `novelties` (anuncios).
- **Auditoría:** casi cada vista en el sistema loguea a `DataHistory` con un `ActivityLogger.log_read/log_create/log_update/log_download/log_error`.

### 3. `business_intelligence` — Dashboards y reportes

El corazón de "insights a partir de la información". Tiene **12 vistas** (algunas con export a Excel/CSV), cada una con su servicio OOP:

| Vista                          | Servicio                                  | ¿Qué hace?                                                                                          |
|--------------------------------|-------------------------------------------|-----------------------------------------------------------------------------------------------------|
| `sales_dashboard`              | `SalesDashboard`                          | KPIs principales (venta neta, target, alcance, margen, unidades) + series de tiempo + 4 charts ECharts + top rutas/productos/clientes. |
| `routes_kpis`                  | `RoutesKpisService`                       | KPIs de una ruta específica.                                                                        |
| `warehouses_kpis`              | (template vacío)                          | Placeholder.                                                                                        |
| `products_kpis`                | (template vacío)                          | Placeholder.                                                                                        |
| `customers_kpis`               | `CustomersKpis` + `CustomerProfileBuilder` | Tabla de clientes con categorización (Diamante/Oro/AA/A/C), comparativos YoY, mes a mes, contribuciones. |
| `customer_kpis/{id}`           | (mismo)                                   | Perfil 360° de un cliente individual. Permite toggle de `opinion_leader`.                          |
| `commercial_risk`              | `CommercialRisk`                          | Métricas avanzadas: **IRC** (Índice de Riesgo Comercial), **Gini** (concentración), churn, inactividad, factor de crecimiento, volatilidad, sesgo. Foto trimestral + tendencia mensual. |
| `target_scope`                 | `TargetScopeService`                      | Alcance de objetivos por ruta × clase de producto. Export a Excel.                                  |
| `monthly_breakdown_by_warehouse` | `MonthlyBreakdownByWarehouse`            | Desglose mensual por gerencia (CEDIS) y línea de producto.                                          |
| `collections`                  | `Collections`                             | Cartera de cuentas por cobrar con KPIs de antigüedad (al corriente, 15, 30, 60, +60).              |
| `sales_breakdown`              | `SalesBreakdownService`                   | Tabla pivote multidimensional (cliente×línea×producto, gerencia×línea×producto, etc.) con paginación. |
| `unique_customers`             | `UniqueCustomersService`                  | Conteo de clientes únicos compradores en un período.                                                |
| `sale_targets`                 | (servicio de carga, no dashboard)         | Listado de objetivos de venta.                                                                      |

> Todas las vistas BI respetan el filtro `get_allowed_routes_for_user(user)` y casi todas registran el acceso en `DataHistory` con los filtros aplicados (auditoría de qué datos vio cada quién).

### 4. `data_assistant` — Capa de IA sobre los reportes

Dos productos de IA distintos:

- **`DataAssistant`** (`data_assistant/data_assistant.py`): análisis **one-shot** de un reporte. La vista recibe `?report_type=commercial_risk` (u otros), consulta un registro en `PROMPTS_REGISTRY` (`apps/data_assistant/prompts/view_rules.py`), arma el contexto vía `data_builders.py` y envía todo a DeepSeek con un prompt muy estructurado (sección de hallazgos, glosario, etc.). Devuelve HTML estilizado.
- **`DatallAssistantService`** (`datall_assistant/datall_assistant_service.py`): **chat conversacional** con memoria persistente (cada thread es un JSON en R2 con `assistant_threads/{thread_id}.json`). Usa tool-calling de DeepSeek y tiene un `tool_registry.json` con herramientas que ejecutan queries SQL/léidas de modelos.

### 5. `sales` — Módulo comercial

- Productos y catálogo: `products/`, `product/{id}` con export a Excel.
- **Transferencias de stock** (`stock_transfers` + `StockTransferCalculatorService`): simulador que calcula cuánto mover entre dos CEDIS según ventas históricas, cobertura objetivo y clase de producto.
- **Transacciones de venta** (`sale_transactions`): listado filtrable con KPIs agregados (neto, bruto, margen, unidades) y export a Excel.
- **Calculadora de objetivos** (`sale_targets_calculator`): toma una ruta origen, una destino, ajusta metas según qué clientes/productos se mueven, y devuelve una propuesta de nuevas cuotas. Modos: "remove", "keep", "growth". Reglas: `exact`, `proportional`, etc.
- Una única vista con prefijo `erp` (`sale_list_view`): el único punto que apunta a los modelos ERP detallados (`Sale`/`SaleLine`).

### 6. `customers` — Clientes y convenios

- `customers_crud` (CRUD básico, lectura filtrable por rutas/regiones/warehouses).
- `customer_agreements` (motor completo de convenios con beneficios, metas por clase de producto, períodos de evaluación, validaciones de margen mínimo por cliente×clase, penalizaciones, evaluación batch). Tiene flujo con HTMX para previsualizar, validar margen y guardar.

### 7. `human_resources` — Personal, organigrama, comisiones y evaluación

- **Empleados:** CRUD con asignación a `Position`, `BusinessUnit`, `Warehouse`, manager (jerarquía recursiva).
- **Organigrama:** endpoint `get_org_chart_data` que devuelve un árbol JSON para un visor visual.
- **Comisiones:** motor completo (`apps/human_resources/services/comissions/comissions.py`):
  - `CommissionProfile` con `CommissionTier` (alcance mínimo + clases completadas → multiplicador + bono extra).
  - `RouteCommissionSetup` para asignar perfiles a rutas en ventanas de tiempo.
  - `RouteCommissionException` (tolerancias especiales para empleados nuevos).
  - `CommissionSettlement` con **snapshots inmutables** del cálculo y `manual_adjustment` para ajustes administrativos.
  - `commissions_report` y `commissions_report/{id}` para consultar cierres por período.
- **Departamentos / Puestos / Habilidades:** catálogos con skills required por puesto y formularios anidados.
- **Monitoring forms:** encuestas configurables (por nivel jerárquico o puesto específico) con preguntas tipadas (texto, número, %, escala 1-5, sí/no, archivo) y envíos por período.

### 8. `accounting` — Solo catálogos fiscales mexicanos

Sin vistas. Define choices de:
- `TaxRegimeChoices` (códigos del SAT 601–626).
- `PaymentFormChoices` (códigos CFDI 01–99).
- `PeriodicityChoices` (1d, 1w, 2w, 1m, ..., 1y) con un método `get_relativedelta()` que las traduce a objetos `relativedelta` y `get_next_date()`.

### 9. `inventory` — Placeholder

Tiene `models.py` muy completo (ProductVariant, Batch, Stock, StockMovement, Attribute, Warehouse con tipos) pero `views.py` está vacío. Es la **base de conocimiento** del dominio inventario en el roadmap.

### 10. `marketing` — Placeholder

`models.py`, `views.py` y `urls.py` vacíos.

---

## Migración dual: `core` vs. ERP detallado

Hay una **duplicidad intencional de modelos** que vale la pena entender:

| Entidad        | Versión "BI plana" (en `core/`)                          | Versión "ERP detallada" (en `sales/`, `customers/`, `inventory/`) |
|----------------|----------------------------------------------------------|-------------------------------------------------------------------|
| Cliente        | `core.Customer` (campos mínimos)                         | `customers.Customer` (con `tax_entities`, `delivery_addresses`, `contacts` como JSON validados por JSON Schema, `opinion_leader`, asignaciones con rango de fechas, márgenes por clase) |
| Producto       | `core.Product` + `core.ProductClass` + `core.ProductCategory` | `inventory.Product` + `inventory.ProductVariant` + `inventory.Batch` + `inventory.Attribute` + `inventory.VariantAttribute` (con propiedades JSON, variantes con atributos múltiples, lotes con caducidad) |
| Venta          | `core.SaleTransaction` (una fila por línea de venta)     | `sales.Sale` + `sales.SaleLine` + `sales.SaleLineTax` (estados, encabezado con subtotal/descuento/impuestos, múltiples líneas, impuestos por línea) |
| Almacén        | `core.Warehouse` + `core.Stock`                          | `inventory.Warehouse` (con tipos) + `inventory.Stock` + `inventory.StockMovement` + `inventory.Batch` |
| Empleado       | `core.Employee` (con `get_reporting_tree_ids`)           | `human_resources.Employee` (con `BusinessUnit`, jerarquía, contract_type, tax_regime, payment_form) |
| Ruta           | `core.Route` + `core.RouteAssignment`                    | `sales.Route` + `sales.RouteAssignment` + `sales.UserRouteAccess` + `sales.RouteWarehouseLogistic` |
| Puesto         | `core.Position`                                          | `human_resources.Position` (con `hierarchy_level`, `reports_to`, skills) |

**Interpretación práctica:**

- La **BI corre 100% sobre las tablas planas de `core/`** (`SaleTransaction`, `Customer`, `Product`, `Stock`, `AccountsReceivable`).
- Los **modelos ERP detallados** están listos como esquema y como destino futuro de operaciones transaccionales (la única vista ERP funcional hoy es `sales/sale_list_view`).
- Los servicios de bulk importan datos a las tablas planas, lo que permite que el sistema funcione aunque los modelos ERP no estén poblados.

---

## Seguridad y visibilidad

- **Autenticación:** Django `auth` con modelo `User` custom (`apps.core.User`).
- **Visibilidad BI:** `get_allowed_routes_for_user(user)` se aplica en TODA vista que muestra datos comerciales. La regla es:
  - `is_superuser` → ve todo.
  - Grupo `acceso global` o flag en `Reference(field_context='allowed_routes')` → ve todo.
  - Resto → se calcula su árbol de reportes (`Employee.get_reporting_tree_ids()`), se buscan las `RouteAssignment` activas y se devuelven esas rutas.
- **RBAC del menú:** `SystemModule.allowed_groups` define qué grupos ven qué módulo. El sidebar se renderiza dinámicamente vía context processor `module_permissions`.
- **CSRF:** manejo custom con redirección HTMX-aware en CSRF failure.
- **Proxy SSL:** `SECURE_PROXY_SSL_HEADER` configurado para despliegue tras proxy.
- **Storage seguro:** medios y estáticos en R2 (S3) en producción, nunca expuestos localmente.

---

## Frontend

- **CSS:** Tailwind compilado en build (`tailwindcss -i static/src/input.css -o static/css/output.css --minify`) **dentro del Dockerfile** con `pytailwindcss`.
- **Tema:** variables CSS con `oklch` (definidas en `core/templates/base.html`).
- **HTMX:** interacciones parciales en listados, formularios y filtros (carga perezoza de partials como `partials/*_rows.html`).
- **ECharts:** todas las visualizaciones BI (línea, barras, pie, heatmap, etc.). `echarts-stat` registrado para clustering.
- **Marked.js:** para renderizar el output markdown del asistente IA.
- **Reglas estrictas de iconos:** solo se permite un set cerrado de íconos Lucide (definido en `agents.md`).
- **Impresión:** estilos `@media print` que limpian la UI y dejan solo los charts y tablas en formato A4 horizontal.

---

## Puesta en marcha

### Variables de entorno (`.env`)

```
DEBUG=True|False
SECRET_KEY=...
DEEPSEEK_API_KEY=...

DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=...

REDIS_URL=redis://127.0.0.1:6379/0

R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...
R2_ENDPOINT_URL=...

RESEND_API_KEY=...
```

### Modo desarrollo

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
# DEBUG=True usa SQLite (db.sqlite3) y FileSystem storage.
```

### Modo producción (Docker)

```bash
docker compose up --build
# Levanta PostgreSQL, Redis y la app (gunicorn + uvicorn workers).
# El Dockerfile compila Tailwind y recolecta estáticos a R2.
```

---

## Estructura de directorios

```
datall/
├── apps/
│   ├── core/                  # Núcleo: auth, modelos del dominio, RBAC, auditoría, Reference
│   │   ├── models.py          # (40 KB) — User, SystemModule, Customer, Product, SaleTransaction, Reference, etc.
│   │   ├── utils.py           # get_reference(), get_allowed_routes_for_user()
│   │   ├── context_processors.py
│   │   ├── services/          # users.py
│   │   └── templates/         # base.html, registration/, errors/, app_versions/, users/, docs/
│   │
│   ├── data_admin/            # ETL central, gobierno de datos
│   │   ├── views.py           # upload_create (orquesta bulk services), users, groups, activity
│   │   └── services/
│   │       ├── data_cleaning/cleaner.py
│   │       ├── data_history/data_history_crud.py  # ActivityLogger
│   │       ├── groups/groups_crud.py
│   │       └── users/users_crud.py
│   │
│   ├── business_intelligence/ # Dashboards y reportes
│   │   ├── views.py           # 12 vistas BI
│   │   ├── services/          # Un subdirectorio por vista/reporte
│   │   │   ├── sales_dashboard/sales_dashboard.py
│   │   │   ├── commercial_risk/commercial_risk.py
│   │   │   ├── customers_kpis/customers_kpis.py
│   │   │   ├── routes_kpis/routes_kpis.py
│   │   │   ├── collections/collections.py
│   │   │   ├── target_scope/target_scope.py
│   │   │   ├── monthly_breakdown_by_warehouse/monthly_breakdown_by_warehouse.py
│   │   │   ├── sales_breakdown/sales_breakdown.py
│   │   │   └── unique_customers/unique_customers.py
│   │   └── templates/business_intelligence/
│   │
│   ├── data_assistant/        # IA sobre los reportes
│   │   ├── views.py           # data_assistant (one-shot) + datall_assistant (chat)
│   │   ├── prompts/           # view_rules.py (PROMPTS_REGISTRY), system_prompts.py
│   │   └── services/
│   │       ├── data_assistant/{data_assistant.py, data_builders.py}
│   │       └── datall_assistant/{datall_assistant_service.py, sales_analytics_service.py, tools.py, tool_registry.json}
│   │
│   ├── sales/                 # Productos, transacciones, transferencias, objetivos
│   │   ├── views.py           # products, stock_transfers, sale_transactions, sale_targets_calculator
│   │   └── services/
│   │       ├── products/{products_crud.py, products_bulk.py}
│   │       ├── sale_transactions/{sale_transactions_crud.py, sales_transactions_bulk.py}
│   │       ├── sale_targets/{sale_targets_crud.py, sale_targets_bulk.py, calculator.py}
│   │       └── stock_transfers/calculator.py
│   │
│   ├── customers/             # Clientes y convenios comerciales
│   │   ├── views.py           # customer_agreements
│   │   └── services/
│   │       ├── customers_crud/{customers_crud.py, customer_bulk.py}
│   │       ├── accounts_receivable/accounts_receivable_crud.py
│   │       └── customer_agreements/customer_agreements.py
│   │
│   ├── human_resources/       # Personal, organigrama, comisiones, monitoring
│   │   ├── views.py           # employees, org_chart, commissions, departments, positions, skills, monitoring
│   │   └── services/
│   │       ├── employees/{employees_crud.py, employees_service.py}
│   │       ├── comissions/comissions.py
│   │       ├── departments.py, positions.py, monitoring.py
│   │
│   ├── accounting/            # Choices fiscales (catálogo SAT, periodicidades)
│   ├── inventory/             # Placeholder (modelos detallados listos)
│   └── marketing/             # Placeholder
│
├── config/
│   ├── settings.py            # DEBUG/PostgreSQL/R2/CSRF/HTMX/Channels/email/INSTALLED_APPS
│   ├── urls.py                # Enrutador raíz + reset password + include de cada app
│   ├── asgi.py / wsgi.py
│
├── static/                    # CSS, JS y assets (Tailwind compilado en static/css/output.css)
├── templates/                 # templates globales (admin/)
├── media/                     # Archivos subidos (dev)
├── docker-compose.yml         # PostgreSQL + Redis + Web
├── Dockerfile                 # Build con Tailwind + gunicorn + uvicorn
├── agents.md                  # Reglas de arquitectura y estilo (la "constitución" del proyecto)
├── manage.py
└── requirements.txt
```

---

## Flujo típico de uso

1. **Carga de datos crudos** (Admin de datos) → el usuario sube CSVs de ventas/clientes/cobranza desde `data_admin/uploads/upload_create/`.
2. **Limpieza y mapeo** (servicio `*Bulk.clean`) → pandas + `Reference` traducen los valores crudos a las claves válidas en la BD.
3. **Inserción** (`*Bulk.create`) → escrituras masivas transaccionales.
4. **Visualización** (BI) → cada usuario ve solo las rutas de su equipo. Filtra por gerencia, región, línea, producto, fecha. Los charts son interactivos.
5. **Análisis con IA** → desde cualquier reporte, el usuario puede pedir un análisis al asistente (one-shot o chat).
6. **Exportación** → cada reporte permite descargar a Excel o CSV.
7. **Cálculo de comisiones** (RR.HH.) → sobre las ventas reales, aplicando perfiles, tiers y excepciones por ruta.
8. **Auditoría** (Admin de datos) → cada acción queda registrada en `DataHistory` con su usuario, módulo, filtros y resultado.

---

## Lo que el proyecto **NO** es (a día de hoy)

- **No es un ERP transaccional en producción.** Los modelos ERP detallados (`Sale`, `SaleLine`, `ProductVariant`, `Batch`, `StockMovement`) están definidos como esquema, pero la única vista que los consume es `sales/sale_list_view`. El sistema funciona sobre las tablas planas `core.SaleTransaction`, `core.Customer`, `core.Product`, etc.
- **No es una herramienta de captura de ventas en campo.** No hay app móvil, no hay POS.
- **`inventory` y `marketing` son placeholders** (modelos vacíos / casi vacíos).
- **`accounting`** solo expone catálogos de choices (régimen fiscal, forma de pago, periodicidad); no tiene vistas ni lógica.

---

## Documentos relacionados

- `config/settings.py` — Configuración completa (DB, R2, email, context processors, INSTALLED_APPS).
- `config/urls.py` — Mapa de rutas raíz.
- `apps/core/models.py` — Catálogo de modelos del dominio "plano" sobre el que corre toda la BI.
- `apps/data_admin/views.py` (función `upload_create`) — Orquestador ETL.
- `apps/business_intelligence/views.py` — Las 12 vistas BI.
- `apps/core/utils.py` — `get_reference`, `get_allowed_routes_for_user` — los dos helpers más críticos del sistema.
