from django.db import models
from django.db.models import Q
from decimal import Decimal

class RouteType(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=500, null=True, blank=True)

    class Meta:
        verbose_name = "Tipo de ruta"
        verbose_name_plural = "Tipos de ruta"

    def __str__(self):
        name = (self.name or '').title()
        return f"{self.id.upper()} {name}"

class SaleChannel(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=500, null=True, blank=True)

    class Meta:
        verbose_name = "Canal de venta"
        verbose_name_plural = "Canales de venta"

    def __str__(self):
        name = (self.name or '').title()
        return f"{self.id.upper()} {name}"

class Route(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)
    warehouse = models.ForeignKey('human_resources.Warehouse', on_delete=models.SET_NULL, related_name="routes", null=True, blank=True)
    sale_channel = models.ForeignKey('SaleChannel', on_delete=models.PROTECT, null=True, blank=True, related_name="routes")
    route_type = models.ForeignKey('RouteType', on_delete=models.PROTECT, null=True, blank=True, related_name="routes")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Ruta"
        verbose_name_plural = "Rutas"

    def __str__(self):
        name = (self.name or '').title()
        return f"{self.id.upper()} {name}"

class RouteAssignment(models.Model):
    route = models.ForeignKey('Route', on_delete=models.CASCADE, related_name="assignments")
    employee = models.ForeignKey('human_resources.Employee', on_delete=models.CASCADE, related_name="route_assignments", blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Asignación de ruta"
        verbose_name_plural = "Asignaciones de rutas"
        constraints = [
            # avoid duplicate assignments at the same day
            models.UniqueConstraint(
                fields=["route", "employee", "start_date"],
                name="unique_route_assignment"
            ),
            # only one active assignment (end_date NULL) per route
            models.UniqueConstraint(
                fields=["route"],
                condition=Q(end_date__isnull=True),
                name="unique_active_assignment_per_route"
            ),
        ]

    def __str__(self):
        route = self.route.id
        if self.employee and self.employee.user:
            name = f"{self.employee.user.first_name.title()} {self.employee.user.last_name.title()}"
        else:
            name = "Sin colaborador asignado"
        return f"Ruta {route}, {name}"

class Sale(models.Model):
    """
    Sale header, indicates the general information about the sale, e.g. date, customer, seller, etc.
    """
    class SaleStatusChoices(models.TextChoices):
        COMPLETED = "completed", "Completada"
        PENDING = "pending", "Pendiente"
        CANCELED = "canceled", "Cancelada"

    class PaymentStatusChoices(models.TextChoices):
        PENDING = "pending", "Pendiente de pago"
        PAID = "paid", "Pagada"
        PARTIALLY_PAID = "partially_paid", "Parcialmente pagada"
        CANCELED = "canceled", "Cancelada"

    class PaymentFormChoices(models.TextChoices):
        EFECTIVO = "01", "01 Efectivo"
        CHEQUE_NOMINATIVO = "02", "02 Cheque nominativo"
        TRANSFERENCIA = "03", "03 Transferencia electrónica de fondos"
        TARJETA_CREDITO = "04", "04 Tarjeta de crédito"
        MONEDERO_ELECTRONICO = "05", "05 Monedero electrónico"
        DINERO_ELECTRONICO = "06", "06 Dinero electrónico"
        VALES_DESPENSA = "08", "08 Vales de despensa"
        DACION_EN_PAGO = "12", "12 Dación en pago"
        PAGO_POR_SUBROGACION = "13", "13 Pago por subrogación"
        PAGO_POR_CONSIGNACION = "14", "14 Pago por consignación"
        CONDONACION = "15", "15 Condonación"
        COMPENSACION = "17", "17 Compensación"
        NOVACION = "23", "23 Novación"
        CONFUSION = "24", "24 Confusión"
        REMISION_DEUDA = "25", "25 Remisión de deuda"
        PRESCRIPCION_CADUCIDAD = "26", "26 Prescripción o caducidad"
        A_SATISFACCION_ACREEDOR = "27", "27 A satisfacción del acreedor"
        TARJETA_DEBITO = "28", "28 Tarjeta de débito"
        TARJETA_SERVICIOS = "29", "29 Tarjeta de servicios"
        APLICACION_ANTICIPOS = "30", "30 Aplicación de anticipos"
        INTERMEDIARIO_PAGO = "31", "31 Intermediario pago"
        POR_DEFINIR = "99", "99 Por definir"

    class PaymentMethodChoices(models.TextChoices):
        PUE = "PUE", "PUE Pago en una sola exhibición"
        PPD = "PPD", "PPD Pago en parcialidades o diferido"

    doc_id = models.CharField(max_length=255, unique=True, db_index=True, help_text='Referencia unica de la venta, conformado por la fecha de emisión y la secuencia de ventas del día. Ejemplo: 20260720_123')
    sale_date = models.DateTimeField(db_index=True, help_text="Fecha y hora en la que se realizó la venta")
    sale_status = models.CharField(max_length=20, choices=SaleStatusChoices.choices, default=SaleStatusChoices.PENDING, db_index=True, help_text="Estado de la venta")
    payment_status = models.CharField(max_length=20, choices=PaymentStatusChoices.choices, default=PaymentStatusChoices.PENDING, db_index=True, help_text="Estado del pago")

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="sales", db_index=True, help_text="Cliente que realizó la compra")
    route = models.ForeignKey("Route", on_delete=models.PROTECT, related_name="sales", null=True, blank=True, db_index=True, help_text="Ruta/vendedor asignado a esta venta")
    warehouse = models.ForeignKey("human_resources.Warehouse", on_delete=models.PROTECT, related_name="sales", null=True, blank=True, db_index=True, help_text="Lugar de expedición de la venta")

    currency = models.CharField(max_length=3, default="MXN", help_text="Divisa en la que se realizó la venta")
    currency_exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, help_text="Valor de la divisa")
    payment_form = models.CharField(max_length=2, choices=PaymentFormChoices.choices, default=PaymentFormChoices.POR_DEFINIR, help_text="Forma de pago")
    payment_method = models.CharField(max_length=3, choices=PaymentMethodChoices.choices, default=PaymentMethodChoices.PUE, help_text="Método de pago")

    subtotal = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Subtotal de la venta sin impuestos ni descuentos")
    discount = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Descuento aplicado a la venta")
    taxes = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Impuestos aplicados a la venta")
    total = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Total de la venta con impuestos y descuentos")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    invoice = models.ForeignKey("Invoice", on_delete=models.SET_NULL, null=True, blank=True, related_name="sales", help_text="Documento fiscal CFDI asociado a esta venta")
    journal_entry = models.OneToOneField('accounting.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, related_name='sale', help_text="Asiento contable generado por esta venta")

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'

    def __str__(self):
        return f'{self.doc_id}: total ${self.total:,.2f}'

class SaleLine(models.Model):
    """
    Indicate a breakdown of the header, this is sold item by item.
    """

    sale = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='lines', help_text='Venta a la que pertenece esta línea')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='sales_lines')
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0, help_text='Cantidad de producto vendido')
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text='Precio unitario del producto')
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.0'), help_text="Costo del producto al momento de vender para asiento de Costo de Ventas")
    discount = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text='Descuento aplicado al producto')
    subtotal = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text='Subtotal de la línea sin impuestos ni descuentos')
    total = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    description_override = models.TextField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Desglose de venta'
        verbose_name_plural = 'Desgloses de ventas'

    def __str__(self):
        return f'{self.sale.id}: {self.product.id.upper()} x {self.quantity}'

