from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.core.validators import RegexValidator
from django.contrib.contenttypes.models import ContentType
from dateutil.relativedelta import relativedelta
from datetime import date

class GenderChoices(models.TextChoices):
    MALE = "M", "Masculino"
    FEMALE = "F", "Femenino"
    NON_BINARY = "NB", "No binario"
    OTHER = "O", "Otro"

class TaxRegimeChoices(models.TextChoices):
    GENERAL_PERSONAS_MORALES = '601', '601 General de Ley Personas Morales'
    PERSONAS_MORALES_FINES_NO_LUCRATIVOS = '603', '603 Personas Morales con Fines no Lucrativos'
    SUELDOS_SALARIOS = '605', '605 Sueldos y Salarios e Ingresos Asimilados a Salarios'
    ARRENDAMIENTO = '606', '606 Arrendamiento'
    ENAJENACION_BIENES = '607', '607 Régimen de Enajenación o Adquisición de Bienes'
    DEMAS_INGRESOS = '608', '608 Demás ingresos'
    RESIDENTES_EXTRANJERO = '610', '610 Residentes en el Extranjero sin Establecimiento Permanente en México'
    DIVIDENDOS = '611', '611 Ingresos por Dividendos (socios y accionistas)'
    ACTIVIDADES_EMPRESARIALES_PROFESIONALES = '612', '612 Personas Físicas con Actividades Empresariales y Profesionales'
    INTERESES = '614', '614 Ingresos por intereses'
    PREMIOS = '615', '615 Régimen de los ingresos por obtención de premios'
    SIN_OBLIGACIONES_FISCALES = '616', '616 Sin obligaciones fiscales'
    SOCIEDADES_COOPERATIVAS = '620', '620 Sociedades Cooperativas de Producción que optan por diferir sus ingresos'
    INCORPORACION_FISCAL = '621', '621 Incorporación Fiscal (RIF)'
    AGRAPES = '622', '622 Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras (AGAPES)'
    GRUPOS_SOCIEDADES = '623', '623 Opcional para Grupos de Sociedades'
    COORDINADOS = '624', '624 Coordinados'
    PLATAFORMAS_TECNOLOGICAS = '625', '625 Actividades Empresariales con ingresos a través de Plataformas Tecnológicas'
    RESICO = '626', '626 Régimen Simplificado de Confianza (RESICO)'

class PaymentFormChoices(models.TextChoices):
    _01 = '01', '01 Efectivo'
    _02 = '02', '02 Cheque nominativo'
    _03 = '03', '03 Transferencia electrónica de fondos'
    _04 = '04', '04 Tarjeta de crédito'
    _05 = '05', '05 Monedero electrónico'
    _06 = '06', '06 Dinero electrónico'
    _08 = '08', '08 Vales de despensa'
    _12 = '12', '12 Dación en pago'
    _13 = '13', '13 Pago por subrogación'
    _14 = '14', '14 Pago por consignación'
    _15 = '15', '15 Condonación'
    _17 = '17', '17 Compensación'
    _23 = '23', '23 Novación'
    _24 = '24', '24 Confusión'
    _25 = '25', '25 Remisión de deuda'
    _26 = '26', '26 Prescripción o caducidad'
    _27 = '27', '27 A satisfacción del acreedor'
    _28 = '28', '28 Tarjeta de débito'
    _29 = '29', '29 Tarjeta de servicios'
    _30 = '30', '30 Aplicación de anticipos'
    _31 = '31', '31 Intermediario pagos'
    _99 = '99', '99 Por definir'

