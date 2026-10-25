import re

from django.utils.html import conditional_escape
from django.utils import timezone
from urllib.parse import urlsplit


DEFAULT_DOWN_EMAIL_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ status }}: {{ service }}</title></head>
<body style="margin:0;padding:32px 12px;background:#f3f5f8;color:#172033;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fff;border:1px solid #e5e9f0;border-radius:14px;overflow:hidden">
<tr><td style="padding:22px 28px;background:#202631;color:#fff;font-size:20px;font-weight:700">Site Monitoring</td></tr>
<tr><td style="padding:28px"><div style="display:inline-block;padding:6px 10px;border-radius:20px;background:#fff0f0;color:#bd343d;font-size:12px;font-weight:bold">{{ status }}</div>
<h1 style="margin:16px 0 8px;font-size:24px;color:#bd343d">Service is down</h1>
<p style="margin:0 0 20px;color:#687386;line-height:1.6">A monitored service changed status. Here are the latest details.</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e5e9f0;border-radius:10px"><tr><td style="padding:12px 16px;color:#687386;font-size:12px">PROJECT</td></tr><tr><td style="padding:0 16px 14px;font-weight:bold">{{ project }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">SERVICE</td></tr><tr><td style="padding:0 16px 14px;font-weight:bold">{{ service }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">SITE</td></tr><tr><td style="padding:0 16px 14px;line-height:1.6"><a href="{{ site_url }}" style="color:#1a73e8;overflow-wrap:anywhere">{{ site_url }}</a></td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">DETECTED AT</td></tr><tr><td style="padding:0 16px 14px">{{ event_time }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">CHECK INTERVAL</td></tr><tr><td style="padding:0 16px 14px">Every {{ check_interval }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">LATEST CHECK DETAILS</td></tr><tr><td style="padding:0 16px 16px;line-height:1.6">{{ details }}</td></tr></table>
<p style="margin:20px 0 0;color:#687386;font-size:13px;line-height:1.6">Review the incident in Site Monitoring and check the latest monitor results.</p></td></tr>
<tr><td style="padding:17px 28px;border-top:1px solid #edf0f4;color:#8a93a2;font-size:12px">Automated notification from Site Monitoring.</td></tr></table>
</td></tr></table></body></html>'''

DEFAULT_RECOVERED_EMAIL_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Service is back up: {{ service }}</title></head>
<body style="margin:0;padding:32px 12px;background:#f3f5f8;color:#172033;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fff;border:1px solid #e5e9f0;border-radius:14px;overflow:hidden">
<tr><td style="padding:22px 28px;background:#202631;color:#fff;font-size:20px;font-weight:700">Site Monitoring</td></tr>
<tr><td style="padding:28px"><div style="display:inline-block;padding:6px 10px;border-radius:20px;background:#eaf8f1;color:#178253;font-size:12px;font-weight:bold">UP</div>
<h1 style="margin:16px 0 8px;font-size:24px;color:#178253">Service is back up</h1>
<p style="margin:0 0 20px;color:#687386;line-height:1.6">The monitored service is responding normally again.</p>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e5e9f0;border-radius:10px"><tr><td style="padding:12px 16px;color:#687386;font-size:12px">PROJECT</td></tr><tr><td style="padding:0 16px 14px;font-weight:bold">{{ project }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">SERVICE</td></tr><tr><td style="padding:0 16px 14px;font-weight:bold">{{ service }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">CURRENT STATUS</td></tr><tr><td style="padding:0 16px 14px;color:#178253;font-weight:bold">Up · Responding normally</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">SITE</td></tr><tr><td style="padding:0 16px 14px;line-height:1.6"><a href="{{ site_url }}" style="color:#1a73e8;overflow-wrap:anywhere">{{ site_url }}</a></td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">RECOVERED AT</td></tr><tr><td style="padding:0 16px 14px">{{ event_time }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">DOWNTIME</td></tr><tr><td style="padding:0 16px 14px">{{ downtime }}</td></tr><tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">CHECK INTERVAL</td></tr><tr><td style="padding:0 16px 16px">Every {{ check_interval }}</td></tr></table>
<p style="margin:20px 0 0;color:#687386;font-size:13px;line-height:1.6">No action is required. Monitoring will continue.</p></td></tr>
<tr><td style="padding:17px 28px;border-top:1px solid #edf0f4;color:#8a93a2;font-size:12px">Automated notification from Site Monitoring.</td></tr></table>
</td></tr></table></body></html>'''
DEFAULT_ATTENTION_EMAIL_HTML = DEFAULT_DOWN_EMAIL_HTML.replace(
    "#fff0f0;color:#bd343d", "#fff6e5;color:#b06000"
).replace("font-size:24px;color:#bd343d", "font-size:24px;color:#b06000").replace("Service is down</h1>", "Service needs attention</h1>")
DEFAULT_EMAIL_HTML = {"DOWN": DEFAULT_DOWN_EMAIL_HTML, "RECOVERED": DEFAULT_RECOVERED_EMAIL_HTML, "ATTENTION": DEFAULT_ATTENTION_EMAIL_HTML}


