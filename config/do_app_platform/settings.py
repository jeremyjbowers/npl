from django.core.management.utils import get_random_secret_key
from pathlib import Path
import os
import sys
import dj_database_url

from config.dev.settings import *

WSGI_APPLICATION = "config.do_app_platform.app.application"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", get_random_secret_key())

DEBUG = False

ALLOWED_HOSTS = ["*"]

# App Platform terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS + [
    "https://*.ondigitalocean.app",
    "https://nationalpastime.org",
    "https://www.nationalpastime.org",
    "https://npldev.org",
    "https://www.npldev.org",
]

DEVELOPMENT_MODE = False

DATABASE_URL = os.environ.get("DATABASE_URL", None)

# App Platform's ${db.DATABASE_URL} binding is only a real postgres URL at
# runtime. During the image build it can be unset or an empty placeholder,
# and parsing that crashes the buildpack's collectstatic step.
_db_scheme = (DATABASE_URL or "").split("://", 1)[0]
if _db_scheme in {"postgres", "postgresql", "pgsql"}:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=60),
    }

STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/"
STATICFILES_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

INSTALLED_APPS = INSTALLED_APPS + ["storages"]