class PeriodicityChoices(models.TextChoices):
    DAILY = '1d', '1 día'
    WEEKLY = '1w', '1 semana'
    FORTNIGHTLY = '2w', '2 semanas'
    MONTHLY = '1m', '1 mes'
    BIMONTHLY = '2m', '2 meses'
    QUARTERLY = '3m', '3 meses'
    FOUR_MONTHS = '4m', '4 meses'
    FIVE_MONTHS = '5m', '5 meses'
    SEMIANNUAL = '6m', '6 meses'
    SEVEN_MONTHS = '7m', '7 meses'
    EIGHT_MONTHS = '8m', '8 meses'
    NINE_MONTHS = '9m', '9 meses'
    TEN_MONTHS = '10m', '10 meses'
    ELEVEN_MONTHS = '11m', '11 meses'
    ANNUAL = '1y', '1 año'

    def get_relativedelta(self) -> relativedelta:
        '''
        calculates the relativedelta based on the numeric and key ref value, example : 1d -> 1 day, 11m -> 11 months, 1y -> 1 year
        '''
        val = str(self.value)
        amount = int(val[:-1])
        unit = val[-1].lower()

        unit_mapping = {
            'd': 'days',
            'w': 'weeks',
            'm': 'months',
            'y': 'years',
        }

        kwargs = {unit_mapping.get(unit, 'months'): amount}
        return relativedelta(**kwargs)

    def get_next_date(self, from_date: date) -> date:
        '''
        calculates the next date from a provided date
        '''
        return from_date + self.get_relativedelta()
    
    
class User(AbstractUser):
    second_last_name = models.CharField(max_length=150, blank=True, default="")
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GenderChoices.choices, default=GenderChoices.OTHER, blank=True)
    phone = models.CharField(max_length=15, blank=True, default="", validators=[RegexValidator(regex=r'^\d{10,15}$', message='El teléfono debe contener solo números.')])
    street = models.CharField(max_length=255, blank=True, default="")
    street_no = models.CharField(max_length=255, blank=True, default="")
    apt_suite = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=255, blank=True, default="")
    state = models.CharField(max_length=255, blank=True, default="")
    country = models.CharField(max_length=255, blank=True, default="")
    zipcode = models.CharField(max_length=255, blank=True, default="")
    unique_personal_id = models.CharField(max_length=20, blank=True, default="")
    notes = models.TextField(max_length=500, blank=True, default="")
    photo = models.FileField(upload_to='users/photos', null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.username}"

    @property
    def missing_profile_fields(self):
        missing = []
        if not self.first_name or not self.first_name.strip() or not self.last_name or not self.last_name.strip():
            missing.append("Nombre y primer apellido")
        if not self.email or not self.email.strip():
            missing.append("Correo electrónico (para restablecer tu contraseña)")
        if not self.gender:
            missing.append("Sexo / Género")
        if not self.birth_date:
            missing.append("Fecha de nacimiento")
        if not self.phone or not self.phone.strip():
            missing.append("Teléfono de contacto")
        return missing

    @property
    def is_profile_incomplete(self):
        return len(self.missing_profile_fields) > 0

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

class Module(models.Model):
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name.title()

    class Meta:
        ordering = ['order']
        verbose_name = 'Módulo'
        verbose_name_plural = 'Módulos'

class Submodule(models.Model):
    name = models.CharField(max_length=100, help_text="Nombre del submódulo visible al usuario")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='submodules', help_text="Módulo al que pertenece el submódulo")
    url_name = models.CharField(max_length=150, help_text="Url asociada al submódulo, de formato app_label:url_name")
    icon = models.TextField(blank=True, default='', help_text="Código SVG del ícono del submódulo")
    allowed_groups = models.ManyToManyField(Group, blank=True, related_name='accessible_submodules', help_text="Grupos autorizados para acceder al submódulo")
    allowed_users = models.ManyToManyField(User, blank=True, related_name='accessible_submodules', help_text="Usuarios autorizados para acceder al submódulo")
    order = models.PositiveIntegerField(default=0, help_text="Orden de aparición del submódulo en el menú")
    is_active = models.BooleanField(default=True, help_text="Indica si el submódulo está activo y se muestra al usuario")

    def __str__(self):
        mod_name = self.module.name.title() if self.module and getattr(self.module, 'name', None) else "Sin Módulo"
        sub_name = self.name.title() if self.name else "Sin Nombre"
        return f"{mod_name} > {sub_name}"
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Submódulo'
        verbose_name_plural = 'Submódulos'

