from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .forms import InvoiceForm, InvoiceItemForm, PaymentForm
from .models import Invoice, InvoiceItem, Payment
from accounts.permissions import proprietor_required


def update_invoice_status(invoice):
    if invoice.balance <= 0 and invoice.total_amount > 0:
        invoice.status = "paid"
    elif invoice.paid_amount > 0:
        invoice.status = "partial"
    else:
        invoice.status = "unpaid"
    invoice.save(update_fields=["status"])


@proprietor_required
def invoice_list(request):
    invoices = Invoice.objects.select_related("student", "session", "term").order_by("-id")
    return render(request, "billing/invoice_list.html", {"invoices": invoices})


@proprietor_required
def invoice_create(request):
    if request.method == "POST":
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save()
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
    else:
        form = InvoiceForm()

    return render(request, "billing/invoice_create.html", {"form": form})


@proprietor_required
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    item_form = InvoiceItemForm()
    payment_form = PaymentForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_item":
            item_form = InvoiceItemForm(request.POST)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.invoice = invoice
                item.save()
                update_invoice_status(invoice)
                return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "add_payment":
            payment_form = PaymentForm(request.POST)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.invoice = invoice
                payment.received_by = request.user
                payment.save()
                update_invoice_status(invoice)
                return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "approve_payment":
            payment_id = request.POST.get("payment_id")
            approval_note = (request.POST.get("approval_note") or "").strip()
            payment = get_object_or_404(Payment, id=payment_id, invoice=invoice)
            if payment.approve(request.user, note=approval_note):
                update_invoice_status(invoice)
                messages.success(request, "Payment approved.")
            else:
                messages.warning(request, "Payment is already processed.")
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "reject_payment":
            payment_id = request.POST.get("payment_id")
            approval_note = (request.POST.get("approval_note") or "").strip()
            payment = get_object_or_404(Payment, id=payment_id, invoice=invoice)
            if payment.reject(request.user, note=approval_note):
                update_invoice_status(invoice)
                messages.success(request, "Payment rejected.")
            else:
                messages.warning(request, "Payment is already processed.")
            return redirect("billing:invoice_detail", invoice_id=invoice.id)

    context = {
        "invoice": invoice,
        "item_form": item_form,
        "payment_form": payment_form,
    }
    return render(request, "billing/invoice_detail.html", context)


@proprietor_required
def receipt(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    return render(request, "billing/receipt.html", {"payment": payment})
