from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitors", "0011_user_assigned_projects"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="theme_preference",
            field=models.CharField(
                choices=[("light", "Light"), ("dark", "Dark")],
                default="light",
                max_length=8,
            ),
        ),
    ]
