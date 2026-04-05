"""Application entrypoint for local development."""

import uvicorn

from app.core.config import settings


def main() -> None:
    """Run the API server using configured host and port."""
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    main()
