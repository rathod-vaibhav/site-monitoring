from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("monitors", "0008_attention_email_alerts")]

    operations = [
        migrations.AlterField(
            model_name="alertemailtemplate",
            name="html_body",
            field=models.TextField(
                blank=True,
                help_text="Complete editable HTML email body. Use {{ service }}, {{ project }}, {{ status }}, {{ details }}, and {{ site_url }} placeholders.",
            ),
        ),
    ]
