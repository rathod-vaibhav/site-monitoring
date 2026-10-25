from django.contrib.auth.models import Permission
ROLE_PERMISSION_KEYS = {
    "projects": "manage_projects",
    "monitors": "manage_monitors",
    "incidents": "manage_incidents",
    "team": "manage_team",
    "passwords": "manage_user_passwords",
    "roles": "manage_roles",
}


ROLE_PERMISSION_LABELS = {
    "projects": "Manage projects",
    "monitors": "Manage monitors",
    "incidents": "Manage incidents",
    "team": "Manage team members",
    "passwords": "Manage user passwords",
    "roles": "Manage roles and permissions",
}


ROLE_PERMISSION_GROUPS = {
    "Workspace": ("projects", "monitors", "incidents"),
    "Administration": ("team", "passwords", "roles"),
}


def permission_queryset():
    return Permission.objects.filter(
        content_type__app_label="monitors",
        content_type__model="accessrole",
        codename__in=ROLE_PERMISSION_KEYS.values(),
    ).select_related("content_type").order_by("codename")


def permissions_for_role(role):
    codenames = set(role.permissions.values_list("codename", flat=True))
    return {key: codename in codenames for key, codename in ROLE_PERMISSION_KEYS.items()}
