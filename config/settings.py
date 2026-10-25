import os
from decouple import config, Csv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = config("DJANGO_SECRET_KEY", default="unsafe-dev-key-change-me")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
SITE_URL = config("SITE_URL", default="http://localhost:8000").rstrip("/")
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "monitors"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [os.path.join(BASE_DIR, "templates")], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.path.join(BASE_DIR, "db.sqlite3")}}
AUTH_USER_MODEL = "monitors.User"
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = int(config("EMAIL_PORT", default=587) or 587)
EMAIL_HOST_USER = config("EMAIL_USER", default=config("EMAIL_HOST_USER", default=""))
EMAIL_HOST_PASSWORD = config("EMAIL_PASSWORD", default=config("EMAIL_HOST_PASSWORD", default=""))
EMAIL_USE_TLS = str(config("EMAIL_USE_TLS", default="1")).strip().lower() in ("1", "true", "yes", "on")
EMAIL_USE_SSL = str(config("EMAIL_USE_SSL", default="0")).strip().lower() in ("1", "true", "yes", "on")
# SMTP SSL (port 465) and STARTTLS cannot be enabled on the same connection.
if EMAIL_USE_SSL:
    EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = config("EMAIL_FROM", default=config("DEFAULT_FROM_EMAIL", default="info+testemail@intellial.com"))
EMAIL_FROM_NAME = config("EMAIL_FROM_NAME", default="Intellial Site Monitoring")
EMAIL_BCC = config("EMAIL_BCC", default="")
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
