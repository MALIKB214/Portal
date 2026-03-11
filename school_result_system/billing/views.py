from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.db.models import Sum
from .forms import InvoiceForm, InvoiceItemForm, PaymentForm
from .models import FinanceEvent, Invoice, InvoiceItem, Payment
from accounts.permissions import finance_monitor_required
from accounts.capabilities import (
    CAP_APPROVE_FINANCE,
    CAP_RECORD_FINANCE,
    CAP_REVERSE_FINANCE,
    CAP_VOID_INVOICE,
    has_capability,
)
from academics.models import AcademicSession, Term
from students.models import Student
from results.models import Notification
from results.notifications import (
    create_parent_notification,
    format_outstanding_reminder_email,
    format_payment_approval_email,
    send_parent_email,
)
from accounts.notifications import notify_staff_event
from accounts.models import User, StaffNotification


def update_invoice_status(invoice):
    if invoice.status == "void":
        return
    if invoice.balance <= 0 and invoice.total_amount > 0:
        invoice.status = "paid"
    elif invoice.paid_amount > 0:
        invoice.status = "partial"
    else:
        invoice.status = "unpaid"
    invoice.save(update_fields=["status"])


def log_finance_event(
    event_type,
    user,
    invoice=None,
    payment=None,
    invoice_item=None,
    amount_delta=0,
    note="",
    metadata=None,
):
    FinanceEvent.objects.create(
        event_type=event_type,
        performed_by=user if user and user.is_authenticated else None,
        invoice=invoice,
        payment=payment,
        invoice_item=invoice_item,
        amount_delta=amount_delta,
        note=note or "",
        metadata=metadata or {},
    )


def create_finance_notification(student, message, session=None, term=None):
    return create_parent_notification(
        student=student,
        session=session,
        term=term,
        message=message,
        category=Notification.CATEGORY_FINANCE,
    )


ACTION_CAPABILITY_MAP = {
    "add_item": CAP_RECORD_FINANCE,
    "add_payment": CAP_RECORD_FINANCE,
    "approve_payment": CAP_APPROVE_FINANCE,
    "reject_payment": CAP_APPROVE_FINANCE,
    "reverse_payment": CAP_REVERSE_FINANCE,
    "void_invoice": CAP_VOID_INVOICE,
}


CAPABILITY_MESSAGE = {
    CAP_RECORD_FINANCE: "Only bursar can perform this financial action.",
    CAP_APPROVE_FINANCE: "Only principal/admin/proprietor can approve or reject payment.",
    CAP_REVERSE_FINANCE: "Only proprietor/admin can reverse payments.",
    CAP_VOID_INVOICE: "Only proprietor/admin can void invoice.",
}


@finance_monitor_required
def dashboard(request):
    session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.order_by("-id").first()
    term = Term.objects.filter(session=session, is_active=True).first() if session else None

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = Term.objects.filter(session=session, is_active=True).first() if session else None
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    invoices = Invoice.objects.select_related("student", "session", "term").prefetch_related("items", "payments")
    if session:
        invoices = invoices.filter(session=session)
    if term:
        invoices = invoices.filter(term=term)

    payments = Payment.objects.select_related("invoice", "invoice__student")
    if session:
        payments = payments.filter(invoice__session=session)
    if term:
        payments = payments.filter(invoice__term=term)

    approved_revenue = payments.filter(approval_status="approved").aggregate(total=Sum("amount"))["total"] or 0
    pending_amount = payments.filter(approval_status="pending").aggregate(total=Sum("amount"))["total"] or 0
    total_outstanding = sum(invoice.balance for invoice in invoices)
    fully_paid_count = sum(1 for invoice in invoices if invoice.balance <= 0 and invoice.total_amount > 0)
    owing_count = sum(1 for invoice in invoices if invoice.balance > 0)

    class_outstanding = {}
    for invoice in invoices:
        cls = invoice.student.class_name or "Unassigned"
        class_outstanding[cls] = class_outstanding.get(cls, 0) + invoice.balance

    class_outstanding_rows = [
        {"class_name": class_name, "balance": balance}
        for class_name, balance in sorted(class_outstanding.items(), key=lambda x: x[1], reverse=True)
    ]

    context = {
        "sessions": AcademicSession.objects.all().order_by("-id"),
        "terms": Term.objects.filter(session=session).order_by("order") if session else [],
        "selected_session": session,
        "selected_term": term,
        "approved_revenue": approved_revenue,
        "pending_amount": pending_amount,
        "total_outstanding": total_outstanding,
        "fully_paid_count": fully_paid_count,
        "owing_count": owing_count,
        "recent_payments": payments.order_by("-paid_at")[:12],
        "pending_payments": payments.filter(approval_status="pending").order_by("-paid_at")[:12],
        "class_outstanding_rows": class_outstanding_rows,
    }
    return render(request, "billing/dashboard.html", context)


