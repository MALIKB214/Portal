from django.contrib.auth.models import Group
from decimal import Decimal
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from academics.models import AcademicSession, SchoolClass, Term
from students.models import Student
from .models import FeeCategory, FinanceEvent, Invoice, InvoiceItem, Payment
from results.models import Notification


@override_settings(CANONICAL_HOST="")
class BillingRoleAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username="teacher_fin",
            password="pass12345",
            is_teacher=True,
        )
        self.bursar = User.objects.create_user(
            username="bursar_fin",
            password="pass12345",
        )
        self.principal = User.objects.create_user(
            username="principal_fin",
            password="pass12345",
        )
        self.proprietor = User.objects.create_user(
            username="prop_fin",
            password="pass12345",
            is_proprietor=True,
        )

        bursar_group, _ = Group.objects.get_or_create(name="Bursar")
        principal_group, _ = Group.objects.get_or_create(name="Principal")
        self.bursar.groups.add(bursar_group)
        self.principal.groups.add(principal_group)

    def test_teacher_is_denied_billing_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("billing:dashboard"))
        self.assertRedirects(
            response,
            reverse("accounts:teacher_dashboard"),
            fetch_redirect_response=False,
        )

    def test_bursar_can_access_billing_dashboard(self):
        self.client.force_login(self.bursar)
        response = self.client.get(reverse("billing:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_principal_can_access_billing_dashboard(self):
        self.client.force_login(self.principal)
        response = self.client.get(reverse("billing:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_proprietor_can_access_billing_dashboard(self):
        self.client.force_login(self.proprietor)
        response = self.client.get(reverse("billing:dashboard"))
        self.assertEqual(response.status_code, 200)


@override_settings(CANONICAL_HOST="")
class BillingLedgerAndReversalTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.bursar = User.objects.create_user(
            username="bursar_ledger",
            password="pass12345",
        )
        self.principal = User.objects.create_user(
            username="principal_ledger",
            password="pass12345",
        )
        self.proprietor = User.objects.create_user(
            username="prop_ledger",
            password="pass12345",
            is_proprietor=True,
        )
        bursar_group, _ = Group.objects.get_or_create(name="Bursar")
        principal_group, _ = Group.objects.get_or_create(name="Principal")
        self.bursar.groups.add(bursar_group)
        self.principal.groups.add(principal_group)

        self.school_class = SchoolClass.objects.create(name="JSS2")
        self.session = AcademicSession.objects.create(name="2025/2026", is_active=True)
        self.term = Term.objects.create(session=self.session, order=1, name="First Term", is_active=True)
        self.student = Student.objects.create(
            first_name="Ada",
            last_name="Bello",
            admission_number="SCH/2026/900",
            gender="F",
            class_name="JSS2",
            school_class=self.school_class,
        )
        self.invoice = Invoice.objects.create(student=self.student, session=self.session, term=self.term)
        self.fee = FeeCategory.objects.create(name="School Fee", category_type="school")
        InvoiceItem.objects.create(invoice=self.invoice, category=self.fee, description="Main fee", amount=Decimal("10000"))

    def test_bursar_records_payment_and_event(self):
        self.client.force_login(self.bursar)
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.id]),
            {
                "action": "add_payment",
                "amount": "4000",
                "method": "cash",
                "reference": "ref-1",
                "notes": "first part",
            },
        )
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(invoice=self.invoice)
        self.assertEqual(payment.amount, Decimal("4000"))
        self.assertTrue(
            FinanceEvent.objects.filter(
                invoice=self.invoice,
                payment=payment,
                event_type="payment_created",
            ).exists()
        )

    def test_principal_cannot_reverse_payment(self):
        payment = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("5000"),
            method="cash",
            approval_status="approved",
            received_by=self.bursar,
        )
        self.client.force_login(self.principal)
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.id]),
            {"action": "reverse_payment", "payment_id": payment.id, "reversal_note": "bad entry"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertFalse(payment.is_reversed)

    def test_proprietor_reverses_payment_and_event_created(self):
        payment = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("5000"),
            method="cash",
            approval_status="approved",
            received_by=self.bursar,
        )
        self.client.force_login(self.proprietor)
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.id]),
            {"action": "reverse_payment", "payment_id": payment.id, "reversal_note": "duplicate"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertTrue(payment.is_reversed)
        self.assertTrue(
            FinanceEvent.objects.filter(
                invoice=self.invoice,
                payment=payment,
                event_type="payment_reversed",
                amount_delta=Decimal("-5000"),
            ).exists()
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, 0)
        self.assertTrue(
            Notification.objects.filter(
                student=self.student,
                message__icontains="reversed",
            ).exists()
        )

    def test_proprietor_voids_invoice_and_logs_event(self):
        self.client.force_login(self.proprietor)
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.id]),
            {"action": "void_invoice", "void_note": "cancelled by school"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "void")
        self.assertTrue(
            FinanceEvent.objects.filter(invoice=self.invoice, event_type="invoice_voided").exists()
        )
