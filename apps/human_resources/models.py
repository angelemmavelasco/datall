from django.db import models

class Department(models.Model):
    id = models.CharField(max_length=3, primary_key=True, help_text='Identificador único del departamento')
    name = models.CharField(max_length=255, help_text='Nombre del departamento')
    description = models.TextField(null=True, blank=True, help_text='Descripción del departamento')

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

# class TaxSystem(models.Model):
#     id = models.CharField(max_length=3, primary_key=True, help_text='Identificador único del sistema de impuestos')
#     name = models.CharField(unique=True, max_length=255, help_text='Nombre del sistema de impuestos')
#     description = models.TextField(max_length=500, null=True, blank=True, help_text='Descripción del sistema de impuestos')

#     class Meta:
#         verbose_name = 'Tax system'
#         verbose_name_plural = 'Tax systems'
#         db_table = 'tax_systems'

#     def __str__(self):
#         return f'{self.id.upper()} {self.name.title()}'


# class PayrollType(models.Model):
#     id = models.CharField(max_length=20,primary_key=True, help_text='Identificador único del tipo de nómina')
#     name = models.CharField(max_length=100,unique=True, help_text='Nombre del tipo de nómina')
#     description = models.TextField(max_length=500, blank=True, null=True, help_text='Descripción del tipo de nómina')

#     class Meta:
#         verbose_name = "Tipo de nómina"
#         verbose_name_plural = "Tipos de nómina"
#         db_table = 'payroll_types'

#     def __str__(self):
#         return f"{self.id.upper()} {self.name.title()}"


# class Periodicity(models.Model):
#     id = models.CharField(max_length=20, primary_key=True)
#     name = models.CharField(max_length=255)

#     class Meta:
#         verbose_name = "Periodicity"
#         verbose_name_plural = "Periodicities"
#         ordering = ["id"]
#         db_table = "periodicities"

#     def __str__(self):
#         return f"{self.id} - {self.name}"

class Position(models.Model):
    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del puesto')
    name = models.CharField(max_length=255, unique=True, help_text='Nombre del puesto')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='%(app_label)s_positions', help_text='Departamento al que pertenece el puesto')
    description = models.TextField(max_length=255, null=True, blank=True, help_text='Descripción del puesto')

    class Meta:
        verbose_name = 'Puesto'
        verbose_name_plural = 'Puestos'

class Employee(models.Model):
    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del colaborador')
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, null=True, blank=True, related_name='%(app_label)s_employees')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, null=True, blank=True, related_name='%(app_label)s_employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='%(app_label)s_direct_reports')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'

    def get_reporting_tree_ids(self):
        """
        Returns a flatten list with this employee Id and all the employees that report to this employee directly or indirectly.
        """
        tree_ids = [self.id]
        direct_reports = Employee.objects.filter(manager=self)
        for report in direct_reports:
            tree_ids.extend(report.get_reporting_tree_ids())
        return list(set(tree_ids))




