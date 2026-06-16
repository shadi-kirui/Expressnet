import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import firebase_admin
import jwt
import requests
from firebase_admin import credentials, db as firebase_db

from .models import AdminAuditLog, AdminUser, Customer, InternetPackage, Payment, SiteSettings, Tenant, Ticket


BASE_DIR = Path(__file__).resolve().parent.parent


class PaymentProviderError(RuntimeError):
    def __init__(self, public_message, detail=None, status_code=502):
        super().__init__(detail or public_message)
        self.public_message = public_message
        self.detail = detail or public_message
        self.status_code = status_code


def utcnow():
    return datetime.now(timezone.utc)


def iso_now():
    return utcnow().isoformat().replace("+00:00", "Z")


def require_secret(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    if len(value) < 32:
        raise RuntimeError(f"{name} must be at least 32 characters")
    return value


def firebase_backup_configured():
    if os.getenv("FIREBASE_BACKUP_ENABLED", "true").lower() in {"0", "false", "no", "off"}:
        return False
    return bool(os.getenv("FIREBASE_DATABASE_URL") and os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))


def init_firebase_backup():
    if not firebase_backup_configured():
        return False
    if firebase_admin._apps:
        return True

    if os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
        service_account = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))
        if service_account.get("private_key"):
            service_account["private_key"] = service_account["private_key"].replace("\\n", "\n")
    else:
        candidates = [BASE_DIR / "serviceAccount.json"]
        candidates += list(BASE_DIR.glob("*firebase-adminsdk*.json"))
        service_path = next((path for path in candidates if path.exists()), None)
        if not service_path:
            return False
        service_account = json.loads(service_path.read_text(encoding="utf-8"))

    database_url = os.getenv("FIREBASE_DATABASE_URL", "").strip().strip("\"'").rstrip(" ,/\t\r\n")
    if not database_url:
        return False

    firebase_admin.initialize_app(credentials.Certificate(service_account), {"databaseURL": database_url})
    return True


def firebase_backup_ref(path):
    if not init_firebase_backup():
        return None
    return firebase_db.reference(path)


def backup_set(path, data):
    backup = firebase_backup_ref(path)
    if backup is not None:
        backup.set(data)


def backup_update(path, data):
    backup = firebase_backup_ref(path)
    if backup is not None:
        backup.update(data)


def backup_delete(path):
    backup = firebase_backup_ref(path)
    if backup is not None:
        backup.delete()


def model_dict(instance, include_id=True, exclude=None):
    return instance.as_dict(include_id=include_id, exclude=exclude) if hasattr(instance, "as_dict") else {}


def model_update(instance, data):
    instance.apply_data(data)
    instance.save()
    return instance