class SaleLineTax(models.Model):
    """
    Indicate taxes applied to each sale line.
    """

    class TaxType(models.TextChoices):
        IVA = "IVA", "IVA"
        ISR = "ISR", "ISR"
        IEPS = "IEPS", "IEPS"
    class TaxFactorType(models.TextChoices):
        TASA = "Tasa", "Tasa"
        CUOTA = "Cuota", "Cuota"
        EXENTO = "Exento", "Exento"

    sale_line = models.ForeignKey('SaleLine', on_delete=models.CASCADE, related_name='taxes')
    tax_type = models.CharField(max_length=10, choices=TaxType.choices, default=TaxType.IVA)
    factor_type = models.CharField(max_length=10, choices=TaxFactorType.choices, default=TaxFactorType.TASA)
    rate = models.DecimalField(max_digits=6, decimal_places=4, help_text="Ej: 0.1600 para 16%")
    base = models.DecimalField(max_digits=18, decimal_places=6, help_text="Base gravable")
    amount = models.DecimalField(max_digits=18, decimal_places=6, help_text="Monto final del impuesto")
    tax_account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT, null=True, blank=True, help_text="Cuenta contable asociada (ej. 209.01 IVA Pendiente de Trasladar)")
    
    class Meta:
        verbose_name = 'Impuesto de desglose de venta'
        verbose_name_plural = 'Impuestos de desgloses de ventas'

