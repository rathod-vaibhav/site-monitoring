from django.db import migrations


def create_password_management_permission(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    db = schema_editor.connection.alias
    content_type, _ = ContentType.objects.using(db).get_or_create(
        app_label="monitors",
        model="accessrole",
    )
    Permission.objects.using(db).get_or_create(
        content_type_id=content_type.pk,
        codename="manage_user_passwords",
        defaults={"name": "Can manage user passwords"},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("monitors", "0004_access_roles"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="accessrole",
            options={
                "ordering": ["name"],
                "permissions": [
                    ("manage_projects", "Can manage projects"),
                    ("manage_monitors", "Can manage monitors"),
                    ("manage_incidents", "Can manage incidents"),
                    ("manage_team", "Can manage team members"),
                    ("manage_user_passwords", "Can manage user passwords"),
                    ("manage_roles", "Can manage roles and permissions"),
                ],
            },
        ),
        migrations.RunPython(create_password_management_permission, migrations.RunPython.noop),
    ]