DEFAULT_ALERT_TEMPLATES = {
    "DOWN": {
        "subject": "[{status}] {service} · Site Monitoring",
        "html_body": DEFAULT_DOWN_EMAIL_HTML,
        "heading": "Service is down",
        "intro": "A monitored service changed status. Here are the latest details.",
        "service_label": "Service",
        "details_label": "Details",
        "closing": "Review the incident in Site Monitoring and check the latest monitor results.",
        "footer": "Automated notification from Site Monitoring.",
        "footer_note": "To change alert recipients, update this service’s monitor settings.",
    },
    "RECOVERED": {
        "subject": "[{status}] {service} · Site Monitoring",
        "html_body": DEFAULT_RECOVERED_EMAIL_HTML,
        "heading": "Service has recovered",
        "intro": "A monitored service is responding normally again. Here are the latest details.",
        "service_label": "Service",
        "details_label": "Details",
        "closing": "Review the incident in Site Monitoring and check the latest monitor results.",
        "footer": "Automated notification from Site Monitoring.",
        "footer_note": "To change alert recipients, update this service’s monitor settings.",
    },
    "ATTENTION": {
        "subject": "[Needs attention] {service} · Site Monitoring",
        "html_body": DEFAULT_ATTENTION_EMAIL_HTML,
        "heading": "Service needs attention",
        "intro": "A monitored service has an unstable check and may need attention.",
        "service_label": "Service",
        "details_label": "Details",
        "closing": "Review the latest monitor results and check this service.",
        "footer": "Automated notification from Site Monitoring.",
        "footer_note": "To change alert recipients, update this service’s monitor settings.",
    },
}


def substitute_tokens(value, tokens):
    for name, replacement in tokens.items():
        value = value.replace("{" + name + "}", str(replacement))
    return value


def format_duration(seconds):
    seconds = max(0, int(seconds or 0))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if seconds or not parts: parts.append(f"{seconds}s")
    return " ".join(parts)


def format_event_time(value):
    return timezone.localtime(value).strftime("%d %b %Y, %I:%M:%S %p %Z") if value else "Not available"


def add_missing_attention_metadata(html_template):
    """Keep older saved attention templates informative as new fields are added."""
    metadata_rows = []
    row_start = '<tr><td style="padding:12px 16px;color:#687386;font-size:12px;border-top:1px solid #e5e9f0">'
    value_start = '<tr><td style="padding:0 16px 14px;line-height:1.6">'
    if "{{ site_url }}" not in html_template and "{{site_url}}" not in html_template:
        metadata_rows.append(
            f'{row_start}SITE</td></tr>{value_start}'
            '<a href="{{ site_url }}" style="color:#1a73e8;overflow-wrap:anywhere">{{ site_url }}</a></td></tr>'
        )
    if "{{ event_time }}" not in html_template and "{{event_time}}" not in html_template:
        metadata_rows.append(
            f'{row_start}DETECTED AT</td></tr>'
            '<tr><td style="padding:0 16px 14px">{{ event_time }}</td></tr>'
        )
    if "{{ check_interval }}" not in html_template and "{{check_interval}}" not in html_template:
        metadata_rows.append(
            f'{row_start}CHECK INTERVAL</td></tr>'
            '<tr><td style="padding:0 16px 14px">Every {{ check_interval }}</td></tr>'
        )
    if not metadata_rows:
        return html_template

    metadata = "".join(metadata_rows)
    details_label = re.search(r"<tr\b[^>]*>\s*<td\b[^>]*>\s*DETAILS\s*</td>\s*</tr>", html_template, re.IGNORECASE)
    if details_label:
        insert_at = details_label.start()
        return html_template[:insert_at] + metadata + html_template[insert_at:]
    first_table_end = html_template.lower().find("</table>")
    if first_table_end >= 0:
        return html_template[:first_table_end] + metadata + html_template[first_table_end:]
    body_end = html_template.lower().find("</body>")
    if body_end >= 0:
        return html_template[:body_end] + metadata + html_template[body_end:]
    return html_template + metadata


