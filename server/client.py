"""HTTP client for the self-hosted Supermemory REST API.

A thin shim: no caching, no retries. Backend errors become SupermemoryError
with the API key redacted. Request/response shapes follow the verified
contract in docs/superpowers/specs/supermemory-api-contract.md.
"""

import logging
from typing import Any

import requests

from server.config import Settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class SupermemoryError(Exception):
    """A Supermemory REST call failed. Message is safe to show a client."""


class SupermemoryClient:
    """Wraps the two Supermemory endpoints the MCP tools need."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.supermemory_api_url
        self._container_tag = settings.supermemory_container_tag
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {settings.supermemory_api_key}",
                "Content-Type": "application/json",
            }
        )

    def add(self, text: str) -> str:
        """Store one memory. Returns a confirmation naming the memory id."""
        payload = {"memories": [{"content": text}], "containerTag": self._container_tag}
        data = self._post("/v4/memories", payload)
        memory_id = None
        if isinstance(data, dict):
            memories = data.get("memories") or []
            if memories and isinstance(memories[0], dict):
                memory_id = memories[0].get("id")
            memory_id = memory_id or data.get("documentId")
        return f"Stored memory {memory_id}." if memory_id else "Stored memory."

    def search(self, query: str) -> str:
        """Search memories. Returns joined text, or "" when nothing matched.

        containerTag is always sent -- omitting it searches every container
        on the instance (binding ruling from Task 0).
        """
        payload = {"q": query, "containerTag": self._container_tag}
        data = self._post("/v4/search", payload)
        results = data.get("results", []) if isinstance(data, dict) else []
        texts = [r["memory"].strip() for r in results if isinstance(r, dict) and r.get("memory", "").strip()]
        return "\n\n".join(texts)

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        """POST and return parsed JSON, or raise SupermemoryError.

        Logs the path and container tag only -- never the session headers,
        which hold the bearer token.
        """
        url = f"{self._base_url}{path}"
        logger.info("POST %s (containerTag=%s)", path, self._container_tag)
        try:
            response = self._session.post(url, json=payload, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            # str(exc) can include the URL but never the Authorization header.
            logger.error("Supermemory backend unreachable at %s: %s", path, type(exc).__name__)
            raise SupermemoryError(f"Supermemory backend unreachable ({type(exc).__name__}). Check SUPERMEMORY_API_URL and that the instance is running.") from exc

        if not response.ok:
            logger.error("Supermemory %s returned %s", path, response.status_code)
            raise SupermemoryError(f"Supermemory returned HTTP {response.status_code} for {path}.")

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Supermemory %s returned non-JSON body", path)
            raise SupermemoryError(f"Supermemory returned a non-JSON response for {path}.") from exc