class OrmRef:
    def __init__(self, path=""):
        self.parts = [part for part in str(path).strip("/").split("/") if part]
        self.key = None

    def _tenant(self, tenant_id):
        return Tenant.objects.get(pk=tenant_id)

    def _package(self, tenant_id, package_id):
        return InternetPackage.objects.get(tenant_id=tenant_id, pk=package_id)

    def _customer(self, tenant_id, customer_id):
        return Customer.objects.get(tenant_id=tenant_id, pk=customer_id)

    def _payment(self, tenant_id, payment_id):
        return Payment.objects.get(tenant_id=tenant_id, pk=payment_id)

    def _ticket(self, tenant_id, ticket_id):
        return Ticket.objects.get(tenant_id=tenant_id, pk=ticket_id)

    def _site_settings(self):
        return SiteSettings.objects.order_by("pk").first()

    def _resolve_instance(self):
        parts = self.parts
        if len(parts) == 2 and parts[0] == "tenants":
            return self._tenant(parts[1])
        if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "packages":
            return self._package(parts[1], parts[3])
        if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "customers":
            return self._customer(parts[1], parts[3])
        if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "payments":
            return self._payment(parts[1], parts[3])
        if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "tickets":
            return self._ticket(parts[1], parts[3])
        if len(parts) == 2 and parts[0] == "admins":
            return AdminUser.objects.get(pk=parts[1])
        if parts == ["site_settings"]:
            return self._site_settings()
        raise KeyError(f"Unsupported relational ref path: {'/'.join(parts)}")

    def get(self):
        parts = self.parts
        try:
            if parts == ["tenants"]:
                return {str(item.pk): model_dict(item, include_id=False) for item in Tenant.objects.all()}
            if len(parts) == 2 and parts[0] == "tenants":
                return model_dict(self._tenant(parts[1]), include_id=False)
            if len(parts) == 3 and parts[0] == "tenants" and parts[2] == "packages":
                return {str(item.pk): model_dict(item, include_id=False) for item in InternetPackage.objects.filter(tenant_id=parts[1])}
            if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "packages":
                return model_dict(self._package(parts[1], parts[3]), include_id=False)
            if len(parts) == 3 and parts[0] == "tenants" and parts[2] == "customers":
                return {str(item.pk): model_dict(item, include_id=False, exclude={"password"}) for item in Customer.objects.filter(tenant_id=parts[1])}
            if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "customers":
                return model_dict(self._customer(parts[1], parts[3]), include_id=False)
            if len(parts) == 3 and parts[0] == "tenants" and parts[2] == "payments":
                return {str(item.pk): model_dict(item, include_id=False) for item in Payment.objects.filter(tenant_id=parts[1])}
            if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "payments":
                return model_dict(self._payment(parts[1], parts[3]), include_id=False)
            if len(parts) == 3 and parts[0] == "tenants" and parts[2] == "tickets":
                return {str(item.pk): model_dict(item, include_id=False) for item in Ticket.objects.filter(tenant_id=parts[1])}
            if len(parts) == 4 and parts[0] == "tenants" and parts[2] == "tickets":
                return model_dict(self._ticket(parts[1], parts[3]), include_id=False)
            if parts == ["admins"]:
                return {str(item.pk): model_dict(item, include_id=False) for item in AdminUser.objects.all()}
            if len(parts) == 2 and parts[0] == "admins":
                return model_dict(AdminUser.objects.get(pk=parts[1]), include_id=False)
            if parts == ["site_settings"]:
                settings = self._site_settings()
                return model_dict(settings, include_id=False) if settings else {}
            if parts == ["admin_audit_logs"]:
                return {str(item.pk): item.as_dict(include_id=False) for item in AdminAuditLog.objects.all()}
        except (Tenant.DoesNotExist, InternetPackage.DoesNotExist, Customer.DoesNotExist, Payment.DoesNotExist, Ticket.DoesNotExist, AdminUser.DoesNotExist):
            return None
        raise KeyError(f"Unsupported relational ref path: {'/'.join(parts)}")

    def push(self, data):
        parts = self.parts
        if parts == ["tenants"]:
            instance = Tenant()
        elif len(parts) == 3 and parts[0] == "tenants" and parts[2] == "packages":
            instance = InternetPackage(tenant_id=parts[1])
        elif len(parts) == 3 and parts[0] == "tenants" and parts[2] == "customers":
            instance = Customer(tenant_id=parts[1])
        elif len(parts) == 3 and parts[0] == "tenants" and parts[2] == "payments":
            instance = Payment(tenant_id=parts[1])
        elif len(parts) == 3 and parts[0] == "tenants" and parts[2] == "tickets":
            instance = Ticket(tenant_id=parts[1])
        elif parts == ["admins"]:
            instance = AdminUser()
        elif parts == ["admin_audit_logs"]:
            instance = AdminAuditLog()
        else:
            raise KeyError(f"Unsupported relational push path: {'/'.join(parts)}")

        if hasattr(instance, "apply_data"):
            instance.apply_data(dict(data or {}))
        else:
            for key, value in (data or {}).items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
        instance.save()
        result = OrmPushResult(instance, self._child_backup_path(instance))
        result.backup_set()
        return result

    def update(self, data):
        parts = self.parts
        if parts == ["site_settings"]:
            instance = self._site_settings() or SiteSettings()
            model_update(instance, dict(data or {}))
            backup_update("site_settings", dict(data or {}))
            return
        instance = self._resolve_instance()
        if not instance:
            return
        model_update(instance, dict(data or {}))
        backup_update(self._backup_path(), dict(data or {}))

    def delete(self):
        instance = self._resolve_instance()
        if instance:
            instance.delete()
            backup_delete(self._backup_path())

    def _backup_path(self):
        return "/".join(self.parts)

    def _child_backup_path(self, instance):
        parts = list(self.parts)
        if parts == ["tenants"]:
            return f"tenants/{instance.pk}"
        if len(parts) == 3 and parts[0] == "tenants" and parts[2] in {"packages", "customers", "payments", "tickets"}:
            return f"{'/'.join(parts)}/{instance.pk}"
        if parts == ["admins"]:
            return f"admins/{instance.pk}"
        if parts == ["admin_audit_logs"]:
            return f"admin_audit_logs/{instance.pk}"
        return f"{'/'.join(parts)}/{instance.pk}"


