from dataclasses import dataclass, field
from django.db import transaction
from apps.inventory.models import Attribute


@dataclass
class AttributeSeederService:
    '''
    Service responsible for seeding standard attributes for Veterinary Medicine 
    and Food Industry products into the database.
    
    Attributes differ from properties in that attributes distinguish and generate 
    a ProductVariant (SKU), whereas properties are intrinsic functional specs.
    '''

    DEFAULT_ATTRIBUTES: list[dict] = field(default_factory=lambda: [
        {
            'name': 'Presentación',
            'description': 'Empaque, volumen o peso comercial que distingue el SKU (ej. Baulto 20 kg, Frasco 100 ml, Caja c/10 ampolletas, Galón 4 L, Saco 5 kg).'
        },
        {
            'name': 'Concentración / Dosis',
            'description': 'Potencia o densidad del principio activo en fármacos, vacunas o suplementos veterinarios (ej. 250 mg, 500 mg, 10%, 20 mg/ml).'
        },
        {
            'name': 'Forma Farmacéutica / Física',
            'description': 'Estado físico o de presentación del producto que genera variantes comerciales (ej. Tabletas, Solución Inyectable, Suspensión Oral, Polvo Soluble, Croqueta Seca, Alimento Húmedo/Lata).'
        },
        {
            'name': 'Sabor / Palatabilidad',
            'description': 'Variedad organoléptica en alimentos, croquetas, premios o suspensiones orales para animales (ej. Pollo, Carne, Salmón, Neutro, Hígado, Vainilla).'
        },
        {
            'name': 'Calibre / Tamaños de Croqueta',
            'description': 'Dimensión o croqueta diferenciada según la fisonomía de la especie o raza (ej. Raza Pequeña/Minis, Raza Mediana, Raza Grande/Maxi, Grano Fino, Grano Grueso).'
        },
        {
            'name': 'Color / Identificador de Empaque',
            'description': 'Identificador visual diferenciador de línea de producto o variante comercial (ej. Azul, Verde, Transparente, Rojo).'
        },
    ])

    def seed(self) -> tuple[list[Attribute], int]:
        '''
        Creates or updates standard attributes.
        Returns a tuple with (list_of_attributes, created_count).
        '''
        created_count = 0
        attributes = []

        with transaction.atomic():
            for item in self.DEFAULT_ATTRIBUTES:
                attr, created = Attribute.objects.get_or_create(
                    name=item['name'],
                    defaults={'description': item['description']}
                )
                if created:
                    created_count += 1
                else:
                    attr.description = item['description']
                    attr.save()
                attributes.append(attr)

        return attributes, created_count
