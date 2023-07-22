import os

settings_file = "config.do_app_platform.settings"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_file)
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
