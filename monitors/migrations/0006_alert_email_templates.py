from django.db import migrations, models


def create_default_alert_templates(apps, schema_editor):
    AlertEmailTemplate = apps.get_model("monitors", "AlertEmailTemplate")
    db = schema_editor.connection.alias
    defaults = {
        "DOWN": {
            "subject": "[{status}] {service} · Intellial Site Monitoring",
            "heading": "Service is down",
            "intro": "A monitored service changed status. Here are the latest details.",
            "service_label": "Service",
            "details_label": "Details",
            "closing": "Review the incident in Intellial Site Monitoring and check the latest monitor results.",
            "footer": "Automated notification from Intellial Site Monitoring.",
            "footer_note": "To change alert recipients, update this service’s monitor settings.",
        },
        "RECOVERED": {
            "subject": "[{status}] {service} · Intellial Site Monitoring",
            "heading": "Service has recovered",
            "intro": "A monitored service is responding normally again. Here are the latest details.",
            "service_label": "Service",
            "details_label": "Details",
            "closing": "Review the incident in Intellial Site Monitoring and check the latest monitor results.",
            "footer": "Automated notification from Intellial Site Monitoring.",
            "footer_note": "To change alert recipients, update this service’s monitor settings.",
        },
    }
    for event, values in defaults.items():
        AlertEmailTemplate.objects.using(db).get_or_create(event=event, defaults=values)


class Migration(migrations.Migration):
    dependencies = [("monitors", "0005_user_password_permission")]

    operations = [
        migrations.CreateModel(
            name="AlertEmailTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.CharField(choices=[("DOWN", "Service down"), ("RECOVERED", "Service recovered")], max_length=12, unique=True)),
                ("subject", models.CharField(max_length=180)),
                ("heading", models.CharField(max_length=160)),
                ("intro", models.CharField(max_length=300)),
                ("service_label", models.CharField(default="Service", max_length=60)),
                ("details_label", models.CharField(default="Details", max_length=60)),
                ("closing", models.CharField(max_length=300)),
                ("footer", models.CharField(max_length=240)),
                ("footer_note", models.CharField(max_length=240)),
            ],
            options={"ordering": ["event"]},
        ),
        migrations.RunPython(create_default_alert_templates, migrations.RunPython.noop),
    ]
