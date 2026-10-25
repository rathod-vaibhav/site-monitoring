from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitors.models import CheckResult


class Command(BaseCommand):
    help = "Delete check history older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days",
            type=int,
            default=30,
            help="Keep this many days of check history (default: 30).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Rows to delete per database batch (default: 5000).",
        )

    def handle(self, *args, **options):
        retention_days = options["retention_days"]
        batch_size = options["batch_size"]
        if retention_days < 1:
            raise CommandError("--retention-days must be at least 1.")
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")

        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted = 0
        while True:
            expired_ids = list(
                CheckResult.objects.filter(checked_at__lt=cutoff)
                .order_by("checked_at")
                .values_list("pk", flat=True)[:batch_size]
            )
            if not expired_ids:
                break
            batch_deleted, _ = CheckResult.objects.filter(pk__in=expired_ids).delete()
            deleted += batch_deleted

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} expired check record(s); retained the last {retention_days} days."
            )
        )
