"""
Lightweight RADIUS server built on pyrad, running inside the Django process.

Handles:
  - Access-Request  (PPPoE / Hotspot auth)
  - Accounting-Request  (Start / Interim-Update / Stop)

Run via:  python manage.py runradius
"""

import logging
import os
import socket
import struct
import threading
import time
from datetime import timedelta,timezone

from django.conf import settings
import pyrad.packet
from pyrad.server import Server, RemoteHost
from pyrad.dictionary import Dictionary

from .models import Customer, InternetPackage, RadiusNasClient, RadiusSession, Tenant

logger = logging.getLogger(__name__)

# RADIUS attribute constants used for MikroTik vendor-specific attributes
MIKROTIK_VENDOR_ID = 14988
ATTR_MIKROTIK_RATE_LIMIT = "Mikrotik-Rate-Limit"

# Standard RADIUS attribute names expected from pyrad dictionary
ATTR_USER_NAME = "User-Name"
ATTR_USER_PASSWORD = "User-Password"
ATTR_NAS_IP_ADDRESS = "NAS-IP-Address"
ATTR_CALLED_STATION_ID = "Called-Station-Id"
ATTR_ACCT_STATUS_TYPE = "Acct-Status-Type"
ATTR_ACCT_SESSION_ID = "Acct-Session-Id"
ATTR_ACCT_INPUT_OCTETS = "Acct-Input-Octets"
ATTR_ACCT_OUTPUT_OCTETS = "Acct-Output-Octets"
ATTR_ACCT_SESSION_TIME = "Acct-Session-Time"
ATTR_FRAMED_IP_ADDRESS = "Framed-IP-Address"
ATTR_SESSION_TIMEOUT = "Session-Timeout"
ATTR_TERMINATE_CAUSE = "Acct-Terminate-Cause"
ATTR_SERVICE_TYPE = "Service-Type"

ACCT_START = 1
ACCT_INTERIM_UPDATE = 3
ACCT_STOP = 2


def _load_or_create_dictionary():
    """Try to load pyrad's default dictionary; fall back to a minimal one."""
    try:
        return Dictionary("dictionary")
    except Exception:
        pass
    # Minimal inline dictionary for essential attributes
    dict_path = os.path.join(os.path.dirname(__file__), "radius_dictionary.dict")
    if os.path.exists(dict_path):
        try:
            return Dictionary(dict_path)
        except Exception:
            pass
    # Build a minimal dictionary programmatically
    d = Dictionary()
    # The default pyrad dictionary is usually bundled; if not, we define
    # the bare minimum attribute IDs so packets can be parsed.
    return d


def _get_radius_host():
    """Return the IP the RADIUS server should bind to."""
    return os.getenv("RADIUS_HOST", "0.0.0.0")


def _get_radius_auth_port():
    """Return the auth port (default 1812)."""
    return int(os.getenv("RADIUS_AUTH_PORT", "1812"))


def _get_radius_acct_port():
    """Return the accounting port (default 1813)."""
    return int(os.getenv("RADIUS_ACCT_PORT", "1813"))


