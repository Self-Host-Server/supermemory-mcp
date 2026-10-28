"""Environment configuration."""

import secrets

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Env-backed settings. Missing required vars raise at construction."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env also carries conda_name and the oauth2-proxy vars
        # Required: pydantic v2 skips validators on defaults without this, so
        # the container-tag generator below would never fire when the var is unset.
        validate_default=True,
    )

    supermemory_api_url: str
    supermemory_api_key: str
    supermemory_container_tag: str = ""
    # Both set -> serve OAuth discovery metadata so claude.ai can log in via Authentik.
    mcp_public_url: str = ""
    authentik_host: str = ""

    @field_validator("supermemory_api_url", "mcp_public_url", "authentik_host")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("supermemory_container_tag")
    @classmethod
    def _default_container_tag(cls, value: str) -> str:
        # Spec: default to a generated id so a fresh deploy is namespaced.
        # Generated per process -- set the var explicitly to reuse existing memories.
        return value or f"mcp_{secrets.token_hex(8)}"


def get_settings() -> Settings:
    """Construct settings, letting validation errors propagate to startup."""
    return Settings()