@finance_monitor_required
def invoice_list(request):
    invoices = (
        Invoice.objects.select_related("student", "session", "term")
        .prefetch_related("items", "payments")
        .order_by("-id")
    )
    can_create_invoice = has_capability(request.user, CAP_RECORD_FINANCE)
    total_revenue = sum(invoice.paid_amount for invoice in invoices)
    total_outstanding = sum(invoice.balance for invoice in invoices)
    fully_paid_count = sum(1 for invoice in invoices if invoice.balance <= 0 and invoice.total_amount > 0)
    owing_count = sum(1 for invoice in invoices if invoice.balance > 0)
    return render(
        request,
        "billing/invoice_list.html",
        {
            "invoices": invoices,
            "can_create_invoice": can_create_invoice,
            "total_revenue": total_revenue,
            "total_outstanding": total_outstanding,
            "fully_paid_count": fully_paid_count,
            "owing_count": owing_count,
        },
    )


@finance_monitor_required
def invoice_create(request):
    if not has_capability(request.user, CAP_RECORD_FINANCE):
        messages.error(request, CAPABILITY_MESSAGE[CAP_RECORD_FINANCE])
        return redirect("billing:invoice_list")
    if request.method == "POST":
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = form.save()
            log_finance_event(
                event_type="invoice_created",
                user=request.user,
                invoice=invoice,
                amount_delta=0,
                note="Invoice created",
            )
            if invoice.balance > 0:
                create_finance_notification(
                    invoice.student,
                    f"New invoice created. Outstanding balance: {invoice.balance}.",
                    session=invoice.session,
                    term=invoice.term,
                )
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
    else:
        form = InvoiceForm()

    return render(request, "billing/invoice_create.html", {"form": form})