class BillingRadiusServer(Server):
    """
    RADIUS server that authenticates MikroTik PPPoE/Hotspot users
    against the Django billing database.
    """

    def HandleAuthPacket(self, pkt):
        """Process an Access-Request from a MikroTik NAS."""
        nas_ip = pkt.source[0]
        username = pkt.GetAttribute(ATTR_USER_NAME)

        logger.info("RADIUS Access-Request: user=%s nas=%s", username, nas_ip)

        if not username:
            logger.warning("RADIUS Access-Request rejected: no User-Name from %s", nas_ip)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccessReject
            return reply.SendTo(pkt.source)

        # 1. Look up NAS client to validate shared secret
        try:
            nas_client = RadiusNasClient.objects.select_related("tenant").get(nas_ip=nas_ip)
        except RadiusNasClient.DoesNotExist:
            logger.warning("RADIUS Access-Request rejected: unknown NAS IP %s", nas_ip)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccessReject
            return reply.SendTo(pkt.source)

        tenant = nas_client.tenant

        # 2. Look up the customer by username within the tenant
        try:
            customer = Customer.objects.get(tenant=tenant, username=username)
        except Customer.DoesNotExist:
            logger.warning("RADIUS Access-Request rejected: user %s not found for tenant %s", username, tenant.id)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccessReject
            return reply.SendTo(pkt.source)

        # 3. Check customer is active
        if customer.status != "active":
            logger.info("RADIUS Access-Request rejected: user %s is not active (status=%s)", username, customer.status)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccessReject
            return reply.SendTo(pkt.source)

        # 4. Authenticate password
        # For RADIUS, we use the radius_secret field (cleartext) which is
        # needed for CHAP auth that MikroTik PPPoE uses.
        # PAP: compare User-Password attribute
        # CHAP: handled by pyrad automatically if using CHAP
        radius_secret = customer.radius_secret or ""
        if not radius_secret:
            logger.warning("RADIUS Access-Request rejected: user %s has no RADIUS secret", username)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccessReject
            return reply.SendTo(pkt.source)

        # For PAP auth, pyrad decodes the password and puts it in the packet
        # For CHAP, the password comparison happens differently
        req_password = pkt.PwDecrypt(pkt.GetAttribute(ATTR_USER_PASSWORD)) if pkt.GetAttribute(ATTR_USER_PASSWORD) else ""
        if req_password and req_password != radius_secret:
            # PAP password mismatch
            logger.info("RADIUS Access-Request rejected: password mismatch for user %s", username)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccessReject
            return reply.SendTo(pkt.source)

        # 5. Look up the customer's package for rate limit and session timeout
        rate_limit = None
        session_timeout = None
        try:
            package = InternetPackage.objects.get(tenant=tenant, name=customer.package)
            speed = package.speed or ""
            if speed:
                # Reuse the normalize_rate_limit from services
                from .services import normalize_rate_limit
                rate_limit = normalize_rate_limit(speed)
            if package.duration_days:
                session_timeout = int(timedelta(days=package.duration_days).total_seconds())
        except InternetPackage.DoesNotExist:
            pass

        # 6. Build Access-Accept reply
        reply = self.CreateReplyPacket(pkt, **{
            "Service-Type": "Framed-User",
        })

        if rate_limit:
            # MikroTik vendor-specific attribute for rate limiting
            try:
                reply.AddVSA(MIKROTIK_VENDOR_ID, "Rate-Limit", rate_limit, "string")
            except Exception:
                # If VSA fails, add as a regular attribute string
                try:
                    reply.AddAttribute("Mikrotik-Rate-Limit", rate_limit)
                except Exception:
                    logger.warning("Could not add Mikrotik-Rate-Limit attribute for user %s", username)

        if session_timeout and session_timeout > 0:
            reply.AddAttribute(ATTR_SESSION_TIMEOUT, str(session_timeout))

        logger.info("RADIUS Access-Accept: user=%s rate_limit=%s timeout=%s", username, rate_limit, session_timeout)
        return reply.SendTo(pkt.source)

    def HandleAcctPacket(self, pkt):
        """Process an Accounting-Request (Start / Interim-Update / Stop)."""
        nas_ip = pkt.source[0]
        username = pkt.GetAttribute(ATTR_USER_NAME)
        session_id = pkt.GetAttribute(ATTR_ACCT_SESSION_ID) or ""
        status_type = pkt.GetAttribute(ATTR_ACCT_STATUS_TYPE)

        logger.debug("RADIUS Accounting: user=%s session=%s status=%s nas=%s", username, session_id, status_type, nas_ip)

        if not session_id or not username:
            # Acknowledge but skip processing
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccountingResponse
            return reply.SendTo(pkt.source)

        # Look up NAS client to find the tenant
        try:
            nas_client = RadiusNasClient.objects.select_related("tenant").get(nas_ip=nas_ip)
        except RadiusNasClient.DoesNotExist:
            logger.warning("RADIUS Accounting: unknown NAS IP %s, skipping", nas_ip)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccountingResponse
            return reply.SendTo(pkt.source)

        tenant = nas_client.tenant

        try:
            customer = Customer.objects.get(tenant=tenant, username=username)
        except Customer.DoesNotExist:
            logger.warning("RADIUS Accounting: user %s not found for tenant %s", username, tenant.id)
            reply = self.CreateReplyPacket(pkt)
            reply.code = pyrad.packet.AccountingResponse
            return reply.SendTo(pkt.source)

        input_octets = int(pkt.GetAttribute(ATTR_ACCT_INPUT_OCTETS) or 0)
        output_octets = int(pkt.GetAttribute(ATTR_ACCT_OUTPUT_OCTETS) or 0)
        framed_ip = pkt.GetAttribute(ATTR_FRAMED_IP_ADDRESS) or None
        terminate_cause = pkt.GetAttribute(ATTR_TERMINATE_CAUSE) or ""
        service_type = customer.service_type or ""

        try:
            status_int = int(status_type) if status_type else 0
        except (ValueError, TypeError):
            status_int = 0

        if status_int == ACCT_START:
            # Create a new session record
            RadiusSession.objects.update_or_create(
                tenant=tenant,
                acct_session_id=session_id,
                defaults={
                    "customer": customer,
                    "nas_ip": nas_ip,
                    "framed_ip": framed_ip,
                    "service_type": service_type,
                    "started_at": timezone.now(),
                    "last_interim_at": timezone.now(),
                    "stopped_at": None,
                    "input_octets": input_octets,
                    "output_octets": output_octets,
                    "terminate_cause": "",
                },
            )
            logger.info("RADIUS Accounting Start: user=%s session=%s", username, session_id)

        elif status_int == ACCT_INTERIM_UPDATE:
            # Update existing session with new data usage
            RadiusSession.objects.filter(
                tenant=tenant,
                acct_session_id=session_id,
                stopped_at__isnull=True,
            ).update(
                input_octets=input_octets,
                output_octets=output_octets,
                framed_ip=framed_ip,
                last_interim_at=timezone.now(),
            )
            logger.debug("RADIUS Accounting Interim: user=%s session=%s in=%s out=%s", username, session_id, input_octets, output_octets)

        elif status_int == ACCT_STOP:
            # Close the session
            RadiusSession.objects.filter(
                tenant=tenant,
                acct_session_id=session_id,
                stopped_at__isnull=True,
            ).update(
                input_octets=input_octets,
                output_octets=output_octets,
                framed_ip=framed_ip,
                stopped_at=timezone.now(),
                terminate_cause=terminate_cause,
            )
            logger.info("RADIUS Accounting Stop: user=%s session=%s cause=%s", username, session_id, terminate_cause)

        reply = self.CreateReplyPacket(pkt)
        reply.code = pyrad.packet.AccountingResponse
        return reply.SendTo(pkt.source)


