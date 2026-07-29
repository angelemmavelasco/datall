PRODUCT_PROPERTIES_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "target_species": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Especies destino (ej. caninos, felinos, bovinos, porcinos, equinos, aves)"
        },
        "active_ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "concentration": {"type": "string"}
                },
                "required": ["name"]
            },
            "description": "Principios activos o componentes principales"
        },
        "administration_route": {
            "type": "string",
            "description": "Vía de administración (ej. Oral, Intramuscular, Subcutánea, Tópica)"
        },
        "sagarpa_register": {
            "type": "string",
            "description": "Número de registro oficial SAGARPA / SENASICA"
        },
        "requires_prescription": {
            "type": "boolean",
            "description": "Indica si requiere receta médica veterinaria"
        },
        "withdrawal_period_days": {
            "type": "integer",
            "minimum": 0,
            "description": "Días de retiro para animales de consumo"
        },
        "storage_conditions": {
            "type": "string",
            "description": "Condiciones de conservación (ej. Conservar entre 2°C y 8°C)"
        },
        "guaranteed_analysis": {
            "type": "object",
            "description": "Análisis nutricional garantizado (Proteína min %, Grasa min %, etc.)"
        }
    },
    "additionalProperties": True
}

VARIANT_PROPERTIES_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "specific_dosing": {
            "type": "string",
            "description": "Instrucción de dosificación específica para esta variante"
        },
        "package_type": {
            "type": "string",
            "description": "Tipo de envase (ej. Frasco de vidrio ámbar, Bolsa de papel tricapa)"
        }
    },
    "additionalProperties": True
}
