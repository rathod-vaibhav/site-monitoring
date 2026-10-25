from datetime import timedelta
from pathlib import Path
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count, F, Q, Window
from django.http import FileResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.db.models.functions import RowNumber
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from .forms import ProjectForm, MonitorForm, TeamUserForm, TeamUserEditForm, TeamUserPasswordForm, UserProfileForm, AccessRoleForm, AlertEmailTemplateForm
from .models import Project, Monitor, Incident, CheckResult, AccessRole, AlertEmailTemplate
from .email_templates import DEFAULT_ALERT_TEMPLATES, DEFAULT_EMAIL_HTML, build_alert_email
from .role_permissions import permissions_for_role, ROLE_PERMISSION_GROUPS, ROLE_PERMISSION_LABELS
from .tasks import run_check

User = get_user_model()

def favicon(request):
    """Serve the app favicon directly, including when DEBUG is disabled."""
    favicon_path = Path(__file__).parent / "static" / "monitors" / "favicon.svg"
    return FileResponse(open(favicon_path, "rb"), content_type="image/svg+xml")

def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.has_perm("monitors.manage_team") or user.has_perm("monitors.manage_roles") or user.has_perm("monitors.manage_user_passwords"))

def can_manage(user):
    return user.is_authenticated and (user.is_superuser or any(user.has_perm(f"monitors.manage_{area}") for area in ("projects", "monitors", "incidents")))

def common_context(user):
    can_manage_projects = has_management_permission(user, "projects")
    can_manage_monitors = has_management_permission(user, "monitors")
    can_manage_incidents = has_management_permission(user, "incidents")
    return {
        "can_manage": can_manage_projects or can_manage_monitors or can_manage_incidents,
        "can_manage_projects": can_manage_projects,
        "can_manage_monitors": can_manage_monitors,
        "can_manage_incidents": can_manage_incidents,
        "is_admin": is_admin(user),
        "can_manage_team": user.is_authenticated and (user.is_superuser or user.has_perm("monitors.manage_team")),
        "can_manage_roles": user.is_authenticated and (user.is_superuser or user.has_perm("monitors.manage_roles")),
        "can_manage_passwords": user.is_authenticated and (user.is_superuser or user.has_perm("monitors.manage_user_passwords")),
    }

def has_management_permission(user, area):
    return user.is_authenticated and (user.is_superuser or user.has_perm(f"monitors.manage_{area}"))

def accessible_projects(user):
    """Return every project for superusers, otherwise only assigned projects."""
    projects = Project.objects.all()
    if user.is_superuser:
        return projects
    return projects.filter(assigned_users=user)

def apply_listing_search(queryset, raw_query, fields):
    """Apply a safe `field:value` search or a plain search across allowed fields."""
    query = (raw_query or "").strip()[:160]
    aliases = {key.casefold(): lookups for key, lookups in fields.items()}
    selected_fields = None
    term = query
    if ":" in query:
        prefix, value = query.split(":", 1)
        selected_fields = aliases.get(prefix.strip().casefold())
        if selected_fields:
            term = value.strip()
    if term:
        lookups = selected_fields or [lookup for values in fields.values() for lookup in values]
        condition = Q()
        for lookup in dict.fromkeys(lookups):
            condition |= Q(**{f"{lookup}__icontains": term})
        queryset = queryset.filter(condition).distinct()
    return queryset, query


def search_field_options(fields):
    return [{"key": key, "label": key.replace("_", " ").title()} for key in fields]


def paginate_queryset(request, queryset, per_page, page_param="page"):
    page_obj = Paginator(queryset, per_page).get_page(request.GET.get(page_param))
    params = request.GET.copy()
    params.pop(page_param, None)
    return page_obj, params.urlencode()

def add_recent_uptime(monitors):
    for monitor in monitors:
        samples = getattr(monitor, "recent_results", [])
        samples.reverse()
        monitor.uptime_percent = round(sum(result.ok for result in samples) * 100 / len(samples), 1) if samples else None
        latencies = [result.response_time_ms for result in samples if result.response_time_ms is not None]
        if latencies:
            ceiling = max(max(latencies), 1) * 1.15
            points = [(round(i / max(len(latencies) - 1, 1) * 100, 1), round(24 - value / ceiling * 21, 1)) for i, value in enumerate(latencies)]
            monitor.sparkline_points = " ".join(f"{x},{y}" for x, y in points)
        else:
            monitor.sparkline_points = ""

