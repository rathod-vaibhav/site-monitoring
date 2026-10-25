from django import forms
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm, UserCreationForm
from django.utils.safestring import mark_safe
from .models import Project, Monitor, User, AccessRole, AlertEmailTemplate
from .role_permissions import ROLE_PERMISSION_GROUPS, ROLE_PERMISSION_KEYS, permission_queryset


def add_password_feedback(form, field_name, user):
    field = form.fields[field_name]
    field.widget.attrs.update({"autocomplete": "new-password", "data-password-input": "true"})
    personal_info = " ".join(value for value in (user.username, user.email, user.first_name, user.last_name) if value)
    field.widget.attrs["data-personal-info"] = personal_info
    field.help_text = mark_safe(
        '<ul class="password-checklist">'
        '<li data-password-rule="similar">Not too similar to your personal information</li>'
        '<li data-password-rule="length">At least 8 characters</li>'
        '<li data-password-rule="common">Not a commonly used password</li>'
        '<li data-password-rule="numeric">Not entirely numeric</li>'
        '</ul>'
    )


class WorkspacePasswordChangeForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        add_password_feedback(self, "new_password1", user)


class PasswordResetSetPasswordForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        add_password_feedback(self, "new_password1", user)

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "code", "description", "status_page_enabled", "status_page_slug"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status_page_enabled") and not cleaned.get("status_page_slug"):
            self.add_error("status_page_slug", "Add a public page slug before enabling the status page.")
        elif not cleaned.get("status_page_slug"):
            cleaned["status_page_slug"] = None
        return cleaned

class MonitorForm(forms.ModelForm):
    alert_email = forms.CharField(
        required=False,
        label="Notification email addresses",
        help_text="Enter one or more addresses, separated by commas.",
        widget=forms.TextInput(attrs={"placeholder": "ops@example.com, owner@example.com", "autocomplete": "email"}),
    )

    class Meta:
        model = Monitor
        fields = ["name", "target", "interval_seconds", "timeout_seconds", "failure_threshold", "recovery_threshold", "alert_email", "is_active"]

    def clean_alert_email(self):
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_email

        raw = self.cleaned_data.get("alert_email", "")
        addresses = list(dict.fromkeys(address.strip() for address in raw.replace(";", ",").split(",") if address.strip()))
        for address in addresses:
            try:
                validate_email(address)
            except ValidationError:
                raise ValidationError(f"Enter valid email addresses separated by commas. Invalid address: {address}")
        normalized = ", ".join(addresses)
        if len(normalized) > 1000:
            raise ValidationError("The combined email addresses are too long.")
        return normalized

