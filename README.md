# Site Monitoring

A self-hosted Django application for monitoring HTTP and HTTPS services, viewing project health, tracking incidents, and sending email alerts.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Local setup](#local-setup)
- [Configuration](#configuration)
- [Run the application](#run-the-application)
- [Using the workspace](#using-the-workspace)
- [How monitoring works](#how-monitoring-works)
- [Management commands](#management-commands)
- [Email alerts](#email-alerts)
- [Deployment and operations](#deployment-and-operations)
- [Fees and license](#fees-and-license)

## Features

- **Dashboard:** service totals, operational and attention counts, open incidents, affected-service lists, a health doughnut chart, and response-time trends. The dashboard can refresh immediately or automatically every 1, 2, 5, or 10 minutes. The selected interval is saved in the browser.
- **Projects and services:** group monitors by project; configure target URL, check interval, timeout, failure and recovery thresholds, alert recipients, and active/paused state.
- **HTTP(S) monitoring:** response code, latency, latest check details, and historical check results. HTTP status codes from 200 through 399 count as a successful response.
- **Incident tracking:** create incidents for confirmed outages, acknowledge or resolve them, and track recovery.
- **Email notifications:** queued email alerts for attention, down, and recovered events. Alert templates can be previewed and customized globally or for a project.
- **Public status pages:** optionally publish a read-only status page for a project.
- **Team access:** built-in Admin, Manager, and Viewer roles; custom permission roles; project assignments; account enable/disable; and user/password management according to permissions.
- **Workspace settings:** profile and password changes, light/dark theme, and email-template and role management.
- **Search and filters:** find projects, services, incidents, and team members, with status filters and pagination where available.
- **Health endpoint:** `GET /healthz` returns a simple response for a load balancer or uptime check.

## Requirements

- Python 3.12 recommended.
- pip and a supported operating system (Windows, Linux, or macOS).
- SQLite, included with Python. The database is stored in `db.sqlite3`.
- An SMTP account if you want the application to send email alerts or password-reset emails.

The project does not require Redis, Celery, or a separate task queue. The monitor runner is a Django management command.

## Local setup

### Windows PowerShell

From the project directory:

```powershell
# Activate virtual environment (if in parent directory or current directory):
..\venv\Scripts\Activate.ps1
# or: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and replace the example secret and SMTP credentials. Generate a Django secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Initialize the database and create the first administrator account:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

### Linux or macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`, then initialize the database and create the first administrator:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python manage.py migrate
python manage.py createsuperuser
```

The migrations create the built-in Admin, Manager, and Viewer access roles.

## Configuration

The application reads settings from `.env` and environment variables. Keep real credentials private and do not commit `.env`.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Private Django signing key. Set a unique, random value. |
| `DJANGO_DEBUG` | Django debug mode. Keep `0` outside local development. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames, such as `localhost,127.0.0.1` or your deployment hostname. |
| `SITE_URL` | Public base URL of this app. Used to build links in alert emails; do not add a trailing slash. |
| `TIME_ZONE` | Time zone for displayed and emailed times. Defaults to `Asia/Kolkata`. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated full origins for a deployed site, including `https://`, for example `https://monitor.example.com`. |
| `EMAIL_HOST` | SMTP server hostname. |
| `EMAIL_PORT` | SMTP port. Common choices: 465 for SSL or 587 for STARTTLS. |
| `EMAIL_USER` | SMTP username. |
| `EMAIL_PASSWORD` | SMTP password or provider credential. |
| `EMAIL_FROM` | Verified sender address. |
| `EMAIL_FROM_NAME` | Name displayed as the sender. |
| `EMAIL_BCC` | Optional BCC address; use `false` or leave empty to disable it. |
| `EMAIL_USE_SSL` | Use implicit TLS, normally `1` for port 465. |
| `EMAIL_USE_TLS` | Use STARTTLS, normally `1` for port 587. Do not enable this together with SSL. |

For local development, the values in `.env.example` allow the site to run without SMTP, but emails will not be delivered until SMTP is configured. Set `DJANGO_DEBUG=1` only for local development.

### Gmail SMTP Setup

To send alert emails using a personal Gmail account (`@gmail.com`):

1. Go to your [Google Account Security](https://myaccount.google.com/security) settings.
2. Ensure **2-Step Verification** is turned **ON**.
3. Go to **[App passwords](https://myaccount.google.com/apppasswords)**.
4. Name the app password (e.g., `Site Monitoring`) and click **Create**.
5. Copy the 16-character password and update `.env`:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_16_digit_app_password
EMAIL_USE_TLS=1
EMAIL_USE_SSL=0
DEFAULT_FROM_EMAIL=your_email@gmail.com
EMAIL_FROM=your_email@gmail.com
EMAIL_FROM_NAME=Site Monitoring
```

Example SMTP choices:

- Port 587 (Standard / Gmail): `EMAIL_USE_SSL=0`, `EMAIL_USE_TLS=1`.
- Port 465 (SSL): `EMAIL_USE_SSL=1`, `EMAIL_USE_TLS=0`.

## Run the application

Run the web application and the monitor runner in separate terminals. Keep the virtual environment activated in each terminal.

**Terminal 1 — web application:**

```bash
python manage.py runserver 127.0.0.1:8000
```

**Terminal 2 — scheduled checks and email delivery:**

```bash
python manage.py monitor_sites
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) and sign in with the superuser you created. `/admin/` also points to the custom monitoring dashboard; Django Admin is not installed as the workspace interface.

To check basic configuration before starting:

```bash
python manage.py check
```

## Using the workspace

1. Sign in and create a project from **Projects**.
2. Open the project and add a service. Enter its HTTP(S) URL and set its check interval, timeout, failure threshold, recovery threshold, and notification recipients.
3. Keep `python manage.py monitor_sites` running. It checks due services and sends queued emails.
4. Use **Overview** to review health, affected services, incidents, and chart history. Use **Refresh now** for an immediate update, or select an automatic interval.
5. Open a service to review check history, run a manual check, pause/resume monitoring, and review related incidents.
6. Configure SMTP and alert email templates under **Settings** if you want email notifications. Add team members, access roles, and project assignments under the team and role settings.
7. Enable a project status page and choose its slug when you want to publish a read-only status view.

### Roles and permissions

- **Admin:** workspace administration, including team members, roles, projects, monitors, and incidents.
- **Manager:** manage projects, monitors, and incidents when those permissions are assigned.
- **Viewer:** view assigned workspace data without change permissions by default.
- **Custom roles:** choose workspace permissions for projects, monitors, incidents, team management, password management, and role management.

Non-superuser accounts can be restricted to assigned projects. A superuser created with `createsuperuser` can access all projects.

## How monitoring works

1. The runner scans for active monitors whose next-check time is due. It scans every 5 seconds by default; this is the scheduler scan frequency, not the service check interval.
2. The checker validates the URL, resolves its host, and sends an HTTP(S) request using the monitor's configured timeout. It does not follow redirects. A 2xx or 3xx response is counted as successful. Targets that resolve to non-public IP addresses are rejected.
3. Each result is recorded with its timestamp, response time or HTTP status, and any failure detail.
4. A service becomes **Suspect** after a failure before the configured failure threshold is reached. Once it reaches the threshold, it becomes **Down** and an incident is opened. The defaults are 3 consecutive failures to go down and 2 consecutive successes to recover.
5. A single timeout is one failed check. With the default threshold, one timeout does not immediately mark a service Down; consecutive failures are required. You can change the threshold on the monitor.
6. Status changes queue email alerts when recipients are configured. The runner sends queued emails and retries temporary delivery failures.
7. The dashboard polls the status endpoint at the chosen interval while its browser tab is active. It refreshes counts, service lists, incident badges, the health chart, and response chart. The manual refresh control requests an update immediately.

New monitors default to a 60-second interval, a 10-second timeout, 3 consecutive failures to go Down, and 2 consecutive successful checks to recover. Configure shorter intervals carefully: frequent checks increase outbound requests to each target.

## Management commands

| Command | Purpose |
| --- | --- |
| `python manage.py migrate` | Apply database migrations. Run after setup and whenever the application is updated. |
| `python manage.py createsuperuser` | Create the first administrator account. |
| `python manage.py runserver 127.0.0.1:8000` | Start Django's development web server. Use a production WSGI server for deployments. |
| `python manage.py monitor_sites` | Continuously scan for due checks and deliver queued alert emails. Stop with Ctrl+C. |
| `python manage.py monitor_sites --poll-interval 10` | Scan for due monitors every 10 seconds instead of the default 5-second scan. |
| `python manage.py monitor_sites --once` | Run one due-monitor scan, process currently queued alerts once, and exit. It does not force every monitor to run. |
| `python manage.py cleanup_check_history` | Delete check results older than 30 days, in batches of 5,000 rows. |
| `python manage.py cleanup_check_history --retention-days 60 --batch-size 1000` | Keep a different number of days and change the deletion batch size. |
| `python manage.py check` | Run Django's configuration checks. |
| `python manage.py test_email <recipient>` | Send a test email to verify SMTP / Gmail configuration. |
| `python manage.py collectstatic --noinput` | Collect static files for a deployment. |

Schedule `cleanup_check_history` once per day with Windows Task Scheduler, cron, or another system scheduler. The cleanup command removes old check-result rows; it does not delete incidents or alert-delivery records. Check-history and uptime summaries use a 30-day window by default.

## Email alerts

Set the SMTP variables in `.env`, then add one or more notification addresses to a monitor. The application can send **Needs attention**, **Down**, and **Recovered** notifications. Messages include the project and service, monitored URL, detected/recovered time, configured check interval, latest check details, and a link back to the service in this workspace.

Email delivery uses a durable queue stored in SQLite. The runner processes pending messages. If delivery fails, it retries with increasing delays, up to about one hour between attempts. The incident page shows alert delivery status. Global templates and project-specific overrides can be edited and previewed in **Settings → Email templates**.

Password-reset emails also require working SMTP configuration. For local development without SMTP, use the password-change flow after signing in as an administrator to set team passwords.

To verify email sending at any time, run:
```bash
python manage.py test_email recipient@example.com
```

## Deployment and operations

- Do not use Django's `runserver` as a production server. Gunicorn is included; a basic WSGI command is:

  ```bash
  gunicorn config.wsgi:application --bind 127.0.0.1:8000
  ```

- Keep the `monitor_sites` runner alive as a separate managed process (for example, a Windows service/process manager, `systemd`, or a container sidecar). Web requests alone do not run scheduled checks or send queued alerts.
- Serve `collectstatic` output through a web server or reverse proxy. Chart.js and web fonts are loaded from external CDNs, so browser access to those CDNs is required for the charts and hosted fonts.
- Set `DJANGO_DEBUG=0`, use a private secret key, configure production hosts and CSRF origins, and put the app behind HTTPS before exposing it outside a trusted network.
- Run this monitor on infrastructure separate from the sites it checks. Back up `db.sqlite3` and protect it: it contains accounts, monitoring history, incidents, and alert configuration.
- Avoid placing usernames, passwords, or tokens in monitored URLs. Configure only targets you are authorized to monitor.

---

**Created by: Vaibhav Rathod**
