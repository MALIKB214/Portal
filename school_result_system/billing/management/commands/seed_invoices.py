from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from academics.models import AcademicSession, Term
from students.models import Student
from billing.models import Invoice, InvoiceItem, FeeCategory, Payment


class Command(BaseCommand):
    help = "Seed invoices and approved payments for all students"

    def add_arguments(self, parser):
        parser.add_argument("--school-fee", type=str, default="45000.00")
        parser.add_argument("--project-fee", type=str, default="5000.00")
        parser.add_argument("--session-id", type=int, default=None)
        parser.add_argument("--term-id", type=int, default=None)
        parser.add_argument("--force", action="store_true", help="Create even if invoice exists")

    def handle(self, *args, **options):
        session = None
        term = None
        if options["session_id"]:
            session = AcademicSession.objects.filter(id=options["session_id"]).first()
        if not session:
            session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.order_by("-id").first()
        if options["term_id"] and session:
            term = Term.objects.filter(id=options["term_id"], session=session).first()
        if not term and session:
            term = Term.objects.filter(session=session, is_active=True).first()
        if not session or not term:
            self.stderr.write("No active session/term found.")
            return

        school_fee = FeeCategory.objects.filter(category_type="school").first() or FeeCategory.objects.create(
            name="School Fee", category_type="school", is_active=True
        )
        project_fee = FeeCategory.objects.filter(category_type="project").first() or FeeCategory.objects.create(
            name="Project Fee", category_type="project", is_active=True
        )
        User = get_user_model()
        cashier = User.objects.filter(is_proprietor=True).first() or User.objects.filter(is_admin=True).first() or User.objects.filter(is_superuser=True).first()

        created = 0
        skipped = 0
        for student in Student.objects.all():
            invoice = Invoice.objects.filter(student=student, session=session, term=term).first()
            if invoice and not options["force"]:
                skipped += 1
                continue
            if not invoice:
                invoice = Invoice.objects.create(student=student, session=session, term=term)
            InvoiceItem.objects.create(invoice=invoice, category=school_fee, description="School Fee", amount=Decimal(options["school_fee"]))
            InvoiceItem.objects.create(invoice=invoice, category=project_fee, description="Project/Invention Fee", amount=Decimal(options["project_fee"]))
            total = sum(item.amount for item in invoice.items.all())
            payment = Payment.objects.create(
                invoice=invoice,
                amount=total,
                method="cash",
                reference="AUTO-SEED",
                notes="Auto-seeded payment",
                received_by=cashier,
            )
            payment.approve(cashier or payment.received_by)
            created += 1

        self.stdout.write(f"Created {created} invoices with payments, skipped {skipped} existing invoices.")