class Invoice(models.Model):
    '''
    Represent an official tax document (CFDI 4.0) and its satelites (payment receipts, etc) issued to the customer.
    '''
    
    class CfdiTypes(models.TextChoices):
        INGRESO = 'I', 'Ingreso'
        EGRESO = 'E', 'Egreso'
        PAGO = 'P', 'Pago'
        TRASLADO = 'T', 'Traslado'
        NOMINA = 'N', 'Nómina'
    class CfdiStatus(models.TextChoices):
        VIGENTE = 'vigente', 'Vigente'
        CANCELADO = 'cancelado', 'Cancelado'
    
    #identifiers
    uuid = models.UUIDField(unique=True, null=True, blank=True, help_text="Folio Fiscal UUID del SAT")
    serie = models.CharField(max_length=25, blank=True, null=True, help_text="Serie del CFDI")
    folio = models.CharField(max_length=25, blank=True, null=True, help_text="Folio del CFDI")
    date = models.DateTimeField(help_text="Fecha de expedición del CFDI")

    #header info
    cfdi_type = models.CharField(max_length=1, choices=CfdiTypes.choices, default=CfdiTypes.INGRESO, help_text="Tipo de comporbante")
    payment_form = models.CharField(max_length=3, help_text="Forma de pago (ej. 01, 03)")
    payment_method = models.CharField(max_length=3, help_text="Método de pago (PUE, PPD)")
    currency = models.CharField(max_length=3, default='MXN')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=1.0)
    exportation = models.CharField(max_length=2, default='01')
    expedition_place = models.CharField(max_length=5, help_text="Código postal de expedición")

    #receiver
    receiver_rfc = models.CharField(max_length=13, help_text="RFC del receptor")
    receiver_name = models.CharField(max_length=255, help_text="Nombre o razón social del receptor")
    receiver_cfdi_use = models.CharField(max_length=3, help_text="Uso CFDI (ej. G03)")
    receiver_fiscal_regime = models.CharField(max_length=3, help_text="Régimen fiscal del receptor")
    receiver_zip_code = models.CharField(max_length=5, help_text="Código postal del receptor")

    #issuer
    issuer_rfc = models.CharField(max_length=13, help_text="RFC del emisor")
    issuer_name = models.CharField(max_length=255, help_text="Nombre o razón social del emisor")
    issuer_fiscal_regime = models.CharField(max_length=3, help_text="Régimen fiscal del emisor")
    issuer_zip_code = models.CharField(max_length=5, help_text="Código postal del emisor")

    #totals
    subtotal = models.DecimalField(max_digits=18, decimal_places=6, help_text="Subtotal general")
    discount = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Descuento general")
    total = models.DecimalField(max_digits=18, decimal_places=6, help_text="Total general")

    #related docs
    status = models.CharField(max_length=20, choices=CfdiStatus.choices, default=CfdiStatus.VIGENTE)
    xml_file = models.FileField(upload_to='invoices/xml/', null=True, blank=True)
    pdf_file = models.FileField(upload_to='invoices/pdf/', null=True, blank=True)

    #metadata
    api_response = models.JSONField(null=True, blank=True, help_text="Respuesta completa de la API")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Fecha de creación (del registro)")
    updated_at = models.DateTimeField(auto_now=True, help_text="Fecha de actualización (del registro)")
    
    class Meta:
        verbose_name = 'Factura (CFDI)'
        verbose_name_plural = 'Facturas (CFDI)'

    def __str__(self):
        return f"CFDI {self.serie or ''}{self.folio or ''} - {self.uuid or 'Sin timbrar'}"
   
