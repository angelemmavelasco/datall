# Sistema de Comisiones

Esta guía explica cómo utilizar el formulario de creación y configuración de perfiles de comisión para rutas de venta, así como la gestión de casos especiales.

## Glosario

* *Perfil de Comisión:* Es el "molde" o esquema base. Agrupa todas las reglas y metas que aplican a un grupo de vendedores con el mismo rol o condiciones.
* *Umbral (Tier):* Es un "escalón" o meta dentro de un perfil. Imagina que es una escalera: cada peldaño (umbral) exige llegar a cierto porcentaje de ventas (Alcance global) y, a cambio, otorga un multiplicador de comisión o un bono fijo. Un perfil puede tener uno o varios umbrales (ej. llegar al 90%, llegar al 100%, llegar al 120%).
* *Excepción:* Una regla temporal y exclusiva para *una sola ruta*. Se usa para dar "ayudas" transitorias, como tolerancias o pagos fijos durante la curva de aprendizaje de un nuevo ingreso.
* *Alcance Global:* El porcentaje de cumplimiento de las metas de venta frente a los objetivos establecidos.

## Consideración: ¿Umbral o Excepción?
Antes de configurar una regla, debes plantearte la siguiente pregunta:
*Si esta regla aplica para todos los vendedores que tengan este esquema, es un Umbral (Tier).*
*Si es algún tipo de tolerancia o regla temporal para una sola ruta en específico, es una Excepción.*

## 1. Tolerancias para Nuevos Ingresos (Curva de aprendizaje)
No se debe crear un "Perfil de Nuevo Ingreso". La idea es que el vendedor ya esté atado a su perfil real definitivo, pero con una "ruedita de entrenamiento" temporal. 

Para lograr esto, se utiliza una *Excepción* en la ruta, la cual cuenta con una fecha de inicio y una de fin. Existen dos formas de ayudar a un nuevo ingreso:

* *Ayuda con porcentaje (Tolerancia):* Si el vendedor logró un 85% real de alcance global y en su excepción se configuró una tolerancia del 10.00%, el sistema sumará ambos valores y evaluará su comisión como si hubiera alcanzado el 95%.
* *Ayuda con dinero (Bono garantizado):* Si la empresa determina asegurar un pago fijo (ejemplo: $5,000) sin importar las ventas durante la curva de aprendizaje, se debe dejar la tolerancia en 0 e ingresar la cantidad en el campo de bono garantizado.

Una vez que la fecha de la excepción vence (por ejemplo, transcurridos los 3 meses de prueba), el motor de comisiones ignora esta regla automáticamente y el vendedor comienza a comisionar de forma normal bajo su configuración base.

## 2. Incentivos Extras y Aceleradores
Estos casos corresponden a reglas de negocio oficiales (ejemplo: "Si llegas al 120%, obtienes un bono extra"). Por lo tanto, se configuran como un *Umbral* dentro del Perfil base de la comisión, ya que cualquier ruta con ese perfil que logre la meta merece el premio.

Para configurarlo, se debe agregar un escalón más alto en el perfil. Por ejemplo, si el tope normal es 100%, para el acelerador del 120% se crea un nuevo umbral con:
* *Alcance global:* 120.00
* *Líneas requeridas:* Las que apliquen (ej. 4)

La recompensa se define utilizando los siguientes campos:
* *Mayor porcentaje:* Se incrementa el multiplicador del bono (ej. 120.00%).
* *Monto fijo extra:* Se mantiene el multiplicador normal (ej. 100%), pero se utiliza el campo de bono extra fijo (ej. 2000.00).

El sistema evaluará siempre de arriba hacia abajo, partiendo del alcance más alto. Revisará primero si el vendedor llegó al 120%; si es así, otorga ese premio y termina. Si no llegó, bajará al escalón del 100%, luego al del 90%, y así sucesivamente.

## Condiciones y Limitaciones en Asignaciones Masivas
Al asignar rutas masivamente desde el formulario del perfil, existen validaciones estrictas para evitar conflictos:

* *Perfiles empalmados:* Si intentas asignar un perfil a una ruta que ya cuenta con un perfil activo en el mismo periodo, el sistema rechazará la operación y mostrará un mensaje indicando qué ruta tiene el conflicto.
* *Solución de conflictos:* Para resolver esto, debes ir al detalle de esa ruta en particular y finalizar la fecha de su perfil actual, o bien, retirar esa ruta de la lista de selección masiva antes de guardar.
* *Fechas obligatorias:* Toda asignación requiere forzosamente una fecha de inicio y especificar si el esquema de bono será fijo o variable.

## 3. Gestión de Excepciones en el Panel
Para gestionar, buscar y crear nuevas reglas temporales (excepciones), el sistema cuenta con un panel dedicado y herramientas de asignación masiva.

* *Listado y Filtros:* En el panel de Excepciones sobre comisiones, puedes visualizar todas las reglas atípicas creadas. Utiliza el menú lateral de filtros para buscar por ID de ruta, nombre del colaborador, rango de fechas de vigencia, o incluso filtrar por rangos específicos de porcentaje de tolerancia y monto garantizado.
* *Creación Masiva:* Desde el panel, puedes crear una *Nueva excepción* y asignarla a múltiples rutas de forma simultánea. 
    * Primero, define las reglas (inicio, fin, tolerancias y justificación).
    * Luego, utiliza la barra de búsqueda en el contenedor de rutas para filtrar la lista en tiempo real.
    * La casilla *Seleccionar todas* cuenta con lógica dinámica: únicamente marcará o desmarcará las rutas que estén actualmente visibles tras aplicar tu filtro de búsqueda, agilizando la asignación por bloques sin afectar rutas ocultas.
