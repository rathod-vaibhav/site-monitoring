import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
class User(AbstractUser):
    class ThemePreference(models.TextChoices):
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        VIEWER = "VIEWER", "Viewer"
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.VIEWER)
    access_role = models.ForeignKey("AccessRole", null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    assigned_projects = models.ManyToManyField("Project", blank=True, related_name="assigned_users")
    theme_preference = models.CharField(max_length=8, choices=ThemePreference.choices, default=ThemePreference.LIGHT)

    def has_perm(self, perm, obj=None):
        if super().has_perm(perm, obj):
            return True
        if not self.is_active or obj is not None or not self.access_role_id or "." not in perm:
            return False
        app_label, codename = perm.split(".", 1)
        return self.access_role.permissions.filter(content_type__app_label=app_label, codename=codename).exists()

    def get_all_permissions(self, obj=None):
        permissions = super().get_all_permissions(obj)
        if self.is_active and obj is None and self.access_role_id:
            permissions |= {f"{app}.{code}" for app, code in self.access_role.permissions.values_list("content_type__app_label", "codename")}
        return permissions


class AccessRole(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=240, blank=True)
    is_protected = models.BooleanField(default=False)
    permissions = models.ManyToManyField("auth.Permission", blank=True, related_name="monitoring_roles")

    class Meta:
        ordering = ["name"]
        permissions = [
            ("manage_projects", "Can manage projects"),
            ("manage_monitors", "Can manage monitors"),
            ("manage_incidents", "Can manage incidents"),
            ("manage_team", "Can manage team members"),
            ("manage_user_passwords", "Can manage user passwords"),
            ("manage_roles", "Can manage roles and permissions"),
        ]

    def __str__(self):
        return self.name
class Project(models.Model):
    name = models.CharField(max_length=120)
    code = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    status_page_enabled = models.BooleanField(default=False)
    status_page_slug = models.SlugField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name
class Monitor(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        UP = "UP", "Up"
        SUSPECT = "SUSPECT", "Suspect"
        DOWN = "DOWN", "Down"
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="monitors")
    name = models.CharField(max_length=160)
    target = models.URLField(max_length=2048)
    interval_seconds = models.PositiveIntegerField(default=60)
    timeout_seconds = models.PositiveIntegerField(default=10)
    failure_threshold = models.PositiveIntegerField(default=3)
    recovery_threshold = models.PositiveIntegerField(default=2)
    alert_email = models.CharField(max_length=1000, blank=True, help_text="Comma-separated notification email addresses.")
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UNKNOWN)
    consecutive_failures = models.PositiveIntegerField(default=0)
    consecutive_successes = models.PositiveIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_response_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name
class CheckResult(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="results")
    checked_at = models.DateTimeField(default=timezone.now, db_index=True)
    ok = models.BooleanField()
    http_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
class Incident(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="incidents")
    started_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.CharField(max_length=500, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

class AlertDelivery(models.Model):
    class Event(models.TextChoices):
        DOWN = "DOWN", "Service down"
        RECOVERED = "RECOVERED", "Service recovered"
        ATTENTION = "ATTENTION", "Needs attention"

    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.CASCADE, related_name="email_alerts")
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="email_alerts")
    recipient = models.EmailField()
    event = models.CharField(max_length=12, choices=Event.choices)
    detail = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["incident", "event", "recipient"], name="unique_incident_recipient_event"),
        ]
        indexes = [
            models.Index(fields=["sent_at", "next_attempt_at"], name="emailalert_pending_idx"),
        ]


class AlertEmailTemplate(models.Model):
    class Event(models.TextChoices):
        DOWN = "DOWN", "Service down"
        RECOVERED = "RECOVERED", "Service recovered"
        ATTENTION = "ATTENTION", "Needs attention"

    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.CASCADE, related_name="alert_email_templates")
    event = models.CharField(max_length=12, choices=Event.choices)
    subject = models.CharField(max_length=180)
    html_body = models.TextField(blank=True, help_text="Complete editable HTML email body. Use {{ service }}, {{ project }}, {{ status }}, {{ details }}, {{ site_url }}, {{ event_time }}, {{ down_since }}, {{ downtime }}, and {{ check_interval }} placeholders.")
    heading = models.CharField(max_length=160)
    intro = models.CharField(max_length=300)
    service_label = models.CharField(max_length=60, default="Service")
    details_label = models.CharField(max_length=60, default="Details")
    closing = models.CharField(max_length=300)
    footer = models.CharField(max_length=240)
    footer_note = models.CharField(max_length=240)

    class Meta:
        ordering = ["event"]
        constraints = [models.UniqueConstraint(fields=["project", "event"], name="unique_project_alert_email_template")]

    def __str__(self):
        return self.get_event_display()
