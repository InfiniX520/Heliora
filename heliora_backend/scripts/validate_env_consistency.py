#!/usr/bin/env python3
"""Validate consistency across runtime environment connection settings."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


POSTGRES_SCHEMES = {"postgresql", "postgres", "postgresql+psycopg"}
RABBITMQ_SCHEMES = {"amqp", "amqps"}


@dataclass(frozen=True)
class ParsedConn:
    scheme: str
    username: str
    password: str
    host: str
    port: int | None
    database: str


def load_env_file(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        raise FileNotFoundError(f"env file not found: {env_file}")

    data: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        normalized = line
        if normalized.startswith("export "):
            normalized = normalized[len("export ") :]

        if "=" not in normalized:
            continue

        key, value = normalized.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def resolve_env_file(raw_env_file: str) -> Path:
    """Resolve env file path with a backend-root fallback for scripts cwd usage."""
    env_path = Path(raw_env_file).expanduser()
    candidates: list[Path] = []

    if env_path.is_absolute():
        candidates.append(env_path)
    else:
        candidates.append((Path.cwd() / env_path).resolve())
        backend_root = Path(__file__).resolve().parents[1]
        candidates.append((backend_root / env_path).resolve())

    # Keep deterministic order while removing duplicates.
    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate)

    for candidate in unique_candidates:
        if candidate.exists():
            return candidate

    attempted = "\n  - ".join(str(item) for item in unique_candidates)
    raise FileNotFoundError(
        "env file not found. attempted paths:\n"
        f"  - {attempted}\n"
        "hint: run from backend root with --env-file .env, "
        "or from scripts with --env-file ../.env"
    )


def parse_conn_url(
    name: str,
    raw_url: str,
    allowed_schemes: set[str],
    *,
    require_database: bool = True,
    default_database: str = "",
) -> tuple[ParsedConn | None, str | None]:
    parsed = urlparse(raw_url)
    if parsed.scheme not in allowed_schemes:
        return None, f"{name} uses unsupported scheme: {parsed.scheme or '<empty>'}"

    if parsed.username is None:
        return None, f"{name} is missing username"
    if parsed.password is None:
        return None, f"{name} is missing password"
    if not parsed.hostname:
        return None, f"{name} is missing hostname"

    database = parsed.path.lstrip("/")
    if not database and not require_database:
        database = default_database
    if not database:
        return None, f"{name} is missing database/vhost segment"

    return (
        ParsedConn(
            scheme=parsed.scheme,
            username=unquote(parsed.username),
            password=unquote(parsed.password),
            host=parsed.hostname,
            port=parsed.port,
            database=database,
        ),
        None,
    )


def validate_env(values: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    database_url = values.get("DATABASE_URL", "")
    postgres_user = values.get("POSTGRES_USER", "")
    postgres_password = values.get("POSTGRES_PASSWORD", "")
    postgres_db = values.get("POSTGRES_DB", "")

    if database_url:
        db_conn, db_error = parse_conn_url("DATABASE_URL", database_url, POSTGRES_SCHEMES)
        if db_error:
            errors.append(db_error)
        elif db_conn is not None:
            if postgres_user and db_conn.username != postgres_user:
                errors.append(
                    "DATABASE_URL username does not match POSTGRES_USER "
                    f"({db_conn.username} != {postgres_user})"
                )
            if postgres_password and db_conn.password != postgres_password:
                errors.append("DATABASE_URL password does not match POSTGRES_PASSWORD")
            if postgres_db and db_conn.database != postgres_db:
                errors.append(
                    "DATABASE_URL database does not match POSTGRES_DB "
                    f"({db_conn.database} != {postgres_db})"
                )
    elif values.get("TASK_PERSISTENCE_BACKEND", "").strip().lower() == "postgres":
        errors.append("DATABASE_URL is required when TASK_PERSISTENCE_BACKEND=postgres")

    rabbitmq_url = values.get("RABBITMQ_URL", "")
    rabbitmq_user = values.get("RABBITMQ_DEFAULT_USER", "")
    rabbitmq_password = values.get("RABBITMQ_DEFAULT_PASS", "")

    if rabbitmq_url:
        rabbit_conn, rabbit_error = parse_conn_url(
            "RABBITMQ_URL",
            rabbitmq_url,
            RABBITMQ_SCHEMES,
            require_database=False,
            default_database="/",
        )
        if rabbit_error:
            errors.append(rabbit_error)
        elif rabbit_conn is not None:
            if rabbitmq_user and rabbit_conn.username != rabbitmq_user:
                errors.append(
                    "RABBITMQ_URL username does not match RABBITMQ_DEFAULT_USER "
                    f"({rabbit_conn.username} != {rabbitmq_user})"
                )
            if rabbitmq_password and rabbit_conn.password != rabbitmq_password:
                errors.append("RABBITMQ_URL password does not match RABBITMQ_DEFAULT_PASS")

    backend = values.get("TASK_PERSISTENCE_BACKEND", "").strip().lower()
    registry_dsn = values.get("TASK_REGISTRY_POSTGRES_DSN", "").strip()
    events_dsn = values.get("TASK_EVENTS_POSTGRES_DSN", "").strip()

    if backend == "postgres":
        effective_registry = registry_dsn or database_url
        effective_events = events_dsn or database_url

        if not effective_registry:
            errors.append("Postgres backend requires TASK_REGISTRY_POSTGRES_DSN or DATABASE_URL")
        if not effective_events:
            errors.append("Postgres backend requires TASK_EVENTS_POSTGRES_DSN or DATABASE_URL")

        if effective_registry:
            _, registry_error = parse_conn_url(
                "effective TASK_REGISTRY_POSTGRES_DSN",
                effective_registry,
                POSTGRES_SCHEMES,
            )
            if registry_error:
                errors.append(registry_error)
        if effective_events:
            _, events_error = parse_conn_url(
                "effective TASK_EVENTS_POSTGRES_DSN",
                effective_events,
                POSTGRES_SCHEMES,
            )
            if events_error:
                errors.append(events_error)

    if backend == "sqlite" and (registry_dsn or events_dsn):
        warnings.append(
            "TASK_PERSISTENCE_BACKEND=sqlite but postgres DSN overrides are set; "
            "this is allowed but may confuse operators"
        )

    return errors, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate backend .env consistency")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to env file (default: .env)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        env_file = resolve_env_file(args.env_file)
        values = load_env_file(env_file)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1

    errors, warnings = validate_env(values)
    for warning in warnings:
        print(f"[-] {warning}")

    if errors:
        print(f"[!] Environment consistency check failed for: {env_file}")
        for error in errors:
            print(f"[!] {error}")
        return 1

    print(f"[+] Environment consistency check passed: {env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
