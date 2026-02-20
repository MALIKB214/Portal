from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:invoice_id>/", views.invoice_detail, name="invoice_detail"),
    path("payments/<int:payment_id>/receipt/", views.receipt, name="receipt"),
]