from functools import wraps

from rest_framework.response import Response

from .models import Tenant
from .services import decode_admin_token, decode_tenant_token, ref


def bearer_token(request):
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    parts = header.split()
    return parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None


def tenant_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        token = bearer_token(request)
        if not token:
            return Response({"message": "No token provided"}, status=401)
        try:
            decoded = decode_tenant_token(token)
            tenant = Tenant.objects.filter(pk=decoded["id"]).first()
            if not tenant:
                return Response({"message": "Tenant not found"}, status=401)
            if tenant.status != "active":
                return Response({"message": "Your account is pending admin activation."}, status=403)
            request.tenant = tenant.as_dict(include_id=True)
            request.tenant["password"] = tenant.password
        except Exception:
            return Response({"message": "Invalid token"}, status=401)
        return view(request, *args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        token = bearer_token(request)
        if not token:
            return Response({"error": "Admin token required"}, status=401)
        try:
            decoded = decode_admin_token(token)
            if decoded.get("role") != "admin":
                return Response({"error": "Insufficient privileges"}, status=403)
            admin_data = ref(f"admins/{decoded['adminId']}").get()
            if not admin_data or not admin_data.get("is_active"):
                return Response({"error": "Admin account inactive"}, status=403)
            request.admin = {
                "adminId": decoded["adminId"],
                "email": decoded.get("email"),
                "name": decoded.get("name"),
                "role": decoded.get("role"),
            }
        except Exception as exc:
            if exc.__class__.__name__ == "ExpiredSignatureError":
                return Response({"error": "Admin session expired"}, status=401)
            return Response({"error": "Invalid admin token"}, status=403)
        return view(request, *args, **kwargs)

    return wrapped
