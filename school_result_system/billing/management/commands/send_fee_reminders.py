from django.core.management.base import BaseCommand

from academics.models import AcademicSession, Term
from billing.models import Invoice
from results.notifications import (
    create_parent_notification,
    format_outstanding_reminder_email,
    send_parent_email,
)
from results.models import Notification


class Command(BaseCommand):
    help = "Send outstanding fee reminders to parents (in-app + email)."

    def add_arguments(self, parser):
        parser.add_argument("--session", type=int, help="AcademicSession id")
        parser.add_argument("--term", type=int, help="Term id")

    def handle(self, *args, **options):
        session = None
        term = None
        if options.get("session"):
            session = AcademicSession.objects.filter(id=options["session"]).first()
        if options.get("term"):
            term = Term.objects.filter(id=options["term"]).first()

        invoices = Invoice.objects.select_related("student", "session", "term")
        if session:
            invoices = invoices.filter(session=session)
        if term:
            invoices = invoices.filter(term=term)

        count = 0
        for invoice in invoices:
            if invoice.balance <= 0:
                continue
            message = (
                f"Outstanding balance: {invoice.balance} "
                f"for {invoice.term} ({invoice.session})."
            )
            create_parent_notification(
                invoice.student,
                message,
                session=invoice.session,
                term=invoice.term,
                category=Notification.CATEGORY_FINANCE,
            )
            subject, body = format_outstanding_reminder_email(
                invoice.student,
                invoice.balance,
                invoice.term,
                invoice.session,
            )
            send_parent_email(subject, body, invoice.student)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Reminders sent for {count} invoice(s)."))
