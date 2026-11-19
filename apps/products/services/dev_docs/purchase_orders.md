##### Documentación: órdenes de compra

---

1. Descripción
2. Casos de uso regulares
3. Primeros pasos
4. Configuración en Reference
5. Configuración de almacenes y datos base
6. Configuración de cada producto y formatos
7. Cómo crear una orden de compra
8. Seguimiento, estatus y exportación

---

###### Descripción
Este módulo está dedicado a la planeación, cálculo, generación y seguimiento de órdenes de compra para reabastecimiento de centros de distribución (CEDIS). A partir del historial de ventas, las existencias físicas actuales y el inventario en tránsito, proyecta las unidades necesarias para cubrir una meta de meses de inventario, redondea automáticamente cada partida a múltiplos cerrados de tarima, estima el peso neto, el peso bruto con madera de tarimas y la cantidad de camiones requeridos, y controla el flujo operativo de la orden desde su creación hasta su recepción.

---

###### Casos de uso regulares
1. Proyección de compras de importación o locales para uno o varios CEDIS con una cobertura objetivo en meses.
2. Planeación separada por CEDIS (asignando manualmente o por sugerencia las unidades de cada almacén antes de consolidar tarimas) o planeación acumulada global.
3. Cálculo logístico de tarimas cerradas, cajas o bultos equivalentes, peso en libras y camiones estimados.
4. Emisión de órdenes de compra con folio único (manual o automático) y descarga en formato Excel bilingüe (español e inglés) con fórmulas dinámicas.
5. Control administrativo del avance de la orden (Realizada, Confirmada, En tránsito y Completada) con bitácora de auditoría.

---

###### Primeros pasos
Antes de generar una orden de compra por primera vez, es necesario verificar tres requisitos previos en el sistema:
1. Tener los parámetros logísticos y permisos configurados en Referencias.
2. Contar con los CEDIS físicos, los almacenes de tránsito vinculados y el historial de ventas e inventario cargado.
3. Tener correctamente configurados el estado activo, la clase y los datos de peso y empaque de cada producto en el catálogo.

---

###### Configuración en Referencias
Los parámetros generales y permisos se administran en el modelo Reference (accesible desde el panel de administración en Core > Referencias).

1. Parámetros logísticos de órdenes (obligatorios para cálculos de peso y camiones)
Se registran con el campo context igual a parametro_logistica_ordenes (no requieren submódulo ni content_type). Si no existen en la base de datos, el sistema los crea automáticamente la primera vez con sus valores predeterminados:

- key: capacidad_camion_lbs
  Formato: número decimal mayor a 0 (predeterminado: 44000). Si el valor es menor o igual a 0 o inválido, el sistema usa 44000.
  Significado: capacidad máxima de carga de un camión en libras. Se utiliza para calcular el estimado de camiones requeridos.

- key: peso_tarima_madera_lbs
  Formato: número decimal mayor o igual a 0 (predeterminado: 75). Si el valor es negativo o inválido, el sistema usa 75.
  Significado: peso en libras de cada tarima de madera vacía. Se multiplica por el total de tarimas y se suma al peso neto del producto para obtener el peso bruto total.

- key: tarimas_maximas_camion
  Formato: número entero mayor a 0 (predeterminado: 22). Si el valor es menor o igual a 0 o inválido, el sistema usa 22.
  Significado: cantidad máxima de tarimas por camión mostrada como referencia operativa en la pantalla de creación.

Ejemplo:
| context                     | key                    | value |
|-----------------------------|------------------------|-------|
| parametro_logistica_ordenes | capacidad_camion_lbs   | 44000 |
| parametro_logistica_ordenes | peso_tarima_madera_lbs | 75    |
| parametro_logistica_ordenes | tarimas_maximas_camion | 22    |


2. Permisos de acceso para gestionar órdenes
<!-- El sistema separa los permisos en dos capas independientes que trabajan juntas

