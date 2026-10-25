from django.core.management.base import BaseCommand
from monitors.mailer import send_email


class Command(BaseCommand):
    help = "Send a test email using the configured SMTP settings to verify Gmail integration."

    def add_arguments(self, parser):
        parser.add_argument("recipient", type=str, help="Email address to receive the test email.")

    def handle(self, *args, **options):
        recipient = options["recipient"].strip()
        self.stdout.write(f"Sending test email to: {recipient} ...")
        try:
            sent = send_email(
                to=recipient,
                subject="[Test] Site Monitoring Gmail Test",
                html_body="<h3>Site Monitoring Gmail Test</h3><p>Your Gmail SMTP integration is working successfully!</p>",
                text_body="Site Monitoring Gmail Test: Your Gmail SMTP integration is working successfully!",
            )
            if sent:
                self.stdout.write(self.style.SUCCESS(f"Success! Test email sent to {recipient}."))
            else:
                self.stdout.write(self.style.ERROR("Email backend returned 0 messages sent."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Failed to send email: {exc}"))
