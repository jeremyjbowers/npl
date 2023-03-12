import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    ")(hv#e)wqd-9pwuvd94wq5-snmz+@m(&-g5e74&zg)+geh-xqe+123+sadjklfhlkh7",
)

DEBUG = os.environ.get("DEBUG", True)

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ['https://*.ngrok.io', 'http://127.0.0.1', 'http://localhost.nationalpastime.org']

SITE_ID = 1

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django_quill",
    "reversion",
    "npl",
    "users",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "npl.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["npl/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
            ],
            "libraries": {
                "npl_tags": "npl.templatetags.npl_tags",
            },
        },
    },
]

WSGI_APPLICATION = "config.dev.app.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("DB_NAME", "npl"),
        "USER": os.environ.get("DB_USER", "npl"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "npl"),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# TIME

TIME_ZONE = 'US/Eastern'
USE_TZ = True

# LOGIN STUFF
AUTH_USER_MODEL = 'users.User'
LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "/"

EMAIL_BACKEND = 'django_mailgun_mime.backends.MailgunMIMEBackend'
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", None)
MAILGUN_DOMAIN_NAME = 'mail.theulmg.com'
DEFAULT_FROM_EMAIL = 'postmaster@mail.theulmg.com'
SERVER_EMAIL = 'admin@mail.theulmg.com'

# PAGES
QUILL_CONFIGS = {
    'default':{
        'theme': 'snow',
        'modules': {
            'syntax': True,
            'toolbar': [
                [
                    { 'header': [] },
                    'bold', 'italic', 'underline', 'strike',
                ],
                [
                    {'align': []},
                    { 'list': 'ordered'}, { 'list': 'bullet' },
                    { 'indent': '-1'}, { 'indent': '+1' },
                ],
                ['code-block', 'blockquote', 'link'],
                ['clean'],
            ]
        }
    }
}


# STATICFILES
STATIC_URL = "/static/"
STATIC_ROOT = "static/"

AWS_S3_REGION_NAME = "nyc3"
AWS_S3_ENDPOINT_URL = f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com"
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", None)
AWS_DEFAULT_ACL = "public-read"
AWS_STORAGE_BUCKET_NAME = "static-thenpl"
AWS_S3_CUSTOM_DOMAIN = "static-thenpl.nyc3.cdn.digitaloceanspaces.com"
AWS_LOCATION = "static"

## MAIL
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", None)

ROSTER_SHEET_ID = "1On6uRXLRQ3pzl2FHYRgWKCedsCdl6UNbNaSF6pwlGiw"
LEAGUE_SHEET_ID = "1UQv_vnBBWUT8BiFRd7tAbvW4COWJ61BNkme7iyzf5po"