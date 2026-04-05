"""Shared API dependencies."""

from fastapi import Header
from starlette.requests import Request

from app.core.config import settings
from app.core.errors import HelioraError


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    """Enforce idempotency key for side-effect endpoints."""
    if not idempotency_key:
        raise HelioraError(
            code="INVALID_ARGUMENT",
            status_code=400,
            message="Idempotency-Key header is required",
        )
    return idempotency_key


def _is_loopback_request(request: Request) -> bool:
    """Return true when request source is local loopback."""
    client = request.client
    if client is None:
        return False

    host = client.host.strip().lower()
    if host.startswith("::ffff:"):
        host = host.removeprefix("::ffff:")

    return host in LOOPBACK_HOSTS


def enforce_security_mode(request: Request | None = None) -> None:
    """Guard trusted local max mode with explicit ack and loopback checks."""
    if settings.security_policy_mode == "trusted_local_max" and not settings.local_max_privilege_ack:
        raise HelioraError(
            code="LOCAL_MAX_PRIVILEGE_ACK_REQUIRED",
            status_code=403,
            message="trusted_local_max requires LOCAL_MAX_PRIVILEGE_ACK=true",
        )

    if (
        settings.security_policy_mode == "trusted_local_max"
        and settings.local_max_privilege_loopback_only
        and request is not None
        and not _is_loopback_request(request)
    ):
        raise HelioraError(
            code="SECURITY_MODE_RESTRICTED",
            status_code=403,
            message="trusted_local_max is restricted to local loopback requests",
            details={"client_host": request.client.host if request.client else None},
        )
