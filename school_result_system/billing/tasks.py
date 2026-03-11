from celery import shared_task

from datetime import timedelta
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from academics.models import AcademicSession, Term
from billing.management.commands.send_fee_reminders import Command as ReminderCommand
from accounts.models import User, StaffNotification
from accounts.notifications import notify_staff_event
from .models import InvoiceItem, Payment


@shared_task
def send_fee_reminders_task(session_id=None, term_id=None):
    cmd = ReminderCommand()
    session = AcademicSession.objects.filter(id=session_id).first() if session_id else None
    term = Term.objects.filter(id=term_id).first() if term_id else None

    options = {}
    if session:
        options["session"] = session.id
    if term:
        options["term"] = term.id

    cmd.handle(**options)


def _finance_recipients():
    return (
        User.objects.filter(
            models.Q(is_proprietor=True)
            | models.Q(is_admin=True)
            | models.Q(is_superuser=True)
            | models.Q(groups__name__in=["Bursar", "Principal"])
        )
        .distinct()
        .only("id", "username", "email", "first_name", "last_name")
    )


@shared_task
def send_weekly_finance_summary_task(
    session_id=None, term_id=None, include_per_class=False, notify_user_id=None
):
    today = timezone.now()
    start = today - timedelta(days=7)

    payment_scope = Payment.objects.all()
    if session_id:
        payment_scope = payment_scope.filter(invoice__session_id=session_id)
    if term_id:
        payment_scope = payment_scope.filter(invoice__term_id=term_id)

    approved_qs = payment_scope.filter(
        approval_status="approved", is_reversed=False, approved_at__gte=start
    )
    approved_count = approved_qs.count()
    approved_total = approved_qs.aggregate(total=Sum("amount"))["total"] or 0

    pending_count = payment_scope.filter(
        approval_status="pending", is_reversed=False
    ).count()
    rejected_count = payment_scope.filter(approval_status="rejected").count()

    invoice_item_scope = InvoiceItem.objects.all()
    if session_id:
        invoice_item_scope = invoice_item_scope.filter(invoice__session_id=session_id)
    if term_id:
        invoice_item_scope = invoice_item_scope.filter(invoice__term_id=term_id)

    total_billed = invoice_item_scope.aggregate(total=Sum("amount"))["total"] or 0
    total_collected = payment_scope.filter(
        approval_status="approved", is_reversed=False
    ).aggregate(total=Sum("amount"))["total"] or 0
    outstanding = max(total_billed - total_collected, 0)

    class_breakdown = ""
    class_summary_line = ""
    if include_per_class:
        class_totals = (
            payment_scope.filter(approval_status="approved", is_reversed=False)
            .values("invoice__student__class_name")
            .annotate(total=Sum("amount"))
            .order_by("invoice__student__class_name")
        )
        lines = []
        for row in class_totals:
            class_name = row["invoice__student__class_name"] or "Unassigned"
            lines.append(f"- {class_name}: ₦{(row['total'] or 0):,.2f}")
        if lines:
            class_breakdown = "\n\nPer-class collection:\n" + "\n".join(lines)
            class_summary_line = "Per-class: " + "; ".join(
                [line.replace("- ", "") for line in lines[:4]]
            )

    scope = []
    if session_id:
        session = AcademicSession.objects.filter(id=session_id).first()
        scope.append(f"session {session or session_id}")
    if term_id:
        term = Term.objects.filter(id=term_id).first()
        scope.append(f"term {term or term_id}")
    scope_label = f" ({', '.join(scope)})" if scope else ""

    message = (
        "Weekly Finance Summary: "
        f"Approved payments {approved_count} (₦{approved_total:,.2f}), "
        f"Pending {pending_count}, Rejected {rejected_count}, "
        f"Outstanding balance ₦{outstanding:,.2f}.{scope_label}"
    )
    subject = "Weekly Finance Summary"
    if include_per_class:
        subject += " (Per-class breakdown)"
    email_body = (
        "Weekly Finance Summary\n\n"
        f"Approved payments: {approved_count} (₦{approved_total:,.2f})\n"
        f"Pending payments: {pending_count}\n"
        f"Rejected payments: {rejected_count}\n"
        f"Outstanding balance: ₦{outstanding:,.2f}\n\n"
        "Please review pending approvals and outstanding balances in the portal."
    )
    if class_breakdown:
        email_body += class_breakdown

    recipients = _finance_recipients()
    if notify_user_id:
        recipients = recipients.filter(id=notify_user_id)

    for user in recipients:
        notify_staff_event(
            user,
            message,
            category=StaffNotification.CATEGORY_FINANCE,
            email_subject=subject,
            email_body=email_body,
            send_email=True,
        )
        if include_per_class and class_summary_line:
            notify_staff_event(
                user,
                class_summary_line[:200],
                category=StaffNotification.CATEGORY_FINANCE,
                send_email=False,
            )
