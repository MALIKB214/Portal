from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email using the configured SMTP settings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="to",
            help="Recipient email address. Defaults to DEFAULT_FROM_EMAIL.",
        )

    def handle(self, *args, **options):
        recipient = options.get("to") or settings.DEFAULT_FROM_EMAIL
        if not recipient:
            raise CommandError("Recipient email missing. Pass --to or set DEFAULT_FROM_EMAIL.")

        subject = "School Portal SMTP Test"
        message = "SMTP is configured correctly."
        from_email = settings.DEFAULT_FROM_EMAIL

        sent = send_mail(subject, message, from_email, [recipient], fail_silently=False)
        if sent != 1:
            raise CommandError("Email not sent. Check SMTP settings.")

        self.stdout.write(self.style.SUCCESS(f"Test email sent to {recipient}"))