Capa 1 - Visibilidad en el menú (modelo Submodule):
En Core > Submódulos se configuran los campos allowed_groups y allowed_users. Esto controla únicamente qué pantallas aparecen en el menú lateral del usuario. Ocultar un submódulo del menú NO quita los permisos internos si el usuario pertenece a un grupo con acceso global.

Capa 2 - Permisos operativos internos (modelo Reference):
Los usuarios marcados como is_staff o is_superuser tienen acceso completo automático. Para cualquier otro usuario, cada módulo/servicio evalúa si tiene permiso total (crear, editar, cambiar estatus, eliminar o ver información de otros usuarios) consultando Reference según estos campos:
- context: indica qué módulo o servicio lee la regla.
- key: etiqueta descriptiva interna (por ejemplo acceso_total o rol_operativo). El evaluador de permisos no filtra por key, sirve solo para identificar la regla.
- value: debe coincidir exactamente con el nombre del Grupo de Django (auth.Group) al que pertenece el usuario.
- content_type y submodule: deben dejarse vacíos para reglas de permisos. -->

Para el módulo de órdenes de compra, el sistema revisa si alguno de los grupos del usuario aparece en Referencias.value bajo alguno de estos context:
- acceso_total_ordenes_compra (exclusivo de órdenes de compra)
- ordenes_compra (exclusivo de órdenes de compra)
- logistica (permiso operativo logístico de órdenes de compra)
- acceso_total_inventario (también aplica a inventario/stock)
- acceso_total_productos (también da acceso total al catálogo de productos)
- acceso_total (comodín global que otorga acceso total en TODOS los servicios del sistema)

Configuración estándar de ejemplo en Referencias (content_type y submodule vacíos):

| context                     | key          | value          | Qué pasa para el usuario con dicho rol (grupo) |
|-----------------------------|--------------|----------------|-------------------------------------------------|
| acceso_total_ordenes_compra | acceso_total | compras        | Puede crear órdenes de compra, avanzar su estatus y exportar Excel. No obtiene acceso total a Productos, Ventas, Clientes ni Usuarios. |
| ordenes_compra              | acceso_total | ordenes_compra | Mismo alcance que acceso_total_ordenes_compra: opera únicamente Órdenes de compra sin permisos de edición en otros módulos. |
| logistica                   | acceso_total | logistica      | Permite crear y gestionar órdenes de compra y su seguimiento operativo. No otorga acceso total a Productos, Ventas ni Usuarios. |
| acceso_total_inventario     | acceso_total | inventario     | Tiene acceso total a Inventario/Existencias (Stock) y también puede crear y gestionar Órdenes de compra. No edita catálogo de Productos ni Ventas. |
| acceso_total_productos      | acceso_total | productos      | Tiene acceso total a Productos (crear, editar y carga masiva), a Inventario/Existencias y a Órdenes de compra. No tiene acceso total a Ventas ni Usuarios. |
| acceso_total_ventas         | acceso_total | facturacion    | Tiene acceso total únicamente en Ventas / Transacciones. Si ve Órdenes de compra en el menú solo podrá consultarlas, sin poder crear ni cambiar estatus. |
| acceso_total                | acceso_total | acceso total   | Comodín global: tiene acceso total en TODOS los servicios del sistema (Usuarios, Clientes, Productos, Ventas, Órdenes de compra, etc.), incluso si ocultas módulos en Submódulos. |

Nota sobre key, value y combinaciones de roles:
- El evaluador de permisos no filtra por key; únicamente verifica si el nombre del Grupo del usuario coincide exactamente con value.
- Si un rol específico (por ejemplo facturacion) necesita acceso total en dos módulos concretos sin heredar permisos globales sobre todo el sistema, NO lo agregues en context = acceso_total. En su lugar, crea el grupo, habilita solo sus pantallas en Core > Submódulos (allowed_groups) y agrega en Core > Referencias una fila por cada módulo requerido con el mismo value:
  - context = acceso_total_ventas, key = acceso_total, value = facturacion
  - context = acceso_total_ordenes_compra, key = acceso_total, value = facturacion
