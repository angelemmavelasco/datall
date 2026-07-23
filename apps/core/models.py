from django.core.validators import RegexValidator
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.conf import settings


class User(AbstractUser):
    second_last_name = models.CharField(max_length=150, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[('f', 'Femenino'),('m', 'Masculino'),('nb', 'No binario'),('o', 'Otro')], null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True, validators=[RegexValidator(regex=r'^\d{10,15}$', message='El teléfono debe contener solo números.')])
    street = models.CharField(max_length=255, null=True, blank=True)
    street_no = models.CharField(max_length=255, null=True, blank=True)
    apt_suite = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    zipcode = models.CharField(max_length=255, null=True, blank=True)
    tax_id = models.CharField(max_length=13, null=True, blank=True)
    unique_personal_id = models.CharField(max_length=20, null=True, blank=True)
    notes = models.TextField(max_length=500, null=True, blank=True)
    photo = models.FileField(upload_to='users/photos', null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.username}"

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

class Periodicity(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Periodicidad"
        verbose_name_plural = "Periodicidades"
        ordering = ["id"]

    def __str__(self):
        return f"{self.id} - {self.name}"

class Reference(models.Model):
    context = models.CharField(max_length=100)
    key = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = 'Referencia'
        verbose_name_plural = 'Referencias'
        constraints = [
            models.UniqueConstraint(
                fields=['context', 'key', 'content_type'], 
                name='unique_context_key_mapping'
            )
        ]
        indexes = [
            models.Index(fields=['context', 'key']),
        ]

    def __str__(self):
        return f'[{self.context}] | {self.key} -> {self.value}'
