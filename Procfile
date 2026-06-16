web: gunicorn billing_saas_django.wsgi --workers ${WEB_CONCURRENCY:-4} --worker-class gevent --bind 0.0.0.0:$PORT --timeout 30
worker: celery -A billing_saas_django worker -l info
beat: celery -A billing_saas_django beat -l info