De esta forma el usuario solo verá esos submódulos en el menú y solo tendrá permisos totales en Ventas y Órdenes de compra.

3. Mapeo para carga masiva de productos (opcional, solo si se importa catálogo por Excel o CSV)
Si el catálogo o los datos de empaque se cargan masivamente desde un archivo CSV, XLSX o XLS:
- Mapeo de columnas: asignar submodule al submódulo con url_name core:upload_options_list_view, content_type igual a products | product, context igual a columna, key igual al nombre exacto de la columna en el archivo (en minúsculas) y value igual al nombre del campo destino (por ejemplo: id, name, product_class, weight, pieces_per_box, boxes_per_pallet, is_active).
  Nota: sin necesidad de darlos de alta en Reference, el cargador de productos ya reconoce automáticamente los encabezados peso, peso_lbs y weight_lbs para weight; piezas_por_caja, piezas_caja y pzas_caja para pieces_per_box; y cajas_por_tarima, cajas_por_pallet, bultos_por_tarima y tarima para boxes_per_pallet.
- Mapeo de valores de clase de producto: usar submodule core:upload_options_list_view, content_type igual a products | productclass y context igual a valor_clase_producto, colocando en key el texto del archivo y en value el id de la ProductClass.

---

###### Configuración de almacenes y datos base
El módulo toma la información comercial y logística de los modelos Warehouse, SaleTransaction y Stock:

1. Centros de distribución elegibles (Warehouse)
En el selector de CEDIS solo aparecen los registros de Warehouse cuyo campo warehouse_type sea warehouse, excluyendo automáticamente el identificador snc.

2. Almacenes en tránsito
Para que el calculador descuente el inventario que ya viene en camino, debe existir un Warehouse con warehouse_type igual a transfer cuyo id siga el formato t_ seguido del id del CEDIS en minúsculas. Por ejemplo, si el CEDIS tiene id gdl, su almacén en tránsito debe tener id t_gdl. Si no existe la coincidencia exacta t_ más id, el sistema busca como respaldo cualquier almacén de tipo transfer cuyo id contenga el id del CEDIS.

3. Ventas y existencias
- Ventas del periodo: se suman las cantidades de SaleTransaction filtradas por producto, CEDIS seleccionados y fecha de venta dentro del rango evaluado.
- Stock físico y tránsito: se suman las cantidades de Stock por producto en los CEDIS seleccionados (stock físico) y en sus almacenes transfer asociados (en tránsito).

---

###### Configuración de cada producto y formatos
Cada producto se puede configurar manualmente desde el formulario de creación o edición de producto, desde el panel de administración, o mediante carga masiva. Los campos relevantes para órdenes de compra y su formato son:

1. Identificador (id)
- Formato: texto único de máximo 255 caracteres. Obligatorio.
- Regla: en el formulario web se normaliza automáticamente a mayúsculas y sin espacios alrededor. Representa la clave o SKU del producto.

2. Nombre o descripción (name)
- Formato: texto de máximo 255 caracteres. Obligatorio en el formulario web.
- Uso: nombre comercial mostrado en las tablas, detalles y archivo Excel.

3. Clase de producto (product_class)
- Formato: relación con ProductClass (clave de clase, por ejemplo dmd, nat, tow, care, cv u otr).
- Uso: permite filtrar los productos incluidos en la proyección y agrupa tanto las filas como los subtotales de peso y tarimas en el Excel exportado. Si en carga masiva un producto nuevo no especifica clase, el sistema asigna otr (o la primera clase disponible).

4. Peso unitario en libras (weight)
- Formato: número decimal en libras (lbs) con hasta 4 decimales (ejemplo: 0.0000 o 12.3500), mayor o igual a 0. Predeterminado: 0.0000. En carga masiva el sistema limpia símbolos $, comas y espacios antes de convertirlo a número.
- Uso: peso de una sola pieza o unidad individual. Al multiplicarse por las unidades ordenadas determina el peso neto de la partida y la estimación de camiones.

