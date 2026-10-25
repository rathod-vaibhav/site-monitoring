from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitors", "0002_alertdelivery"),
    ]

    operations = [
        migrations.AlterField(
            model_name="monitor",
            name="alert_email",
            field=models.CharField(
                blank=True,
                help_text="Comma-separated notification email addresses.",
                max_length=1000,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="alertdelivery",
            name="unique_incident_email_event",
        ),
        migrations.AddConstraint(
            model_name="alertdelivery",
            constraint=models.UniqueConstraint(
                fields=("incident", "event", "recipient"),
                name="unique_incident_recipient_event",
            ),
        ),
    ]
