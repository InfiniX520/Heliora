"""Configuration path portability tests."""

from pathlib import Path

import pytest

from app.core import config as config_module


def test_env_file_is_backend_root_dotenv() -> None:
    """Settings should always read .env from backend root."""
    env_file = config_module.Settings.model_config.get("env_file")

    assert env_file is not None
    assert Path(env_file) == config_module.BACKEND_ROOT / ".env"


def test_settings_load_with_different_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing cwd should not break settings loading."""
    monkeypatch.chdir(config_module.BACKEND_ROOT.parent)

    loaded = config_module.Settings()

    assert loaded.app_name
