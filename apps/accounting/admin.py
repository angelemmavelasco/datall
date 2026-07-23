from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import Account, JournalEntry, JournalEntryLine


# @admin.register(Account)
# class AccountAdmin(admin.ModelAdmin):
#     list_display = ['code', 'name', 'account_type', 'formatted_balance']
#     list_filter = ['account_type']
#     search_fields = ['code', 'name']
#     readonly_fields = ['balance']

#     def formatted_balance(self, obj):
#         color = 'green' if obj.balance >= 0 else 'red'
#         amount = f"${abs(obj.balance):,.2f}"
#         return format_html(
#             '<span style="color: {}; font-weight: bold;">{}</span>',
#             color,
#             amount
#         )
#     formatted_balance.short_description = 'Saldo'


# class JournalEntryLineInline(admin.TabularInline):
#     model = JournalEntryLine
#     extra = 2

#     def get_readonly_fields(self, request, obj=None):
#         if obj and obj.is_posted:
#             return ['account', 'debit', 'credit', 'description']
#         return super().get_readonly_fields(request, obj)

#     def has_add_permission(self, request, obj=None):
#         if obj and obj.is_posted:
#             return False
#         return super().has_add_permission(request, obj)

#     def has_delete_permission(self, request, obj=None):
#         if obj and obj.is_posted:
#             return False
#         return super().has_delete_permission(request, obj)


# @admin.register(JournalEntry)
# class JournalEntryAdmin(admin.ModelAdmin):
#     list_display = [
#         'date', 
#         'reference', 
#         'description', 
#         'is_posted'
#     ]
#     list_filter = ['date', 'is_posted']
#     search_fields = ['reference', 'description']
#     inlines = [JournalEntryLineInline]
#     actions = ['post_entries']

#     def get_readonly_fields(self, request, obj=None):
#         if obj and obj.is_posted:
#             return ['date', 'reference', 'description', 'is_posted']
#         return ['is_posted']

#     def post_entries(self, request, queryset):
#         """Acción masiva para aplicar asientos contables seleccionados."""
#         posted_count = 0
#         unposted_entries = queryset.filter(is_posted=False)

#         if not unposted_entries.exists():
#             self.message_user(
#                 request,
#                 'Los asientos seleccionados ya estaban aplicados.',
#                 level=messages.WARNING
#             )
#             return

#         for entry in unposted_entries:
#             try:
#                 entry.post()
#                 posted_count += 1
#             except ValidationError as e:
#                 self.message_user(
#                     request,
#                     f'Error en asiento {entry.reference}: {str(e)}',
#                     level=messages.ERROR
#                 )
#                 return

#         self.message_user(
#             request,
#             f'Se aplicaron {posted_count} asiento(s) correctamente.',
#             level=messages.SUCCESS
#         )

#     post_entries.short_description = "Aplicar asientos seleccionados"