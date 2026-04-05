"""Exception definitions and FastAPI handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.response import error_response


logger = logging.getLogger(__name__)


class HelioraError(Exception):
    """Domain-level exception with HTTP mapping metadata."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        details: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.details = details


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on app startup."""

    @app.exception_handler(HelioraError)
    async def handle_heliora_error(request: Request, exc: HelioraError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                request,
                code="VALIDATION_ERROR",
                message="request validation failed",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_response(
                request,
                code="INTERNAL_ERROR",
                message="internal server error",
            ),
        )
