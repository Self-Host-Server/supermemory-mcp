"""Settings loading and validation."""

import pytest
from pydantic import ValidationError

from server.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://10.0.0.5:6767/")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_key")
    monkeypatch.setenv("SUPERMEMORY_CONTAINER_TAG", "my_tag")

    settings = Settings()

    assert settings.supermemory_api_url == "http://10.0.0.5:6767"  # trailing slash stripped
    assert settings.supermemory_api_key == "sm_key"
    assert settings.supermemory_container_tag == "my_tag"


def test_settings_generates_container_tag_when_absent(monkeypatch):
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://10.0.0.5:6767")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_key")
    monkeypatch.delenv("SUPERMEMORY_CONTAINER_TAG", raising=False)

    settings = Settings()

    assert settings.supermemory_container_tag.startswith("mcp_")
    assert len(settings.supermemory_container_tag) > 8


def test_settings_rejects_missing_api_key(monkeypatch):
    """Review Focus 5: startup must fail loudly, naming the missing var."""
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://10.0.0.5:6767")
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)

    with pytest.raises(ValidationError) as exc:
        Settings()

    assert "supermemory_api_key" in str(exc.value).lower()


def test_settings_rejects_missing_api_url(monkeypatch):
    monkeypatch.delenv("SUPERMEMORY_API_URL", raising=False)
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_key")

    with pytest.raises(ValidationError) as exc:
        Settings()

    assert "supermemory_api_url" in str(exc.value).lower()
