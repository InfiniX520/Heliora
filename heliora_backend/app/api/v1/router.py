"""Version v1 API router."""

from fastapi import APIRouter

from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.memory import router as memory_router
from app.api.v1.endpoints.tasks import router as tasks_router


v1_router = APIRouter()
v1_router.include_router(chat_router)
v1_router.include_router(memory_router)
v1_router.include_router(tasks_router)
