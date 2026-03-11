from django.conf import settings
from django.core.mail import send_mail
import logging
from email.utils import formataddr, parseaddr

from .models import SchoolBranding
from .models import StaffNotification, SystemEventLog

logger = logging.getLogger(__name__)


def _school_name():
    try:
        return SchoolBranding.get_solo().school_name
    except Exception:
        return getattr(settings, "SCHOOL_NAME", "School Portal")


def _from_email():
    school = _school_name()
    configured = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    _, email_addr = parseaddr(configured)
    if not email_addr:
        email_addr = configured
    if not email_addr:
        email_addr = getattr(settings, "EMAIL_HOST_USER", "") or "no-reply@localhost"
    return formataddr((school, email_addr))


def create_staff_notification(user, message, category=StaffNotification.CATEGORY_SYSTEM):
    return StaffNotification.objects.create(
        user=user,
        category=category,
        message=message,
    )


def send_staff_email(subject, message, user):
    if not user or not user.email:
        return 0
    if not getattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True):
        return 0
    try:
        sent = send_mail(
            subject,
            message,
            _from_email(),
            [user.email],
            fail_silently=False,
        )
        SystemEventLog.objects.create(
            action="email.sent",
            detail=f"to={user.email} subject={subject[:80]}",
            created_by=user,
        )
        return sent
    except Exception as exc:
        logger.exception("Failed to send staff email notification: %s", exc)
        SystemEventLog.objects.create(
            action="email.failed",
            detail=f"to={user.email} error={str(exc)[:120]}",
            created_by=user,
        )
        return 0


def format_staff_login_email(user, ip_address="", user_agent=""):
    school = _school_name()
    subject = "Successful Login Alert"
    display_name = user.get_full_name() or user.username
    body = (
        f"Dear {display_name},\n\n"
        f"A successful login to your staff portal account was detected.\n"
        f"IP Address: {ip_address or '-'}\n"
        f"Device: {user_agent or '-'}\n\n"
        f"If this was not you, change your password immediately and contact the administrator.\n\n"
        f"Regards,\n{school}"
    )
    return subject, body


def notify_staff_event(
    user,
    message,
    category=StaffNotification.CATEGORY_SYSTEM,
    email_subject="",
    email_body="",
    send_email=False,
):
    if not user:
        return
    create_staff_notification(user, message, category=category)
    if send_email and email_subject and email_body:
        send_staff_email(email_subject, email_body, user)
