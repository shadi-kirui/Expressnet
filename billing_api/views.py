import json
import os
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

import jwt
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .auth import admin_required, tenant_required
from .models import AdminUser, Customer, InternetPackage, Payment, SubscriptionPayment, Tenant, TenantSubscription, Ticket, User
from .services import (
    admin_token,
    check_password,
    create_hotspot_profile,
    create_ppp_profile,
    configure_router_port,
    create_paystack_subaccount,
    delete_router_customer,
    captive_portal_url,
    ensure_hotspot_captive_portal,
    find_child_by_field,
    has_mikrotik_credentials,
    hash_password,
    initiate_paystack_payment,
    iso_now,
    firebase_backup_configured,
    list_children,
    normalize_phone,
    package_service_type,
    PaymentProviderError,
    ref,
    _get_jwt_secret,
    router_interface_status,
    router_items,
    send_whatsapp_message,
    set_customer_enabled,
    tenant_token,
    upsert_customer_access,
    utcnow,
    verify_paystack_signature,
    verify_paystack_transaction,
    write_audit_log,
)


DEFAULT_SITE = {
    "brand_name": "Billing SaaS",
    "headline": "Internet billing built for hotspot businesses",
    "subheadline": "Sell packages, collect Paystack payments, and activate MikroTik users automatically.",
    "about": "We help hotspot operators manage customers, packages, payments, and access control from one secure platform.",
    "phone": "+254 700 000 000",
    "email": "support@example.com",
    "location": "Nairobi, Kenya",
    "address": "Nairobi, Kenya",
    "cta_label": "Register your business",
    "cta_url": "/register",
}
MASKED = "••••••••"
SENSITIVE_FIELDS = {"password", "mikrotik_pass", "paystack_secret_key"}


def body(request):
    if hasattr(request, "data"):
        return request.data if isinstance(request.data, dict) else dict(request.data)
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def ok(data=None, status=200):
    return Response(data if data is not None else {}, status=status)


def err(message, status=400):
    return Response({"error": message}, status=status)


def admin_notification_recipients():
    configured = list(getattr(settings, "ADMIN_NOTIFICATION_EMAILS", []))
    firebase_admins = [admin.get("email") for admin in list_children("admins") if admin.get("email")]
    django_admins = list(User.objects.filter(is_staff=True, is_active=True).values_list("email", flat=True))
    return sorted({email for email in [*configured, *firebase_admins, *django_admins] if email})


def send_system_email(subject, message, recipients):
    recipients = [email for email in recipients if email]
    if not recipients:
        return 0
    try:
        return send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
    except Exception:
        return 0


def notify_admins_tenant_signup(tenant_id, tenant):
    default_dashboard_url = f"/{settings.ADMIN_FRONTEND_PATH}/tenants"
    dashboard_url = os.getenv("ADMIN_TENANTS_URL", default_dashboard_url)
    send_system_email(
        "New tenant account pending activation",
        (
            f"A new tenant account is waiting for activation.\n\n"
            f"Business: {tenant.get('business_name')}\n"
            f"Owner: {tenant.get('owner_name')}\n"
            f"Email: {tenant.get('email')}\n"
            f"Phone: {tenant.get('phone')}\n"
            f"Tenant ID: {tenant_id}\n\n"
            f"Review and activate it here: {dashboard_url}"
        ),
        admin_notification_recipients(),
    )


def notify_tenant_activated(tenant):
    send_system_email(
        "Your Billing SaaS account is active",
        (
            f"Hello {tenant.get('owner_name') or tenant.get('business_name')},\n\n"
            f"Your {tenant.get('business_name') or 'Billing SaaS'} account has been activated. "
            "You can now sign in and finish setting up your workspace.\n\n"
            "Login: /login"
        ),
        [tenant.get("email")],
    )


def method(request, *allowed):
    return request.method.upper() in allowed


def parse_page(request):
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(200, max(1, int(request.GET.get("page_size", 50))))
    except (TypeError, ValueError):
        page_size = 50
    return page, page_size


def paginate_items(request, items):
    page, page_size = parse_page(request)
    paginator = Paginator(list(items), page_size)
    current = paginator.get_page(page)
    path = request.path
    next_url = f"{path}?page={current.next_page_number()}&page_size={page_size}" if current.has_next() else None
    prev_url = f"{path}?page={current.previous_page_number()}&page_size={page_size}" if current.has_previous() else None
    return {"results": list(current.object_list), "count": paginator.count, "pages": paginator.num_pages, "next": next_url, "previous": prev_url}


def as_collection_response(request, items):
    if request.GET.get("all") == "1" or request.GET.get("format") == "legacy":
        return ok(list(items))
    return ok(paginate_items(request, items))


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def payment_date(payment):
    return parse_date(payment.get("paid_at") or payment.get("initiated_at") or payment.get("created_at"))


def package_duration_delta(package):
    unit = str((package or {}).get("duration_unit") or "").strip().lower()
    hours = (package or {}).get("duration_hours")
    if hours not in {None, ""}:
        try:
            return timedelta(hours=float(hours))
        except (TypeError, ValueError):
            pass
    if unit in {"hour", "hours"}:
        try:
            return timedelta(hours=float((package or {}).get("duration_value") or (package or {}).get("duration_days") or 1))
        except (TypeError, ValueError):
            return timedelta(hours=1)
    try:
        return timedelta(days=int((package or {}).get("duration_days") or 1))
    except (TypeError, ValueError):
        return timedelta(days=1)


def normalized_package_payload(data):
    service_type = str((data or {}).get("service_type") or "hotspot").strip().lower()
    if service_type not in {"hotspot", "pppoe"}:
        service_type = "hotspot"
    duration_unit = "hours" if str((data or {}).get("duration_unit") or "").lower().startswith("hour") else "days"
    if service_type == "pppoe":
        duration_unit = "days"
    duration_value = float((data or {}).get("duration_value") or (data or {}).get("duration_hours") or (data or {}).get("duration_days") or 1)
    if service_type == "pppoe" and duration_value < 1:
        duration_value = 1
    duration_days = 1 if duration_unit == "hours" else int(duration_value)
    duration_hours = duration_value if duration_unit == "hours" else duration_value * 24
    return {
        "service_type": service_type,
        "duration_unit": duration_unit,
        "duration_value": duration_value,
        "duration_days": duration_days,
        "duration_hours": duration_hours,
    }


def sync_package_profile(tenant, package):
    service_type = package_service_type(package)
    if service_type == "pppoe":
        return create_ppp_profile(tenant, package.get("name"), package.get("speed"))
    return create_hotspot_profile(tenant, package.get("name"), package.get("speed"))


def package_duration_label(package):
    delta = package_duration_delta(package)
    total_seconds = int(delta.total_seconds())
    if total_seconds < 86400:
        hours = max(1, round(total_seconds / 3600))
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = max(1, round(total_seconds / 86400))
    return f"{days} day{'s' if days != 1 else ''}"


def normalize_mac(value):
    raw = "".join(ch for ch in str(value or "").upper() if ch in "0123456789ABCDEF")
    if len(raw) != 12:
        return ""
    return ":".join(raw[index : index + 2] for index in range(0, 12, 2))


def format_money(value):
    return float(Decimal(str(value or 0)))


def health_payload():
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = "error"
        checks["dbError"] = f"{exc.__class__.__name__}: {str(exc)[:240]}"
    try:
        import redis
        from django.conf import settings as django_settings
        redis.Redis.from_url(django_settings.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = "error"
        checks["redisError"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
    try:
        checks["firebase"] = "ok" if not firebase_backup_configured() else "ok"
    except Exception:
        checks["firebase"] = "error"
    checks["status"] = "healthy" if checks["db"] == "ok" and checks["redis"] == "ok" else "degraded"
    return checks


def ensure_subscription(tenant, plan="basic"):
    plan_amounts = {"basic": 1500, "pro": 3500, "enterprise": 8000}
    now = timezone.now()
    subscription, _ = TenantSubscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            "plan": plan if plan in plan_amounts else "basic",
            "amount": plan_amounts.get(plan, 1500),
            "started_at": now,
            "expires_at": now + timedelta(days=30),
        },
    )
    return subscription


def subscription_payload(subscription, include_payments=False):
    data = subscription.as_dict()
    if include_payments:
        data["payments"] = [payment.as_dict() for payment in subscription.payments.order_by("-paid_at")]
    return data


def record_subscription_payment(subscription, data, admin_email=""):
    now = timezone.now()
    current_expiry = subscription.expires_at if subscription.expires_at and subscription.expires_at > now else now
    period_start = current_expiry
    period_end = period_start + timedelta(days=subscription.billing_cycle_days)
    payment = SubscriptionPayment.objects.create(
        subscription=subscription,
        amount=Decimal(str(data.get("amount") or subscription.amount or 0)),
        currency=data.get("currency") or subscription.currency,
        method=data.get("method") or "manual",
        reference=data.get("reference") or "",
        notes=data.get("notes") or "",
        period_start=period_start,
        period_end=period_end,
        recorded_by=admin_email or "",
    )
    subscription.last_paid_at = payment.paid_at
    subscription.expires_at = period_end
    subscription.save(update_fields=["last_paid_at", "expires_at", "updated_at"])
    if subscription.tenant.status == "suspended":
        subscription.tenant.status = "active"
        subscription.tenant.save(update_fields=["status", "updated_at"])
    return payment


def react_app(request):
    index = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
    if not index.exists():
        raise Http404("Build the React app first with npm --prefix frontend run build")
    return FileResponse(index.open("rb"), content_type="text/html")


