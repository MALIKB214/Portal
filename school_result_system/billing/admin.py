from django.contrib import admin
from .models import FeeCategory, FinanceEvent, Invoice, InvoiceItem, Payment


@admin.register(FeeCategory)
class FeeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category_type", "is_active")
    list_filter = ("category_type", "is_active")
    search_fields = ("name",)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "session", "term", "status", "created_at")
    list_filter = ("status", "session")
    search_fields = ("student__first_name", "student__last_name", "student__admission_number")
    inlines = [InvoiceItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "invoice", "amount", "method", "approval_status", "is_reversed", "paid_at")
    list_filter = ("method", "approval_status", "is_reversed", "paid_at")
    search_fields = ("receipt_number", "invoice__student__admission_number")


@admin.register(FinanceEvent)
class FinanceEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "invoice", "payment", "amount_delta", "performed_by", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("invoice__id", "payment__receipt_number", "note")