class OrmPushResult:
    def __init__(self, instance, backup_path):
        self.instance = instance
        self.key = str(instance.pk)
        self.backup_path = backup_path

    def update(self, data):
        model_update(self.instance, dict(data or {}))
        backup_update(self.backup_path, dict(data or {}))

    def backup_set(self):
        if hasattr(self.instance, "as_dict"):
            backup_set(self.backup_path, self.instance.as_dict(include_id=False))
        else:
            backup_set(self.backup_path, {})


def ref(path=""):
    return OrmRef(path)


def list_children(path):
    value = ref(path).get() or {}
    if not isinstance(value, dict):
        return []
    return [{"id": key, **(item or {})} for key, item in value.items()]


def find_child_by_field(path, field, expected):
    expected = str(expected).lower().strip()
    for item in list_children(path):
        if str(item.get(field, "")).lower().strip() == expected:
            return item
    return None


def hash_password(password):
    return bcrypt.hashpw(str(password).encode(), bcrypt.gensalt(rounds=10)).decode()


def check_password(password, hashed):
    if not hashed:
        return False
    return bcrypt.checkpw(str(password).encode(), str(hashed).encode())


def tenant_token(tenant_id):
    return jwt.encode(
        {"id": tenant_id, "exp": utcnow() + timedelta(days=7)},
        require_secret("JWT_SECRET"),
        algorithm="HS256",
    )


def admin_token(admin_id, admin_data):
    return jwt.encode(
        {
            "adminId": admin_id,
            "email": admin_data.get("email"),
            "name": admin_data.get("name"),
            "role": "admin",
            "exp": utcnow() + timedelta(hours=4),
        },
        require_secret("ADMIN_JWT_SECRET"),
        algorithm="HS256",
    )


def decode_tenant_token(token):
    return jwt.decode(token, require_secret("JWT_SECRET"), algorithms=["HS256"])


def decode_admin_token(token):
    return jwt.decode(token, require_secret("ADMIN_JWT_SECRET"), algorithms=["HS256"])