@finance_monitor_required
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(
        Invoice.objects.select_related("student", "session", "term")
        .prefetch_related("items__category", "payments", "events__performed_by"),
        id=invoice_id,
    )
    item_form = InvoiceItemForm()
    payment_form = PaymentForm()
    can_record_money = has_capability(request.user, CAP_RECORD_FINANCE)
    can_approve_payment = has_capability(request.user, CAP_APPROVE_FINANCE)
    can_reverse_payment = has_capability(request.user, CAP_REVERSE_FINANCE)
    can_void_invoice = has_capability(request.user, CAP_VOID_INVOICE)

    if request.method == "POST":
        action = request.POST.get("action")
        required_capability = ACTION_CAPABILITY_MAP.get(action)
        if required_capability and not has_capability(request.user, required_capability):
            messages.error(request, CAPABILITY_MESSAGE.get(required_capability, "Not authorized."))
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
        if invoice.status == "void" and action in {"add_item", "add_payment", "approve_payment", "reject_payment", "reverse_payment"}:
            messages.error(request, "Voided invoices are locked.")
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
        if action == "add_item":
            item_form = InvoiceItemForm(request.POST)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.invoice = invoice
                item.save()
                update_invoice_status(invoice)
                log_finance_event(
                    event_type="invoice_item_added",
                    user=request.user,
                    invoice=invoice,
                    invoice_item=item,
                    amount_delta=item.amount,
                    note=item.description or item.category.name,
                )
                if invoice.balance > 0:
                    create_finance_notification(
                        invoice.student,
                        f"Invoice updated. Outstanding balance: {invoice.balance}.",
                        session=invoice.session,
                        term=invoice.term,
                    )
                return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "add_payment":
            payment_form = PaymentForm(request.POST)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.invoice = invoice
                payment.received_by = request.user
                payment.save()
                update_invoice_status(invoice)
                log_finance_event(
                    event_type="payment_created",
                    user=request.user,
                    invoice=invoice,
                    payment=payment,
                    amount_delta=payment.amount,
                    note=payment.notes,
                )
                return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "approve_payment":
            payment_id = request.POST.get("payment_id")
            approval_note = (request.POST.get("approval_note") or "").strip()
            payment = get_object_or_404(Payment, id=payment_id, invoice=invoice)
            if payment.approve(request.user, note=approval_note):
                update_invoice_status(invoice)
                log_finance_event(
                    event_type="payment_approved",
                    user=request.user,
                    invoice=invoice,
                    payment=payment,
                    amount_delta=0,
                    note=approval_note,
                )
                bursars = User.objects.filter(groups__name="Bursar")
                for bursar in bursars:
                    notify_staff_event(
                        bursar,
                        f"Payment approved for {invoice.student.full_name}.",
                        category=StaffNotification.CATEGORY_FINANCE,
                        email_subject=f"Payment Approved - {invoice.student.full_name}",
                        email_body=(
                            f"A payment for {invoice.student.full_name} was approved.\n"
                            f"Invoice: #{invoice.id}\n"
                            f"Amount: {payment.amount}"
                        ),
                        send_email=True,
                    )
                if invoice.balance > 0:
                    create_finance_notification(
                        invoice.student,
                        f"Payment approved. Outstanding balance: {invoice.balance}.",
                        session=invoice.session,
                        term=invoice.term,
                    )
                else:
                    create_finance_notification(
                        invoice.student,
                        "Payment approved. Your invoice is fully settled.",
                        session=invoice.session,
                        term=invoice.term,
                    )
                subject, body = format_payment_approval_email(
                    invoice.student,
                    payment.amount,
                    invoice.term,
                    invoice.session,
                    receipt_number=payment.receipt_number,
                )
                send_parent_email(subject, body, invoice.student)
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
                log_finance_event(
                    event_type="payment_rejected",
                    user=request.user,
                    invoice=invoice,
                    payment=payment,
                    amount_delta=0,
                    note=approval_note,
                )
                bursars = User.objects.filter(groups__name="Bursar")
                for bursar in bursars:
                    notify_staff_event(
                        bursar,
                        f"Payment rejected for {invoice.student.full_name}.",
                        category=StaffNotification.CATEGORY_FINANCE,
                        email_subject=f"Payment Rejected - {invoice.student.full_name}",
                        email_body=(
                            f"A payment for {invoice.student.full_name} was rejected.\n"
                            f"Invoice: #{invoice.id}\n"
                            f"Amount: {payment.amount}"
                        ),
                        send_email=True,
                    )
                create_finance_notification(
                    invoice.student,
                    "Payment was rejected. Please contact bursary for clarification.",
                    session=invoice.session,
                    term=invoice.term,
                )
                messages.success(request, "Payment rejected.")
            else:
                messages.warning(request, "Payment is already processed.")
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "reverse_payment":
            payment_id = request.POST.get("payment_id")
            reversal_note = (request.POST.get("reversal_note") or "").strip()
            payment = get_object_or_404(Payment, id=payment_id, invoice=invoice)
            if payment.reverse(request.user, note=reversal_note):
                update_invoice_status(invoice)
                log_finance_event(
                    event_type="payment_reversed",
                    user=request.user,
                    invoice=invoice,
                    payment=payment,
                    amount_delta=-payment.amount,
                    note=reversal_note,
                )
                create_finance_notification(
                    invoice.student,
                    f"A payment was reversed. Outstanding balance: {invoice.balance}.",
                    session=invoice.session,
                    term=invoice.term,
                )
                messages.success(request, "Payment reversed.")
            else:
                messages.warning(request, "Payment is already reversed.")
            return redirect("billing:invoice_detail", invoice_id=invoice.id)
        elif action == "void_invoice":
            void_note = (request.POST.get("void_note") or "").strip()
            if invoice.status == "void":
                messages.info(request, "Invoice is already voided.")
            else:
                invoice.status = "void"
                invoice.save(update_fields=["status"])
                log_finance_event(
                    event_type="invoice_voided",
                    user=request.user,
                    invoice=invoice,
                    amount_delta=0,
                    note=void_note,
                )
                create_finance_notification(
                    invoice.student,
                    "Your invoice was voided by school finance office.",
                    session=invoice.session,
                    term=invoice.term,
                )
                messages.success(request, "Invoice voided successfully.")
            return redirect("billing:invoice_detail", invoice_id=invoice.id)

    context = {
        "invoice": invoice,
        "item_form": item_form,
        "payment_form": payment_form,
        "can_record_money": can_record_money,
        "can_approve_payment": can_approve_payment,
        "can_reverse_payment": can_reverse_payment,
        "can_void_invoice": can_void_invoice,
        "finance_events": invoice.events.select_related("performed_by", "payment", "invoice_item")[:20],
    }
    return render(request, "billing/invoice_detail.html", context)