class TeamUserForm(UserCreationForm):
    access_role = forms.ModelChoiceField(queryset=AccessRole.objects.none(), label="Role")
    assigned_projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),
        label="Project access",
        required=False,
        help_text="Choose which projects this teammate can view.",
        widget=forms.SelectMultiple(attrs={"size": "5"}),
    )
    password1 = forms.CharField(
        label="Password", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-password-input": "true"}),
        help_text=mark_safe('<ul class="password-checklist"><li data-password-rule="similar">Not too similar to your personal information</li><li data-password-rule="length">At least 8 characters</li><li data-password-rule="common">Not a commonly used password</li><li data-password-rule="numeric">Not entirely numeric</li></ul>'),
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "access_role", "assigned_projects"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["access_role"].queryset = AccessRole.objects.order_by("name")
        self.fields["assigned_projects"].queryset = Project.objects.order_by("name")
        self.fields["password1"].widget.attrs["data-password-input"] = "true"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.access_role = self.cleaned_data["access_role"]
        user.role = user.access_role.name.upper() if user.access_role.name.upper() in User.Role.values else User.Role.VIEWER
        if commit:
            user.save()
            self.save_m2m()
        return user

class TeamUserEditForm(forms.ModelForm):
    access_role = forms.ModelChoiceField(queryset=AccessRole.objects.none(), label="Role")
    assigned_projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),
        label="Project access",
        required=False,
        help_text="Choose which projects this teammate can view.",
        widget=forms.SelectMultiple(attrs={"size": "5"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "access_role", "assigned_projects", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["access_role"].queryset = AccessRole.objects.order_by("name")
        self.fields["assigned_projects"].queryset = Project.objects.order_by("name")
        if self.instance and self.instance.is_superuser:
            self.fields.pop("assigned_projects")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = user.access_role.name.upper() if user.access_role and user.access_role.name.upper() in User.Role.values else User.Role.VIEWER
        if commit:
            user.save()
            self.save_m2m()
        return user


class TeamUserPasswordForm(SetPasswordForm):
    """Let an authorized manager set a teammate's new password."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("new_password1", "new_password2"):
            self.fields[field_name].widget.attrs.update({
                "autocomplete": "new-password",
                "data-password-input": "true" if field_name == "new_password1" else "false",
            })
        personal_info = " ".join(
            value for value in (
                self.user.username,
                self.user.email,
                self.user.first_name,
                self.user.last_name,
            ) if value
        )
        add_password_feedback(self, "new_password1", self.user)


class AccessRoleForm(forms.ModelForm):
    class Meta:
        model = AccessRole
        fields = ["name", "description", "permissions"]
        widgets = {"permissions": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = permission_queryset()
        permissions_by_id = {
            str(permission.pk): permission
            for permission in self.fields["permissions"].queryset
        }
        grouped_choices = {group: [] for group in ROLE_PERMISSION_GROUPS}
        for choice in self["permissions"]:
            permission = permissions_by_id.get(str(choice.data["value"]))
            if not permission:
                continue
            key = next((key for key, codename in ROLE_PERMISSION_KEYS.items() if codename == permission.codename), None)
            group = next((name for name, keys in ROLE_PERMISSION_GROUPS.items() if key in keys), None)
            if group:
                grouped_choices[group].append(choice)
        self.permission_groups = [
            {"name": name, "choices": choices}
            for name, choices in grouped_choices.items()
            if choices
        ]
        if self.instance and self.instance.is_protected:
            self.fields["name"].disabled = True

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        reserved = {"master", "admin", "manager", "viewer"}
        if name.casefold() in reserved and (not self.instance.pk or self.instance.name.casefold() != name.casefold()):
            raise forms.ValidationError("That role name is reserved.")
        return name


class AlertEmailTemplateForm(forms.ModelForm):
    html_body = forms.CharField(
        label="Complete HTML email",
        help_text="Paste your full HTML email. Placeholders: {{ service }}, {{ project }}, {{ status }}, {{ details }}, {{ site_url }}, {{ event_time }}, {{ down_since }}, {{ downtime }}, {{ check_interval }}.",
        widget=forms.Textarea(attrs={"rows": 30, "spellcheck": "false", "class": "html-source-editor", "wrap": "off"}),
    )

    class Meta:
        model = AlertEmailTemplate
        fields = ["subject", "html_body"]
        labels = {
            "subject": "Email subject",
            "html_body": "Complete HTML email",
        }
        help_texts = {
            "subject": "Available placeholders: {service}, {project}, {status}, {details}, {site_url}.",
            "html_body": "Use {{ service }}, {{ project }}, {{ status }}, {{ details }}, {{ site_url }}, {{ event_time }}, {{ down_since }}, {{ downtime }}, and {{ check_interval }} placeholders.",
        }
        widgets = {
            "html_body": forms.Textarea(attrs={"rows": 30, "spellcheck": "false", "class": "html-source-editor", "wrap": "off"}),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "theme_preference"]
        labels = {"theme_preference": "Default theme"}
        help_texts = {"theme_preference": "Choose the theme used when you open your workspace."}
        widgets = {"theme_preference": forms.RadioSelect}
