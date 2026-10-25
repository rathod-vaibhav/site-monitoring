from django.db import migrations, models
import django.db.models.deletion


def copy_alert_monitors(apps, schema_editor):
    AlertDelivery = apps.get_model("monitors", "AlertDelivery")
    db = schema_editor.connection.alias
    for delivery in AlertDelivery.objects.using(db).select_related("incident").all().iterator():
        delivery.monitor_id = delivery.incident.monitor_id
        delivery.save(using=db, update_fields=["monitor"])


class Migration(migrations.Migration):
    dependencies = [("monitors", "0007_project_html_alert_templates")]

    operations = [
        migrations.AddField(
            model_name="alertdelivery",
            name="monitor",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="email_alerts", to="monitors.monitor"),
        ),
        migrations.RunPython(copy_alert_monitors, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="alertdelivery",
            name="incident",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="email_alerts", to="monitors.incident"),
        ),
        migrations.AlterField(
            model_name="alertdelivery",
            name="monitor",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_alerts", to="monitors.monitor"),
        ),
        migrations.AlterField(
            model_name="alertdelivery",
            name="event",
            field=models.CharField(choices=[("DOWN", "Service down"), ("RECOVERED", "Service recovered"), ("ATTENTION", "Needs attention")], max_length=12),
        ),
        migrations.AlterField(
            model_name="alertemailtemplate",
            name="event",
            field=models.CharField(choices=[("DOWN", "Service down"), ("RECOVERED", "Service recovered"), ("ATTENTION", "Needs attention")], max_length=12),
        ),
    ]
