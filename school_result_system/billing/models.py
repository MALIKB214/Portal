import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone

from academics.models import AcademicSession, Term
from students.models import Student


class FeeCategory(models.Model):
    CATEGORY_CHOICES = (
        ("school", "School Fee"),
        ("project", "Project/Invention Fee"),
    )

    name = models.CharField(max_length=120)
    category_type = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category_type", "name")

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class Invoice(models.Model):
    STATUS_CHOICES = (
        ("unpaid", "Unpaid"),
        ("partial", "Partially Paid"),
        ("paid", "Paid"),
        ("void", "Voided"),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unpaid")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("session", "term", "status")),
            models.Index(fields=("student", "status")),
        ]

    def __str__(self):
        return f"Invoice #{self.id} - {self.student.full_name}"

    @property
    def total_amount(self):
        return sum(item.amount for item in self.items.all())

    @property
    def paid_amount(self):
        return sum(
            payment.amount
            for payment in self.payments.filter(approval_status="approved", is_reversed=False)
        )

    @property
    def balance(self):
        return max(self.total_amount - self.paid_amount, 0)


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name="items", on_delete=models.CASCADE)
    category = models.ForeignKey(FeeCategory, on_delete=models.PROTECT)
    description = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.category.name} - {self.amount}"


class Payment(models.Model):
    METHOD_CHOICES = (
        ("cash", "Cash"),
        ("bank", "Bank Transfer"),
    )
    APPROVAL_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    invoice = models.ForeignKey(Invoice, related_name="payments", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="cash")
    reference = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=40, unique=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_CHOICES, default="pending"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_payments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_note = models.CharField(max_length=200, blank=True)
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversed_payments",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_note = models.CharField(max_length=200, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-paid_at",)
        indexes = [
            models.Index(fields=("invoice", "approval_status")),
            models.Index(fields=("approval_status", "is_reversed", "-paid_at")),
            models.Index(fields=("received_by", "-paid_at")),
        ]

    def __str__(self):
        return f"{self.receipt_number} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            stamp = timezone.now().strftime("%Y%m%d")
            short = uuid.uuid4().hex[:6].upper()
            self.receipt_number = f"RCPT-{stamp}-{short}"
        super().save(*args, **kwargs)

    def approve(self, user, note=""):
        if self.approval_status != "pending" or self.is_reversed:
            return False
        self.approval_status = "approved"
        self.approved_by = user
        self.approved_at = timezone.now()
        if note:
            self.approval_note = note
        self.save(
            update_fields=["approval_status", "approved_by", "approved_at", "approval_note"]
        )
        return True

    def reject(self, user, note=""):
        if self.approval_status != "pending" or self.is_reversed:
            return False
        self.approval_status = "rejected"
        self.approved_by = user
        self.approved_at = timezone.now()
        if note:
            self.approval_note = note
        self.save(
            update_fields=["approval_status", "approved_by", "approved_at", "approval_note"]
        )
        return True

    def reverse(self, user, note=""):
        if self.is_reversed:
            return False
        self.is_reversed = True
        self.reversed_by = user
        self.reversed_at = timezone.now()
        if note:
            self.reversal_note = note
        self.save(
            update_fields=["is_reversed", "reversed_by", "reversed_at", "reversal_note"]
        )
        return True


class FinanceEvent(models.Model):
    EVENT_CHOICES = (
        ("invoice_created", "Invoice Created"),
        ("invoice_item_added", "Invoice Item Added"),
        ("invoice_voided", "Invoice Voided"),
        ("payment_created", "Payment Created"),
        ("payment_approved", "Payment Approved"),
        ("payment_rejected", "Payment Rejected"),
        ("payment_reversed", "Payment Reversed"),
    )

    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    invoice_item = models.ForeignKey(
        InvoiceItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    amount_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    note = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("event_type", "-created_at")),
            models.Index(fields=("invoice", "-created_at")),
            models.Index(fields=("payment", "-created_at")),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.created_at:%Y-%m-%d %H:%M}"