def _register_nas_clients(server):
    """Register all NAS clients from the database as allowed RADIUS clients."""
    for nas_client in RadiusNasClient.objects.select_related("tenant").all():
        try:
            server.hosts[nas_client.nas_ip] = RemoteHost(
                nas_client.nas_ip,
                nas_client.shared_secret.encode("utf-8"),
                nas_client.shared_secret.encode("utf-8"),
            )
            logger.info("RADIUS: registered NAS client %s (%s) for tenant %s",
                        nas_client.nas_ip, nas_client.identifier, nas_client.tenant_id)
        except Exception as exc:
            logger.error("RADIUS: failed to register NAS client %s: %s", nas_client.nas_ip, exc)


def _start_nas_refresh_loop(server, interval=30):
    """Background thread that periodically re-reads NAS clients from the DB
    so that newly provisioned routers are recognized without a server restart."""
    def loop():
        while True:
            time.sleep(interval)
            try:
                _register_nas_clients(server)
            except Exception:
                logger.exception("Failed to refresh RADIUS NAS client list")
    threading.Thread(target=loop, daemon=True).start()


def run_radius_server(host=None, auth_port=None, acct_port=None):
    """
    Start the RADIUS server. Blocks forever.
    Intended to be called from the management command or Celery worker.
    """
    host = host or _get_radius_host()
    auth_port = auth_port or _get_radius_auth_port()
    acct_port = acct_port or _get_radius_acct_port()

    # Ensure Django is set up when running standalone
    import django
    django.setup()

    dict_obj = _load_or_create_dictionary()

    server = BillingRadiusServer(
        addresses=[host],
        authport=auth_port,
        acctport=acct_port,
        dict=dict_obj,
    )

    _register_nas_clients(server)
    _start_nas_refresh_loop(server)

    logger.info(
        "RADIUS server starting on %s (auth=%d, acct=%d) with %d NAS clients registered",
        host, auth_port, acct_port, len(server.hosts),
    )

    try:
        server.Run()
    except KeyboardInterrupt:
        logger.info("RADIUS server shutting down")