def build_alert_email(template, *, monitor_name, project_name, monitor_url, detail, monitor_link="", event_time=None, incident_started_at=None, downtime_seconds=None, check_interval_seconds=60):
    status = {"DOWN": "Down", "RECOVERED": "Recovered", "ATTENTION": "Needs attention"}[template.event]
    parsed_url = urlsplit(monitor_url or "")
    safe_url = monitor_url if parsed_url.scheme in {"http", "https"} and parsed_url.netloc else ""
    parsed_monitor_link = urlsplit(monitor_link or "")
    safe_monitor_link = monitor_link if parsed_monitor_link.scheme in {"http", "https"} and parsed_monitor_link.netloc else ""
    has_monitor_link_token = "{{ monitor_link }}" in (template.html_body or "") or "{{monitor_link}}" in (template.html_body or "")
    tokens = {
        "service": monitor_name,
        "project": project_name,
        "status": status,
        "details": detail,
        "site_url": safe_url,
        "monitor_link": safe_monitor_link,
        "event_time": format_event_time(event_time),
        "down_since": format_event_time(incident_started_at),
        "downtime": format_duration(downtime_seconds),
        "check_interval": format_duration(check_interval_seconds),
    }
    copy = {
        field: substitute_tokens(getattr(template, field), tokens)
        for field in ("heading", "intro", "service_label", "details_label", "closing", "footer", "footer_note")
    }
    subject = substitute_tokens(template.subject, tokens)
    html_template = template.html_body or DEFAULT_EMAIL_HTML[template.event]
    if template.event == "ATTENTION":
        html_template = add_missing_attention_metadata(html_template)
    html = html_template
    for name, replacement in tokens.items():
        safe_value = conditional_escape(replacement)
        html = html.replace("{{ " + name + " }}", str(safe_value)).replace("{{" + name + "}}", str(safe_value))
    if safe_monitor_link and not has_monitor_link_token:
        safe_link = conditional_escape(safe_monitor_link)
        monitor_cta = (
            '<p style="margin:20px 0 0;text-align:center">'
            f'<a href="{safe_link}" style="display:inline-block;padding:12px 18px;border-radius:8px;background:#2563eb;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none">'
            'Open service in Site Monitoring</a></p>'
        )
        if "</body>" in html.lower():
            body_end = html.lower().rfind("</body>")
            html = html[:body_end] + monitor_cta + html[body_end:]
        else:
            html += monitor_cta
    if template.event == "RECOVERED":
        text = (
            f"{copy['heading']}\n\n{copy['intro']}\n\n"
            f"Project: {project_name}\n{copy['service_label']}: {monitor_name}\n"
            f"Current status: Up · Responding normally\nSite: {safe_url}\nOpen service in Site Monitoring: {safe_monitor_link}\n"
            f"Recovered at: {tokens['event_time']}\nDowntime: {tokens['downtime']}\n"
            f"Check interval: every {tokens['check_interval']}\n\n"
            f"{copy['closing']}\n\n{copy['footer']}\n{copy['footer_note']}"
        )
    else:
        text = (
            f"{copy['heading']}\n\n{copy['intro']}\n\n"
            f"Project: {project_name}\n{copy['service_label']}: {monitor_name}\n"
            f"Site: {safe_url}\nOpen service in Site Monitoring: {safe_monitor_link}\nDetected at: {tokens['event_time']}\n"
            f"Check interval: every {tokens['check_interval']}\n"
            f"{copy['details_label']}: {detail}\n\n{copy['closing']}\n\n"
            f"{copy['footer']}\n{copy['footer_note']}"
        )
    return subject, html, text