def react_asset(request, asset_path):
    assets_dir = (Path(settings.BASE_DIR) / "frontend" / "dist" / "assets").resolve()
    requested = (assets_dir / asset_path).resolve()
    if assets_dir not in requested.parents or not requested.exists() or not requested.is_file():
        raise Http404("Asset not found")
    content_types = {
        ".css": "text/css",
        ".js": "application/javascript",
        ".map": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    return FileResponse(requested.open("rb"), content_type=content_types.get(requested.suffix.lower(), "application/octet-stream"))


def public_base_url(request):
    configured = os.getenv("PUBLIC_APP_URL") or os.getenv("PAYSTACK_CALLBACK_BASE_URL")
    return (configured or f"{request.scheme}://{request.get_host()}").rstrip("/")


def tenant_theme_payload(tenant):
    return {
        "business_name": tenant.get("business_name") or "",
        "owner_name": tenant.get("owner_name") or "",
        "phone": tenant.get("phone") or "",
        "support_email": tenant.get("support_email") or tenant.get("email") or "",
        "theme_color": tenant.get("theme_color") or "#fa8200",
        "font": tenant.get("font") or "Work Sans",
        "dark_mode": bool(tenant.get("dark_mode")),
        "theme_mode": tenant.get("theme_mode") or ("dark" if tenant.get("dark_mode") else "light"),
        "business_number": tenant.get("business_number") or "",
        "bank_code": tenant.get("bank_code") or "",
        "bank_name": tenant.get("bank_name") or "",
        "bank_account_number": tenant.get("bank_account_number") or "",
        "paystack_subaccount_code": tenant.get("paystack_subaccount_code") or "",
        "paystack_subaccount_status": tenant.get("paystack_subaccount_status") or "not_created",
        "paystack_platform_percentage": tenant.get("paystack_platform_percentage") or os.getenv("PAYSTACK_PLATFORM_PERCENTAGE", "1"),
    }


def create_or_update_tenant_subaccount(tenant_id, tenant_data, data):
    bank_code = str(data.get("bank_code") or tenant_data.get("bank_code") or "").strip()
    account_number = str(data.get("bank_account_number") or tenant_data.get("bank_account_number") or "").strip()
    if not bank_code or not account_number:
        return {"paystack_subaccount_status": "missing_bank_details"}

    subaccount = create_paystack_subaccount(
        {"id": tenant_id, **tenant_data, **data},
        bank_code,
        account_number,
        business_number=data.get("business_number") or tenant_data.get("business_number"),
        percentage_charge=data.get("paystack_platform_percentage") or tenant_data.get("paystack_platform_percentage"),
    )
    return {
        "paystack_subaccount_code": subaccount.get("subaccount_code"),
        "paystack_subaccount_id": subaccount.get("id"),
        "paystack_subaccount_status": "active",
        "paystack_subaccount_created_at": iso_now(),
    }


@csrf_exempt
@api_view(["GET"])
def health(request):
    checks = health_payload()
    return ok(
        {
            "ok": True,
            "service": "billing-saas-django",
            "cronEnabled": os.getenv("ENABLE_CRON") == "true",
            "config": {
                "nodeEnv": os.getenv("NODE_ENV", "development"),
                "databaseEngine": settings.DATABASES["default"]["ENGINE"],
                "databaseName": str(settings.DATABASES["default"]["NAME"]),
                "firebaseBackupEnabled": firebase_backup_configured(),
                "jwtSecretSet": bool(os.getenv("JWT_SECRET")),
                "adminJwtSecretSet": bool(os.getenv("ADMIN_JWT_SECRET")),
            },
            **checks,
        }
    )


@csrf_exempt
@api_view(["POST"])
def auth_register(request):
    data = body(request)
    missing = [field for field in ["business_name", "owner_name", "email", "phone", "password"] if not data.get(field)]
    if missing:
        return ok({"message": f"Missing fields: {', '.join(missing)}"}, 400)
    email = data["email"].lower().strip()
    if find_child_by_field("tenants", "email", email):
        return ok({"message": "Email already registered"}, 400)

    tenant_ref = ref("tenants").push(
        {
            "business_name": data["business_name"],
            "owner_name": data["owner_name"],
            "email": email,
            "phone": data["phone"],
            "password": hash_password(data["password"]),
            "business_number": str(data.get("business_number") or "").strip(),
            "bank_code": str(data.get("bank_code") or "").strip(),
            "bank_name": str(data.get("bank_name") or "").strip(),
            "bank_account_number": str(data.get("bank_account_number") or "").strip(),
            "mikrotik_host": "",
            "mikrotik_user": "",
            "mikrotik_pass": "",
            "mikrotik_port": 8728,
            "paystack_secret_key": "",
            "paystack_subaccount_code": "",
            "paystack_bearer": "subaccount",
            "paystack_currency": os.getenv("PAYSTACK_CURRENCY", "KES"),
            "paystack_platform_percentage": os.getenv("PAYSTACK_PLATFORM_PERCENTAGE", "1"),
            "paystack_subaccount_status": "not_created",
            "theme_color": data.get("theme_color") or "#fa8200",
            "dark_mode": False,
            "status": "pending_setup",
            "created_at": iso_now(),
        }
    )
    tenant_data = ref(f"tenants/{tenant_ref.key}").get() or {}
    subaccount_status = {"paystack_subaccount_status": "missing_bank_details"}
    if tenant_data.get("bank_code") and tenant_data.get("bank_account_number"):
        try:
            subaccount_status = create_or_update_tenant_subaccount(tenant_ref.key, tenant_data, data)
        except PaymentProviderError as exc:
            subaccount_status = {"paystack_subaccount_status": "failed", "paystack_subaccount_error": exc.detail}
        ref(f"tenants/{tenant_ref.key}").update(subaccount_status)
    notify_admins_tenant_signup(tenant_ref.key, {**tenant_data, **subaccount_status})
    return ok({"success": True, "message": "Business registered successfully. An admin will activate your account before you can sign in.", "tenantId": tenant_ref.key, **subaccount_status})


@csrf_exempt
@api_view(["POST"])
def auth_login(request):
    data = body(request)
    if not data.get("email") or not data.get("password"):
        return ok({"message": "Email and password are required"}, 400)
    email = str(data["email"]).lower().strip()
    tenant_obj = Tenant.objects.filter(email__iexact=email).first()
    if not tenant_obj:
        return ok({"message": "Business not found"}, 404)
    if not check_password(str(data["password"]).strip(), tenant_obj.password):
        return ok({"message": "Wrong password"}, 401)
    tenant = tenant_obj.as_dict(include_id=True)
    if tenant.get("status") != "active":
        return ok({"message": "Your account is pending admin activation. You will receive an email once it is active."}, 403)
    try:
        token = tenant_token(tenant["id"])
    except Exception as exc:
        return ok({"message": f"Server configuration error: {exc}"}, 500)
    return ok(
        {
            "success": True,
            "token": token,
            "tenant": {"id": tenant["id"], "business_name": tenant.get("business_name"), "email": tenant.get("email"), **tenant_theme_payload(tenant)},
        }
    )


@csrf_exempt
@api_view(["GET"])
def public_site(request):
    return ok({**DEFAULT_SITE, **(ref("site_settings").get() or {})})


@csrf_exempt
@api_view(["GET"])
def public_stats(request):
    tenants = list_children("tenants")
    active_tenants = [tenant for tenant in tenants if tenant.get("status") == "active"]
    customers = []
    for tenant in tenants:
        customers.extend(list_children(f"tenants/{tenant['id']}/customers"))
    active_customers = [customer for customer in customers if customer.get("status") == "active"]
    return ok(
        {
            "totalTenants": len(tenants),
            "activeTenants": len(active_tenants),
            "totalCustomers": len(customers),
            "activeCustomers": len(active_customers),
        }
    )


@csrf_exempt
@api_view(["GET"])
def public_tenant(request, tenant_id):
    tenant = ref(f"tenants/{tenant_id}").get()
    if not tenant:
        return ok({"message": "Tenant not found"}, 404)
    return ok({"id": tenant_id, "business_name": tenant.get("business_name"), "phone": tenant.get("phone"), "status": tenant.get("status"), "logo_url": tenant.get("logo_url") or ""})


@csrf_exempt
@api_view(["GET"])
def public_packages(request, tenant_id):
    tenant = ref(f"tenants/{tenant_id}").get()
    if not tenant:
        return ok({"message": "Tenant not found"}, 404)
    if tenant.get("status") == "suspended":
        return ok({"message": "Tenant is not accepting payments"}, 403)
    requested_service = str(request.GET.get("service_type") or "").strip().lower()
    packages = [
        {
            **{key: pkg.get(key) for key in ["id", "name", "speed", "duration_days", "duration_unit", "duration_value", "duration_hours", "price", "service_type"]},
            "service_type": package_service_type(pkg),
            "duration_label": package_duration_label(pkg),
        }
        for pkg in list_children(f"tenants/{tenant_id}/packages")
        if pkg.get("is_active") is not False and (requested_service not in {"hotspot", "pppoe"} or package_service_type(pkg) == requested_service)
    ]
    return ok(sorted(packages, key=lambda item: float(item.get("price") or 0)))


@csrf_exempt
@api_view(["POST"])
def public_pay(request, tenant_id):
    data = body(request)
    if not data.get("package_id") or not data.get("phone"):
        return ok({"message": "Package and phone number are required"}, 400)
    tenant_data = ref(f"tenants/{tenant_id}").get()
    if not tenant_data:
        return ok({"message": "Tenant not found"}, 404)
    if tenant_data.get("status") == "suspended":
        return ok({"message": "Tenant is not accepting payments"}, 403)
    pkg = ref(f"tenants/{tenant_id}/packages/{data['package_id']}").get()
    if not pkg or pkg.get("is_active") is False:
        return ok({"message": "Package not found"}, 404)
    tenant = {"id": tenant_id, **tenant_data}
    phone = normalize_phone(data["phone"])
    service_type = str(data.get("service_type") or "hotspot").strip().lower()
    if service_type not in {"hotspot", "pppoe", "tv"}:
        return ok({"message": "Invalid service type"}, 400)
    package_type = package_service_type(pkg)
    if service_type in {"hotspot", "pppoe"} and service_type != package_type:
        return ok({"message": f"This package is only available for {package_type.upper()} customers"}, 400)
    if service_type == "tv" and package_type != "hotspot":
        return ok({"message": "TV MAC access is only available for hotspot packages"}, 400)
    customer = None
    mac_address = ""
    if service_type == "pppoe":
        username = str(data.get("username") or "").strip()
        if not username:
            return ok({"message": "PPPoE username is required"}, 400)
        customer = next(
            (
                item
                for item in list_children(f"tenants/{tenant_id}/customers")
                if str(item.get("username") or "").lower() == username.lower()
            ),
            None,
        )
        if not customer:
            return ok({"message": "PPPoE account not found. Please contact your ISP."}, 404)
        phone = normalize_phone(data.get("phone") or customer.get("phone"))
    elif service_type == "tv":
        mac_address = normalize_mac(data.get("mac_address"))
        if not mac_address:
            return ok({"message": "Enter a valid TV MAC address"}, 400)
    payment_ref = ref(f"tenants/{tenant_id}/payments").push(
        {
            "customer_id": customer.get("id") if customer else None,
            "customer_name": customer.get("name") if customer else None,
            "package_id": data["package_id"],
            "package_name": pkg.get("name"),
            "amount": float(pkg.get("price") or 0),
            "payment_code": None,
            "phone": phone,
            "status": "pending",
            "paid_at": None,
            "initiated_at": iso_now(),
            "service_type": service_type,
            "username": customer.get("username") if customer else None,
            "mac_address": mac_address,
            "source": "customer_portal",
            "provider": "paystack",
        }
    )
    try:
        checkout = initiate_paystack_payment(
            tenant,
            payment_ref.key,
            pkg.get("price"),
            email=data.get("email"),
            phone=phone,
            description=f"{pkg.get('name')} internet package",
            metadata={
                "package_id": data["package_id"],
                "package_name": pkg.get("name"),
                "service_type": service_type,
                "username": customer.get("username") if customer else None,
                "mac_address": mac_address,
            },
        )
    except PaymentProviderError as exc:
        payment_ref.update({"status": "failed", "failed_at": iso_now(), "callback_result_desc": exc.detail})
        return ok({"success": False, "message": exc.public_message, "paymentId": payment_ref.key}, exc.status_code)
    payment_ref.update(
        {
            "paystack_reference": checkout.get("reference"),
            "paystack_access_code": checkout.get("access_code"),
            "paystack_authorization_url": checkout.get("authorization_url"),
            "paystack_customer_email": checkout.get("customer_email"),
            "currency": checkout.get("currency"),
            "checkout_requested_at": iso_now(),
        }
    )
    return ok({"success": True, "message": "Redirecting to Paystack checkout", "paymentId": payment_ref.key, "reference": checkout.get("reference"), "authorizationUrl": checkout.get("authorization_url")})


@csrf_exempt
@api_view(["POST"])
def public_redeem(request, tenant_id):
    receipt_code = body(request).get("receipt_code") or body(request).get("payment_code")
    if not receipt_code:
        return ok({"message": "Payment reference is required"}, 400)
    payment = None
    for item in list_children(f"tenants/{tenant_id}/payments"):
        candidates = [item.get("payment_code"), item.get("paystack_reference")]
        if any(str(candidate or "").upper() == str(receipt_code).strip().upper() for candidate in candidates):
            payment = item
            break
    if not payment or payment.get("status") != "success":
        return ok({"message": "Paid transaction not found"}, 404)
    if not payment.get("access_expires_at") or str(payment["access_expires_at"]) <= iso_now():
        return ok({"message": "This package has expired"}, 410)
    tenant = {"id": tenant_id, **(ref(f"tenants/{tenant_id}").get() or {})}
    if payment.get("access_username"):
        set_customer_enabled(tenant, payment["access_username"], payment.get("service_type", "hotspot"), True)
    return ok(
        {
            "success": True,
            "package_name": payment.get("package_name"),
            "service_type": payment.get("service_type"),
            "phone": payment.get("phone"),
            "username": payment.get("access_username"),
            "password": payment.get("access_password"),
            "mac_address": payment.get("access_mac_address") or payment.get("mac_address"),
            "expires_at": payment.get("access_expires_at"),
        }
    )


@csrf_exempt
@api_view(["GET"])
def public_verify(request, tenant_id):
    reference = request.GET.get("reference") or request.GET.get("trxref")
    if not reference:
        return ok({"message": "Payment reference is required"}, 400)
    found_tenant_id, payment_id, payment = find_payment_by_paystack_reference(reference, tenant_id=tenant_id)
    if found_tenant_id != str(tenant_id) or not payment:
        return ok({"message": "Payment not found"}, 404)
    if payment.get("status") != "success":
        tenant = {"id": tenant_id, **(ref(f"tenants/{tenant_id}").get() or {})}
        try:
            verified = verify_paystack_transaction(tenant, reference)
            if verified.get("status") == "success":
                complete_paystack_payment(verified)
                payment = ref(f"tenants/{tenant_id}/payments/{payment_id}").get() or payment
            else:
                return ok({"success": False, "status": "failed", "message": verified.get("gateway_response") or "Payment was not successful"}, 400)
        except Exception:
            return ok({"success": False, "status": payment.get("status") or "pending", "message": "Payment verification is still pending. Please contact your ISP if this continues."}, 202)
    return ok(
        {
            "success": payment.get("status") == "success",
            "status": payment.get("status"),
            "package_name": payment.get("package_name"),
            "service_type": payment.get("service_type"),
            "phone": payment.get("phone"),
            "username": payment.get("access_username"),
            "password": payment.get("access_password"),
            "mac_address": payment.get("access_mac_address") or payment.get("mac_address"),
            "expires_at": payment.get("access_expires_at"),
            "paymentId": payment_id,
        }
    )


@csrf_exempt
@api_view(["GET", "PATCH", "DELETE"])
@tenant_required
def customers(request, customer_id=None):
    tenant = request.tenant
    if method(request, "GET") and not customer_id:
        return as_collection_response(request, list_children(f"tenants/{tenant['id']}/customers"))
    if method(request, "GET") and customer_id:
        customer = ref(f"tenants/{tenant['id']}/customers/{customer_id}").get()
        if not customer:
            return ok({"message": "Customer not found"}, 404)
        return ok({"id": customer_id, **customer})
    if method(request, "PATCH") and customer_id:
        customer = ref(f"tenants/{tenant['id']}/customers/{customer_id}").get()
        if not customer:
            return ok({"message": "Customer not found"}, 404)
        data = body(request)
        allowed = ["name", "phone", "username", "package", "service_type", "status", "expiry_date", "auto_reconnect"]
        updates = {field: data[field] for field in allowed if field in data}
        if not updates:
            return ok({"message": "No customer fields provided"}, 400)
        updates["updated_at"] = iso_now()
        ref(f"tenants/{tenant['id']}/customers/{customer_id}").update(updates)
        return ok({"success": True, "message": "Customer updated", "customer": {"id": customer_id, **customer, **updates}})
    if method(request, "DELETE") and customer_id:
        customer = ref(f"tenants/{tenant['id']}/customers/{customer_id}").get()
        if not customer:
            return ok({"message": "Customer not found"}, 404)
        try:
            delete_router_customer(tenant, customer.get("username"), customer.get("service_type") or "pppoe")
        except Exception:
            pass
        ref(f"tenants/{tenant['id']}/customers/{customer_id}").delete()
        return ok({"success": True, "message": "Customer deleted"})
    return ok({"message": "Method not allowed"}, 405)


@csrf_exempt
@api_view(["POST"])
@tenant_required
def customer_add(request):
    data = body(request)
    required = ["name", "phone", "username", "password", "package_name"]
    if any(not data.get(field) for field in required):
        return ok({"message": "Name, phone, username, password, and package are required"}, 400)
    if any(str(c.get("username", "")).lower() == str(data["username"]).lower() for c in list_children(f"tenants/{request.tenant['id']}/customers")):
        return ok({"message": "A customer with this username already exists"}, 409)
    service_type = str(data.get("service_type") or "pppoe").strip().lower()
    if service_type not in {"pppoe", "hotspot"}:
        return ok({"message": "Customer service type must be PPPoE or Hotspot"}, 400)
    provision = data.get("provision_mikrotik", True)
    if provision:
        if not has_mikrotik_credentials(request.tenant):
            return ok({"message": "Configure MikroTik credentials before provisioning customers"}, 400)
        pkg = find_child_by_field(f"tenants/{request.tenant['id']}/packages", "name", data["package_name"])
        if not pkg:
            return ok({"message": f"Package \"{data['package_name']}\" was not found"}, 404)
        if service_type == "pppoe":
            create_ppp_profile(request.tenant, pkg["name"], pkg.get("speed"))
        else:
            create_hotspot_profile(request.tenant, pkg["name"], pkg.get("speed"))
        upsert_customer_access(request.tenant, {**data, "service_type": service_type}, disabled=True)
    new_ref = ref(f"tenants/{request.tenant['id']}/customers").push(
        {
            "name": data["name"],
            "phone": data["phone"],
            "username": data["username"],
            "password": data["password"],
            "package": data["package_name"],
            "service_type": service_type,
            "provisioning_status": "provisioned" if provision else "not_requested",
            "provisioning_message": f"{service_type.upper()} access created on MikroTik and kept disabled until payment" if provision else None,
            "status": "inactive",
            "expiry_date": None,
            "auto_reconnect": True,
            "created_at": iso_now(),
        }
    )
    return ok({"success": True, "message": "Customer added", "customerId": new_ref.key})


@csrf_exempt
@api_view(["POST"])
@tenant_required
def customer_provision(request, customer_id):
    customer = ref(f"tenants/{request.tenant['id']}/customers/{customer_id}").get()
    if not customer:
        return ok({"message": "Customer not found"}, 404)
    if not has_mikrotik_credentials(request.tenant):
        return ok({"message": "Configure MikroTik credentials before provisioning customers"}, 400)
    service_type = customer.get("service_type") or "pppoe"
    pkg = find_child_by_field(f"tenants/{request.tenant['id']}/packages", "name", customer.get("package"))
    if pkg:
        if service_type == "pppoe":
            create_ppp_profile(request.tenant, pkg["name"], pkg.get("speed"))
        elif service_type == "hotspot":
            create_hotspot_profile(request.tenant, pkg["name"], pkg.get("speed"))
    upsert_customer_access(request.tenant, {**customer, "package_name": customer.get("package"), "service_type": service_type}, disabled=customer.get("status") != "active")
    ref(f"tenants/{request.tenant['id']}/customers/{customer_id}").update(
        {"provisioning_status": "provisioned", "service_type": service_type, "auto_reconnect": True, "provisioning_message": f"{service_type.upper()} access synced on MikroTik", "provisioned_at": iso_now()}
    )
    return ok({"success": True, "message": "Customer provisioned on MikroTik"})


@csrf_exempt
@api_view(["GET"])
@tenant_required
def customer_hotspot_portal(request):
    tenant_id = request.tenant["id"]
    tenant = {"id": tenant_id, **request.tenant}
    portal_url = captive_portal_url(tenant)
    return ok(
        {
            "tenant_id": tenant_id,
            "portal_url": portal_url,
            "fallback_portal_url": portal_url,
            "hotspot_url": portal_url,
            "hotspot_profile": "billing-saas-captive",
            "description": "Assign the customer-facing router port as Hotspot. The billing-saas-captive profile redirects unpaid users to this portal so they can select a package and pay before access is activated.",
        }
    )


@csrf_exempt
@api_view(["GET", "PATCH", "DELETE"])
@tenant_required
def packages(request, package_id=None):
    tenant_id = request.tenant["id"]
    if method(request, "GET") and not package_id:
        return as_collection_response(request, list_children(f"tenants/{tenant_id}/packages"))
    if method(request, "PATCH") and package_id:
        data = body(request)
        updates = {key: data[key] for key in ["name", "speed", "duration_days", "duration_unit", "duration_value", "duration_hours", "price", "is_active", "service_type"] if key in data}
        if not updates:
            return ok({"message": "No package fields provided"}, 400)
        if "price" in updates:
            updates["price"] = float(updates["price"])
        if "is_active" in updates:
            updates["is_active"] = bool(updates["is_active"])
        if any(key in data for key in ["service_type", "duration_unit", "duration_value", "duration_days", "duration_hours"]):
            updates.update(normalized_package_payload({**data, **updates}))
        existing = ref(f"tenants/{tenant_id}/packages/{package_id}").get()
        if not existing:
            return ok({"message": "Package not found"}, 404)
        router_updates = {"updated_at": iso_now()}
        if has_mikrotik_credentials(request.tenant):
            try:
                sync_package_profile(request.tenant, {**existing, **updates})
                router_updates.update({"ppp_profile_status": "synced", "ppp_profile_synced_at": iso_now(), "ppp_profile_error": None})
            except Exception as exc:
                router_updates.update({"ppp_profile_status": "failed", "ppp_profile_error": str(exc)})
        else:
            router_updates.update({"ppp_profile_status": "pending"})
        ref(f"tenants/{tenant_id}/packages/{package_id}").update({**updates, **router_updates})
        return ok({"success": True, "message": "Package and MikroTik hotspot profile updated"})
    if method(request, "DELETE") and package_id:
        ref(f"tenants/{tenant_id}/packages/{package_id}").delete()
        return ok({"success": True, "message": "Package deleted"})
    return ok({"message": "Method not allowed"}, 405)


@csrf_exempt
@api_view(["POST"])
@tenant_required
def package_add(request):
    data = body(request)
    if any(not data.get(field) for field in ["name", "speed", "price"]):
        return ok({"message": "All package fields are required"}, 400)
    package_payload = normalized_package_payload(data)
    if find_child_by_field(f"tenants/{request.tenant['id']}/packages", "name", data["name"]):
        return ok({"message": "A package with this name already exists"}, 409)
    router_synced = False
    router_error = None
    if has_mikrotik_credentials(request.tenant):
        try:
            sync_package_profile(request.tenant, {**data, **package_payload})
            router_synced = True
        except Exception as exc:
            router_error = str(exc)
    new_ref = ref(f"tenants/{request.tenant['id']}/packages").push(
        {
            "name": data["name"],
            "speed": data["speed"],
            **package_payload,
            "price": float(data["price"]),
            "is_active": data.get("is_active") is not False,
            "ppp_profile_status": "synced" if router_synced else "pending",
            "ppp_profile_synced_at": iso_now() if router_synced else "",
            "ppp_profile_error": router_error,
            "created_at": iso_now(),
        }
    )
    message = "Package and MikroTik profile created" if router_synced else "Package created. Sync router after MikroTik is connected."
    return ok({"success": True, "message": message, "packageId": new_ref.key}, 201)


@csrf_exempt
@api_view(["GET"])
@tenant_required
def router_profiles(request):
    if not has_mikrotik_credentials(request.tenant):
        return ok({"message": "Configure MikroTik credentials before viewing router profiles"}, 400)
    profiles = router_items(request.tenant, "ppp", "profile")
    return ok([{"id": p.get(".id"), "name": p.get("name"), "rate_limit": p.get("rate-limit"), "local_address": p.get("local-address"), "remote_address": p.get("remote-address")} for p in profiles])


@csrf_exempt
@api_view(["GET"])
@tenant_required
def router_status(request):
    if not has_mikrotik_credentials(request.tenant):
        return ok({"message": "Configure MikroTik credentials before pulling router status"}, 400)
    try:
        status = router_interface_status(request.tenant)
        assignments = request.tenant.get("router_port_assignments") or {}
        return ok({**status, "assignments": assignments})
    except Exception as exc:
        return ok({"message": f"Unable to pull MikroTik status: {exc}"}, 400)


@csrf_exempt
@api_view(["POST"])
@tenant_required
def router_ports(request):
    if not has_mikrotik_credentials(request.tenant):
        return ok({"message": "Configure MikroTik credentials before assigning router ports"}, 400)
    data = body(request)
    interface_name = str(data.get("interface") or "").strip()
    service_type = str(data.get("service_type") or "").strip().lower()
    profile_name = str(data.get("profile") or "default").strip() or "default"
    if not interface_name:
        return ok({"message": "Router interface is required"}, 400)
    try:
        result = configure_router_port(request.tenant, interface_name, service_type, profile_name)
        assignments = dict(request.tenant.get("router_port_assignments") or {})
        assignments[interface_name] = {
            "service_type": service_type,
            "profile": result.get("profile") or profile_name,
            "portal_url": result.get("portal_url"),
            "updated_at": iso_now(),
        }
        ref(f"tenants/{request.tenant['id']}").update({"router_port_assignments": assignments})
        return ok({"success": True, "message": f"{interface_name} assigned to {service_type.upper()}", "result": result, "assignments": assignments})
    except Exception as exc:
        return ok({"message": f"Unable to assign router port: {exc}"}, 400)


@csrf_exempt
@api_view(["GET"])
@tenant_required
def router_provision_command(request):
    api_password = secrets.token_urlsafe(18)
    expires_at = utcnow() + timedelta(minutes=15)
    payload = {
        "purpose": "mikrotik_provision",
        "tenant_id": request.tenant["id"],
        "api_user": "billing-api",
        "api_password": api_password,
        "exp": expires_at,
    }
    token = jwt.encode(payload, _get_jwt_secret("JWT_SECRET"), algorithm="HS256")
    ref(f"tenants/{request.tenant['id']}").update({"provision_token_expires_at": expires_at.isoformat()})
    script_url = f"{public_base_url(request)}/api/router/provision/{token}"
    command = f'/tool fetch mode=https url="{script_url}" dst-path=billing-saas.rsc; delay 2s; /import billing-saas.rsc;'
    return ok({"command": command, "script_url": script_url, "api_user": "billing-api", "api_password": api_password, "expires_in_minutes": 15, "expires_at": expires_at.isoformat()})


@csrf_exempt
@api_view(["GET"])
def router_provision_script(request, token):
    try:
        payload = jwt.decode(token, _get_jwt_secret("JWT_SECRET"), algorithms=["HS256"])
    except Exception:
        return HttpResponse("# Invalid or expired provisioning token\n", status=401, content_type="text/plain")
    if payload.get("purpose") != "mikrotik_provision":
        return HttpResponse("# Invalid provisioning token\n", status=401, content_type="text/plain")
    tenant_id = str(payload.get("tenant_id") or "")
    base_url = public_base_url(request).rstrip("/")
    portal_url = f"{base_url}/portal/{tenant_id}"
    portal_host = urlparse(base_url).netloc.split("@")[-1].split(":")[0]
    login_html = f"<!doctype html><html><head><meta http-equiv='refresh' content='0; url={portal_url}'></head><body><script>location.replace('{portal_url}');</script></body></html>"
    api_user = str(payload.get("api_user") or "billing-api").replace('"', "")
    api_password = str(payload.get("api_password") or "").replace('"', "")
    script = f""":log info "Billing SaaS provisioning started";
:do {{ /user group add name=billing-saas policy=api,read,write,test,sensitive }} on-error={{}}
:do {{ /user remove [find name="{api_user}"] }} on-error={{}}
/user add name="{api_user}" password="{api_password}" group=billing-saas comment="Billing SaaS API user";
/ip service enable api;
:do {{ /ip hotspot profile add name=billing-saas-captive login-by=http-chap,http-pap use-radius=no html-directory=hotspot comment="Billing SaaS captive portal: {portal_url}" }} on-error={{ /ip hotspot profile set [find name=billing-saas-captive] login-by=http-chap,http-pap use-radius=no html-directory=hotspot comment="Billing SaaS captive portal: {portal_url}" }}
:do {{ /ip hotspot walled-garden add action=allow dst-host="{portal_host}" comment="billing-saas captive portal access" }} on-error={{}}
:do {{ /ip hotspot walled-garden add action=allow dst-host="checkout.paystack.com" comment="billing-saas captive portal access" }} on-error={{}}
:do {{ /ip hotspot walled-garden add action=allow dst-host="api.paystack.co" comment="billing-saas captive portal access" }} on-error={{}}
:do {{ /ip hotspot walled-garden add action=allow dst-host="*.paystack.co" comment="billing-saas captive portal access" }} on-error={{}}
:do {{ /ip hotspot walled-garden add action=allow dst-host="*.paystack.com" comment="billing-saas captive portal access" }} on-error={{}}
:local billingLogin "{login_html}";
:do {{ /file set [find name="hotspot/login.html"] contents=$billingLogin }} on-error={{ :do {{ /file add name="hotspot/login.html" contents=$billingLogin }} on-error={{}} }}
:do {{ /file set [find name="flash/hotspot/login.html"] contents=$billingLogin }} on-error={{}}
:log info "Billing SaaS provisioning complete";
"""
    return HttpResponse(script, content_type="text/plain")


@csrf_exempt
@api_view(["POST"])
@tenant_required
def package_sync(request, package_id=None):
    if not has_mikrotik_credentials(request.tenant):
        return ok({"message": "Configure MikroTik credentials before syncing package profiles"}, 400)
    tenant_id = request.tenant["id"]
    packages_to_sync = list_children(f"tenants/{tenant_id}/packages") if package_id is None else [{"id": package_id, **(ref(f"tenants/{tenant_id}/packages/{package_id}").get() or {})}]
    if package_id and not packages_to_sync[0].get("name"):
        return ok({"message": "Package not found"}, 404)
    results = []
    for pkg in packages_to_sync:
        try:
            sync_package_profile(request.tenant, pkg)
            ref(f"tenants/{tenant_id}/packages/{pkg['id']}").update({"ppp_profile_status": "synced", "ppp_profile_synced_at": iso_now(), "ppp_profile_error": None})
            results.append({"id": pkg["id"], "name": pkg["name"], "success": True})
        except Exception as exc:
            ref(f"tenants/{tenant_id}/packages/{pkg['id']}").update({"ppp_profile_status": "failed", "ppp_profile_error": str(exc), "ppp_profile_failed_at": iso_now()})
            results.append({"id": pkg["id"], "name": pkg.get("name"), "success": False, "message": str(exc)})
    if package_id:
        return ok({"success": True, "message": "MikroTik package profile synced"})
    synced = len([r for r in results if r["success"]])
    failed = len(results) - synced
    return ok({"success": failed == 0, "message": "All package profiles synced" if failed == 0 else f"{synced} package profiles synced, {failed} failed", "synced": synced, "failed": failed, "results": results})


@csrf_exempt
@api_view(["GET", "POST"])
@tenant_required
def payments(request):
    if method(request, "GET"):
        payments_data = list_children(f"tenants/{request.tenant['id']}/payments")
        status_filter = request.GET.get("status")
        from_date = parse_date(request.GET.get("from"))
        to_date = parse_date(request.GET.get("to"))
        if status_filter and status_filter != "all":
            payments_data = [item for item in payments_data if item.get("status") == status_filter]
        if from_date or to_date:
            filtered = []
            for item in payments_data:
                current = payment_date(item)
                if not current:
                    continue
                if from_date and current < from_date:
                    continue
                if to_date and current > to_date:
                    continue
                filtered.append(item)
            payments_data = filtered
        return as_collection_response(request, payments_data)
    data = body(request)
    if not data.get("phone"):
        return ok({"message": "Customer phone is required"}, 400)
    phone = normalize_phone(data["phone"])
    payment_ref = ref(f"tenants/{request.tenant['id']}/payments").push(
        {
            "customer_id": data.get("customer_id"),
            "customer_name": data.get("customer_name"),
            "package_name": data.get("package_name"),
            "service_type": data.get("service_type") or "pppoe",
            "amount": float(data.get("amount") or 0),
            "payment_code": None,
            "phone": phone,
            "status": "pending",
            "paid_at": None,
            "initiated_at": iso_now(),
            "provider": "paystack",
        }
    )
    try:
        checkout = initiate_paystack_payment(
            request.tenant,
            payment_ref.key,
            data.get("amount"),
            email=data.get("email"),
            phone=phone,
            description=f"{data.get('package_name') or 'Internet'} payment",
            metadata={
                "customer_id": data.get("customer_id"),
                "customer_name": data.get("customer_name"),
                "package_name": data.get("package_name"),
                "service_type": data.get("service_type") or "pppoe",
            },
        )
    except PaymentProviderError as exc:
        payment_ref.update({"status": "failed", "failed_at": iso_now(), "callback_result_desc": exc.detail})
        return ok({"success": False, "message": exc.public_message, "paymentId": payment_ref.key}, exc.status_code)
    payment_ref.update(
        {
            "paystack_reference": checkout.get("reference"),
            "paystack_access_code": checkout.get("access_code"),
            "paystack_authorization_url": checkout.get("authorization_url"),
            "paystack_customer_email": checkout.get("customer_email"),
            "currency": checkout.get("currency"),
            "checkout_requested_at": iso_now(),
        }
    )
    return ok({"success": True, "message": "Paystack checkout created", "paymentId": payment_ref.key, "reference": checkout.get("reference"), "authorizationUrl": checkout.get("authorization_url")})


@csrf_exempt
@api_view(["POST"])
@tenant_required
def payment_mark_paid(request, payment_id):
    payment = ref(f"tenants/{request.tenant['id']}/payments/{payment_id}").get()
    if not payment:
        return ok({"message": "Payment not found"}, 404)
    payment_code = payment.get("payment_code") or payment.get("paystack_reference") or f"CASH-{secrets.token_hex(4).upper()}"
    updates = {
        "status": "success",
        "provider": payment.get("provider") or "cash",
        "payment_code": payment_code,
        "paid_at": iso_now(),
        "callback_result_code": "manual",
        "callback_result_desc": "Marked as paid by operator",
    }
    ref(f"tenants/{request.tenant['id']}/payments/{payment_id}").update(updates)
    try:
        activate_paid_access(request.tenant, payment_id, {**payment, **updates}, payment.get("phone"), payment_code)
    except Exception as exc:
        ref(f"tenants/{request.tenant['id']}/payments/{payment_id}").update({"access_status": "activation_failed", "callback_result_desc": str(exc)})
        return ok({"success": True, "message": "Payment marked paid, but router activation failed", "activation_error": str(exc)})
    return ok({"success": True, "message": "Payment marked as paid and access activated"})


@csrf_exempt
@api_view(["POST"])
@tenant_required
def customer_renew(request, customer_id):
    data = body(request)
    customer = ref(f"tenants/{request.tenant['id']}/customers/{customer_id}").get()
    if not customer:
        return ok({"message": "Customer not found"}, 404)
    package_id = data.get("package_id")
    package = ref(f"tenants/{request.tenant['id']}/packages/{package_id}").get() if package_id else find_child_by_field(f"tenants/{request.tenant['id']}/packages", "name", customer.get("package"))
    if not package or package.get("is_active") is False:
        return ok({"message": "Active package not found"}, 404)
    payment_ref = ref(f"tenants/{request.tenant['id']}/payments").push(
        {
            "customer_id": customer_id,
            "customer_name": customer.get("name"),
            "package_id": package_id or package.get("id"),
            "package_name": package.get("name"),
            "service_type": customer.get("service_type") or "pppoe",
            "amount": float(package.get("price") or 0),
            "payment_code": f"MANUAL-{secrets.token_hex(4).upper()}",
            "phone": customer.get("phone"),
            "status": "success",
            "paid_at": iso_now(),
            "initiated_at": iso_now(),
            "provider": data.get("provider") or "cash",
            "source": "manual_renewal",
        }
    )
    try:
        activate_paid_access(request.tenant, payment_ref.key, {**payment_ref.instance.as_dict(), "package_name": package.get("name")}, customer.get("phone"), payment_ref.instance.payment_code)
    except Exception as exc:
        payment_ref.update({"access_status": "activation_failed", "callback_result_desc": str(exc)})
        return ok({"success": True, "message": "Renewal saved, but router activation failed", "paymentId": payment_ref.key, "activation_error": str(exc)})
    return ok({"success": True, "message": "Customer renewed and access activated", "paymentId": payment_ref.key})


def tenant_payments(tenant_id):
    return list_children(f"tenants/{tenant_id}/payments")


def tenant_customers(tenant_id):
    return list_children(f"tenants/{tenant_id}/customers")


def tenant_packages(tenant_id):
    return list_children(f"tenants/{tenant_id}/packages")


def month_key(value):
    dt = parse_date(value)
    return dt.strftime("%b") if dt else ""


def in_range(item_date, start, end):
    if not item_date:
        return False
    if start and item_date < start:
        return False
    if end and item_date > end:
        return False
    return True


@csrf_exempt
@api_view(["GET"])
@tenant_required
def dashboard_stats(request):
    tenant_id = request.tenant["id"]
    payments_data = tenant_payments(tenant_id)
    customers_data = tenant_customers(tenant_id)
    packages_data = tenant_packages(tenant_id)
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    paid_payments = [p for p in payments_data if p.get("status") == "success"]
    revenue_this_month = sum(float(p.get("amount") or 0) for p in paid_payments if (payment_date(p) or now) >= month_start)

    last_12 = []
    for offset in range(11, -1, -1):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        label = datetime(year, month, 1).strftime("%b")
        total = sum(float(p.get("amount") or 0) for p in paid_payments if (payment_date(p) and payment_date(p).year == year and payment_date(p).month == month))
        last_12.append([label, round(total, 2)])

    days = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date()
        label = day.strftime("%a")
        active = len([c for c in customers_data if c.get("status") == "active"])
        new = len([c for c in customers_data if parse_date(c.get("created_at")) and parse_date(c.get("created_at")).date() == day])
        days.append([label, active, new])

    package_counts = Counter(c.get("package") or "Unassigned" for c in customers_data)
    palette = ["#fa8200", "#2563eb", "#16a34a", "#dc2626", "#9333ea", "#0f766e"]
    package_utilization = [[name, count, palette[index % len(palette)]] for index, (name, count) in enumerate(package_counts.items())]
    package_revenue = defaultdict(float)
    for payment in paid_payments:
        package_revenue[payment.get("package_name") or "Unassigned"] += float(payment.get("amount") or 0)
    package_performance = []
    for package in packages_data:
        name = package.get("name")
        active_count = len([c for c in customers_data if c.get("package") == name and c.get("status") == "active"])
        revenue = package_revenue.get(name, 0)
        package_performance.append(
            {
                "name": name,
                "price": float(package.get("price") or 0),
                "active_users": active_count,
                "monthly_revenue": round(revenue, 2),
                "avg_data_usage": float(package.get("avg_data_usage") or 0),
                "arpu": round(revenue / active_count, 2) if active_count else 0,
                "sync_status": package.get("ppp_profile_status") or "pending",
            }
        )

    return ok(
        {
            "summary": {
                "revenue_this_month": round(revenue_this_month, 2),
                "sms_balance": float(request.tenant.get("sms_balance") or 0),
                "total_customers": len(customers_data),
                "active_customers": len([c for c in customers_data if c.get("status") == "active"]),
            },
            "payments_chart": last_12,
            "active_users_chart": days,
            "retention_chart": [[item[0], item[1], max(0, item[1] - item[2]), 90] for item in days[-6:]],
            "data_usage_chart": [[item[0], float(index * 8 + item[1])] for index, item in enumerate(days[-8:])],
            "package_utilization": package_utilization,
            "revenue_forecast": last_12[-6:] + [[f"+{i}", round((last_12[-1][1] if last_12 else 0) * (1 + i * 0.05), 2)] for i in range(1, 4)],
            "sms_chart": [[item[0], int(request.tenant.get("sms_sent_today") or 0)] for item in days],
            "most_active_users": sorted(
                [
                    {
                        "username": c.get("username") or c.get("phone"),
                        "phone": c.get("phone"),
                        "data_used": float(c.get("data_used") or c.get("data_usage") or 0),
                    }
                    for c in customers_data
                ],
                key=lambda item: item["data_used"],
                reverse=True,
            )[:6],
            "package_performance": package_performance,
        }
    )


@csrf_exempt
@api_view(["GET"])
@tenant_required
def report_revenue(request):
    start = parse_date(request.GET.get("from"))
    end = parse_date(request.GET.get("to"))
    monthly = defaultdict(float)
    for payment in tenant_payments(request.tenant["id"]):
        dt = payment_date(payment)
        if payment.get("status") == "success" and in_range(dt, start, end):
            monthly[dt.strftime("%Y-%m")] += float(payment.get("amount") or 0)
    rows = [{"month": key, "revenue": round(value, 2)} for key, value in sorted(monthly.items())]
    return ok({"results": rows, "total": round(sum(item["revenue"] for item in rows), 2)})


@csrf_exempt
@api_view(["GET"])
@tenant_required
def report_customers(request):
    start = parse_date(request.GET.get("from"))
    end = parse_date(request.GET.get("to"))
    monthly = defaultdict(int)
    customers_data = tenant_customers(request.tenant["id"])
    for customer in customers_data:
        dt = parse_date(customer.get("created_at"))
        if in_range(dt, start, end):
            monthly[dt.strftime("%Y-%m")] += 1
    expired = len([c for c in customers_data if c.get("expiry_date") and str(c.get("expiry_date")) < iso_now()])
    return ok({"results": [{"month": key, "new_customers": value} for key, value in sorted(monthly.items())], "total_customers": len(customers_data), "expired_customers": expired})


@csrf_exempt
@api_view(["GET"])
@tenant_required
def report_packages(request):
    customers_data = tenant_customers(request.tenant["id"])
    payments_data = [p for p in tenant_payments(request.tenant["id"]) if p.get("status") == "success"]
    rows = []
    for package in tenant_packages(request.tenant["id"]):
        name = package.get("name")
        revenue = sum(float(p.get("amount") or 0) for p in payments_data if p.get("package_name") == name)
        rows.append({"package": name, "price": float(package.get("price") or 0), "active_customers": len([c for c in customers_data if c.get("package") == name and c.get("status") == "active"]), "revenue": round(revenue, 2)})
    return ok({"results": rows})


@csrf_exempt
@api_view(["GET"])
@tenant_required
def report_expenses(request):
    expenses = request.tenant.get("expenses") or []
    if not isinstance(expenses, list):
        expenses = []
    by_category = defaultdict(float)
    for expense in expenses:
        by_category[expense.get("category") or "Other"] += float(expense.get("amount") or 0)
    revenue = sum(float(p.get("amount") or 0) for p in tenant_payments(request.tenant["id"]) if p.get("status") == "success")
    total_expenses = sum(by_category.values())
    return ok({"results": [{"category": key, "amount": round(value, 2)} for key, value in sorted(by_category.items())], "total_expenses": round(total_expenses, 2), "net_revenue": round(revenue - total_expenses, 2)})


@csrf_exempt
@api_view(["GET", "PATCH"])
@tenant_required
def settings_business(request):
    tenant_id = request.tenant["id"]
    if method(request, "GET"):
        return ok(tenant_theme_payload(request.tenant))

    data = body(request)
    allowed = [
        "business_name",
        "owner_name",
        "phone",
        "support_email",
        "theme_color",
        "font",
        "dark_mode",
        "theme_mode",
        "business_number",
        "bank_code",
        "bank_name",
        "bank_account_number",
        "paystack_platform_percentage",
    ]
    updates = {}
    for field in allowed:
        if field in data:
            updates[field] = bool(data[field]) if field == "dark_mode" else str(data[field]).strip()
    if updates.get("theme_mode") not in {None, "light", "dark", "system"}:
        updates["theme_mode"] = "light"
    if "theme_mode" in updates:
        updates["dark_mode"] = updates["theme_mode"] == "dark"
    if "theme_color" in updates and not updates["theme_color"].startswith("#"):
        updates["theme_color"] = f"#{updates['theme_color']}"
    updates["business_settings_updated_at"] = iso_now()

    merged = {**request.tenant, **updates}
    if data.get("create_subaccount") or (
        merged.get("bank_code")
        and merged.get("bank_account_number")
        and not merged.get("paystack_subaccount_code")
    ):
        try:
            updates.update(create_or_update_tenant_subaccount(tenant_id, merged, merged))
        except PaymentProviderError as exc:
            updates.update({"paystack_subaccount_status": "failed", "paystack_subaccount_error": exc.detail})
            ref(f"tenants/{tenant_id}").update(updates)
            return ok({"success": False, "message": exc.public_message, "config": tenant_theme_payload({**merged, **updates})}, exc.status_code)

    ref(f"tenants/{tenant_id}").update(updates)
    return ok({"success": True, "message": "Business settings saved", "config": tenant_theme_payload({**merged, **updates})})


@csrf_exempt
@api_view(["GET", "PATCH"])
@tenant_required
def profile(request):
    if method(request, "GET"):
        return ok({"owner_name": request.tenant.get("owner_name") or "", "email": request.tenant.get("email") or "", "phone": request.tenant.get("phone") or "", "business_name": request.tenant.get("business_name") or ""})
    data = body(request)
    updates = {}
    if "owner_name" in data:
        updates["owner_name"] = str(data.get("owner_name") or "").strip()
    if "phone" in data:
        updates["phone"] = str(data.get("phone") or "").strip()
    if "email" in data and str(data.get("email") or "").strip().lower() != request.tenant.get("email"):
        if not check_password(data.get("current_password", ""), request.tenant.get("password")):
            return ok({"message": "Current password is required to change email"}, 400)
        updates["email"] = str(data["email"]).strip().lower()
    if data.get("new_password"):
        if not check_password(data.get("current_password", ""), request.tenant.get("password")):
            return ok({"message": "Current password is incorrect"}, 400)
        if data.get("new_password") != data.get("confirm_password"):
            return ok({"message": "New password and confirmation do not match"}, 400)
        updates["password"] = hash_password(data["new_password"])
    if not updates:
        return ok({"message": "No profile fields provided"}, 400)
    ref(f"tenants/{request.tenant['id']}").update({**updates, "profile_updated_at": iso_now()})
    return ok({"success": True, "message": "Profile updated"})


@csrf_exempt
@api_view(["POST"])
@tenant_required
def settings_logo(request):
    upload = request.FILES.get("logo")
    if not upload:
        return ok({"message": "Logo file is required"}, 400)
    if upload.size > 2 * 1024 * 1024:
        return ok({"message": "Logo must be smaller than 2MB"}, 400)
    ext = Path(upload.name).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
        return ok({"message": "Logo must be PNG, JPG, WEBP, or SVG"}, 400)
    storage = FileSystemStorage(location=Path(settings.MEDIA_ROOT) / "tenant-logos", base_url=f"{settings.MEDIA_URL}tenant-logos/")
    filename = storage.save(f"tenant-{request.tenant['id']}{ext}", upload)
    logo_url = storage.url(filename)
    ref(f"tenants/{request.tenant['id']}").update({"logo_url": logo_url, "logo_updated_at": iso_now()})
    return ok({"success": True, "message": "Logo uploaded", "logo_url": logo_url})


@csrf_exempt
@api_view(["POST"])
@tenant_required
def settings_test_sms(request):
    data = body(request)
    phone = normalize_phone(data.get("phone") or request.tenant.get("phone"))
    if not phone:
        return ok({"message": "Phone number is required"}, 400)
    return ok({"success": True, "message": "Test SMS queued", "phone": phone})


@csrf_exempt
@api_view(["GET", "POST", "PATCH", "DELETE"])
@tenant_required
def tickets(request, ticket_id=None):
    tenant_id = request.tenant["id"]
    if method(request, "GET") and not ticket_id:
        items = list_children(f"tenants/{tenant_id}/tickets")
        status_filter = request.GET.get("status")
        if status_filter and status_filter != "all":
            items = [item for item in items if item.get("status") == status_filter]
        return as_collection_response(request, items)
    if method(request, "POST") and not ticket_id:
        data = body(request)
        if not data.get("title"):
            return ok({"message": "Ticket title is required"}, 400)
        ticket_ref = ref(f"tenants/{tenant_id}/tickets").push(
            {
                "title": str(data.get("title") or "").strip(),
                "description": str(data.get("description") or "").strip(),
                "customer_id": str(data.get("customer_id") or "").strip(),
                "status": data.get("status") or "open",
                "priority": data.get("priority") or "medium",
            }
        )
        return ok({"success": True, "message": "Ticket created", "ticketId": ticket_ref.key}, 201)
    if not ticket_id:
        return ok({"message": "Ticket id is required"}, 400)
    ticket = ref(f"tenants/{tenant_id}/tickets/{ticket_id}").get()
    if not ticket:
        return ok({"message": "Ticket not found"}, 404)
    if method(request, "PATCH"):
        data = body(request)
        allowed = ["title", "description", "customer_id", "status", "priority"]
        updates = {field: data[field] for field in allowed if field in data}
        if updates.get("status") in {"resolved", "closed"} and not ticket.get("resolved_at"):
            updates["resolved_at"] = iso_now()
        updates["updated_at"] = iso_now()
        ref(f"tenants/{tenant_id}/tickets/{ticket_id}").update(updates)
        return ok({"success": True, "message": "Ticket updated", "ticket": {"id": ticket_id, **ticket, **updates}})
    if method(request, "DELETE"):
        ref(f"tenants/{tenant_id}/tickets/{ticket_id}").delete()
        return ok({"success": True, "message": "Ticket deleted"})
    return ok({"message": "Method not allowed"}, 405)


@csrf_exempt
@api_view(["POST"])
@tenant_required
def settings_delete_customers(request):
    data = body(request)
    if str(data.get("confirm") or "").strip() != str(request.tenant.get("business_name") or "").strip():
        return ok({"message": "Type your business name exactly to confirm"}, 400)
    customers_data = list_children(f"tenants/{request.tenant['id']}/customers")
    for customer in customers_data:
        try:
            delete_router_customer(request.tenant, customer.get("username"), customer.get("service_type") or "pppoe")
        except Exception:
            pass
        ref(f"tenants/{request.tenant['id']}/customers/{customer['id']}").delete()
    return ok({"success": True, "message": f"Deleted {len(customers_data)} customers"})


@csrf_exempt
@api_view(["GET", "PATCH"])
@tenant_required
def settings_mikrotik(request):
    if method(request, "GET"):
        return ok({"mikrotik_host": request.tenant.get("mikrotik_host", ""), "mikrotik_user": request.tenant.get("mikrotik_user", ""), "mikrotik_port": int(request.tenant.get("mikrotik_port") or 8728), "has_mikrotik_password": bool(request.tenant.get("mikrotik_pass"))})
    data = body(request)
    updates = {}
    for field in ["mikrotik_host", "mikrotik_user", "mikrotik_pass"]:
        if field in data and (field != "mikrotik_pass" or str(data[field]).strip()):
            updates[field] = str(data[field]).strip() if field != "mikrotik_pass" else str(data[field])
    if "mikrotik_port" in data:
        updates["mikrotik_port"] = int(data.get("mikrotik_port") or 8728)
    if "mikrotik_port" in updates and not 1 <= updates["mikrotik_port"] <= 65535:
        return ok({"message": "MikroTik port must be between 1 and 65535"}, 400)
    updates["mikrotik_updated_at"] = iso_now()
    ref(f"tenants/{request.tenant['id']}").update(updates)
    merged = {**request.tenant, **updates}
    return ok({"success": True, "message": "MikroTik configuration saved", "config": {"mikrotik_host": merged.get("mikrotik_host", ""), "mikrotik_user": merged.get("mikrotik_user", ""), "mikrotik_port": int(merged.get("mikrotik_port") or 8728), "has_mikrotik_password": bool(merged.get("mikrotik_pass"))}})


@csrf_exempt
@api_view(["POST"])
@tenant_required
def settings_mikrotik_test(request):
    candidate = {**request.tenant, **body(request)}
    if not candidate.get("mikrotik_pass"):
        return ok({"message": "MikroTik password is required to test the connection"}, 400)
    profiles = router_items(candidate, "ppp", "profile")
    captive = ensure_hotspot_captive_portal(candidate)
    return ok({"success": True, "message": "MikroTik connection successful. Captive portal profile is ready.", "profile_count": len(profiles), "hotspot_profile": (captive or {}).get("profile"), "portal_url": (captive or {}).get("portal_url")})


@csrf_exempt
@api_view(["GET", "PATCH"])
@tenant_required
def settings_notifications(request):
    if method(request, "GET"):
        return ok(
            {
                "provider": request.tenant.get("notification_provider") or "whatsapp_cloud",
                "sms_enabled": request.tenant.get("sms_enabled") is not False,
                "whatsapp_enabled": bool(request.tenant.get("whatsapp_enabled")) or os.getenv("WHATSAPP_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
                "roamtech_sender_id": request.tenant.get("roamtech_sender_id") or "",
                "payment_sms_template": request.tenant.get("payment_sms_template") or "Hi {{name}}, your {{package}} payment of Ksh {{amount}} is confirmed. Username: {{username}}, Password: {{password}}.",
                "payment_whatsapp_template": request.tenant.get("payment_whatsapp_template") or "Hi {{name}}, your {{package}} internet package is active. Amount: Ksh {{amount}}. Username: {{username}}, Password: {{password}}.",
            }
        )
    data = body(request)
    updates = {
        "notification_provider": str(data.get("provider") or "whatsapp_cloud").strip(),
        "sms_enabled": data.get("sms_enabled") is not False,
        "whatsapp_enabled": bool(data.get("whatsapp_enabled")),
        "roamtech_sender_id": str(data.get("roamtech_sender_id") or "").strip(),
        "payment_sms_template": str(data.get("payment_sms_template") or "").strip(),
        "payment_whatsapp_template": str(data.get("payment_whatsapp_template") or "").strip(),
        "notifications_updated_at": iso_now(),
    }
    ref(f"tenants/{request.tenant['id']}").update(updates)
    return ok({"success": True, "message": "Notification settings saved", "config": updates})


def to_access_username(phone):
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def render_notification_template(template, context):
    rendered = str(template or "")
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", str(value if value is not None else ""))
    return rendered


def notify_payment_access(tenant, payment, access):
    if not ((tenant or {}).get("whatsapp_enabled") or os.getenv("WHATSAPP_ENABLED", "false").lower() in {"1", "true", "yes", "on"}):
        return None
    template = (tenant or {}).get("payment_whatsapp_template") or "Hi {{name}}, your {{package}} internet package is active. Amount: Ksh {{amount}}. Username: {{username}}, Password: {{password}}."
    message = render_notification_template(
        template,
        {
            "name": payment.get("customer_name") or payment.get("phone") or "customer",
            "package": payment.get("package_name") or "",
            "amount": payment.get("amount") or "",
            "username": access.get("username") or access.get("mac_address") or "",
            "password": access.get("password") or "",
            "expires_at": access.get("expiry_date") or "",
        },
    )
    return send_whatsapp_message(payment.get("phone"), message, tenant)


def activate_paid_access(tenant, payment_id, payment, phone, payment_code):
    tenant_id = tenant["id"]
    package_name = payment.get("package_name")
    customers_data = list_children(f"tenants/{tenant_id}/customers")
    customer = None
    if payment.get("customer_id"):
        customer = next((c for c in customers_data if str(c.get("id")) == str(payment.get("customer_id"))), None)
    if not customer and payment.get("username"):
        customer = next((c for c in customers_data if str(c.get("username") or "").lower() == str(payment.get("username") or "").lower()), None)
    if not customer and phone:
        customer = next((c for c in customers_data if str(c.get("phone")) == str(phone)), None)
    service_type = payment.get("service_type") or (customer or {}).get("service_type") or "hotspot"
    package_for_access = package_name or (customer or {}).get("package")
    pkg = find_child_by_field(f"tenants/{tenant_id}/packages", "name", package_for_access)
    expiry = utcnow() + package_duration_delta(pkg)
    mac_address = normalize_mac(payment.get("mac_address") or (customer or {}).get("mac_address"))
    username = mac_address if service_type == "tv" else (payment.get("username") or (customer or {}).get("username") or to_access_username(phone))
    password = str(payment_code)
    if customer:
        updates = {"username": username, "password": password, "package": package_for_access, "service_type": service_type, "status": "active", "expiry_date": expiry.isoformat(), "last_payment_id": payment_id, "last_payment_code": payment_code, "auto_reconnect": True, "updated_at": iso_now()}
        if mac_address:
            updates["mac_address"] = mac_address
        ref(f"tenants/{tenant_id}/customers/{customer['id']}").update(updates)
        customer_id = customer["id"]
    else:
        new_ref = ref(f"tenants/{tenant_id}/customers").push({"name": mac_address or phone, "phone": phone, "username": username, "password": password, "package": package_for_access, "service_type": service_type, "status": "active", "expiry_date": expiry.isoformat(), "last_payment_id": payment_id, "last_payment_code": payment_code, "auto_reconnect": True, "mac_address": mac_address, "created_at": iso_now()})
        customer_id = new_ref.key
    if service_type == "hotspot" and pkg:
        create_hotspot_profile(tenant, pkg["name"], pkg.get("speed"))
    if service_type == "pppoe" and pkg:
        create_ppp_profile(tenant, pkg["name"], pkg.get("speed"))
    if service_type == "tv" and not mac_address:
        raise ValueError("TV MAC address is required for activation")
    upsert_customer_access(tenant, {"username": username, "password": password, "package_name": package_for_access, "service_type": service_type, "mac_address": mac_address})
    set_customer_enabled(tenant, username, service_type, True)
    ref(f"tenants/{tenant_id}/payments/{payment_id}").update({"customer_id": customer_id, "access_username": username, "access_password": password, "access_mac_address": mac_address, "access_expires_at": expiry.isoformat(), "access_status": "active", "auto_reconnect": True})
    access = {"username": username, "password": password, "mac_address": mac_address, "expiry_date": expiry.isoformat()}
    try:
        notify_result = notify_payment_access(tenant, {**payment, "phone": phone, "package_name": package_for_access}, access)
        if notify_result:
            ref(f"tenants/{tenant_id}/payments/{payment_id}").update({"whatsapp_status": "sent" if notify_result.get("sent") else "skipped", "whatsapp_detail": notify_result.get("skipped") or ""})
    except Exception as exc:
        ref(f"tenants/{tenant_id}/payments/{payment_id}").update({"whatsapp_status": "failed", "whatsapp_detail": str(exc)})
    return access


def find_payment_by_paystack_reference(reference, tenant_id=None, payment_id=None):
    tenant_ids = [tenant_id] if tenant_id else [tenant["id"] for tenant in list_children("tenants")]
    for current_tenant_id in tenant_ids:
        if not current_tenant_id:
            continue
        if payment_id:
            payment = ref(f"tenants/{current_tenant_id}/payments/{payment_id}").get()
            if payment:
                return current_tenant_id, payment_id, payment
        for item in list_children(f"tenants/{current_tenant_id}/payments"):
            if item.get("paystack_reference") == reference:
                return current_tenant_id, item["id"], item
    return None, None, None


def complete_paystack_payment(event_data):
    reference = event_data.get("reference")
    metadata = event_data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    tenant_id, payment_id, payment = find_payment_by_paystack_reference(reference, metadata.get("tenant_id"), metadata.get("payment_id"))
    if not tenant_id or not payment_id:
        return False
    if payment.get("status") == "success":
        return True

    customer = event_data.get("customer") or {}
    authorization = event_data.get("authorization") or {}
    payment_code = reference or event_data.get("id")
    phone = metadata.get("phone") or payment.get("phone")
    update = {
        "provider": "paystack",
        "amount": float(event_data.get("amount") or 0) / 100,
        "currency": event_data.get("currency") or payment.get("currency"),
        "payment_code": payment_code,
        "paystack_reference": reference,
        "paystack_transaction_id": event_data.get("id"),
        "paystack_channel": event_data.get("channel"),
        "paystack_paid_at": event_data.get("paid_at") or event_data.get("paidAt"),
        "paystack_customer_email": customer.get("email") or payment.get("paystack_customer_email"),
        "paystack_authorization_code": authorization.get("authorization_code"),
        "phone": phone,
        "status": "success",
        "paid_at": iso_now(),
        "callback_result_code": "success",
        "callback_result_desc": event_data.get("gateway_response") or "Paystack charge successful",
    }
    ref(f"tenants/{tenant_id}/payments/{payment_id}").update(update)
    tenant_data = ref(f"tenants/{tenant_id}").get() or {}
    activate_paid_access({"id": tenant_id, **tenant_data}, payment_id, {**payment, **metadata}, phone, payment_code)
    return True


def paystack_secrets_to_try():
    seen = set()
    for secret in [os.getenv("PAYSTACK_SECRET_KEY")]:
        if secret and "replace_with" not in secret and not secret.strip().endswith("_secret_key") and secret not in seen:
            seen.add(secret)
            yield secret


@csrf_exempt
@api_view(["POST"])
def paystack_webhook(request):
    signature = request.headers.get("x-paystack-signature") or request.headers.get("X-Paystack-Signature")
    if not any(verify_paystack_signature(request.body, signature, secret) for secret in paystack_secrets_to_try()):
        return ok({"message": "Invalid Paystack signature"}, 401)
    event = body(request)
    if event.get("event") == "charge.success":
        event_data = event.get("data") or {}
        reference = event_data.get("reference")
        tenant_id, payment_id, payment = find_payment_by_paystack_reference(reference, (event_data.get("metadata") or {}).get("tenant_id"), (event_data.get("metadata") or {}).get("payment_id"))
        if payment and payment.get("status") == "success":
            return ok({"success": True})
        if reference:
            tenant = {"id": tenant_id, **(ref(f"tenants/{tenant_id}").get() or {})} if tenant_id else {}
            verified = verify_paystack_transaction(tenant, reference)
            complete_paystack_payment(verified)
    return ok({"success": True})


@csrf_exempt
@api_view(["GET"])
def paystack_callback(request):
    reference = request.GET.get("reference") or request.GET.get("trxref")
    if not reference:
        return ok({"message": "Missing Paystack reference"}, 400)
    tenant_id, payment_id, payment = find_payment_by_paystack_reference(reference)
    if not tenant_id:
        return ok({"message": "Payment not found"}, 404)
    tenant = {"id": tenant_id, **(ref(f"tenants/{tenant_id}").get() or {})}
    verified = verify_paystack_transaction(tenant, reference)
    if verified.get("status") == "success":
        complete_paystack_payment(verified)
        return ok({"success": True, "message": "Payment verified. You can return to the customer portal.", "paymentId": payment_id})
    ref(f"tenants/{tenant_id}/payments/{payment_id}").update({"status": "failed", "callback_result_desc": verified.get("gateway_response") or "Paystack verification did not succeed", "failed_at": iso_now()})
    return ok({"success": False, "message": "Payment was not successful"}, 400)


@csrf_exempt
@api_view(["POST"])
def admin_login(request):
    data = body(request)
    if not data.get("email") or not data.get("password"):
        return ok({"error": "Email and password required"}, 400)
    email = str(data["email"]).lower().strip()
    password = data["password"]
    admin = find_child_by_field("admins", "email", email)

    if admin and admin.get("is_active") and check_password(password, admin.get("password")):
        login_count = int(admin.get("login_count") or 0) + 1
        ref(f"admins/{admin['id']}").update({"last_login": iso_now(), "login_count": login_count})
        write_audit_log(admin["id"], admin.get("email"), "LOGIN", admin["id"], "admin", request, {"login_count": login_count})
        try:
            token = admin_token(admin["id"], admin)
        except Exception as exc:
            return ok({"error": f"Server configuration error: {exc}"}, 500)
        return ok({"token": token, "admin": {"id": admin["id"], "name": admin.get("name"), "email": admin.get("email"), "role": admin.get("role")}})

    user = User.objects.filter(email__iexact=email).first()
    if not user or not user.is_active or not user.check_password(password):
        return ok({"error": "Invalid credentials"}, 401)
    if not (user.is_superuser or user.is_staff or user.role == User.Role.ADMIN):
        return ok({"error": "Insufficient privileges"}, 403)

    admin_profile = AdminUser.objects.filter(user=user).first() or AdminUser.objects.filter(email__iexact=email).first()
    if not admin_profile:
        admin_profile = AdminUser(user=user, name=user.name, email=user.email, password="", role="admin", is_active=True)
    admin_profile.user = user
    admin_profile.name = admin_profile.name or user.name
    admin_profile.email = user.email
    admin_profile.role = "admin"
    admin_profile.is_active = True
    admin_profile.last_login = iso_now()
    admin_profile.login_count = int(admin_profile.login_count or 0) + 1
    admin_profile.save()

    admin = admin_profile.as_dict()
    admin["id"] = str(admin_profile.pk)
    write_audit_log(admin["id"], admin.get("email"), "LOGIN", admin["id"], "admin", request, {"login_count": admin_profile.login_count})
    try:
        token = admin_token(admin["id"], admin)
    except Exception as exc:
        return ok({"error": f"Server configuration error: {exc}"}, 500)
    return ok({"token": token, "admin": {"id": admin["id"], "name": admin.get("name"), "email": admin.get("email"), "role": admin.get("role")}})


def mask_tenant(tenant):
    return {key: (MASKED if key in SENSITIVE_FIELDS and value else value) for key, value in tenant.items()}


def tenant_admin_payload(tenant):
    tenant_id = tenant.get("id")
    instance = Tenant.objects.filter(pk=tenant_id).first()
    subscription = ensure_subscription(instance) if instance else None
    payload = {"id": tenant_id, **mask_tenant(tenant)}
    payload["subscription"] = subscription_payload(subscription) if subscription else None
    payload["onboarding"] = {
        "mikrotik": bool(tenant.get("mikrotik_host") and tenant.get("mikrotik_user")),
        "customers": len(list_children(f"tenants/{tenant_id}/customers")) > 0,
        "packages": len(list_children(f"tenants/{tenant_id}/packages")) > 0,
    }
    return payload


@csrf_exempt
@api_view(["GET", "POST", "PATCH", "DELETE"])
@admin_required
def admin_tenants(request, tenant_id=None, child=None):
    if tenant_id and child == "customers":
        return ok(list_children(f"tenants/{tenant_id}/customers"))
    if tenant_id and child == "payments":
        return ok(list_children(f"tenants/{tenant_id}/payments"))
    if tenant_id and child == "packages":
        return ok(list_children(f"tenants/{tenant_id}/packages"))
    if method(request, "GET") and not tenant_id:
        tenants = [tenant_admin_payload(item) for item in list_children("tenants")]
        write_audit_log(request.admin["adminId"], request.admin["email"], "LIST_TENANTS", target_type="tenant", request=request, metadata={"count": len(tenants)})
        return ok(tenants)
    if method(request, "GET") and tenant_id:
        tenant = ref(f"tenants/{tenant_id}").get()
        if not tenant:
            return ok({"error": "Tenant not found"}, 404)
        return ok(tenant_admin_payload({"id": tenant_id, **tenant}))
    if method(request, "POST") and not tenant_id:
        data = body(request)
        required = ["business_name", "owner_name", "email", "phone", "password", "mikrotik_host", "mikrotik_user", "mikrotik_pass"]
        missing = [field for field in required if not data.get(field)]
        if missing:
            return ok({"error": f"Missing fields: {', '.join(missing)}"}, 400)
        if find_child_by_field("tenants", "email", data["email"]):
            return ok({"error": "Email already registered"}, 409)
        optional_payment_fields = ["paystack_secret_key", "paystack_subaccount_code", "paystack_bearer", "paystack_currency"]
        new_ref = ref("tenants").push({**{field: data.get(field) for field in required if field != "password"}, **{field: data.get(field, "") for field in optional_payment_fields}, "paystack_bearer": data.get("paystack_bearer") or "subaccount", "paystack_currency": data.get("paystack_currency") or os.getenv("PAYSTACK_CURRENCY", "KES"), "email": data["email"].lower().strip(), "password": hash_password(data["password"]), "mikrotik_port": int(data.get("mikrotik_port") or 8728), "status": "active", "created_by": f"admin:{request.admin['adminId']}", "created_at": iso_now()})
        tenant_instance = Tenant.objects.get(pk=new_ref.key)
        ensure_subscription(tenant_instance, data.get("plan") or "basic")
        write_audit_log(request.admin["adminId"], request.admin["email"], "CREATE_TENANT", new_ref.key, "tenant", request, {"business_name": data["business_name"], "email": data["email"].lower().strip()})
        return ok({"message": "Tenant created", "tenantId": new_ref.key}, 201)
    if method(request, "PATCH") and tenant_id:
        data = body(request)
        existing_tenant = ref(f"tenants/{tenant_id}").get() or {}
        if "password" in data:
            return ok({"error": "Cannot update sensitive fields via this route: password"}, 400)
        allowed = ["business_name", "owner_name", "email", "phone", "mikrotik_host", "mikrotik_user", "mikrotik_pass", "mikrotik_port", "paystack_secret_key", "paystack_subaccount_code", "paystack_bearer", "paystack_currency", "status"]
        updates = {}
        for field in allowed:
            if field in data:
                value = data[field]
                if field in {"mikrotik_pass", "paystack_secret_key"} and (not str(value).strip() or value == MASKED):
                    continue
                updates[field] = value
        if "email" in updates:
            updates["email"] = str(updates["email"]).lower().strip()
        if "mikrotik_port" in updates:
            updates["mikrotik_port"] = int(updates["mikrotik_port"] or 8728)
        if not updates:
            return ok({"error": "No allowed fields provided"}, 400)
        ref(f"tenants/{tenant_id}").update(updates)
        if updates.get("status") == "active" and existing_tenant.get("status") != "active":
            notify_tenant_activated({**existing_tenant, **updates, "id": tenant_id})
        if data.get("plan"):
            tenant_instance = Tenant.objects.filter(pk=tenant_id).first()
            if tenant_instance:
                subscription = ensure_subscription(tenant_instance, data.get("plan"))
                subscription.plan = data.get("plan")
                subscription.save(update_fields=["plan", "updated_at"])
        write_audit_log(request.admin["adminId"], request.admin["email"], "UPDATE_TENANT", tenant_id, "tenant", request, {"updated_fields": list(updates)})
        return ok({"message": "Tenant updated"})
    if method(request, "DELETE") and tenant_id:
        ref(f"tenants/{tenant_id}").update({"status": "suspended", "suspended_by": request.admin["adminId"], "suspended_at": iso_now()})
        write_audit_log(request.admin["adminId"], request.admin["email"], "SUSPEND_TENANT", tenant_id, "tenant", request)
        return ok({"message": "Tenant suspended"})
    return ok({"message": "Method not allowed"}, 405)


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_stats(request):
    return admin_system_stats(request)


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_system_stats(request):
    now = timezone.now()
    today = now.date()
    month_payments = SubscriptionPayment.objects.filter(paid_at__year=now.year, paid_at__month=now.month).aggregate(total=Sum("amount"))["total"] or 0
    payments_today = Payment.objects.filter(paid_at__startswith=today.isoformat()).aggregate(total=Sum("amount"))["total"] or 0
    tenants_qs = Tenant.objects.all()
    top_tenants = []
    for tenant in tenants_qs:
        top_tenants.append({"id": str(tenant.pk), "business_name": tenant.business_name, "customer_count": Customer.objects.filter(tenant=tenant).count()})
    top_tenants = sorted(top_tenants, key=lambda item: item["customer_count"], reverse=True)[:5]
    return ok(
        {
            "totalTenants": tenants_qs.count(),
            "activeTenants": tenants_qs.filter(status="active").count(),
            "suspendedTenants": tenants_qs.filter(status="suspended").count(),
            "pendingTenants": tenants_qs.filter(status="pending_setup").count(),
            "totalCustomers": Customer.objects.count(),
            "paymentsToday": float(payments_today or 0),
            "monthlyRevenue": float(month_payments or 0),
            "expiringThisWeek": TenantSubscription.objects.filter(expires_at__lte=now + timedelta(days=7), expires_at__gte=now).count(),
            "expiredCount": TenantSubscription.objects.filter(expires_at__lt=now).count(),
            "systemHealth": health_payload(),
            "topTenants": top_tenants,
        }
    )


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_revenue_chart(request):
    try:
        days = min(90, max(1, int(request.GET.get("days", 30))))
    except ValueError:
        days = 30
    now = timezone.now()
    start = now - timedelta(days=days - 1)
    rows = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        total = SubscriptionPayment.objects.filter(paid_at__date=day).aggregate(total=Sum("amount"))["total"] or 0
        rows.append({"date": day.isoformat(), "amount": float(total)})
    return ok(rows)


@csrf_exempt
@api_view(["GET", "PATCH"])
@admin_required
def admin_subscriptions(request, subscription_id=None):
    if subscription_id:
        subscription = TenantSubscription.objects.select_related("tenant").filter(pk=subscription_id).first()
        if not subscription:
            return err("Subscription not found", 404)
        if method(request, "GET"):
            return ok(subscription_payload(subscription, include_payments=True))
        data = body(request)
        for field in ["plan", "amount", "expires_at", "auto_renew", "notes"]:
            if field in data:
                value = data[field]
                if field == "expires_at":
                    value = parse_date(value)
                setattr(subscription, field, value)
        subscription.save()
        write_audit_log(request.admin["adminId"], request.admin["email"], "UPDATE_SUBSCRIPTION", str(subscription.pk), "subscription", request)
        return ok({"message": "Subscription updated", "subscription": subscription_payload(subscription)})
    qs = TenantSubscription.objects.select_related("tenant").order_by("expires_at")
    status = request.GET.get("status", "all")
    plan = request.GET.get("plan")
    search = str(request.GET.get("search") or "").lower()
    now = timezone.now()
    if status == "expired":
        qs = qs.filter(expires_at__lt=now)
    elif status == "expiring_soon":
        qs = qs.filter(expires_at__gte=now, expires_at__lte=now + timedelta(days=7))
    elif status == "active":
        qs = qs.filter(expires_at__gte=now)
    if plan and plan != "all":
        qs = qs.filter(plan=plan)
    items = [subscription_payload(item) for item in qs]
    if search:
        items = [item for item in items if search in item.get("tenant_name", "").lower() or search in item.get("tenant_email", "").lower()]
    return ok(paginate_items(request, items))


@csrf_exempt
@api_view(["GET", "POST"])
@admin_required
def admin_subscription_payments(request, subscription_id):
    subscription = TenantSubscription.objects.select_related("tenant").filter(pk=subscription_id).first()
    if not subscription:
        return err("Subscription not found", 404)
    if method(request, "GET"):
        return ok([payment.as_dict() for payment in subscription.payments.order_by("-paid_at")])
    payment = record_subscription_payment(subscription, body(request), request.admin.get("email"))
    write_audit_log(request.admin["adminId"], request.admin["email"], "RECORD_SUBSCRIPTION_PAYMENT", str(subscription.pk), "subscription", request, {"payment_id": payment.pk})
    return ok({"message": "Payment recorded", "payment": payment.as_dict(), "subscription": subscription_payload(subscription)})


@csrf_exempt
@api_view(["GET", "PATCH", "POST"])
@admin_required
def admin_tenant_subscription(request, tenant_id):
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if not tenant:
        return err("Tenant not found", 404)
    subscription = ensure_subscription(tenant)
    if method(request, "GET"):
        return ok(subscription_payload(subscription, include_payments=True))
    if method(request, "PATCH"):
        data = body(request)
        for field in ["plan", "amount", "expires_at", "auto_renew", "notes"]:
            if field in data:
                value = data[field]
                if field == "expires_at":
                    value = parse_date(value)
                setattr(subscription, field, value)
        subscription.save()
        write_audit_log(request.admin["adminId"], request.admin["email"], "UPDATE_TENANT_SUBSCRIPTION", tenant_id, "tenant", request)
        return ok({"message": "Subscription updated", "subscription": subscription_payload(subscription, include_payments=True)})
    payment = record_subscription_payment(subscription, body(request), request.admin.get("email"))
    write_audit_log(request.admin["adminId"], request.admin["email"], "RECORD_TENANT_SUBSCRIPTION_PAYMENT", tenant_id, "tenant", request, {"payment_id": payment.pk})
    return ok({"message": "Payment recorded", "payment": payment.as_dict(), "subscription": subscription_payload(subscription, include_payments=True)})


@csrf_exempt
@api_view(["POST"])
@admin_required
def admin_subscription_remind(request, tenant_id):
    write_audit_log(request.admin["adminId"], request.admin["email"], "SEND_SUBSCRIPTION_REMINDER", tenant_id, "tenant", request)
    return ok({"message": "Reminder queued"})


@csrf_exempt
@api_view(["POST"])
@admin_required
def admin_mikrotik_test(request, tenant_id):
    tenant = ref(f"tenants/{tenant_id}").get()
    if not tenant:
        return err("Tenant not found", 404)
    try:
        profiles = router_items({"id": tenant_id, **tenant}, "ppp", "profile")
        return ok({"success": True, "error": None, "routers_count": len(profiles), "profile_count": len(profiles)})
    except Exception as exc:
        return ok({"success": False, "error": str(exc), "routers_count": 0}, 400)


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_system_migrations(request):
    out = StringIO()
    call_command("showmigrations", stdout=out)
    return ok({"migrations": out.getvalue().splitlines()})


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_system(request):
    return ok({"health": health_payload(), "database": settings.DATABASES["default"]["ENGINE"], "rate_limits": SimpleRateLimitMiddleware.RULES if False else {}})


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_legacy_stats_unreachable(request):
    tenants = list_children("tenants")
    today = iso_now()[:10]
    total_customers = 0
    payments_today = 0
    for tenant in tenants:
        total_customers += len(list_children(f"tenants/{tenant['id']}/customers"))
        for payment in list_children(f"tenants/{tenant['id']}/payments"):
            if payment.get("paid_at") and str(payment["paid_at"])[:10] == today:
                payments_today += float(payment.get("amount") or 0)
    return ok({"totalTenants": len(tenants), "activeTenants": len([t for t in tenants if t.get("status") != "suspended"]), "suspendedTenants": len([t for t in tenants if t.get("status") == "suspended"]), "totalCustomers": total_customers, "paymentsToday": payments_today, "systemHealth": "healthy"})


@csrf_exempt
@api_view(["GET"])
@admin_required
def admin_audit_logs(request):
    logs = sorted(list_children("admin_audit_logs"), key=lambda item: str(item.get("timestamp")), reverse=True)[:100]
    write_audit_log(request.admin["adminId"], request.admin["email"], "VIEW_AUDIT_LOGS", target_type="admin", request=request, metadata={"count": len(logs)})
    return ok(logs)


@csrf_exempt
@api_view(["GET", "PATCH"])
@admin_required
def admin_site(request):
    if method(request, "GET"):
        return ok(ref("site_settings").get() or {})
    data = body(request)
    allowed = ["brand_name", "headline", "subheadline", "about", "phone", "email", "location", "address", "cta_label", "cta_url"]
    updates = {field: data[field] for field in allowed if field in data}
    ref("site_settings").update({**updates, "updated_at": iso_now(), "updated_by": request.admin["adminId"]})
    write_audit_log(request.admin["adminId"], request.admin["email"], "UPDATE_SITE", target_type="site", request=request, metadata={"updated_fields": list(updates)})
    return ok({"message": "Site settings updated"})


@csrf_exempt
@api_view(["GET", "PATCH", "POST"])
@admin_required
def admin_users(request, tenant_id=None, customer_id=None, action=None):
    if method(request, "GET"):
        users = []
        for tenant in list_children("tenants"):
            for customer in list_children(f"tenants/{tenant['id']}/customers"):
                users.append({**customer, "tenant_id": tenant["id"], "tenant_name": tenant.get("business_name")})
        return ok(users)
    tenant = {"id": tenant_id, **(ref(f"tenants/{tenant_id}").get() or {})}
    customer = ref(f"tenants/{tenant_id}/customers/{customer_id}").get()
    if not tenant or not customer:
        return ok({"error": "Tenant or user not found"}, 404)
    if method(request, "PATCH"):
        data = body(request)
        allowed = ["name", "phone", "username", "package", "status", "expiry_date", "auto_reconnect"]
        updates = {field: data[field] for field in allowed if field in data}
        ref(f"tenants/{tenant_id}/customers/{customer_id}").update(updates)
        write_audit_log(request.admin["adminId"], request.admin["email"], "UPDATE_USER", customer_id, "customer", request, {"tenantId": tenant_id, "updated_fields": list(updates)})
        return ok({"message": "User updated"})
    if action == "reconnect":
        set_customer_enabled(tenant, customer.get("username"), customer.get("service_type", "hotspot"), True)
        return ok({"message": "User reconnected"})
    if action == "disable":
        set_customer_enabled(tenant, customer.get("username"), customer.get("service_type", "hotspot"), False)
        ref(f"tenants/{tenant_id}/customers/{customer_id}").update({"status": "inactive"})
        return ok({"message": "User disabled"})
    return ok({"message": "Method not allowed"}, 405)