5. Piezas por caja o bulto (pieces_per_box)
- Formato: número entero positivo mayor o igual a 1. Predeterminado: 1. Si se ingresa vacío o menor a 1, se guarda como 1.
- Uso: indica cuántas unidades individuales contiene una caja o bulto.

6. Cajas o bultos por tarima (boxes_per_pallet)
- Formato: número entero positivo mayor o igual a 1. Predeterminado: 1. Si se ingresa vacío o menor a 1, se guarda como 1.
- Uso: indica cuántas cajas integran una tarima cerrada.

7. Unidades por tarima (campo calculado automáticamente)
- Fórmula: pieces_per_box x boxes_per_pallet.
- Regla importante: la orden de compra siempre redondea hacia arriba a múltiplos cerrados de esta cantidad. Si ambos campos quedan en 1, el sistema pedirá piezas sueltas de 1 en 1 en lugar de tarimas reales.

8. Activo en catálogo (is_active)
- Formato: booleano (verdadero o falso). Predeterminado: verdadero.
- Regla importante: únicamente los productos con is_active verdadero participan en la calculadora de órdenes de compra. Además, un producto activo solo se muestra en la tabla de resultados si tiene ventas mayores a 0, stock físico mayor a 0 o inventario en tránsito mayor a 0 para los CEDIS y periodo seleccionados.

9. Campos complementarios del catálogo
- Código de barras (barcode): texto opcional, máx. 255 caracteres.
- Unidad de medida (unit_of_measure): texto opcional, máx. 255 caracteres (por ejemplo PZA, CAJA, FRASCO). Si está vacío se asume PIEZA.
- Costo unitario (cost): número decimal con hasta 4 decimales, mayor o igual a 0.
- Precio de venta (price): número decimal con hasta 2 decimales, mayor o igual a 0.
Nota: estos cuatro campos son informativos dentro del catálogo y no alteran el cálculo de unidades ni el redondeo a tarimas.

---

###### Cómo crear una orden de compra
El proceso se realiza en la vista de Nueva orden de compra y se divide en cuatro pasos.

Paso 1: Definir los parámetros de evaluación y calcular la vista previa
En la sección superior se configuran los criterios de cálculo:

1. Origen de la orden (origin_type)
- Valores permitidos: Importación (importacion) o Local (local).
- Significado: clasificación logística del tipo de abastecimiento (internacional o nacional) para seguimiento y filtrado.

2. Modo de cálculo (grouping_mode)
- Valores permitidos: Separado por CEDIS (separado, opción predeterminada) o Acumulado (acumulado).
- Significado en modo Separado: evalúa ventas, promedio mensual, stock físico y tránsito de forma independiente para cada CEDIS seleccionado. La sugerencia total del producto es la suma de las necesidades positivas de cada CEDIS, y la tabla te permite editar las unidades pedidas por cada almacén individual antes de consolidar tarimas.
- Significado en modo Acumulado: suma las ventas, existencias físicas y tránsito de todos los CEDIS seleccionados en un solo cálculo global. La tabla no desglosa cajas editables por almacén y permite editar directamente el total de unidades requeridas del producto.

3. Periodo de evaluación (start_date y end_date)
- Formato: mes y año en formato YYYY-MM (por ejemplo 2026-06 y 2026-10). De forma predeterminada, la pantalla precarga los últimos 5 meses calendario cerrados.
- Significado: rango histórico usado para sumar las ventas y calcular el promedio mensual. El sistema toma desde el día 1 del mes inicial hasta el último día calendario del mes final y divide las ventas entre el número de meses completos del intervalo. La fecha inicial debe ser anterior o igual a la final.

4. Cobertura objetivo en meses (coverage_months)
- Formato: número decimal mayor o igual a 0.1, en pasos de 0.1 (predeterminado: 1.0).
- Significado: cantidad de meses de venta promedio que se busca tener cubiertos en inventario considerando stock físico y tránsito. Si ya calculaste la orden y modificas este campo, se actualiza automáticamente la columna Meta (meses) de todos los productos mostrados.

