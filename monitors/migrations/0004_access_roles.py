from django.db import migrations, models
import django.db.models.deletion


PERMISSIONS = {
    "manage_projects": "Can manage projects",
    "manage_monitors": "Can manage monitors",
    "manage_incidents": "Can manage incidents",
    "manage_team": "Can manage team members",
    "manage_roles": "Can manage roles and permissions",
}


def create_roles_and_preserve_assignments(apps, schema_editor):
    AccessRole = apps.get_model("monitors", "AccessRole")
    User = apps.get_model("monitors", "User")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    db = schema_editor.connection.alias
    content_type, _ = ContentType.objects.using(db).get_or_create(app_label="monitors", model="accessrole")
    permission_ids = {}
    for codename, name in PERMISSIONS.items():
        permission, _ = Permission.objects.using(db).get_or_create(
            content_type_id=content_type.pk,
            codename=codename,
            defaults={"name": name},
        )
        permission_ids[codename] = permission.pk

    everyone = list(permission_ids.values())
    definitions = {
        "Master": ("Protected full-access role.", everyone),
        "Admin": ("Manage members, roles, projects, monitors, and incidents.", everyone),
        "Manager": ("Manage projects, monitors, and incidents.", [permission_ids[key] for key in ("manage_projects", "manage_monitors", "manage_incidents")]),
        "Viewer": ("View workspace data without making changes.", []),
    }
    roles = {}
    for name, (description, permission_pks) in definitions.items():
        role, _ = AccessRole.objects.using(db).get_or_create(
            name=name,
            defaults={"description": description, "is_protected": True},
        )
        role.permissions.set(permission_pks)
        roles[name.upper()] = role

    for user in User.objects.using(db).all().iterator():
        target_role = roles.get(user.role, roles["VIEWER"])
        User.objects.using(db).filter(pk=user.pk).update(access_role_id=target_role.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("monitors", "0003_multiple_monitor_recipients"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("description", models.CharField(blank=True, max_length=240)),
                ("is_protected", models.BooleanField(default=False)),
                ("permissions", models.ManyToManyField(blank=True, related_name="monitoring_roles", to="auth.permission")),
            ],
            options={
                "ordering": ["name"],
                "permissions": list(PERMISSIONS.items()),
            },
        ),
        migrations.AddField(
            model_name="user",
            name="access_role",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="users", to="monitors.accessrole"),
        ),
        migrations.RunPython(create_roles_and_preserve_assignments, migrations.RunPython.noop),
    ]