class Reference(models.Model):
    submodule = models.ForeignKey('Submodule', on_delete=models.CASCADE, help_text='Módulo en el cual dicha referencia va a ser usada', related_name='references', blank=True, null=True)
    context = models.CharField(max_length=100, blank=True, default='', help_text='Descripción o valor que indica el contexto de uso (formato notacion_guion_bajo). Ej: mapeo_columnas_archivo_ventas')
    key = models.CharField(max_length=100, blank=True, default='', help_text='Valor crudo usado para ser mapeado')
    value = models.CharField(max_length=100, blank=True, default='', help_text='Valor homologado resultante del mapeo')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True, related_name='references', help_text='Tabla o modelo al cual se le aplica el valor homologado de la referencia')

    def __str__(self):
        sub_name = self.submodule.name.title() if self.submodule and getattr(self.submodule, 'name', None) else "General"
        ctx = self.context or "sin_contexto"
        return f"{sub_name}: {ctx} ({self.key} -> {self.value})"

    @property
    def reference(self):
        return self.value

    class Meta:
        verbose_name = 'Referencia'
        verbose_name_plural = 'Referencias'

class GeneratedReport(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'En proceso'
        COMPLETED = 'completed', 'Completado'
        FAILED = 'failed', 'Error'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_reports')
    title = models.CharField(max_length=255, help_text="Título descriptivo del reporte")
    module_name = models.CharField(max_length=100, default='analytics', help_text="Módulo de origen")
    file = models.FileField(upload_to='reports/%Y/%m/', null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default='')
    filters = models.JSONField(default=dict, blank=True)
    is_seen = models.BooleanField(default=False, help_text="Indica si el usuario ya vio el reporte completado")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} - {self.user.username} ({self.get_status_display()})"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Reporte Generado'
        verbose_name_plural = 'Reportes Generados'

class AppVersion(models.Model):
    class VersionType(models.TextChoices):
        MAJOR = 'MAJOR', 'Mayor'
        MINOR = 'MINOR', 'Menor'
        PATCH = 'PATCH', 'Parche'

    version_number = models.CharField(max_length=50, unique=True, verbose_name="Version number", help_text="Example: 1.0.0, 2.1.4-beta")
    release_type = models.CharField(max_length=10, choices=VersionType.choices, default=VersionType.PATCH, verbose_name="Release type")
    release_date = models.DateField(verbose_name="Release date", help_text="Release date")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    title = models.CharField(max_length=200, blank=True, verbose_name="Short Title", help_text="Example: Security update or UI redesign")
    description = models.TextField(verbose_name="Details", help_text="Describe the changes detailed. You can use Markdown format.")
    is_published = models.BooleanField(default=False, verbose_name="Published", help_text="If checked, it will be displayed in the public documentation.")

    class Meta:
        ordering = ['-release_date', '-id']
        verbose_name = "Versión"
        verbose_name_plural = "Versiones"

    def __str__(self):
        return f"v{self.version_number} ({self.release_date})"

class SupportCategory(models.Model):
    name = models.CharField(max_length=100, help_text="Nombre de categoría")
    description = models.CharField(max_length=255, blank=True, default="", help_text="Descripción corta")
    icon = models.CharField(max_length=50, default="help-circle", help_text="Nombre del ícono Lucide (ej: help-circle, key, shield, file-text, phone, sliders, database, user)")
    order = models.PositiveIntegerField(default=0, help_text="Orden de visualización")
    is_active = models.BooleanField(default=True, help_text="Activa")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = "Categoría de Soporte"
        verbose_name_plural = "Categorías de Soporte"

    def __str__(self):
        return self.name

class SupportArticle(models.Model):
    category = models.ForeignKey(SupportCategory, on_delete=models.CASCADE, related_name="articles", help_text="Categoría")
    title = models.CharField(max_length=200, help_text="Título o Pregunta")
    content = models.TextField(help_text="Describe la solución o guía. Puedes usar formato Markdown.")
    order = models.PositiveIntegerField(default=0, help_text="Orden")
    is_published = models.BooleanField(default=True, help_text="Publicado")
    is_highlighted = models.BooleanField(default=False, help_text="Si se marca, se muestra en la sección de preguntas destacadas/frecuentes.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__order', 'order', 'title']
        verbose_name = "Artículo / Pregunta"
        verbose_name_plural = "Artículos y Preguntas"

    def __str__(self):
        return f"{self.category.name} - {self.title}"