def response_chart_series(monitors, hours):
    monitors = list(monitors)
    if not monitors:
        return []
    window_start = timezone.now() - timedelta(hours=hours)
    checks = (
        CheckResult.objects.filter(monitor_id__in=[monitor.pk for monitor in monitors], checked_at__gte=window_start)
        .annotate(sample_rank=Window(
            expression=RowNumber(),
            partition_by=[F("monitor_id")],
            order_by=F("checked_at").desc(),
        ))
        .filter(sample_rank__lte=120)
        .values("monitor_id", "response_time_ms", "checked_at", "ok")
        .order_by("monitor_id", "checked_at")
    )
    samples_by_monitor = {}
    for check in checks:
        samples_by_monitor.setdefault(check["monitor_id"], []).append((check["checked_at"], check["response_time_ms"], check["ok"]))

    colors = ["#2563eb", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5", "#0f766e"]
    series = []
    for index, monitor in enumerate(monitors):
        samples = samples_by_monitor.get(monitor.pk, [])
        data = [{
            "x": round((checked_at - window_start).total_seconds() / 3600, 3),
            "y": (latency or 0) if not ok else latency,
            "ok": ok,
            "checked_at": checked_at.isoformat(),
        } for checked_at, latency, ok in samples]
        color = colors[index % len(colors)]
        series.append({
            "name": monitor.name,
            "color": color,
            "is_down": monitor.is_active and monitor.status == Monitor.Status.DOWN,
            "latest": samples[-1][1] if samples and samples[-1][2] else None,
            "samples": len(samples),
            "has_data": bool(samples),
            "chart_dataset": {
                "label": monitor.name,
                "data": data,
                "borderColor": color,
                "backgroundColor": color,
                "monitorStatus": monitor.status,
                "monitorActive": monitor.is_active,
                "borderWidth": 2,
                "tension": 0.25,
                "spanGaps": True,
                "pointRadius": 2.5,
                "pointHoverRadius": 6,
                "pointBackgroundColor": color,
                "pointBorderColor": "#fff",
                "pointBorderWidth": 1.5,
            },
        })
    return series


def chart_range(request):
    allowed = {1, 2, 6, 12, 24}
    try:
        value = int(request.GET.get("range", "1"))
    except (TypeError, ValueError):
        value = 1
    return value if value in allowed else 1


@login_required
@never_cache
def dashboard_status(request):
    """Return a compact, access-scoped status snapshot for dashboard polling."""
    projects = accessible_projects(request.user)
    monitors = Monitor.objects.filter(project__in=projects)
    selected_range = chart_range(request)
    aggregate = monitors.aggregate(
        total=Count("id"),
        up=Count("id", filter=Q(is_active=True, status=Monitor.Status.UP)),
        down=Count("id", filter=Q(is_active=True, status=Monitor.Status.DOWN)),
    )
    aggregate["other"] = max(0, aggregate["total"] - aggregate["up"] - aggregate["down"])
    aggregate["incidents"] = Incident.objects.filter(
        monitor__project__in=projects, resolved_at__isnull=True
    ).count()
    status_labels = {
        Monitor.Status.UP: "Up",
        Monitor.Status.DOWN: "Down",
        Monitor.Status.SUSPECT: "Degraded",
        Monitor.Status.UNKNOWN: "Unknown",
    }
    chart_monitors = list(monitors.select_related("project").order_by("project__name", "name"))
    snapshot = []
    for monitor in chart_monitors:
        snapshot.append({
            "id": monitor.id,
            "name": monitor.name,
            "project_id": monitor.project_id,
            "project_name": monitor.project.name,
            "is_active": monitor.is_active,
            "status": monitor.status,
            "last_response_ms": monitor.last_response_ms,
            "label": "Paused" if not monitor.is_active else status_labels.get(monitor.status, "Unknown"),
            "detail_url": reverse("monitor_detail", args=[monitor.id]),
        })
    response_series = response_chart_series(chart_monitors, selected_range)
    return JsonResponse({
        "counts": aggregate,
        "monitors": snapshot,
        "chart_datasets": [series["chart_dataset"] for series in response_series],
        "chart_range": selected_range,
    })

@login_required
def dashboard(request):
    recent_checks = Prefetch("results", queryset=CheckResult.objects.order_by("-checked_at")[:12], to_attr="recent_results")
    monitor_preview = Prefetch("monitors", queryset=Monitor.objects.prefetch_related(recent_checks).order_by("name"), to_attr="preview_monitors")
    projects = accessible_projects(request.user).prefetch_related(monitor_preview).annotate(monitor_count=Count("monitors")).order_by("name")
    projects = list(projects)
    for project in projects:
        add_recent_uptime(project.preview_monitors)
    scoped_monitors = Monitor.objects.filter(project__in=projects)
    monitor_counts = scoped_monitors.aggregate(
        total=Count("id"),
        up=Count("id", filter=Q(is_active=True, status=Monitor.Status.UP)),
        down=Count("id", filter=Q(is_active=True, status=Monitor.Status.DOWN)),
        paused=Count("id", filter=Q(is_active=False)),
    )
    monitor_counts["attention"] = max(0, monitor_counts["total"] - monitor_counts["up"] - monitor_counts["down"])
    counts = {
        "total": monitor_counts["total"],
        "up": monitor_counts["up"],
        "down": monitor_counts["down"],
        "paused": monitor_counts["paused"],
        "incidents": Incident.objects.filter(monitor__project__in=projects, resolved_at__isnull=True).count(),
    }
    counts["other"] = max(0, counts["total"] - counts["up"] - counts["down"])
    status_total = max(counts["total"], 1)
    counts["up_percent"] = round(counts["up"] * 100 / status_total, 2)
    counts["other_percent"] = round(counts["other"] * 100 / status_total, 2)
    counts["down_percent"] = round(counts["down"] * 100 / status_total, 2)
    counts["other_end_percent"] = round((counts["up"] + counts["other"]) * 100 / status_total, 2)
    recent_incidents = Incident.objects.filter(monitor__project__in=projects).select_related("monitor", "monitor__project").order_by("resolved_at", "-started_at")[:5]

    selected_range = chart_range(request)
    chart_monitors = [monitor for project in projects for monitor in project.preview_monitors]
    service_chart = response_chart_series(chart_monitors, selected_range)

    alert_monitors = [monitor for monitor in chart_monitors if not monitor.is_active or monitor.status != Monitor.Status.UP]
    status_priority = {Monitor.Status.DOWN: 0, Monitor.Status.SUSPECT: 1, Monitor.Status.UNKNOWN: 2}
    alert_monitors.sort(key=lambda monitor: (status_priority.get(monitor.status, 3) if monitor.is_active else 4, monitor.name.casefold()))
    down_alert_monitors = [monitor for monitor in alert_monitors if monitor.is_active and monitor.status == Monitor.Status.DOWN][:8]
    attention_alert_monitors = [monitor for monitor in alert_monitors if not monitor.is_active or monitor.status not in (Monitor.Status.UP, Monitor.Status.DOWN)][:8]

    context = {
        "alert_monitors": alert_monitors,
        "down_alert_monitors": down_alert_monitors,
        "attention_alert_monitors": attention_alert_monitors,
        "projects": projects,
        "project_total": len(projects),
        "dashboard_updated_at": timezone.localtime(),
        "counts": counts,
        "recent_incidents": recent_incidents,
        "service_chart": service_chart,
        "service_chart_data": [series["chart_dataset"] for series in service_chart],
        "service_chart_total": len(chart_monitors),
        "service_chart_samples": sum(item["samples"] for item in service_chart),
        "selected_range": selected_range,
        "range_choices": [(1, "Last hour"), (2, "Last 2 hours"), (6, "Last 6 hours"), (12, "Last 12 hours"), (24, "Last 24 hours")],
    }
    context.update(common_context(request.user))
    return render(request, "monitors/dashboard.html", context)

@login_required
def projects_page(request):
    recent_checks = Prefetch("results", queryset=CheckResult.objects.order_by("-checked_at")[:24], to_attr="recent_results")
    monitor_preview = Prefetch("monitors", queryset=Monitor.objects.prefetch_related(recent_checks).order_by("name")[:8], to_attr="preview_monitors")
    projects = accessible_projects(request.user).prefetch_related(monitor_preview).annotate(monitor_count=Count("monitors")).order_by("name")
    status_page = request.GET.get("status_page", "")
    if status_page == "enabled": projects = projects.filter(status_page_enabled=True)
    elif status_page == "disabled": projects = projects.filter(status_page_enabled=False)
    health = request.GET.get("health", "")
    health_values = {Monitor.Status.UP, Monitor.Status.DOWN, Monitor.Status.SUSPECT, Monitor.Status.UNKNOWN}
    if health == "PAUSED": projects = projects.filter(monitors__is_active=False)
    elif health == "ATTENTION": projects = projects.filter(Q(monitors__is_active=False) | Q(monitors__is_active=True, monitors__status__in=[Monitor.Status.SUSPECT, Monitor.Status.UNKNOWN]))
    elif health in health_values: projects = projects.filter(monitors__status=health, monitors__is_active=True)
    elif health != "": health = ""
    project_search_fields = {"name": ["name"], "description": ["description"], "service": ["monitors__name", "monitors__target"]}
    projects, search_query = apply_listing_search(projects, request.GET.get("q", ""), project_search_fields)
    projects = projects.distinct()
    page_obj, pagination_query = paginate_queryset(request, projects, 12)
    for project in page_obj.object_list:
        add_recent_uptime(project.preview_monitors)
    context = {"projects": page_obj, "page_obj": page_obj, "pagination_query": pagination_query, "page_param": "page", "page_title": "Projects", "selected_status_page": status_page, "selected_health": health, "search_query": search_query, "search_fields": search_field_options(project_search_fields)}; context.update(common_context(request.user))
    return render(request, "monitors/projects.html", context)

@login_required
def project_detail(request, project_id):
    project = get_object_or_404(accessible_projects(request.user), pk=project_id)
    monitors = Monitor.objects.filter(project=project).order_by("name")
    status = request.GET.get("status", "")
    if status == "PAUSED":
        monitors = monitors.filter(is_active=False)
    elif status == "ATTENTION":
        monitors = monitors.filter(Q(is_active=False) | Q(is_active=True, status__in=[Monitor.Status.SUSPECT, Monitor.Status.UNKNOWN]))
    elif status in Monitor.Status.values:
        monitors = monitors.filter(is_active=True, status=status)
    else:
        status = ""

    monitor_search_fields = {"name": ["name"], "url": ["target"]}
    monitors, search_query = apply_listing_search(monitors, request.GET.get("q", ""), monitor_search_fields)
    page_obj, pagination_query = paginate_queryset(request, monitors, 24)
    page_monitors = list(page_obj.object_list)
    recent_checks = Prefetch("results", queryset=CheckResult.objects.order_by("-checked_at")[:24], to_attr="recent_results")
    checked_monitors = Monitor.objects.filter(pk__in=[monitor.pk for monitor in page_monitors]).prefetch_related(recent_checks)
    recent_by_id = {monitor.pk: monitor.recent_results for monitor in checked_monitors}
    for monitor in page_monitors:
        monitor.recent_results = recent_by_id.get(monitor.pk, [])
    add_recent_uptime(page_monitors)
    uptime_30d = {
        row["monitor_id"]: round(row["passed"] * 100 / row["total"], 2)
        for row in CheckResult.objects.filter(monitor__in=page_monitors, checked_at__gte=timezone.now() - timedelta(days=30))
        .values("monitor_id").annotate(total=Count("id"), passed=Count("id", filter=Q(ok=True)))
    }
    for monitor in page_monitors:
        monitor.uptime_30d = uptime_30d.get(monitor.pk)
    page_obj.object_list = page_monitors
    monitor_counts = project.monitors.aggregate(
        total=Count("id"),
        up=Count("id", filter=Q(is_active=True, status=Monitor.Status.UP)),
        down=Count("id", filter=Q(is_active=True, status=Monitor.Status.DOWN)),
        attention=Count("id", filter=Q(is_active=True, status__in=[Monitor.Status.SUSPECT, Monitor.Status.UNKNOWN])),
        paused=Count("id", filter=Q(is_active=False)),
    )
    monitor_counts["attention"] += monitor_counts["paused"]
    context = {
        "project": project,
        "monitors": page_obj,
        "page_obj": page_obj,
        "pagination_query": pagination_query,
        "page_param": "page",
        "selected_status": status,
        "monitor_counts": monitor_counts,
        "search_query": search_query,
        "search_fields": search_field_options(monitor_search_fields),
    }
    context.update(common_context(request.user))
    return render(request, "monitors/project_detail.html", context)

@login_required
def monitors_page(request):
    projects = accessible_projects(request.user)
    monitors = Monitor.objects.filter(project__in=projects).select_related("project").order_by("project__name", "name")
    status = request.GET.get("status", "")
    if status == "PAUSED":
        monitors = monitors.filter(is_active=False)
    elif status == "ATTENTION":
        monitors = monitors.filter(Q(is_active=False) | Q(is_active=True, status__in=[Monitor.Status.SUSPECT, Monitor.Status.UNKNOWN]))
    elif status in Monitor.Status.values:
        monitors = monitors.filter(is_active=True, status=status)
    else:
        status = ""
    project_id = request.GET.get("project", "")
    if project_id.isdigit(): monitors = monitors.filter(project_id=project_id)
    else: project_id = ""
    monitor_search_fields = {"name": ["name"], "url": ["target"], "project": ["project__name"]}
    monitors, search_query = apply_listing_search(monitors, request.GET.get("q", ""), monitor_search_fields)
    page_obj, pagination_query = paginate_queryset(request, monitors, 24)
    page_monitors = list(page_obj.object_list)
    recent_checks = Prefetch("results", queryset=CheckResult.objects.order_by("-checked_at")[:24], to_attr="recent_results")
    checked_monitors = list(Monitor.objects.filter(pk__in=[monitor.pk for monitor in page_monitors]).prefetch_related(recent_checks))
    recent_by_id = {monitor.pk: monitor.recent_results for monitor in checked_monitors}
    for monitor in page_monitors:
        monitor.recent_results = recent_by_id.get(monitor.pk, [])
    add_recent_uptime(page_monitors)
    uptime_30d = {
        row["monitor_id"]: round(row["passed"] * 100 / row["total"], 2)
        for row in CheckResult.objects.filter(monitor__in=page_monitors, checked_at__gte=timezone.now() - timedelta(days=30))
        .values("monitor_id").annotate(total=Count("id"), passed=Count("id", filter=Q(ok=True)))
    }
    for monitor in page_monitors:
        monitor.uptime_30d = uptime_30d.get(monitor.pk)
    page_obj.object_list = page_monitors
    monitor_counts = monitors.aggregate(
        total=Count("id"),
        up=Count("id", filter=Q(is_active=True, status=Monitor.Status.UP)),
        suspect=Count("id", filter=Q(is_active=True, status=Monitor.Status.SUSPECT)),
        unknown=Count("id", filter=Q(is_active=True, status=Monitor.Status.UNKNOWN)),
        down=Count("id", filter=Q(is_active=True, status=Monitor.Status.DOWN)),
        paused=Count("id", filter=Q(is_active=False)),
    )
    monitor_counts["attention"] = monitor_counts["suspect"] + monitor_counts["unknown"] + monitor_counts["paused"]
    context = {"monitors": page_obj, "page_obj": page_obj, "pagination_query": pagination_query, "page_param": "page", "projects": projects.order_by("name"), "selected_status": status, "selected_project": project_id, "page_title": "Monitors", "monitor_counts": monitor_counts, "search_query": search_query, "search_fields": search_field_options(monitor_search_fields)}
    context.update(common_context(request.user))
    return render(request, "monitors/monitors.html", context)

@login_required
def monitor_detail(request, monitor_id):
    monitor = get_object_or_404(Monitor.objects.filter(project__in=accessible_projects(request.user)).select_related("project"), pk=monitor_id)
    results, results_query = paginate_queryset(request, monitor.results.order_by("-checked_at"), 25, "checks_page")
    incidents, incidents_query = paginate_queryset(request, monitor.incidents.order_by("-started_at"), 10, "incidents_page")
    selected_range = chart_range(request)
    service_chart = response_chart_series([monitor], selected_range)
    context = {"monitor": monitor, "results": results, "incidents": incidents, "results_query": results_query, "incidents_query": incidents_query, "service_chart": service_chart, "service_chart_data": [series["chart_dataset"] for series in service_chart], "service_chart_samples": sum(item["samples"] for item in service_chart), "service_chart_total": 1, "selected_range": selected_range, "range_choices": [(1, "Last hour"), (2, "Last 2 hours"), (6, "Last 6 hours"), (12, "Last 12 hours"), (24, "Last 24 hours")]}; context.update(common_context(request.user))
    return render(request, "monitors/monitor_detail.html", context)

@login_required
def project_create(request):
    if not has_management_permission(request.user, "projects"): return HttpResponseForbidden("You do not have permission to manage projects.")
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        if not request.user.is_superuser:
            project.assigned_users.add(request.user)
        messages.success(request, "Project created."); return redirect("projects_page")
    context = {"form": form, "title": "New project"}; context.update(common_context(request.user))
    return render(request, "monitors/project_form.html", context)

@login_required
def project_edit(request, project_id):
    if not has_management_permission(request.user, "projects"): return HttpResponseForbidden("You do not have permission to manage projects.")
    project = get_object_or_404(accessible_projects(request.user), pk=project_id)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Project updated."); return redirect("projects_page")
    context = {"form": form, "title": "Edit project", "project": project}; context.update(common_context(request.user))
    return render(request, "monitors/project_form.html", context)

@login_required
def monitor_create(request, project_id):
    if not has_management_permission(request.user, "monitors"): return HttpResponseForbidden("You do not have permission to manage monitors.")
    project = get_object_or_404(accessible_projects(request.user), pk=project_id)
    form = MonitorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        monitor = form.save(commit=False); monitor.project = project; monitor.save(); messages.success(request, "Monitor added."); return redirect("project_detail", project_id=project.id)
    context = {"form": form, "project": project, "title": "Add monitor"}; context.update(common_context(request.user))
    return render(request, "monitors/monitor_form.html", context)

@login_required
def monitor_edit(request, monitor_id):
    if not has_management_permission(request.user, "monitors"): return HttpResponseForbidden("You do not have permission to edit monitors.")
    monitor = get_object_or_404(Monitor.objects.filter(project__in=accessible_projects(request.user)).select_related("project"), pk=monitor_id)
    form = MonitorForm(request.POST or None, instance=monitor)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Monitor updated."); return redirect("monitor_detail", monitor_id=monitor.id)
    context = {"form": form, "project": monitor.project, "title": "Edit monitor", "monitor": monitor}; context.update(common_context(request.user))
    return render(request, "monitors/monitor_form.html", context)

@login_required
def monitor_check_now(request, monitor_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "monitors"): return HttpResponseForbidden()
    monitor = get_object_or_404(Monitor.objects.filter(project__in=accessible_projects(request.user)), pk=monitor_id)
    run_check(monitor.id, force=True)
    messages.success(request, "Check finished.")
    return redirect("monitor_detail", monitor_id=monitor.id)

@login_required
def monitor_toggle(request, monitor_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "monitors"): return HttpResponseForbidden()
    monitor = get_object_or_404(Monitor.objects.filter(project__in=accessible_projects(request.user)), pk=monitor_id)
    monitor.is_active = not monitor.is_active
    if monitor.is_active: monitor.next_check_at = timezone.now()
    monitor.save(update_fields=["is_active", "next_check_at"])
    messages.success(request, "Monitoring resumed." if monitor.is_active else "Monitoring paused.")
    return redirect("monitor_detail", monitor_id=monitor.id)

@login_required
def project_delete(request, project_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "projects"): return HttpResponseForbidden()
    get_object_or_404(accessible_projects(request.user), pk=project_id).delete(); messages.success(request, "Project deleted."); return redirect("projects_page")

@login_required
def monitor_delete(request, monitor_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "monitors"): return HttpResponseForbidden()
    get_object_or_404(Monitor.objects.filter(project__in=accessible_projects(request.user)), pk=monitor_id).delete(); messages.success(request, "Monitor deleted."); return redirect("monitors_page")

@login_required
def incidents_page(request):
    projects = accessible_projects(request.user)
    incidents = Incident.objects.filter(monitor__project__in=projects).select_related("monitor", "monitor__project", "acknowledged_by").prefetch_related("email_alerts").order_by("resolved_at", "-started_at")
    state = request.GET.get("state", "open")
    if state not in {"open", "resolved", "all"}: state = "open"
    if state == "open": incidents = incidents.filter(resolved_at__isnull=True)
    elif state == "resolved": incidents = incidents.filter(resolved_at__isnull=False)
    incident_search_fields = {"monitor": ["monitor__name"], "project": ["monitor__project__name"], "note": ["resolution_note"], "acknowledger": ["acknowledged_by__username", "acknowledged_by__first_name", "acknowledged_by__last_name"]}
    incidents, search_query = apply_listing_search(incidents, request.GET.get("q", ""), incident_search_fields)
    page_obj, pagination_query = paginate_queryset(request, incidents, 25)
    incident_counts = {
        "open": Incident.objects.filter(monitor__project__in=projects, resolved_at__isnull=True).count(),
        "resolved": Incident.objects.filter(monitor__project__in=projects, resolved_at__isnull=False).count(),
    }
    context = {"incidents": page_obj, "page_obj": page_obj, "pagination_query": pagination_query, "page_param": "page", "selected_state": state, "incident_counts": incident_counts, "search_query": search_query, "search_fields": search_field_options(incident_search_fields)}; context.update(common_context(request.user))
    return render(request, "monitors/incidents.html", context)

@login_required
def incident_acknowledge(request, incident_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "incidents"): return HttpResponseForbidden()
    incident = get_object_or_404(Incident.objects.filter(monitor__project__in=accessible_projects(request.user)), pk=incident_id, resolved_at__isnull=True)
    incident.acknowledged_by = request.user; incident.acknowledged_at = timezone.now()
    incident.save(update_fields=["acknowledged_by", "acknowledged_at"])
    messages.success(request, "Incident acknowledged."); return redirect("incidents_page")

@login_required
def incident_resolve(request, incident_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "incidents"): return HttpResponseForbidden()
    incident = get_object_or_404(Incident.objects.filter(monitor__project__in=accessible_projects(request.user)), pk=incident_id, resolved_at__isnull=True)
    incident.resolved_at = timezone.now(); incident.resolution_note = "Resolved manually"; incident.save(update_fields=["resolved_at", "resolution_note"])
    messages.success(request, "Incident resolved."); return redirect("incidents_page")

@login_required
def team_users(request):
    can_manage_team = has_management_permission(request.user, "team")
    can_manage_passwords = has_management_permission(request.user, "user_passwords")
    if not (can_manage_team or can_manage_passwords): return HttpResponseForbidden("You do not have permission to view team members.")
    form = TeamUserForm(request.POST or None)
    if request.method == "POST":
        if not can_manage_team: return HttpResponseForbidden("You do not have permission to create team members.")
        if form.is_valid(): form.save(); messages.success(request, "User created."); return redirect("team_users")
    users = User.objects.prefetch_related("assigned_projects").order_by("username")
    role = request.GET.get("role", "")
    access = request.GET.get("access", "")
    if role.isdigit(): users = users.filter(access_role_id=role)
    if access == "active": users = users.filter(is_active=True)
    elif access == "disabled": users = users.filter(is_active=False)
    team_search_fields = {"username": ["username"], "email": ["email"], "first": ["first_name"], "last": ["last_name"], "role": ["access_role__name", "role"]}
    users, search_query = apply_listing_search(users, request.GET.get("q", ""), team_search_fields)
    page_obj, pagination_query = paginate_queryset(request, users, 25)
    context = {"form": form, "users": page_obj, "users_total": User.objects.count(), "filtered_users_total": users.count(), "selected_role": role, "selected_access": access, "roles": AccessRole.objects.order_by("name"), "page_obj": page_obj, "pagination_query": pagination_query, "page_param": "page", "search_query": search_query, "search_fields": search_field_options(team_search_fields)}; context.update(common_context(request.user))
    return render(request, "monitors/users.html", context)

@login_required
def team_user_edit(request, user_id):
    if not has_management_permission(request.user, "team"): return HttpResponseForbidden("You do not have permission to manage team members.")
    person = get_object_or_404(User, pk=user_id)
    form = TeamUserEditForm(request.POST or None, instance=person)
    if person.is_superuser:
        form.fields["access_role"].disabled = True
        form.fields["access_role"].required = False
        form.fields["is_active"].disabled = True
    if request.method == "POST" and form.is_valid():
        if person.pk == request.user.pk and not form.cleaned_data.get("is_active"):
            form.add_error("is_active", "You cannot deactivate your own account.")
        else:
            form.save(); messages.success(request, "User updated."); return redirect("team_users")
    context = {"form": form, "person": person}; context.update(common_context(request.user))
    return render(request, "monitors/user_form.html", context)

@login_required
def team_user_password(request, user_id):
    if not has_management_permission(request.user, "user_passwords"):
        return HttpResponseForbidden("You do not have permission to manage user passwords.")
    person = get_object_or_404(User, pk=user_id)
    if person.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden("Only a superuser can change a superuser password.")
    form = TeamUserPasswordForm(person, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Password updated for {person.get_full_name() or person.username}.")
        return redirect("team_users")
    context = {"form": form, "person": person, "title": "Reset password"}
    context.update(common_context(request.user))
    return render(request, "monitors/user_password_form.html", context)

@login_required
def settings_home(request):
    if not is_admin(request.user): return HttpResponseForbidden("You do not have permission to access workspace settings.")
    context = {"users_total": User.objects.count(), "roles_total": AccessRole.objects.count(), "email_templates_total": len(AlertEmailTemplate.Event.values)}
    context.update(common_context(request.user))
    return render(request, "monitors/settings.html", context)


@login_required
def email_templates_page(request):
    if not is_admin(request.user): return HttpResponseForbidden("You do not have permission to manage email templates.")
    is_edit_mode = request.GET.get("edit") == "1" or request.method == "POST"
    if not is_edit_mode:
        templates_by_event = {}
        for event, _label in AlertEmailTemplate.Event.choices:
            templates_by_event[event], _ = AlertEmailTemplate.objects.get_or_create(
                project=None,
                event=event,
                defaults=DEFAULT_ALERT_TEMPLATES[event],
            )
        email_templates = [
            {"event": event, "label": label, "template": templates_by_event.get(event)}
            for event, label in AlertEmailTemplate.Event.choices
        ]
        context = {"email_templates": email_templates, "is_edit_mode": False}
        context.update(common_context(request.user))
        return render(request, "monitors/email_templates.html", context)
    event = request.GET.get("event") or request.POST.get("event") or AlertEmailTemplate.Event.DOWN
    if event not in AlertEmailTemplate.Event.values:
        event = AlertEmailTemplate.Event.DOWN
    template, _ = AlertEmailTemplate.objects.get_or_create(project=None, event=event, defaults=DEFAULT_ALERT_TEMPLATES[event])
    initial = {"html_body": DEFAULT_EMAIL_HTML[event]} if not template.html_body else None
    form = AlertEmailTemplateForm(request.POST or None, instance=template, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{template.get_event_display()} email template saved.")
        return redirect(f"{reverse('email_templates_page')}?event={event}&edit=1")
    _, preview_html, _ = build_alert_email(
        template,
        monitor_name="BETA ASM",
        project_name="ASM Sparrow",
        monitor_url="https://betaspar.eurocircuits.com/",
        monitor_link=request.build_absolute_uri(reverse("monitors_page")),
        detail="DNS lookup failed",
        event_time=timezone.now(),
        check_interval_seconds=60,
    )
    context = {"form": form, "email_template": template, "selected_event": event, "preview_html": preview_html, "is_edit_mode": True}
    context.update(common_context(request.user))
    return render(request, "monitors/email_templates.html", context)


@login_required
def email_template_preview(request):
    if not is_admin(request.user): return HttpResponseForbidden("You do not have permission to preview email templates.")
    if request.method != "POST": return HttpResponse(status=405)
    event = request.POST.get("event", AlertEmailTemplate.Event.DOWN)
    if event not in AlertEmailTemplate.Event.values:
        return HttpResponseBadRequest("Unknown email event.")
    template, _ = AlertEmailTemplate.objects.get_or_create(project=None, event=event, defaults=DEFAULT_ALERT_TEMPLATES[event])
    form = AlertEmailTemplateForm(request.POST, instance=template)
    if not form.is_valid():
        return HttpResponseBadRequest("Complete the required template fields to preview.")
    unsaved_template = form.save(commit=False)
    _, preview_html, _ = build_alert_email(
        unsaved_template,
        monitor_name="BETA ASM",
        project_name="ASM Sparrow",
        monitor_url="https://betaspar.eurocircuits.com/",
        monitor_link=request.build_absolute_uri(reverse("monitors_page")),
        detail="DNS lookup failed",
        event_time=timezone.now(),
        incident_started_at=timezone.now() - timedelta(minutes=14),
        downtime_seconds=14 * 60,
        check_interval_seconds=60,
    )
    return HttpResponse(preview_html)

@login_required
def roles_page(request):
    if not has_management_permission(request.user, "roles"): return HttpResponseForbidden("You do not have permission to manage roles.")
    roles = AccessRole.objects.annotate(member_count=Count("users", distinct=True)).prefetch_related("permissions").order_by("name")
    roles_total = roles.count()
    role_search_fields = {"name": ["name"], "description": ["description"], "permission": ["permissions__name", "permissions__codename"]}
    roles, search_query = apply_listing_search(roles, request.GET.get("q", ""), role_search_fields)
    for role in roles:
        role.permission_flags = permissions_for_role(role)
        role.permission_labels = [label for key, label in ROLE_PERMISSION_LABELS.items() if role.permission_flags[key]]
        role.permission_groups = [
            {
                "name": group_name,
                "labels": [ROLE_PERMISSION_LABELS[key] for key in keys if role.permission_flags[key]],
            }
            for group_name, keys in ROLE_PERMISSION_GROUPS.items()
            if any(role.permission_flags[key] for key in keys)
        ]
    context = {"roles": roles, "roles_total": roles_total, "filtered_roles_total": roles.count(), "search_query": search_query, "search_fields": search_field_options(role_search_fields)}
    context.update(common_context(request.user))
    return render(request, "monitors/roles.html", context)

@login_required
def role_create(request):
    if not has_management_permission(request.user, "roles"): return HttpResponseForbidden("You do not have permission to manage roles.")
    form = AccessRoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Role created."); return redirect("roles_page")
    context = {"form": form, "title": "Add role", "submit_label": "Create role"}
    context.update(common_context(request.user))
    return render(request, "monitors/role_form.html", context)

@login_required
def role_edit(request, role_id):
    if not has_management_permission(request.user, "roles"): return HttpResponseForbidden("You do not have permission to manage roles.")
    role = get_object_or_404(AccessRole, pk=role_id)
    if role.name == "Master": return HttpResponseForbidden("The Master role cannot be edited.")
    form = AccessRoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Role updated."); return redirect("roles_page")
    context = {"form": form, "role": role, "title": "Edit role", "submit_label": "Save changes"}
    context.update(common_context(request.user))
    return render(request, "monitors/role_form.html", context)

@login_required
def role_delete(request, role_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "roles"): return HttpResponseForbidden("You do not have permission to manage roles.")
    role = get_object_or_404(AccessRole, pk=role_id)
    if role.is_protected:
        messages.error(request, "Protected roles cannot be deleted.")
    elif role.users.exists():
        messages.error(request, "Reassign this role's members before deleting it.")
    else:
        role.delete(); messages.success(request, "Role deleted.")
    return redirect("roles_page")

@login_required
def team_user_toggle(request, user_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "team"): return HttpResponseForbidden()
    person = get_object_or_404(User, pk=user_id)
    if person.pk == request.user.pk or person.is_superuser:
        messages.error(request, "That account cannot be disabled here.")
    else:
        person.is_active = not person.is_active
        person.save(update_fields=["is_active"])
        messages.success(request, "User enabled." if person.is_active else "User disabled.")
    return redirect("team_users")

@login_required
def profile_edit(request):
    form = UserProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated.")
        return redirect("dashboard")
    context = {"form": form}; context.update(common_context(request.user))
    return render(request, "monitors/profile_form.html", context)

@login_required
def theme_preference(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    theme = request.POST.get("theme")
    if theme not in User.ThemePreference.values:
        return JsonResponse({"error": "Invalid theme preference."}, status=400)
    request.user.theme_preference = theme
    request.user.save(update_fields=["theme_preference"])
    return JsonResponse({"theme": theme})

@login_required
def team_user_delete(request, user_id):
    if request.method != "POST": return HttpResponse(status=405)
    if not has_management_permission(request.user, "team"): return HttpResponseForbidden()
    person = get_object_or_404(User, pk=user_id)
    if person.pk == request.user.pk or person.is_superuser:
        messages.error(request, "Your own account and superuser accounts cannot be deleted here.")
    else:
        person.delete()
        messages.success(request, "User deleted.")
    return redirect("team_users")

def public_status(request, slug):
    project = get_object_or_404(Project, status_page_slug=slug, status_page_enabled=True)
    monitor_query = Monitor.objects.filter(project=project).order_by("name")
    total_monitors = monitor_query.count()
    active_monitors = monitor_query.filter(is_active=True)
    up_count = active_monitors.filter(status=Monitor.Status.UP).count()
    down_count = active_monitors.filter(status=Monitor.Status.DOWN).count()
    paused_count = monitor_query.filter(is_active=False).count()
    other_count = total_monitors - up_count - down_count
    if not total_monitors:
        overall_status, overall_label = "unknown", "No services are being monitored"
    elif down_count:
        overall_status, overall_label = "down", "Some services are currently unavailable"
    elif other_count:
        overall_status, overall_label = "attention", "Some services are paused or need attention"
    else:
        overall_status, overall_label = "up", "All systems operational"
    page_obj, pagination_query = paginate_queryset(request, monitor_query, 30)
    context = {
        "project": project,
        "public_monitors": page_obj,
        "page_obj": page_obj,
        "pagination_query": pagination_query,
        "page_param": "page",
        "total_monitors": total_monitors,
        "up_count": up_count,
        "down_count": down_count,
        "other_count": other_count,
        "paused_count": paused_count,
        "overall_status": overall_status,
        "overall_label": overall_label,
        "open_incidents": Incident.objects.filter(monitor__project=project, resolved_at__isnull=True).count(),
    }
    return render(request, "monitors/public_status.html", context)

def healthz(request):
    try:
        with connection.cursor() as cursor: cursor.execute("SELECT 1")
        return HttpResponse("ok")
    except Exception: return HttpResponse("unavailable", status=503)
