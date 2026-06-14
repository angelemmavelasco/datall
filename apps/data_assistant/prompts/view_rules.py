from apps.data_assistant.services.data_assistant.data_builders import build_commercial_risk_data, build_sales_dashboard_data

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
}