class InvoiceItem(models.Model):
    """
    Breakdown of an invoice, also know as concepts in a CFDI. It stores data of a single concept in a CFDI and its non-changable info.
    """
    invoice = models.ForeignKey('Invoice', related_name='items', on_delete=models.CASCADE)
    
    product_code = models.CharField(max_length=10, help_text="Clave de producto o servicio del SAT (ej. 10111302)")
    identification_number = models.CharField(max_length=50, blank=True, null=True, help_text="No. Identificación o SKU interno")
    description = models.CharField(max_length=1000)
    
    unit_code = models.CharField(max_length=5, help_text="Clave de unidad del SAT (ej. H87)")
    unit_name = models.CharField(max_length=50, help_text="Descripción de la unidad (ej. Pieza)")
    
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_price = models.DecimalField(max_digits=18, decimal_places=6)
    subtotal = models.DecimalField(max_digits=18, decimal_places=6)
    discount = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    
    tax_object = models.CharField(max_length=2, help_text="ObjetoImp (01, 02, 03)")

    class Meta:
        verbose_name = 'Concepto de factura'
        verbose_name_plural = 'Conceptos de factura'

    def __str__(self):
        return f"{self.product_code} - {self.description}"

class InvoiceItemTax(models.Model):
    """
    Impuestos fiscales desglosados por concepto del CFDI.
    """
    item = models.ForeignKey('InvoiceItem', related_name='taxes', on_delete=models.CASCADE)
    name = models.CharField(max_length=10, help_text="IVA, ISR, IEPS")
    is_retention = models.BooleanField(default=False)
    is_federal_tax = models.BooleanField(default=True)
    
    base = models.DecimalField(max_digits=18, decimal_places=6)
    rate = models.DecimalField(max_digits=6, decimal_places=4)
    total = models.DecimalField(max_digits=18, decimal_places=6)
    
    class Meta:
        verbose_name = 'Impuesto de factura'
        verbose_name_plural = 'Impuestos de factura'

    def __str__(self):
        return f"{self.name.upper()} {self.item.description.title()}"

class InvoiceRelation(models.Model):
    """
    Handles the CfdiRelacionados node of the SAT.
    It allows linking a Credit Note (Egreso), a Payment Receipt (Pago), 
    or a Substitution (04) to its original invoice (Ingreso).
    """
    class RelationTypes(models.TextChoices):
        NOTA_CREDITO = '01', '01 Nota de crédito'
        NOTA_DEBITO = '02', '02 Nota de débito'
        DEVOLUCION = '03', '03 Devolución de mercancía'
        SUSTITUCION = '04', '04 Sustitución de los CFDI previos'
        TRASLADOS = '05', '05 Traslados de mercancías facturados previamente'
        FACTURA_POR_TRASLADOS = '06', '06 Factura generada por los traslados previos'
        ANTICIPO = '07', '07 CFDI por aplicación de anticipo'
        PAGOS = '08', '08 Factura generada por pagos en parcialidades'
        PAGOS_DIFERIDOS = '09', '09 Factura generada por pagos diferidos'

    source_invoice = models.ForeignKey(
        'Invoice', 
        related_name='related_documents', 
        on_delete=models.CASCADE, 
        help_text="CFDI que se está emitiendo (Hijo)"
    )
    
    target_invoice = models.ForeignKey(
        'Invoice', 
        related_name='referenced_by', 
        on_delete=models.CASCADE, 
        help_text="CFDI previo relacionado (Padre)"
    )
    
    relation_type = models.CharField(
        max_length=2, 
        choices=RelationTypes.choices, 
        help_text="Tipo de relación SAT (ej. 04 para Sustitución)"
    )

    class Meta:
        verbose_name = 'CFDI Relacionado'
        verbose_name_plural = 'CFDIs Relacionados'
        unique_together = ('source_invoice', 'target_invoice', 'relation_type')

    def __str__(self):
        return f"{self.source_invoice.uuid} -> {self.relation_type} -> {self.target_invoice.uuid}"

class SaleTarget(models.Model):
    period = models.DateField()
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='sale_targets')
    warehouse = models.ForeignKey('human_resources.Warehouse', on_delete=models.PROTECT, related_name='sale_targets')
    product_class = models.ForeignKey('inventory.ProductClass', on_delete=models.PROTECT, related_name='sale_targets')
    target_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    is_valid_for_comission = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Objetivo de venta'
        verbose_name_plural = 'Objetivos de venta'
        constraints = [
            models.UniqueConstraint(
                fields=["period", "route", "product_class"],
                name="unique_sale_target_per_period_route_class"
            )
        ]

    def __str__(self):
        route = self.route_id
        cls_name = (self.product_class_id or "").title()
        return f'Ruta {route}, clase {cls_name}, periodo {self.period:%b %Y}'
