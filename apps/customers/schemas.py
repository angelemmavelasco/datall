# apps/customers/schemas.py
#tax info schema
TAX_ENTITIES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "legal_name": {"type": "string", "minLength": 3},
            "tax_id": {"type": "string", "minLength": 12, "maxLength": 13},
            "zip_code": {"type": "string", "minLength": 5, "maxLength": 5},
            "tax_system": {"type": "string"},
            "is_default": {"type": "boolean"}
        },
        "required": ["legal_name", "tax_id", "zip_code"],
        "additionalProperties": False
    }
}

#delivery addresses schema
DELIVERY_ADDRESSES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "alias": {"type": "string"},
            "street": {"type": "string"},
            "ext_number": {"type": "string"},
            "int_number": {"type": "string"},
            "neighborhood": {"type": "string"},
            "zip_code": {"type": "string", "minLength": 5, "maxLength": 5},
            "city": {"type": "string"},
            "state": {"type": "string"},
            "is_default": {"type": "boolean"}
        },
        "required": ["alias", "street", "zip_code"],
        "additionalProperties": False
    }
}

#contacts schema
CONTACTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "role": {"type": "string"},
            "email": {"type": "string", "format": "email"},
            "phone": {"type": "string"}
        },
        "required": ["name"],
        "additionalProperties": False
    }
}