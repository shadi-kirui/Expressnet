import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "billing_saas_django.Settings.production")

app = Celery("billing_saas_django")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