5. Nivel de rotación (rotation_levels)
- Formato: selector opcional.
- Significado: filtra los productos según su volumen total de ventas acumuladas en el periodo evaluado:
  - Todos los niveles (vacío): no filtra por rotación.
  - Alta rotación (1): más de 50 unidades vendidas en el periodo.
  - Media rotación (2): entre 10 y 50 unidades vendidas en el periodo.
  - Baja rotación (3): menos de 10 unidades vendidas en el periodo.

6. Folio (custom_folio, opcional)
- Formato: texto único de máximo 50 caracteres (se guarda en mayúsculas).
- Significado: identificador de la orden de compra. Si escribes uno personalizado, el sistema valida que no exista otra orden con ese folio. Si lo dejas en blanco, genera uno automáticamente con el formato YYYYMMDD_UUID de 8 caracteres hexadecimales (por ejemplo 20261118_A1B2C3D4).

7. Notas u observaciones (notes, opcional)
- Formato: texto libre de máximo 1000 caracteres.
- Significado: comentarios operativos o referencias de carga que quedan registrados en la orden y en el evento de creación dentro de la bitácora.

8. Centros de distribución (warehouses)
- Formato: casillas de verificación (todos los CEDIS elegibles aparecen marcados por defecto). Obligatorio seleccionar al menos uno.
- Significado: define qué almacenes aportan ventas, stock físico y tránsito (t_ más id) al cálculo, y qué CEDIS quedan asociados a la orden.

9. Clases de producto (product_classes)
- Formato: casillas de verificación (por defecto vienen preseleccionadas las clases dmd, nat, tow, care y cv). Opcional: si no se selecciona ninguna, el sistema incluye todas las clases activas.
- Significado: limita el cálculo a las familias o líneas de productos marcadas.

Una vez llenos estos campos, haz clic en Calcular orden. Esto muestra el resumen y la tabla interactiva sin guardar todavía la orden en la base de datos.

Paso 2: Revisar el resumen estimado de la orden
Arriba de la tabla aparecen cuatro tarjetas informativas que se actualizan en tiempo real conforme editas cantidades en la tabla:
- Tarimas estimadas: total de tarimas cerradas a pedir y su equivalente en cajas o bultos.
- Unidades ordenadas: suma de unidades finales en tarimas cerradas, junto con las unidades requeridas originales antes del redondeo (req.).
- Peso neto producto: peso total de la mercancía en libras (sin incluir madera de tarimas).
- Peso bruto c/tarimas: peso neto del producto más el peso de las tarimas de madera (total de tarimas x peso_tarima_madera_lbs), junto con los camiones estimados (peso bruto / capacidad_camion_lbs).

Paso 3: Revisar y ajustar el desglose por producto
Los productos aparecen agrupados por clase de producto y ordenados de mayor a menor venta. Significado de cada columna:
- Producto: clave SKU, nombre y ficha de empaque (piezas por caja x cajas por tarima = unidades por tarima y peso unitario en libras).
- Ventas (Nm): unidades vendidas acumuladas durante los N meses evaluados en los CEDIS seleccionados.
- Prom. mensual: venta promedio mensual (Ventas / meses del periodo).
- Stock físico: existencia física disponible en los CEDIS seleccionados.
- En tránsito: inventario disponible en los almacenes de transferencia t_ asociados a los CEDIS seleccionados.
- Cobertura actual: porcentaje actual de inventario respecto al consumo promedio mensual, calculado como ((Stock físico + En tránsito) / Prom. mensual) x 100. Si el promedio mensual es 0 y existe inventario o tránsito, muestra 100.0%; si no hay ventas ni existencias, muestra 0.0%.
- Meta (meses): campo numérico editable por producto (inicia igual que Cobertura objetivo). Al editarlo, recalcula las unidades sugeridas del producto con la fórmula:
  Sugerencia = máximo entre 0 y el redondeo entero de ((Prom. mensual x Meta) - Stock físico - En tránsito).
  En modo Separado aplica esta fórmula por cada CEDIS y suma los resultados.
