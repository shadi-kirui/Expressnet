import os
import sys
import time

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "billing_saas_django.Settings.production")

app = Celery("billing_saas_django")
app.config_from_object("django.conf:settings", namespace="CELERY")

if any(arg in {"worker", "beat"} for arg in sys.argv):
    redis_url = getattr(settings, "REDIS_URL", "")
    is_production = os.getenv("DJANGO_SETTINGS_MODULE", "").endswith(".production")
    if is_production and redis_url.startswith("redis://localhost:"):
        print("REDIS_URL is not configured for production; Celery process disabled.")
        while True:
            time.sleep(3600)

app.autodiscover_tasks()
