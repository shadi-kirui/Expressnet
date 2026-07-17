"""
RADIUS CoA (Change of Authorization) / Disconnect-Message service.

Sends Disconnect-Request to a MikroTik NAS to immediately terminate
a user's session. Used instead of the RouterOS API path when
tenant.radius_enabled is True.
"""

import logging

from django.utils import timezone
import pyrad.client
import pyrad.packet

from .models import RadiusNasClient

logger = logging.getLogger(__name__)

# RouterOS default CoA/DM port
COA_PORT = 3799


def radius_disconnect_customer(tenant_obj, customer_username):
    """
    Send a RADIUS Disconnect-Request to the NAS for a given customer.

    Args:
        tenant_obj: A Tenant model instance (not a dict).
        customer_username: The customer's username to disconnect.

    Returns:
        dict with "success" bool and "message" string.
    """
    try:
        nas = RadiusNasClient.objects.filter(tenant=tenant_obj).first()
    except Exception as exc:
        return {"success": False, "message": f"Database error looking up NAS client: {exc}"}

    if not nas:
        return {"success": False, "message": "No RADIUS NAS client configured for this tenant. Run the provisioning script first."}

    try:
        client = pyrad.client.Client(
            server=nas.nas_ip,
            authport=COA_PORT,
            secret=nas.shared_secret.encode("utf-8"),
            dict=None,
        )
        client.timeout = 5
        client.retries = 2

        # Create a Disconnect-Request packet (RFC 5176)
        # pyrad doesn't have a built-in DisconnectRequest, so we use
        # the Status-Server (43) code as a base and override to
        # Disconnect-Request (40). Alternatively, use raw packet construction.
        # MikroTik uses port 3799 for CoA/DM and accepts standard
        # Disconnect-Request packets.

        # Build the packet manually
        req = pyrad.packet.AuthPacket(
            code=pyrad.packet.DisconnectRequest,
            secret=nas.shared_secret.encode("utf-8"),
            dict=None,
            authenticator=None,
        )
        req.AddAttribute("User-Name", customer_username)

        reply = client.SendPacket(req)

        if reply.code == pyrad.packet.DisconnectACK:
            logger.info("RADIUS Disconnect-ACK for user %s on NAS %s", customer_username, nas.nas_ip)
            return {"success": True, "message": f"Disconnect-ACK received from {nas.nas_ip}"}
        elif reply.code == pyrad.packet.DisconnectNAK:
            reason = reply.GetAttribute("Error-Cause") or "unknown"
            logger.warning("RADIUS Disconnect-NAK for user %s on NAS %s: %s", customer_username, nas.nas_ip, reason)
            return {"success": False, "message": f"Disconnect-NAK from {nas.nas_ip}: {reason}"}
        else:
            logger.warning("RADIUS unexpected reply code %d for user %s", reply.code, customer_username)
            return {"success": False, "message": f"Unexpected RADIUS reply code {reply.code}"}

    except TimeoutError:
        logger.warning("RADIUS Disconnect-Request timed out for user %s on NAS %s", customer_username, nas.nas_ip)
        return {"success": False, "message": f"Disconnect request timed out (NAS {nas.nas_ip} unreachable on port {COA_PORT})"}
    except OSError as exc:
        logger.warning("RADIUS Disconnect-Request failed for user %s: %s", customer_username, exc)
        return {"success": False, "message": f"Network error sending disconnect: {exc}"}
    except Exception as exc:
        logger.error("RADIUS Disconnect-Request error for user %s: %s", customer_username, exc)
        return {"success": False, "message": f"RADIUS error: {exc}"}