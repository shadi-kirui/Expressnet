import logging
import platform
import threading

from celery import shared_task
from django.utils import timezone

from .models import TenantSubscription
from .services import iso_now, list_children, ref, set_customer_enabled, write_audit_log

logger = logging.getLogger(__name__)

# Firestore calls in expire_customer_access should never be allowed to hang
# indefinitely. If the operation runs longer than this, we bail out so the
# worker process keeps running and picks up the next scheduled run.
EXPIRE_CUSTOMER_ACCESS_TIMEOUT_SECONDS = 60


class TaskTimeoutError(Exception):
    """Raised when a task exceeds its allotted execution time."""


def _run_with_timeout(func, timeout_seconds, *args, **kwargs):
    """
    Run ``func`` with a hard timeout so it can never hang the worker forever.

    Uses SIGALRM on platforms that support it (main thread on Linux/macOS,
    which is how Celery prefork/solo workers execute tasks). Falls back to a
    background-thread based timeout everywhere else (e.g. Windows, or when
    called from a non-main thread), which cannot forcibly kill the call but
    will still let the task return instead of hanging forever.
    """
    if platform.system() != "Windows":
        try:
            import signal as signal_module

            if threading.current_thread() is threading.main_thread():
                def _handle_timeout(signum, frame):
                    raise TaskTimeoutError(f"Timed out after {timeout_seconds}s")

                previous_handler = signal_module.signal(signal_module.SIGALRM, _handle_timeout)
                signal_module.alarm(timeout_seconds)
                try:
                    return func(*args, **kwargs)
                finally:
                    signal_module.alarm(0)
                    signal_module.signal(signal_module.SIGALRM, previous_handler)
        except (ValueError, AttributeError):
            # signal.alarm not available (e.g. not on main thread) - fall
            # through to the thread-based timeout below.
            pass

    result_box = {}
    error_box = {}

    def _target():
        try:
            result_box["value"] = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            error_box["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TaskTimeoutError(f"Timed out after {timeout_seconds}s")
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("value")


@shared_task
def expire_tenant_subscriptions():
    try:
        now = timezone.now()
        expired = TenantSubscription.objects.select_related("tenant").filter(expires_at__lt=now).exclude(tenant__status="suspended")
        count = 0
        for subscription in expired:
            try:
                subscription.tenant.status = "suspended"
                subscription.tenant.save(update_fields=["status", "updated_at"])
                write_audit_log(action="AUTO_SUSPEND_EXPIRED_SUBSCRIPTION", target_id=str(subscription.tenant_id), target_type="tenant", metadata={"subscription_id": subscription.pk})
                count += 1
            except Exception:
                logger.exception("expire_tenant_subscriptions: failed to suspend tenant subscription %s", getattr(subscription, "pk", None))
        return count
    except Exception:
        logger.exception("expire_tenant_subscriptions: task failed")
        return 0


@shared_task
def send_subscription_reminder_sms():
    try:
        now = timezone.now()
        soon = now + timezone.timedelta(days=3)
        return TenantSubscription.objects.filter(expires_at__date=soon.date()).count()
    except Exception:
        logger.exception("send_subscription_reminder_sms: task failed")
        return 0


def _expire_customer_access_impl():
    now = iso_now()
    count = 0
    for tenant in list_children("tenants"):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        for customer in list_children(f"tenants/{tenant_id}/customers"):
            expiry = str(customer.get("expiry_date") or "")
            if not expiry or expiry > now or customer.get("status") == "expired":
                continue
            service_type = customer.get("service_type") or "hotspot"
            username = customer.get("mac_address") if service_type == "tv" else customer.get("username")
            try:
                set_customer_enabled({"id": tenant_id, **tenant}, username, service_type, False)
            except Exception:
                logger.exception(
                    "expire_customer_access: set_customer_enabled failed for tenant=%s username=%s",
                    tenant_id,
                    username,
                )
            try:
                ref(f"tenants/{tenant_id}/customers/{customer['id']}").update(
                    {
                        "status": "expired",
                        "auto_reconnect": False,
                        "expired_at": now,
                        "updated_at": now,
                    }
                )
                count += 1
            except Exception:
                logger.exception(
                    "expire_customer_access: failed to mark customer expired for tenant=%s customer=%s",
                    tenant_id,
                    customer.get("id"),
                )
    return count


@shared_task
def expire_customer_access():
    logger.info("expire_customer_access: starting")
    try:
        count = _run_with_timeout(_expire_customer_access_impl, EXPIRE_CUSTOMER_ACCESS_TIMEOUT_SECONDS)
        logger.info("expire_customer_access: finished, expired=%s", count)
        return count
    except TaskTimeoutError:
        logger.error(
            "expire_customer_access: timed out after %ss, likely stuck waiting on Firestore",
            EXPIRE_CUSTOMER_ACCESS_TIMEOUT_SECONDS,
        )
        return 0
    except Exception:
        logger.exception("expire_customer_access: task failed")
        return 0
