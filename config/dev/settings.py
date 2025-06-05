import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    ")(hv#e)wqd-9pwuvd94wq5-snmz+@m(&-g5e74&zg)+geh-xqe+123+sadjklfhlkh7",
)

DEBUG = os.environ.get("DEBUG", True)

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ['https://*.ngrok.io', 'http://127.0.0.1', 'http://localhost.nationalpastime.org', 'https://*.ngrok-free.app']

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
    "allauth",
    "allauth.account",
    "sesame",
    "npl",
    "users",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "sesame.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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

# CACHES
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache_table',
        'TIMEOUT': 300,  # 5 minutes default timeout
        'KEY_PREFIX': 'npl_dev_',
        'VERSION': 1,
        'OPTIONS': {
            'MAX_ENTRIES': 10000,  # Limit cache table size
            'CULL_FREQUENCY': 4,   # Delete 1/4 of entries when MAX_ENTRIES reached
        }
    }
}

# Cache session backend for better performance  
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'

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

# AUTHENTICATION BACKENDS
AUTHENTICATION_BACKENDS = [
    'sesame.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# DJANGO-ALLAUTH SETTINGS
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_RATE_LIMITS = {
    'login_failed': None,
}
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_PASSWORD_MIN_LENGTH = None

# DJANGO-SESAME SETTINGS (Magic Links)
SESAME_MAX_AGE = 60 * 60 * 24 * 30
SESAME_ONE_TIME = False
SESAME_INVALIDATE_ON_PASSWORD_CHANGE = False

# SESSION SETTINGS (Database-backed for persistence across deployments)
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

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

## SHEETS
ROSTER_SHEET_ID = "1On6uRXLRQ3pzl2FHYRgWKCedsCdl6UNbNaSF6pwlGiw"
LEAGUE_SHEET_ID = "1UQv_vnBBWUT8BiFRd7tAbvW4COWJ61BNkme7iyzf5po"

## LOOKUPS
ROSTER_TEAM_IDS = [
    ("1", "LAA", "Los Angeles Angels"),
    ("2", "BAL", "Baltimore Orioles"),
    ("3", "BOS", "Boston Red Sox"),
    ("4", "CHW", "Chicago White Sox"),
    ("5", "CLE", "Cleveland Guardians"),
    ("6", "DET", "Detroit Tigers"),
    ("7", "KCR", "Kansas City Royals"),
    ("8", "MIN", "Minnesota Twins"),
    ("9", "NYY", "New York Yankees"),
    ("10", "OAK", "Oakland Athletics"),
    ("11", "SEA", "Seattle Mariners"),
    ("12", "TBR", "Tampa Bay Rays"),
    ("13", "TEX", "Texas Rangers"),
    ("14", "TOR", "Toronto Blue Jays"),
    ("15", "ARI", "Arizona Diamondbacks"),
    ("16", "ATL", "Atlanta Braves"),
    ("17", "CHC", "Chicago Cubs"),
    ("18", "CIN", "Cincinatti Reds"),
    ("19", "COL", "Colorado Rockies"),
    ("20", "MIA", "Miami Marlins"),
    ("21", "HOU", "Houston Astros"),
    ("22", "LAD", "Los Angeles Dodgers"),
    ("23", "MIL", "Milwaukee Brewers"),
    ("24", "WAS", "Washington Nationals"),
    ("24", "WSN", "Washington Nationals"),
    ("25", "NYM", "New York Mets"),
    ("26", "PHI", "Philadelphia Phillies"),
    ("27", "PIT", "Pittsburgh Pirates"),
    ("28", "STL", "St. Louis Cardinals"),
    ("29", "SDP", "San Diego Padres"),
    ("30", "SFG", "San Francisco Giants"),
]

MLB_URL_TO_ORG_NAME = {
    "orioles": "BAL",
    "whitesox": "CWS",
    "astros": "HOU",
    "redsox": "BOS",
    "guardians": "CLE",
    "indians": "CLE",
    "angels": "LAA",
    "athletics": "ATH",
    "yankees": "NYY",
    "tigers": "DET",
    "rays": "TB",
    "royals": "KC",
    "mariners": "SEA",
    "bluejays": "TOR",
    "twins": "MIN",
    "rangers": "TEX",
    "braves": "ATL",
    "cubs": "CHC",
    "dbacks": "AZ",
    "marlins": "MIA",
    "reds": "CIN",
    "rockies": "COL",
    "mets": "NYM",
    "brewers": "MIL",
    "dodgers": "LAD",
    "phillies": "PHI",
    "pirates": "PIT",
    "padres": "SD",
    "nationals": "WSH",
    "cardinals": "STL",
    "giants": "SF"
}

LEVELS = [
    (16,"R"),
    (15, "R"),
    (14,"A"),
    (13,"A+"),
    (12,'AA'),
    (11,"AAA"),
    (1,"MLB"),
]

## LEAGUE STUFF
LEAGUE_YEAR = 2025
LEAGUE_SEASON = "midseason"
