from django.core.exceptions import ValidationError
from django.db import models, transaction
from decimal import Decimal

class Account(models.Model):
    """
    Represents an accounting account, e.g. cash, bank accounts, accounts receivable, accounts payable, etc.
    """
    ACCOUNT_TYPES = [
        ('ASSET', 'Activo'),      # Aumenta con debe
        ('LIABILITY', 'Pasivo'),  # Aumenta con el haber
        ('EQUITY', 'Capital'),    # Aumenta con el haber
        ('INCOME', 'Ingreso'),    # Aumenta con el haber
        ('EXPENSE', 'Gasto')      # Aumenta con debe
    ]
    code = models.CharField(max_length=20, unique=True, help_text="Código único de la cuenta según el plan contable, ej: 110501")
    name = models.CharField(max_length=100, help_text="Nombre de la cuenta, ej: Caja General")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, help_text="Tipo de cuenta")
    balance = models.DecimalField(max_digits=18, decimal_places=6, default=0.0, help_text="Saldo actual de la cuenta")

    @property
    def increases_with_debit(self):
        """determines if the account increases with debit"""
        return self.account_type in ('ASSET', 'EXPENSE')

    def update_balance(self, debit=0, credit=0):
        """Updates the balance of the account"""
        debit = Decimal(str(debit))
        credit = Decimal(str(credit))
        if self.increases_with_debit:
            self.balance += debit - credit
        else:
            self.balance += credit - debit
        self.save()
    
    def __str__(self):
        return f"{self.code.upper()} {self.name.title()}"

    class Meta:
        verbose_name = "Cuenta contable"
        verbose_name_plural = "Cuentas contables"
        ordering = ['code']
        db_table = "accounts"
    
class JournalEntry(models.Model):
    """
    Represents a journal entry, which is a record of a financial transaction.
    """
    date = models.DateField(help_text="Fecha de la transacción")
    reference = models.CharField(max_length=50, unique=True, help_text="Referencia de la transacción")
    description = models.CharField(max_length=200, help_text="Descripción de la transacción")
    is_posted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Validates that the journal entry is balanced"""
        if self.pk:
            if not self.lines.exists():
                raise ValidationError('El asiento debe tener al menos dos líneas.')
            total_debit = sum(line.debit for line in self.lines.all())
            total_credit = sum(line.credit for line in self.lines.all())
            if total_debit != total_credit:
                raise ValidationError('El asiento no está equilibrado. Los débitos deben ser iguales a los créditos.')
    
    @transaction.atomic
    def post(self):
        """Applies the journal entry updating the balances"""
        if not self.pk:
            raise ValidationError('Debes guardar el asiento antes de aplicarlo.')
        if self.is_posted:
            raise ValidationError('Este asiento ya fue aplicado')

        lines = list(self.lines.select_for_update().select_related('account'))

        self.clean()  # Validar balance

        for line in lines:
            line.account.update_balance(
                debit=line.debit,
                credit=line.credit
            )

        self.is_posted = True
        self.save(update_fields=['is_posted'])


    def __str__(self):
        return f"{self.date} {self.description}"

    class Meta:
        db_table = "journal_entries"
        verbose_name = "Asiento contable"
        verbose_name_plural = "Asientos contables"
        ordering = ['date']


class JournalEntryLine(models.Model):
    """
    Represents a line item in a journal entry
    """
    entry = models.ForeignKey(JournalEntry, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.000000'))
    credit = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.000000'))
    description = models.CharField(max_length=200, blank=True, null=True)

    def clean(self):
        """validates that line has either debit or credit, but not both"""
        if self.pk and self.entry_id:
            # Prevent editing lines if the entry was ALREADY posted in the database
            if JournalEntry.objects.filter(pk=self.entry_id, is_posted=True).exists():
                raise ValidationError('No se pueden editar líneas de un asiento ya aplicado.')
        if self.debit < 0 or self.credit < 0:
            raise ValidationError('Los valores de débito y crédito deben ser positivos')
        if self.debit > 0 and self.credit > 0:
            raise ValidationError('Una línea no puede tener débito y crédito simultáneamente')
        if self.debit == 0 and self.credit == 0:
            raise ValidationError('Debe especificar un valor de débito o crédito mayor a cero.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        if self.entry.is_posted:
            raise ValidationError('No se pueden eliminar líneas de un asiento ya aplicado')
        super().delete(*args, **kwargs)

    def __str__(self):
        account_str = f"{self.account.code} {self.account.name}" if self.account_id else "Sin cuenta"
        return f"{account_str} | D: ${self.debit:,.2f} C: ${self.credit:,.2f}"

    
        
    