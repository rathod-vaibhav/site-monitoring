from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitors", "0009_alert_email_site_url_help")]

    operations = [
        migrations.AlterField(
            model_name="alertemailtemplate",
            name="html_body",
            field=models.TextField(
                blank=True,
                help_text="Complete editable HTML email body. Use {{ service }}, {{ project }}, {{ status }}, {{ details }}, {{ site_url }}, {{ event_time }}, {{ down_since }}, {{ downtime }}, and {{ check_interval }} placeholders.",
            ),
        ),
    ]
