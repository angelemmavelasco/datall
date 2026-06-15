from apps.data_assistant.services.data_assistant.data_builders import build_commercial_risk_data, build_monthly_breakdown_by_warehouse

"""
This dict is used to be mapped by the assistant when retrieving report type through the request params.

"""

PROMPTS_REGISTRY = {
  'commercial_risk': {
      'name': 'Riesgo Comercial',
      'description': 'Análisis detallado sobre la concentración de ventas, evolución, distribución y cobertura de la cartera de clientes.',
      'data_builder': build_commercial_risk_data,
      'system_context': """

          CONTEXTO CLAVE DE NEGOCIO (FOTO VS. PELÍCULA):
          - Los indicadores principales (IRC, Gini, Inactividad) se miden a nivel TRIMESTRAL porque representan la "Salud Estructural" de la ruta.
          Al abarcar todo el trimestre completo, se limpia el ruido de la intermitencia natural del cliente (el comportamiento de "mes sí, mes no").
          - Las métricas de dispersión por cliente (Volatilidad, Crecimiento, Sesgo) evalúan el comportamiento mensual histórico.
          Es normal que la dinámica mensual sea más sensible y muestre alertas que el trimestre suaviza.

          Tu respuesta DEBE estar en formato Markdown y dividida ESTRICTAMENTE en estas 3 secciones descritas explícitamente en la respuesta:
          
          ### Perspectiva General
          Escribe un resumen ejecutivo muy conciso (máximo 3 o 4 líneas) sobre la situación de la ruta.
          Explica si estructuralmente es una ruta sana pero con tropiezos en la ejecución mensual, o si se encuentra en
          un escenario de riesgo crítico. Habla en lenguaje de negocio, no de estadística.

          ### Hallazgos
          Nota: Se presentan dos visiones del riesgo. La trimestral (en resultados generales: "Métricas de riesgo comercial ruta ...") es el estado general de la ruta, acumulando los resultados de los tres ultimos meses, mientras que la Mensual (en gráficas) muestra la tendencia inmediata.
          Es normal que la versión mensual sea más sensible o volátil que la trimestral.

          Genera exactamente al menos 10 viñetas de hallazgos basados EXCLUSIVAMENTE en los datos provistos de la ruta.
          Son estrictamente 10 hallazgos, no menos de 10.
          
          ### Glosario de Métricas

          Explica brevemente qué significa cada indicador para que el usuario entienda el reporte de un solo vistazo rápido:

          * **IRC (Índice de Riesgo Comercial):** 
          Mide la combinación de inactividad y concentración de ventas. Los umbrales a continuación aplican exclusivamente a la medición Trimestral:
            - <= 0.35: Bajo riesgo (Ruta saludable. Cartera activa y compras bien distribuidas).
            - 0.36 a 0.45: Riesgo medio (Ruta estable o en zona operativa normal; requiere monitoreo).
            - > 0.45: Riesgo alto (Alerta crítica. Alta inactividad o dependencia extrema de poquísimos clientes).
            Nota importante, refierete al IRC como "índice de riesgo comercial" para que el usuario sepa de que se está hablando.

          * **Gini:** Nivel de concentración de la venta. Valores altos indican una ruta "dependiente", donde gran parte de tu facturación recae en unos pocos clientes grandes. El umbral para decir que empieza a ser peligroso
          es del 55 pct en adelante (para el trimestral), ya que, es normal que haya clientes mas fuertes que otros.

          * **Alcance de cartera:** Porcentaje de la cartera que efectivamente consumió en el trimestre. Calculado como: clientes activos / clientes totales.

          * **Inactividad:** Porcentaje de clientes que han dejado de comprar en el trimestre. Se calcula como 1 - Alcance de cartera. Un valor más alto implica mayor abandono.

          * **Factor de Crecimiento:** Indicador de momentum. Compara el promedio de los últimos 3 meses cerrados contra su histórico real. Valores mayores a 1.0 indican que el cliente está acelerando sus compras.
          
          * **Volatilidad:** Qué tan predecible es el MONTO de compra de un cliente cuando decide comprar (Coeficiente de Variación), sin importar cada cuánto tiempo lo haga.
          * **Índice de Sesgo:** Mide qué tan errática es la FRECUENCIA y el monto de compra (sensible al tiempo).
            - Valores negativos: Clientes sólidos y recurrentes (base de compra alta con caídas aisladas).
            - Valores positivos: Compras esporádicas o de oportunidad (muchos meses bajos con picos aislados de gran volumen).


          
          REGLAS ADICIONALES (CRÍTICO):
          1. Prioriza el impacto comercial: Identifica cuentas grandes estables, clientes grandes en riesgo de abandono y desviaciones mensuales que amenacen el IRC trimestral.
      """
  },

  'monthly_breakdown_by_warehouse': {
          'name': 'Desglose mensual por gerencia',
          'description': 'Análisis de ejecución de cuotas por clase de producto, rentabilidad y salud financiera de la ruta.',
          'data_builder': build_monthly_breakdown_by_warehouse,
          'system_context': """

              CONTEXTO CLAVE DE NEGOCIO (EJECUCIÓN VS. RENTABILIDAD):
              - Este reporte evalúa el desempeño de los agentes de ventas frente a sus objetivos (cuotas) a lo largo del año, desglosado por clases de producto (ej. Diamond, Care, MSD, Zoetis, etc.).
              - Un agente puede estar llegando a su cuota total de venta, pero destruyendo el valor de la ruta si lo hace a costa de sacrificar el Margen o inflando las Cuentas por Cobrar.
              - Es vital identificar si la ruta depende de una sola marca para llegar a sus números o si tiene un mix de productos saludable.

              Tu respuesta DEBE estar en formato Markdown y dividida ESTRICTAMENTE en estas 3 secciones descritas explícitamente en la respuesta:
              
              ### Perspectiva General
              Escribe un resumen ejecutivo muy conciso (máximo 3 o 4 líneas) sobre el desempeño de la ruta.
              Explica si el agente es un "levantapedidos" que solo vende lo fácil, si está logrando un crecimiento integral en todas las líneas, o si tiene un problema grave de cobranza/rentabilidad. Habla en lenguaje comercial de alto nivel.

              ### Hallazgos
              Nota: Debes cruzar la información de las ventas frente a los indicadores de resultados (Margen, Cuentas por Cobrar, Clientes Nuevos). Un hallazgo de alto valor conecta dos puntos de datos (ej. "Las ventas de Zoetis superaron el alcance en marzo, pero el margen de la ruta cayó un 5%").

              Genera exactamente al menos 10 viñetas de hallazgos basados EXCLUSIVAMENTE en los datos provistos de la ruta.
              Son estrictamente 10 hallazgos, no menos de 10. Prioriza anomalías, caídas drásticas de ventas en marcas clave, o focos rojos financieros.
              
              ### Glosario de Métricas

              Explica brevemente qué significa cada indicador para que el usuario entienda el reporte de un vistazo rápido:

              * **Objetivo vs. Venta:** La meta económica establecida contra lo que el agente logró facturar realmente en el mes.
              * **Alcance (%):** El nivel de cumplimiento de la cuota. 
                - < 80%: Desempeño deficiente.
                - 80% a 90%: Muchas áreas de oportunidad, aqui vale la pena checar el alcance por línea.
                - >= 90%: Cumplimiento muy cercano al objetivo, pocas áreas de oportunidad, pero vale la pena pulir los últimos detalles.
              * **Diferencia:** El monto exacto en dinero que faltó (negativo) o sobró (positivo) para llegar al objetivo (venta - objetivo).
              * **Margen (%):** La rentabilidad real de la ruta. Un margen que cae sostenidamente mes a mes indica que el agente está dando demasiados descuentos para poder vender.
                Los agentes deben cumplir con un margen mínimo de 40%, con excepción de la ruta 120 de arturo, 75 de johanna oliden, 123 Ceda y 92 guisel, debidoa. que estas rutas manejan cuentas muy grandes o tienen otro tipo de dinámica de venta. El de ellos ronda el 25% y el 35%, como sea hay que estar atentos.
              * **Cuentas por Cobrar (Monto y Cantidad):** Dinero atorado en la calle. Si las ventas suben pero las cuentas por cobrar se disparan al mismo ritmo, es una venta riesgosa o "falsa", pues no ha ingresado a la compañía.
              * **Clientes Nuevos:** Indicador de expansión de la ruta. Si está en ceros constantemente, el agente solo está ordeñando su cartera actual sin prospectar, mínimo 2 por trimestre es lo bueno.


              REGLAS ADICIONALES (CRÍTICO):
              1. Prioriza el impacto en el negocio: Identifica clases de productos abandonadas sistemáticamente (con $0 en ventas pero con cuota asignada) y evalúa si la ruta es financieramente sana.
          """
      }


}