"""Application settings."""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    app_name: str = "Heliora Backend"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    # Keep as plain string to avoid env JSON auto-decoding issues in pydantic-settings.
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    enable_memory_service: bool = True
    memory_graph_retrieval_p1: bool = True

    security_policy_mode: str = "strict"
    local_max_privilege_ack: bool = False
    local_max_privilege_loopback_only: bool = True
    idempotency_ttl_seconds: int = 86400
    chat_max_content_chars: int = 4000
    memory_max_query_chars: int = 512
    task_queue_backend: str = "memory"
    task_persistence_backend: str = "sqlite"
    database_url: str = ""
    rabbitmq_url: str = "amqp://heliora:heliora_rmq_pass@127.0.0.1:5672/"
    task_queue_sla_p0_ms: int = 3000
    task_queue_sla_p1_ms: int = 3000
    task_queue_sla_p2_ms: int = 15000
    task_queue_sla_p3_ms: int = 300000
    task_queue_sla_memory_ms: int = 5000
    task_retry_max_attempts: int = 2
    task_retry_base_delay_seconds: float = 1.0
    task_retry_max_delay_seconds: float = 30.0
    task_retry_backoff_factor: float = 2.0
    task_queue_fail_open: bool = True
    task_registry_persistence_enabled: bool = True
    task_registry_sqlite_path: str = ".data/task_registry.db"
    task_registry_postgres_dsn: str = ""
    task_events_persistence_enabled: bool = True
    task_events_sqlite_path: str = ".data/task_events.db"
    task_events_postgres_dsn: str = ""

    model_config = SettingsConfigDict(
        # Use backend-root .env so running from any cwd behaves consistently.
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        allowed = {"development", "staging", "production"}
        if value not in allowed:
            raise ValueError(f"app_env must be one of {sorted(allowed)}")
        return value

    @field_validator("security_policy_mode")
    @classmethod
    def validate_security_policy_mode(cls, value: str) -> str:
        allowed = {"strict", "trusted_local_max"}
        if value not in allowed:
            raise ValueError(f"security_policy_mode must be one of {sorted(allowed)}")
        return value

    @field_validator("idempotency_ttl_seconds")
    @classmethod
    def validate_idempotency_ttl_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("idempotency_ttl_seconds must be > 0")
        return value

    @field_validator("chat_max_content_chars")
    @classmethod
    def validate_chat_max_content_chars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("chat_max_content_chars must be > 0")
        return value

    @field_validator("memory_max_query_chars")
    @classmethod
    def validate_memory_max_query_chars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory_max_query_chars must be > 0")
        return value

    @field_validator("task_queue_backend")
    @classmethod
    def validate_task_queue_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"memory", "rabbitmq"}
        if normalized not in allowed:
            raise ValueError(f"task_queue_backend must be one of {sorted(allowed)}")
        return normalized

    @field_validator("task_persistence_backend")
    @classmethod
    def validate_task_persistence_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"sqlite", "postgres"}
        if normalized not in allowed:
            raise ValueError(f"task_persistence_backend must be one of {sorted(allowed)}")
        return normalized

    @field_validator("database_url", "task_registry_postgres_dsn", "task_events_postgres_dsn")
    @classmethod
    def normalize_optional_dsn(cls, value: str) -> str:
        return value.strip()

    @field_validator("rabbitmq_url")
    @classmethod
    def validate_rabbitmq_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rabbitmq_url must not be empty")
        return normalized

    @field_validator(
        "task_queue_sla_p0_ms",
        "task_queue_sla_p1_ms",
        "task_queue_sla_p2_ms",
        "task_queue_sla_p3_ms",
        "task_queue_sla_memory_ms",
    )
    @classmethod
    def validate_task_queue_sla_ms(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("task queue SLA must be > 0")
        return value

    @field_validator("task_retry_max_attempts")
    @classmethod
    def validate_task_retry_max_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("task_retry_max_attempts must be >= 1")
        return value

    @field_validator("task_retry_base_delay_seconds")
    @classmethod
    def validate_task_retry_base_delay_seconds(cls, value: float) -> float:
        if value < 0:
            raise ValueError("task_retry_base_delay_seconds must be >= 0")
        return value

    @field_validator("task_retry_max_delay_seconds")
    @classmethod
    def validate_task_retry_max_delay_seconds(cls, value: float) -> float:
        if value < 0:
            raise ValueError("task_retry_max_delay_seconds must be >= 0")
        return value

    @field_validator("task_retry_backoff_factor")
    @classmethod
    def validate_task_retry_backoff_factor(cls, value: float) -> float:
        if value < 1:
            raise ValueError("task_retry_backoff_factor must be >= 1")
        return value

    @field_validator("task_registry_sqlite_path")
    @classmethod
    def validate_task_registry_sqlite_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("task_registry_sqlite_path must not be empty")
        return normalized

    @field_validator("task_events_sqlite_path")
    @classmethod
    def validate_task_events_sqlite_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("task_events_sqlite_path must not be empty")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def normalize_cors_origins(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins parsed from either JSON array or comma-separated string."""
        raw = (self.cors_origins or "").strip()
        if not raw:
            return []

        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass

        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
