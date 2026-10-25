import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitors", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient", models.EmailField(max_length=254)),
                ("event", models.CharField(choices=[("DOWN", "Service down"), ("RECOVERED", "Service recovered")], max_length=12)),
                ("detail", models.CharField(blank=True, max_length=500)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("next_attempt_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_alerts", to="monitors.incident")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="alertdelivery",
            constraint=models.UniqueConstraint(fields=("incident", "event"), name="unique_incident_email_event"),
        ),
        migrations.AddIndex(
            model_name="alertdelivery",
            index=models.Index(fields=["sent_at", "next_attempt_at"], name="emailalert_pending_idx"),
        ),
    ]