@finance_monitor_required
def receipt(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    return render(request, "billing/receipt.html", {"payment": payment})


def parent_receipt(request, payment_id):
    student_id = request.session.get("parent_student_id")
    if not student_id:
        messages.error(request, "Login to parent portal to access receipts.")
        return redirect("results:parent_login")

    payment = get_object_or_404(
        Payment.objects.select_related("invoice", "invoice__student"),
        id=payment_id,
    )
    if payment.invoice.student_id != student_id:
        return HttpResponseForbidden("You are not authorized to view this receipt.")
    return render(request, "billing/receipt.html", {"payment": payment})


def my_payment_history(request):
    student_id = request.session.get("parent_student_id")
    if not student_id:
        messages.error(request, "Login to parent portal to view payment history.")
        return redirect("results:parent_login")

    student = get_object_or_404(Student, id=student_id)
    invoices = (
        Invoice.objects.filter(student=student)
        .select_related("session", "term")
        .prefetch_related("items__category", "payments")
        .order_by("-created_at")
    )
    totals = {
        "billed": sum(invoice.total_amount for invoice in invoices),
        "paid": sum(invoice.paid_amount for invoice in invoices),
        "balance": sum(invoice.balance for invoice in invoices),
    }

    return render(
        request,
        "billing/my_payment_history.html",
        {"student": student, "invoices": invoices, "totals": totals},
    )


@finance_monitor_required
def reconciliation_report(request):
    session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.order_by("-id").first()
    term = Term.objects.filter(session=session, is_active=True).first() if session else None
    class_name = (request.GET.get("class_name") or "").strip()

    if request.GET.get("session"):
        session = AcademicSession.objects.filter(id=request.GET.get("session")).first()
        term = Term.objects.filter(session=session, is_active=True).first() if session else None
    if request.GET.get("term"):
        term = Term.objects.filter(id=request.GET.get("term"), session=session).first()

    invoices = (
        Invoice.objects.select_related("student", "session", "term")
        .prefetch_related("items", "payments__received_by", "payments__approved_by", "payments__reversed_by")
        .order_by("-id")
    )
    if session:
        invoices = invoices.filter(session=session)
    if term:
        invoices = invoices.filter(term=term)
    if class_name:
        invoices = invoices.filter(student__class_name=class_name)

    rows = []
    totals = {
        "billed": 0,
        "approved": 0,
        "pending": 0,
        "rejected": 0,
        "reversed": 0,
        "balance": 0,
    }
    for invoice in invoices:
        billed = float(invoice.total_amount or 0)
        approved = sum(
            float(p.amount)
            for p in invoice.payments.all()
            if p.approval_status == "approved" and not p.is_reversed
        )
        pending = sum(
            float(p.amount) for p in invoice.payments.all() if p.approval_status == "pending"
        )
        rejected = sum(
            float(p.amount) for p in invoice.payments.all() if p.approval_status == "rejected"
        )
        reversed_amount = sum(
            float(p.amount) for p in invoice.payments.all() if p.is_reversed
        )
        balance = float(invoice.balance or 0)
        chain = " | ".join(
            [
                (
                    f"{p.receipt_number or '-'}:"
                    f"{p.approval_status}"
                    f"{' (reversed)' if p.is_reversed else ''}"
                    f" by {p.approved_by.username if p.approved_by else '-'}"
                )
                for p in invoice.payments.all()
            ]
        )

        totals["billed"] += billed
        totals["approved"] += approved
        totals["pending"] += pending
        totals["rejected"] += rejected
        totals["reversed"] += reversed_amount
        totals["balance"] += balance

        rows.append(
            {
                "invoice": invoice,
                "billed": billed,
                "approved": approved,
                "pending": pending,
                "rejected": rejected,
                "reversed": reversed_amount,
                "balance": balance,
                "approval_chain": chain,
            }
        )

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        filename = f"reconciliation_{session}_{term}.csv".replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write(
            "Invoice ID,Student,Class,Session,Term,Status,Billed,Approved,Pending,Rejected,Reversed,Balance,Approval Chain\n"
        )
        for row in rows:
            invoice = row["invoice"]
            response.write(
                f'{invoice.id},"{invoice.student.full_name}","{invoice.student.class_name}",'
                f'"{invoice.session}","{invoice.term or ""}","{invoice.status}",'
                f'{row["billed"]},{row["approved"]},{row["pending"]},{row["rejected"]},'
                f'{row["reversed"]},{row["balance"]},"{row["approval_chain"]}"\n'
            )
        return response
    if request.GET.get("export") == "pdf":
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
        except Exception:
            messages.error(request, "PDF export requires reportlab.")
            return redirect("billing:reconciliation_report")

        response = HttpResponse(content_type="application/pdf")
        filename = f"reconciliation_{session}_{term}.pdf".replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        pdf = canvas.Canvas(response, pagesize=landscape(A4))
        width, height = landscape(A4)

        y = height - 36
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(28, y, f"Billing Reconciliation - {session} - {term}")
        y -= 18
        pdf.setFont("Helvetica", 8)
        pdf.drawString(
            28,
            y,
            f"Class: {class_name or 'All'} | Billed: {totals['billed']} | Approved: {totals['approved']} | Balance: {totals['balance']}",
        )
        y -= 18

        headers = [
            "Inv",
            "Student",
            "Class",
            "St",
            "Billed",
            "Appr",
            "Pend",
            "Rej",
            "Rev",
            "Bal",
        ]
        widths = [26, 130, 48, 30, 52, 52, 50, 44, 44, 50]
        x = 28
        pdf.setFont("Helvetica-Bold", 7.5)
        for w, h in zip(widths, headers):
            pdf.drawString(x + 2, y, h)
            x += w
        y -= 10
        pdf.setFont("Helvetica", 7)
        for row in rows:
            if y < 36:
                pdf.showPage()
                y = height - 36
                x = 28
                pdf.setFont("Helvetica-Bold", 7.5)
                for w, h in zip(widths, headers):
                    pdf.drawString(x + 2, y, h)
                    x += w
                y -= 10
                pdf.setFont("Helvetica", 7)
            values = [
                f"#{row['invoice'].id}",
                row["invoice"].student.full_name[:28],
                (row["invoice"].student.class_name or "")[:10],
                row["invoice"].status[:8],
                str(row["billed"]),
                str(row["approved"]),
                str(row["pending"]),
                str(row["rejected"]),
                str(row["reversed"]),
                str(row["balance"]),
            ]
            x = 28
            for w, value in zip(widths, values):
                pdf.drawString(x + 2, y, value)
                x += w
            y -= 10
            chain = row["approval_chain"] or "-"
            for chunk_start in range(0, len(chain), 120):
                if y < 30:
                    pdf.showPage()
                    y = height - 36
                    pdf.setFont("Helvetica", 7)
                pdf.drawString(34, y, f"Chain: {chain[chunk_start:chunk_start+120]}")
                y -= 8
            y -= 3

        pdf.save()
        return response

    classes = (
        Student.objects.exclude(class_name__isnull=True)
        .exclude(class_name="")
        .values_list("class_name", flat=True)
        .distinct()
        .order_by("class_name")
    )
    return render(
        request,
        "billing/reconciliation_report.html",
        {
            "sessions": AcademicSession.objects.all().order_by("-id"),
            "terms": Term.objects.filter(session=session).order_by("order") if session else [],
            "selected_session": session,
            "selected_term": term,
            "selected_class_name": class_name,
            "class_names": classes,
            "rows": rows,
            "totals": totals,
        },
    )
