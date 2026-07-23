from django.db import models


class MenuSection(models.Model):
    """
    Handle module grouping on the navigation bar
    """
    name = models.CharField(max_length=50, unique=True, help_text="Nombre de la sección de menú")
    order = models.PositiveIntegerField(default=0, help_text="Orden de aparición en el menú")
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Sección de menú'
        verbose_name_plural = 'Secciones de menú'  
        
    def __str__(self):
        return self.name.title

class SystemModule(models.Model):
    """
    Handle each system module
    """
    section = models.ForeignKey('MenuSection', on_delete=models.CASCADE, related_name='modules', help_text="Sección a la que pertenece el módulo")
    name = models.CharField(max_length=100, help_text="Nombre del módulo")
    url_name = models.CharField(max_length=150, help_text="Nombre de la URL (ej. 'business_intelligence:sales_dashboard')")
    allowed_groups = models.ManyToManyField('auth.Group', related_name='accessible_modules', help_text="Grupos permitidos para acceder al módulo")
    order = models.PositiveIntegerField(default=0, help_text="Orden de aparición dentro de la sección")
    is_active = models.BooleanField(default=True, help_text="Indica si el módulo está activo")

    class Meta:
        ordering = ['section__order', 'order']
        verbose_name = 'Módulo del sistema'
        verbose_name_plural = 'Módulos del sistema'  
        
    def __str__(self):
        return f"{self.section.name} -> {self.name}"

class AppVersion(models.Model):
    class VersionType(models.TextChoices):
        MAJOR = 'MAJOR', 'Mayor'
        MINOR = 'MINOR', 'Menor'
        PATCH = 'PATCH', 'Parche'

    version_number = models.CharField(max_length=50, unique=True, help_text="Número de versión, ej. 1.0.0, 2.1.4-beta")
    release_type = models.CharField(max_length=10, choices=VersionType.choices, default=VersionType.PATCH, help_text="Tipo de lanzamiento")
    release_date = models.DateField(help_text="Fecha de lanzamiento")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Fecha y hora de creación")
    updated_at = models.DateTimeField(auto_now=True, help_text="Fecha y hora de actualización")
    title = models.CharField(max_length=200, blank=True, help_text="Título corto, ej. Actualización de seguridad o Rediseño de UI")
    description = models.TextField(help_text="Descripción detallada de los cambios.")
    is_published = models.BooleanField(default=False, help_text="Si está marcado, se mostrará en la documentación pública.")

    class Meta:
        ordering = ['-release_date', '-id']
        verbose_name = "Versión de la aplicación"
        verbose_name_plural = "Versiones de la aplicación"

    def __str__(self):
        return f"v{self.version_number} ({self.release_date})"

class Novelty(models.Model):
    title = models.CharField(max_length=255, help_text="Título de la novedad")
    content = models.TextField(help_text="Contenido de la novedad")
    image = models.FileField(upload_to='novelties', null=True, blank=True, help_text="Imagen opcional para la novedad")
    is_active = models.BooleanField(default=True, help_text="Indica si la novedad está activa")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Fecha y hora de creación")

    class Meta:
        verbose_name = 'Novedad'
        verbose_name_plural = 'Novedades'
        indexes = [
            models.Index(fields=["created_at"]), 
        ]

    def __str__(self):
        return self.title.title()
