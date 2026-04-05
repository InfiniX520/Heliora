"""Trace ID middleware and helper functions."""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


TRACE_ID_HEADER = "X-Trace-Id"


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Attach a trace ID to each request/response lifecycle."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(TRACE_ID_HEADER, "").strip()
        trace_id = incoming if incoming else uuid4().hex[:16]
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response


def get_trace_id(request: Request) -> str:
    """Return trace_id stored in request state."""
    return getattr(request.state, "trace_id", "")
