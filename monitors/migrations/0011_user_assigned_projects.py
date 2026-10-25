from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("monitors", "0010_alert_email_event_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="assigned_projects",
            field=models.ManyToManyField(blank=True, related_name="assigned_users", to="monitors.project"),
        ),
    ]