def normalize_phone(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return f"254{digits[1:]}"
    if digits.startswith("7") and len(digits) == 9:
        return f"254{digits}"
    return digits


def get_public_base_url():
    configured = os.getenv("PUBLIC_APP_URL") or os.getenv("PAYSTACK_CALLBACK_BASE_URL")
    return (configured or "").rstrip("/")


def get_platform_paystack_secret():
    secret = os.getenv("PAYSTACK_SECRET_KEY")
    if secret and "replace_with" not in secret and not secret.strip().endswith("_secret_key"):
        return secret.strip()
    raise PaymentProviderError(
        "Payment is temporarily unavailable. Please contact support.",
        "PAYSTACK_SECRET_KEY is not configured",
        503,
    )


def get_paystack_secret(tenant=None):
    tenant_secret = (tenant or {}).get("paystack_secret_key")
    if tenant_secret and str(tenant_secret).strip() and "â€¢" not in str(tenant_secret) and "replace_with" not in str(tenant_secret):
        return str(tenant_secret).strip()
    return get_platform_paystack_secret()


def make_paystack_reference(tenant_id):
    return f"ps_{tenant_id}_{uuid.uuid4().hex[:24]}"


def paystack_amount(amount):
    return int(round(float(amount or 0) * 100))


def paystack_platform_percentage():
    try:
        return float(os.getenv("PAYSTACK_PLATFORM_PERCENTAGE", "1"))
    except ValueError:
        return 1.0


def create_paystack_subaccount(tenant, bank_code, account_number, business_number=None, percentage_charge=None):
    secret = get_platform_paystack_secret()
    payload = {
        "business_name": tenant.get("business_name") or tenant.get("email") or "Internet tenant",
        "bank_code": str(bank_code or "").strip(),
        "account_number": str(account_number or "").strip(),
        "percentage_charge": paystack_platform_percentage() if percentage_charge is None else float(percentage_charge),
        "description": f"ISP tenant settlement account for {tenant.get('business_name') or tenant.get('id')}",
        "primary_contact_name": tenant.get("owner_name") or tenant.get("business_name") or "",
        "primary_contact_email": tenant.get("email") or "",
        "primary_contact_phone": tenant.get("phone") or "",
    }
    if business_number:
        payload["metadata"] = {"business_number": business_number}

    if not payload["bank_code"] or not payload["account_number"]:
        raise PaymentProviderError("Bank code and account number are required to create a settlement account.", "Missing bank_code or account_number", 400)

    response = requests.post(
        "https://api.paystack.co/subaccount",
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise PaymentProviderError(
            "Could not create the tenant settlement account. Please verify the bank details.",
            f"Paystack subaccount creation failed {response.status_code}: {response.text[:500]}",
            502 if response.status_code not in {401, 403} else 503,
        ) from exc
    data = response.json()
    if not data.get("status"):
        raise PaymentProviderError("Could not create the tenant settlement account. Please verify the bank details.", data.get("message") or "Paystack rejected subaccount creation", 502)
    return data.get("data") or {}


def initiate_paystack_payment(tenant, payment_id, amount, email=None, phone=None, description=None, metadata=None):
    secret = get_platform_paystack_secret()
    subaccount_code = str((tenant or {}).get("paystack_subaccount_code") or "").strip()
    if not subaccount_code:
        raise PaymentProviderError(
            "Payment is not ready for this business. Please contact support.",
            "Tenant has no Paystack subaccount code",
            503,
        )
    reference = make_paystack_reference(tenant.get("id"))
    base_url = get_public_base_url()
    if not base_url:
        raise RuntimeError("PUBLIC_APP_URL or PAYSTACK_CALLBACK_BASE_URL is required for Paystack checkout")

    customer_email = str(email or "").strip()
    if not customer_email:
        digits = "".join(ch for ch in str(phone or "") if ch.isdigit()) or "customer"
        customer_email = f"{digits}@example.com"

    payload = {
        "amount": paystack_amount(amount),
        "email": customer_email,
        "currency": tenant.get("paystack_currency") or os.getenv("PAYSTACK_CURRENCY", "KES"),
        "reference": reference,
        "callback_url": f"{base_url}/api/paystack/callback",
        "metadata": {
            "tenant_id": tenant.get("id"),
            "payment_id": payment_id,
            "phone": phone,
            **(metadata or {}),
        },
    }
    if description:
        payload["metadata"]["description"] = description

    payload["subaccount"] = subaccount_code
    payload["bearer"] = tenant.get("paystack_bearer") or "subaccount"

    response = requests.post(
        "https://api.paystack.co/transaction/initialize",
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:500]
        public_message = "Payment gateway rejected the request. Please contact support."
        status_code = 502
        if response.status_code in {401, 403}:
            public_message = "Payment is temporarily unavailable. Please contact support."
            status_code = 503
        raise PaymentProviderError(public_message, f"Paystack initialize failed {response.status_code}: {detail}", status_code) from exc
    data = response.json()
    if not data.get("status"):
        raise PaymentProviderError("Payment gateway rejected the request. Please contact support.", data.get("message") or "Paystack rejected the transaction")
    result = data.get("data") or {}
    result.update({"reference": reference, "customer_email": customer_email, "currency": payload["currency"]})
    return result


def verify_paystack_transaction(tenant, reference):
    secret = get_platform_paystack_secret()
    response = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers={"Authorization": f"Bearer {secret}"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("status"):
        raise RuntimeError(data.get("message") or "Paystack verification failed")
    return data.get("data") or {}


def verify_paystack_signature(raw_body, signature, secret):
    if not signature or not secret:
        return False
    digest = hmac.new(str(secret).encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, str(signature))


def has_mikrotik_credentials(tenant):
    return bool(tenant.get("mikrotik_host") and tenant.get("mikrotik_user") and tenant.get("mikrotik_pass"))


def normalize_rate_limit(speed):
    value = str(speed or "").strip()
    if not value:
        return None
    if "/" in value:
        return "".join(value.split())
    amount = "".join(ch for ch in value if ch.isdigit() or ch == ".")
    unit = "".join(ch for ch in value if ch.isalpha()).lower() or "m"
    router_unit = "G" if unit.startswith("g") else "K" if unit.startswith("k") else "M"
    return f"{amount}{router_unit}/{amount}{router_unit}" if amount else value.replace(" ", "")


def router_connect(tenant):
    from librouteros import connect

    return connect(
        host=tenant.get("mikrotik_host"),
        username=tenant.get("mikrotik_user"),
        password=tenant.get("mikrotik_pass"),
        port=int(tenant.get("mikrotik_port") or 8728),
        timeout=8,
    )


def router_items(tenant, *path):
    if not has_mikrotik_credentials(tenant):
        return []
    api = router_connect(tenant)
    try:
        return list(api.path(*path).select())
    finally:
        api.close()


def router_first(tenant, *path):
    items = router_items(tenant, *path)
    return items[0] if items else {}


def router_update_item(tenant, path, item_id, fields):
    api = router_connect(tenant)
    try:
        return api.path(*path).update(**{".id": item_id, **fields})
    finally:
        api.close()


def router_add_item(tenant, path, fields):
    api = router_connect(tenant)
    try:
        return api.path(*path).add(**fields)
    finally:
        api.close()


def find_router_item(api, path, name):
    for item in api.path(*path).select():
        if item.get("name") == name:
            return item
    return None


def upsert_router_profile(tenant, path, name, speed):
    if not has_mikrotik_credentials(tenant):
        return None
    api = router_connect(tenant)
    try:
        router_path = api.path(*path)
        existing = find_router_item(api, path, name)
        fields = {"name": name}
        rate_limit = normalize_rate_limit(speed)
        if rate_limit:
            fields["rate-limit"] = rate_limit
        if existing and existing.get(".id"):
            router_path.update(**{".id": existing[".id"], **fields})
            return existing[".id"]
        return router_path.add(**fields)
    finally:
        api.close()


def create_ppp_profile(tenant, name, speed):
    return upsert_router_profile(tenant, ("ppp", "profile"), name, speed)


def create_hotspot_profile(tenant, name, speed):
    return upsert_router_profile(tenant, ("ip", "hotspot", "user", "profile"), name, speed)


def router_interface_status(tenant):
    resource = router_first(tenant, "system", "resource")
    routerboard = router_first(tenant, "system", "routerboard")
    interfaces = router_items(tenant, "interface")
    pppoe_servers = router_items(tenant, "interface", "pppoe-server", "server")
    hotspot_servers = router_items(tenant, "ip", "hotspot")
    ppp_profiles = router_items(tenant, "ppp", "profile")
    hotspot_profiles = router_items(tenant, "ip", "hotspot", "user", "profile")

    return {
        "device": {
            "board_name": resource.get("board-name") or routerboard.get("model"),
            "version": resource.get("version"),
            "uptime": resource.get("uptime"),
            "cpu_load": resource.get("cpu-load"),
            "free_memory": resource.get("free-memory"),
            "total_memory": resource.get("total-memory"),
            "architecture": resource.get("architecture-name"),
        },
        "interfaces": [
            {
                "id": item.get(".id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "running": item.get("running") in {True, "true", "yes"},
                "disabled": item.get("disabled") in {True, "true", "yes"},
                "mac_address": item.get("mac-address"),
                "comment": item.get("comment", ""),
                "mtu": item.get("mtu"),
            }
            for item in interfaces
        ],
        "pppoe_servers": [
            {
                "id": item.get(".id"),
                "name": item.get("service-name") or item.get("name"),
                "interface": item.get("interface"),
                "default_profile": item.get("default-profile"),
                "disabled": item.get("disabled") in {True, "true", "yes"},
            }
            for item in pppoe_servers
        ],
        "hotspot_servers": [
            {
                "id": item.get(".id"),
                "name": item.get("name"),
                "interface": item.get("interface"),
                "profile": item.get("profile"),
                "disabled": item.get("disabled") in {True, "true", "yes"},
            }
            for item in hotspot_servers
        ],
        "profiles": {
            "pppoe": [{"name": item.get("name"), "rate_limit": item.get("rate-limit")} for item in ppp_profiles],
            "hotspot": [{"name": item.get("name"), "rate_limit": item.get("rate-limit")} for item in hotspot_profiles],
        },
    }


def configure_router_port(tenant, interface_name, service_type, profile_name="default"):
    service_type = str(service_type or "").lower().strip()
    if service_type not in {"pppoe", "hotspot"}:
        raise ValueError("Port service must be either pppoe or hotspot")

    interfaces = router_items(tenant, "interface")
    interface = next((item for item in interfaces if item.get("name") == interface_name), None)
    if not interface or not interface.get(".id"):
        raise ValueError("Router interface not found")

    router_update_item(
        tenant,
        ("interface",),
        interface[".id"],
        {"comment": f"billing-saas:{service_type}:profile={profile_name or 'default'}"},
    )

    if service_type == "pppoe":
        servers = router_items(tenant, "interface", "pppoe-server", "server")
        existing = next((item for item in servers if item.get("interface") == interface_name), None)
        fields = {
            "service-name": f"billing-{interface_name}",
            "interface": interface_name,
            "default-profile": profile_name or "default",
            "one-session-per-host": "yes",
            "disabled": "no",
        }
        if existing and existing.get(".id"):
            router_update_item(tenant, ("interface", "pppoe-server", "server"), existing[".id"], fields)
            return {"updated": True, "service_type": service_type, "interface": interface_name}
        router_add_item(tenant, ("interface", "pppoe-server", "server"), fields)
        return {"created": True, "service_type": service_type, "interface": interface_name}

    servers = router_items(tenant, "ip", "hotspot")
    existing = next((item for item in servers if item.get("interface") == interface_name), None)
    fields = {
        "name": f"billing-hotspot-{interface_name}",
        "interface": interface_name,
        "profile": profile_name or "default",
        "disabled": "no",
    }
    if existing and existing.get(".id"):
        router_update_item(tenant, ("ip", "hotspot"), existing[".id"], fields)
        return {"updated": True, "service_type": service_type, "interface": interface_name}
    router_add_item(tenant, ("ip", "hotspot"), fields)
    return {"created": True, "service_type": service_type, "interface": interface_name}


def upsert_customer_access(tenant, customer, disabled=False):
    if not has_mikrotik_credentials(tenant):
        return None
    service_type = customer.get("service_type") or "pppoe"
    api = router_connect(tenant)
    try:
        path = ("ppp", "secret") if service_type == "pppoe" else ("ip", "hotspot", "user")
        router_path = api.path(*path)
        existing = find_router_item(api, path, customer.get("username"))
        fields = {
            "name": customer.get("username"),
            "password": customer.get("password"),
            "profile": customer.get("package_name") or customer.get("package"),
            "disabled": "yes" if disabled else "no",
        }
        if service_type == "pppoe":
            fields["service"] = "pppoe"
        if existing and existing.get(".id"):
            router_path.update(**{".id": existing[".id"], **fields})
            return existing[".id"]
        return router_path.add(**fields)
    finally:
        api.close()


def set_customer_enabled(tenant, username, service_type="hotspot", enabled=True):
    if not has_mikrotik_credentials(tenant):
        return None
    api = router_connect(tenant)
    try:
        path = ("ppp", "secret") if service_type == "pppoe" else ("ip", "hotspot", "user")
        existing = find_router_item(api, path, username)
        if not existing or not existing.get(".id"):
            return None
        return api.path(*path).update(**{".id": existing[".id"], "disabled": "no" if enabled else "yes"})
    finally:
        api.close()


def delete_router_customer(tenant, username, service_type="pppoe"):
    if not has_mikrotik_credentials(tenant) or not username:
        return None
    api = router_connect(tenant)
    try:
        path = ("ppp", "secret") if service_type == "pppoe" else ("ip", "hotspot", "user")
        existing = find_router_item(api, path, username)
        if not existing or not existing.get(".id"):
            return None
        return api.path(*path).remove(existing[".id"])
    finally:
        api.close()


def write_audit_log(admin_id=None, admin_email=None, action=None, target_id=None, target_type=None, request=None, metadata=None):
    ref("admin_audit_logs").push(
        {
            "admin_id": admin_id,
            "admin_email": admin_email,
            "action": action,
            "target_id": target_id,
            "target_type": target_type,
            "ip": request.META.get("REMOTE_ADDR") if request else None,
            "user_agent": request.META.get("HTTP_USER_AGENT") if request else None,
            "metadata": metadata or {},
        }
    )
