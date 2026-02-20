from django import forms
from .models import Invoice, InvoiceItem, Payment


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["student", "session", "term"]


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["category", "description", "amount"]


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "reference", "notes"]