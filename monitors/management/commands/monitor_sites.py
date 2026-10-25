import logging
import time
from datetime import timedelta
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand
from django.utils import timezone

from monitors.models import Monitor
from monitors.tasks import run_check, send_pending_alerts


logger = logging.getLogger("monitors.runner")


class Command(BaseCommand):
    help = "Run due site checks and email alerts without Celery or Redis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=5,
            help="Seconds between scans for due monitors (default: 5).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one scan of due monitors, then exit.",
        )

    def handle(self, *args, **options):
        poll_interval = max(1, options["poll_interval"])
        once = options["once"]
        self.stdout.write(self.style.SUCCESS(
            f"Site monitoring runner started (scan every {poll_interval:g}s). Press Ctrl+C to stop."
        ))

        try:
            while True:
                self.scan_due_monitors()
                if once:
                    return
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write("\nSite monitoring runner stopped.")

    def scan_due_monitors(self):
        now = timezone.now()
        due = list(
            Monitor.objects.filter(is_active=True, next_check_at__lte=now)
            .order_by("next_check_at")
            .values_list("id", "interval_seconds")[:500]
        )

        for monitor_id, interval_seconds in due:
            claimed_at = timezone.now()
            claimed = Monitor.objects.filter(
                pk=monitor_id,
                is_active=True,
                next_check_at__lte=claimed_at,
            ).update(next_check_at=claimed_at + timedelta(seconds=interval_seconds))
            if not claimed:
                continue

            try:
                monitor = Monitor.objects.get(pk=monitor_id)
                safe_host = urlsplit(monitor.target).hostname or "invalid target"
                self.stdout.write(f"Checking {monitor.name} ({safe_host})")
                run_check(monitor_id)
                self.stdout.write(self.style.SUCCESS(f"Check complete: {monitor.name}"))
            except Monitor.DoesNotExist:
                continue
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Monitor check or alert failed for id={monitor_id}: {exc}"))
                logger.exception("Monitor check failed for id=%s", monitor_id)

        processed_alerts = send_pending_alerts()
        if processed_alerts:
            self.stdout.write(f"Processed {processed_alerts} queued email alert(s).")

