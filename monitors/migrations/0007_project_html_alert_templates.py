from django.db import migrations, models
import django.db.models.deletion


def remove_legacy_branding(apps, schema_editor):
    Template = apps.get_model("monitors", "AlertEmailTemplate")
    db = schema_editor.connection.alias
    for template in Template.objects.using(db).all():
        template.subject = template.subject.replace("Intellial ", "")
        template.closing = template.closing.replace("Intellial ", "")
        template.footer = template.footer.replace("Intellial ", "")
        template.save(using=db, update_fields=["subject", "closing", "footer"])


class Migration(migrations.Migration):
    dependencies = [("monitors", "0006_alert_email_templates")]

    operations = [
        migrations.AlterField(
            model_name="alertemailtemplate",
            name="event",
            field=models.CharField(choices=[("DOWN", "Service down"), ("RECOVERED", "Service recovered")], max_length=12),
        ),
        migrations.AddField(
            model_name="alertemailtemplate",
            name="project",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="alert_email_templates", to="monitors.project"),
        ),
        migrations.AddField(
            model_name="alertemailtemplate",
            name="html_body",
            field=models.TextField(blank=True, help_text="Complete editable HTML email body. Use {{ service }}, {{ project }}, {{ status }}, and {{ details }} placeholders."),
        ),
        migrations.AddConstraint(
            model_name="alertemailtemplate",
            constraint=models.UniqueConstraint(fields=("project", "event"), name="unique_project_alert_email_template"),
        ),
        migrations.RunPython(remove_legacy_branding, migrations.RunPython.noop),
    ]
