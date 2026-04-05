"""Top-level API router."""

from fastapi import APIRouter, Request

from app.api.v1.router import v1_router
from app.core.response import success_response


api_router = APIRouter()


@api_router.get("/health")
async def health_check(request: Request) -> dict:
    """Lightweight health endpoint for service readiness checks."""
    return success_response(request, data={"status": "healthy"})


api_router.include_router(v1_router, prefix="/api/v1")