- Columnas por CEDIS (visibles únicamente en modo Separado): campo numérico entero editable por cada almacén seleccionado para ajustar manualmente cuántas unidades solicitar para ese CEDIS. Debajo del campo muestra S (stock físico del CEDIS), T (en tránsito del CEDIS) y P (promedio mensual del CEDIS).
- Uds. requeridas: total de unidades solicitadas antes de ajustar a tarima cerrada. En modo Separado es de solo lectura y suma automáticamente las cantidades capturadas en las columnas de CEDIS. En modo Acumulado es editable directamente.
- Uds. / tarima: cantidad de piezas que conforman una tarima cerrada (pieces_per_box x boxes_per_pallet).
- Tarimas: tarimas cerradas calculadas redondeando hacia arriba: ceil(Uds. requeridas / Uds. por tarima). Si Uds. requeridas es 0, resulta en 0 tarimas.
- Cajas / Bultos: equivalente en cajas de las tarimas resultantes (Tarimas x boxes_per_pallet).
- Uds. ordenadas: cantidad final de piezas que se pedirán en múltiplos de tarima (Tarimas x Uds. por tarima).
- Peso total (lbs): peso neto total de la partida (Uds. ordenadas x weight).

Paso 4: Generar y guardar la orden de compra
Cuando las cantidades sean correctas, haz clic en Generar orden de compra.
- El sistema valida nuevamente los parámetros y toma los valores editados por CEDIS (en modo Separado), por unidades requeridas (en modo Acumulado) y por cobertura individual.
- Cualquier producto cuya cantidad requerida u ordenada sea 0 se excluye automáticamente de la orden.
- Debe existir al menos un producto con cantidad mayor a 0; de lo contrario mostrará un error y no creará la orden.
- Al guardar, crea la orden en estatus Realizada, almacena en cada partida una copia histórica del empaque, peso, ventas y existencias del momento, registra el evento en la bitácora y redirige a la pantalla de detalle de la orden.

---

###### Seguimiento, estatus y exportación
1. Flujo secuencial de estatus
Desde el detalle de la orden, los usuarios con permiso pueden avanzar el estatus en un orden estricto paso a paso (opcionalmente capturando una nota que se anexa con fecha y hora al historial de notas de la orden y a la bitácora):
- Realizada (realizada): estatus inicial al crearse la orden.
- Confirmada (confirmada): orden confirmada (registra fecha y hora en confirmed_at).
- En tránsito (en_transito): mercancía en camino (registra fecha y hora en in_transit_at).
- Completada (completada): orden recibida o concluida administrativamente (registra fecha y hora en completed_at).
No es posible saltar estatus intermedios ni retroceder a un estatus anterior.

2. Exportación a Excel bilingüe (ES / EN)
En el detalle de la orden existe la acción Exportar Excel (ES / EN). Genera un libro con dos pestañas bilingües:
- Orden - Purchase Order: enfocada en la orden real, con secciones diferenciadas para atributos de producto y empaque (Product Attributes), desglose por CEDIS únicamente cuando el modo es Separado (en modo Acumulado solo se indica en el encabezado), y consolidado de orden (unidades requeridas, redondeo CEILING a tarimas, cajas, unidades ordenadas y peso en libras) con subtotales por línea y resumen final de camiones.
- Proyección - Forecast: respaldo analítico por producto con existencia física, inventario en tránsito, ventas del periodo evaluado, promedio mensual, meta de cobertura en meses, cantidad sugerida por el sistema, cantidad seleccionada (vinculada por fórmula viva a la primera pestaña), diferencia y total ordenado final.

3. Listado y consulta de órdenes
En el listado general de órdenes de compra se pueden consultar los indicadores globales (órdenes totales, pendientes, en tránsito, completadas, tarimas ordenadas, tarimas en tránsito, unidades ordenadas y peso neto) y filtrar por búsqueda libre (folio, notas o usuario creador), estatus, origen y CEDIS.
