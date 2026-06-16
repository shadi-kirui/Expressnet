from celery import shared_task
from django.utils import timezone

from .models import TenantSubscription
from .services import write_audit_log


@shared_task
def expire_tenant_subscriptions():
    now = timezone.now()
    expired = TenantSubscription.objects.select_related("tenant").filter(expires_at__lt=now).exclude(tenant__status="suspended")
    count = 0
    for subscription in expired:
        subscription.tenant.status = "suspended"
        subscription.tenant.save(update_fields=["status", "updated_at"])
        write_audit_log(action="AUTO_SUSPEND_EXPIRED_SUBSCRIPTION", target_id=str(subscription.tenant_id), target_type="tenant", metadata={"subscription_id": subscription.pk})
        count += 1
    return count


@shared_task
def send_subscription_reminder_sms():
    now = timezone.now()
    soon = now + timezone.timedelta(days=3)
    return TenantSubscription.objects.filter(expires_at__date=soon.date()).count()
