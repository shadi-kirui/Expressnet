import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "billing_saas_django.Settings.production")

application = get_asgi_application()
