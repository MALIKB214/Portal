from django.conf import settings
from django.core.mail import send_mail
import logging
from email.utils import formataddr, parseaddr

from accounts.models import SchoolBranding
from accounts.models import User
from .models import Notification, ParentPortalAccount

logger = logging.getLogger(__name__)


def _school_name():
    try:
        return SchoolBranding.get_solo().school_name
    except Exception:
        return getattr(settings, "SCHOOL_NAME", "School Portal")


def _parent_emails(student):
    emails = set()
    portal = ParentPortalAccount.objects.filter(student=student, is_active=True).select_related("user").first()
    if portal and portal.user and portal.user.email:
        emails.add(portal.user.email.strip())
    if student.parent_email:
        emails.add(student.parent_email.strip())
    if student.email:
        emails.add(student.email.strip())
    return [email for email in emails if email]


def _from_email():
    school = _school_name()
    configured = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    _, email_addr = parseaddr(configured)
    if not email_addr:
        email_addr = configured
    if not email_addr:
        email_addr = getattr(settings, "EMAIL_HOST_USER", "") or "no-reply@localhost"
    return formataddr((school, email_addr))


def create_parent_notification(student, message, session=None, term=None, category=Notification.CATEGORY_SYSTEM):
    return Notification.objects.create(
        student=student,
        session=session,
        term=term,
        category=category,
        message=message,
    )


def send_parent_email(subject, message, student):
    recipients = _parent_emails(student)
    if not recipients:
        return 0
    if not getattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True):
        return 0
    from_email = _from_email()
    try:
        return send_mail(
            subject,
            message,
            from_email,
            recipients,
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Failed to send parent email notification: %s", exc)
        return 0


def notify_parent_event(
    student,
    message,
    session=None,
    term=None,
    category=Notification.CATEGORY_SYSTEM,
    send_email=False,
    email_subject="",
    email_body="",
):
    create_parent_notification(
        student,
        message,
        session=session,
        term=term,
        category=category,
    )
    if send_email and email_subject and email_body:
        send_parent_email(email_subject, email_body, student)


def send_teacher_emails_for_class(subject, message, school_class):
    if not school_class:
        return 0
    teachers = (
        User.objects.filter(is_teacher=True, teacher_class=school_class)
        .exclude(email__isnull=True)
        .exclude(email="")
    )
    if not teachers:
        return 0
    if not getattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True):
        return 0
    from_email = _from_email()
    sent = 0
    for teacher in teachers:
        try:
            sent += send_mail(
                subject,
                message,
                from_email,
                [teacher.email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception(
                "Failed to send teacher email notification to %s: %s",
                teacher.email,
                exc,
            )
    return sent


def format_result_release_email(student, term, session):
    school = _school_name()
    subject = f"Result Released - {term} {session}"
    body = (
        f"Dear Parent/Guardian,\n\n"
        f"{student.full_name}'s {term} results for {session} are now available on the portal.\n"
        f"Please login to view and download the result slip.\n\n"
        f"Regards,\n{school}"
    )
    return subject, body


def format_parent_login_email(student, ip_address="", user_agent=""):
    school = _school_name()
    subject = "Successful Parent Portal Login"
    body = (
        f"Dear Parent/Guardian,\n\n"
        f"A successful login to {student.full_name}'s parent portal was detected.\n"
        f"IP Address: {ip_address or '-'}\n"
        f"Device: {user_agent or '-'}\n\n"
        f"If this was not you, reset your password immediately.\n\n"
        f"Regards,\n{school}"
    )
    return subject, body


def format_payment_approval_email(student, amount, term, session, receipt_number=""):
    school = _school_name()
    subject = f"Payment Approved - {student.full_name}"
    receipt_line = f"Receipt No: {receipt_number}\n" if receipt_number else ""
    body = (
        f"Dear Parent/Guardian,\n\n"
        f"Your payment of {amount} for {student.full_name} ({term}, {session}) has been approved.\n"
        f"{receipt_line}\n"
        f"Regards,\n{school}"
    )
    return subject, body


def format_outstanding_reminder_email(student, balance, term, session):
    school = _school_name()
    subject = f"Outstanding Balance - {student.full_name}"
    body = (
        f"Dear Parent/Guardian,\n\n"
        f"This is a reminder that {student.full_name} has an outstanding balance of {balance}\n"
        f"for {term} ({session}).\n\n"
        f"Regards,\n{school}"
    )
    return subject, body


def format_teacher_result_approved_email(school_class, term, session, approver_name=""):
    school = _school_name()
    subject = f"Results Approved - {school_class} {term}"
    approver_line = f"Approved by {approver_name}.\n" if approver_name else ""
    body = (
        f"Dear Teacher,\n\n"
        f"Results for {school_class} have been approved for {term} ({session}).\n"
        f"{approver_line}\n"
        f"Regards,\n{school}"
    )
    return subject, body


def format_teacher_result_released_email(school_class, term, session, releaser_name=""):
    school = _school_name()
    subject = f"Results Released - {school_class} {term}"
    releaser_line = f"Released by {releaser_name}.\n" if releaser_name else ""
    body = (
        f"Dear Teacher,\n\n"
        f"Results for {school_class} have been released for {term} ({session}).\n"
        f"{releaser_line}\n"
        f"Regards,\n{school}"
    )
    return subject, body
