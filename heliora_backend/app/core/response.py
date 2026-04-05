"""Unified response payload helpers."""

from datetime import datetime, timezone

from starlette.requests import Request

from app.core.trace import get_trace_id


def now_iso() -> str:
    """Return current UTC datetime in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def success_response(
    request: Request,
    data: object,
    code: str = "OK",
    message: str = "success",
) -> dict[str, object]:
    """Build standard success envelope."""
    return {
        "code": code,
        "message": message,
        "data": data,
        "trace_id": get_trace_id(request),
        "ts": now_iso(),
    }


def error_response(
    request: Request,
    code: str,
    message: str,
    details: object | None = None,
) -> dict[str, object]:
    """Build standard error envelope."""
    return {
        "code": code,
        "message": message,
        "details": details,
        "trace_id": get_trace_id(request),
        "ts": now_iso(),
    }
