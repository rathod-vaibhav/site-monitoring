from datetime import timedelta
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.urls import reverse

from .checks import check_url
from .mailer import send_email
from .models import AlertDelivery, AlertEmailTemplate, CheckResult, Incident, Monitor
from .email_templates import DEFAULT_ALERT_TEMPLATES, build_alert_email


logger = logging.getLogger(__name__)


def run_check(monitor_id, force=False):
    try:
        monitor = Monitor.objects.get(pk=monitor_id)
        if not force and not monitor.is_active:
            return
    except Monitor.DoesNotExist:
        return

    ok, code, elapsed, error = check_url(monitor.target, monitor.timeout_seconds)
    now = timezone.now()

    with transaction.atomic():
        monitor = Monitor.objects.select_for_update().get(pk=monitor_id)
        if not force and not monitor.is_active:
            return
        previous_status = monitor.status

        CheckResult.objects.create(
            monitor=monitor,
            checked_at=now,
            ok=ok,
            http_status_code=code,
            response_time_ms=elapsed,
            error_message=error,
        )
        incident = Incident.objects.filter(
            monitor=monitor,
            resolved_at__isnull=True,
        ).order_by("started_at").first()

        if ok:
            monitor.consecutive_successes += 1
            monitor.consecutive_failures = 0
            monitor.status = (
                Monitor.Status.UP
                if monitor.consecutive_successes >= monitor.recovery_threshold
                else (Monitor.Status.SUSPECT if incident else Monitor.Status.UP)
            )
        else:
            monitor.consecutive_failures += 1
            monitor.consecutive_successes = 0
            monitor.status = (
                Monitor.Status.DOWN
                if monitor.consecutive_failures >= monitor.failure_threshold
                else Monitor.Status.SUSPECT
            )

        monitor.last_checked_at = now
        monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
        monitor.last_response_ms = elapsed
        monitor.save()

        if monitor.status == Monitor.Status.SUSPECT and previous_status in (Monitor.Status.UP, Monitor.Status.UNKNOWN):
            _queue_attention_alert(monitor, error or "The service check is unstable and needs attention.")

        if monitor.status == Monitor.Status.DOWN and incident is None:
            incident = Incident.objects.create(monitor=monitor)
            _queue_alert(incident, monitor, AlertDelivery.Event.DOWN, error)
        elif incident and monitor.status == Monitor.Status.UP:
            incident.resolved_at = now
            incident.save(update_fields=["resolved_at"])
            _queue_alert(
                incident,
                monitor,
                AlertDelivery.Event.RECOVERED,
                "The endpoint is responding again.",
            )


def _queue_alert(incident, monitor, event, detail):
    recipients = list(dict.fromkeys(address.strip() for address in monitor.alert_email.replace(";", ",").split(",") if address.strip()))
    for recipient in recipients:
        AlertDelivery.objects.get_or_create(
            incident=incident,
            event=event,
            recipient=recipient,
            defaults={"monitor": monitor, "detail": (detail or "No additional details were provided by the latest check.")[:500]},
        )


def _queue_attention_alert(monitor, detail):
    recipients = list(dict.fromkeys(address.strip() for address in monitor.alert_email.replace(";", ",").split(",") if address.strip()))
    for recipient in recipients:
        AlertDelivery.objects.create(
            incident=None,
            monitor=monitor,
            event=AlertDelivery.Event.ATTENTION,
            recipient=recipient,
            detail=(detail or "The service needs attention.")[:500],
        )


def send_pending_alerts(limit=20):
    """Deliver queued alerts with durable retries and a short claim lock."""
    due_ids = list(
        AlertDelivery.objects.filter(
            sent_at__isnull=True,
            next_attempt_at__lte=timezone.now(),
        ).order_by("created_at").values_list("id", flat=True)[:limit]
    )
    processed = 0

    for alert_id in due_ids:
        claimed_at = timezone.now()
        claimed = AlertDelivery.objects.filter(
            pk=alert_id,
            sent_at__isnull=True,
            next_attempt_at__lte=claimed_at,
        ).update(
            attempts=F("attempts") + 1,
            next_attempt_at=claimed_at + timedelta(minutes=5),
        )
        if not claimed:
            continue

        alert = AlertDelivery.objects.select_related("monitor", "monitor__project").get(pk=alert_id)
        monitor = alert.monitor
        try:
            send_alert(alert.recipient, monitor, alert.event, alert.detail, incident=alert.incident, queued_at=alert.created_at)
        except Exception as exc:
            retry_seconds = min(3600, 30 * (2 ** min(alert.attempts - 1, 7)))
            alert.last_error = f"Email delivery failed ({type(exc).__name__})"
            alert.next_attempt_at = timezone.now() + timedelta(seconds=retry_seconds)
            alert.save(update_fields=["last_error", "next_attempt_at"])
            logger.warning(
                "Alert delivery id=%s failed on attempt %s (%s); retry scheduled.",
                alert.id,
                alert.attempts,
                type(exc).__name__,
            )
        else:
            alert.sent_at = timezone.now()
            alert.last_error = ""
            alert.save(update_fields=["sent_at", "last_error"])
            logger.info(
                "Delivered %s alert for incident id=%s.",
                alert.event,
                alert.incident_id,
            )
        processed += 1

    return processed


def send_alert(recipient, monitor, event, detail, *, incident=None, queued_at=None):
    detail = detail or "No additional details were provided by the latest check."
    template, _ = AlertEmailTemplate.objects.get_or_create(
        project=None,
        event=event,
        defaults=DEFAULT_ALERT_TEMPLATES[event],
    )
    event_time = queued_at
    incident_started_at = None
    downtime_seconds = None
    if incident:
        if event == AlertDelivery.Event.DOWN:
            event_time = incident.started_at
        elif event == AlertDelivery.Event.RECOVERED:
            event_time = incident.resolved_at or queued_at
            incident_started_at = incident.started_at
            if incident.resolved_at:
                downtime_seconds = (incident.resolved_at - incident.started_at).total_seconds()
    subject, html_body, text_body = build_alert_email(
        template,
        monitor_name=monitor.name,
        project_name=monitor.project.name,
        monitor_url=monitor.target,
        monitor_link=f"{settings.SITE_URL}{reverse('monitor_detail', args=[monitor.pk])}",
        detail=detail,
        event_time=event_time,
        incident_started_at=incident_started_at,
        downtime_seconds=downtime_seconds,
        check_interval_seconds=monitor.interval_seconds,
    )
    sent = send_email(
        recipient,
        subject,
        html_body,
        text_body=text_body,
    )
    if not sent:
        raise RuntimeError("The email backend did not report a successful delivery")
