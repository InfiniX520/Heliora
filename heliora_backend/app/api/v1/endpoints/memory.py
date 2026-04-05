"""Memory endpoints."""

from fastapi import APIRouter, Request

from app.api.deps import enforce_security_mode
from app.core.config import settings
from app.core.errors import HelioraError
from app.core.response import success_response
from app.schemas.memory import MemoryRetrieveRequest
from app.services.memory_store import build_injected_context, memory_store


router = APIRouter(tags=["memory"])


@router.post("/memory/retrieve")
async def memory_retrieve(request: Request, body: MemoryRetrieveRequest) -> dict:
    """Retrieve matched memories for current query and scope."""
    enforce_security_mode(request)

    if not settings.enable_memory_service:
        raise HelioraError(
            code="FORBIDDEN",
            status_code=403,
            message="memory service is disabled",
        )

    query = body.query.strip()
    if not query:
        raise HelioraError(
            code="INVALID_ARGUMENT",
            status_code=400,
            message="query cannot be blank after trimming",
        )

    if len(query) > settings.memory_max_query_chars:
        raise HelioraError(
            code="QUERY_TOO_LONG",
            status_code=400,
            message=f"query exceeds limit: {settings.memory_max_query_chars}",
            details={"max_chars": settings.memory_max_query_chars},
        )

    memories = memory_store.retrieve(
        query=query,
        scope=body.scope,
        top_k=body.top_k,
        graph_retrieval_enabled=settings.memory_graph_retrieval_p1,
    )

    data = {
        "memories": memories,
        "injected_context": build_injected_context(memories),
        "scope": body.scope,
        "top_k": body.top_k,
        "retrieval_mode": "rules_v1",
    }
    return success_response(request, data=data)
