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
        # `memory` can be null on a forgotten/redacted result (the backend has a
        # forget state -- see forgetAfter/forgetReason in the add response), so
        # coerce before calling string methods and drop the textless ones.
        texts = [(r.get("memory") or "").strip() for r in results if isinstance(r, dict)]
        return "\n\n".join(text for text in texts if text)

    def delete(self, memory_id: str) -> str:
        """Delete a memory by ID. Returns a confirmation message."""
        self._request("delete", f"/v4/memories/{memory_id}")
        return f"Deleted memory {memory_id}."

    def modify(self, memory_id: str, new_content: str) -> str:
        """Update a memory's content by ID. Returns a confirmation message."""
        self._request("patch", f"/v4/memories/{memory_id}", {"content": new_content})
        return f"Updated memory {memory_id}."

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """Make HTTP request and return parsed JSON, or raise SupermemoryError.

        Logs the path and container tag only -- never the session headers,
        which hold the bearer token.
        """
        url = f"{self._base_url}{path}"
        logger.info("%s %s (containerTag=%s)", method.upper(), path, self._container_tag)
        try:
            if method.lower() == "post":
                response = self._session.post(url, json=payload, timeout=TIMEOUT_SECONDS)
            elif method.lower() == "patch":
                response = self._session.patch(url, json=payload, timeout=TIMEOUT_SECONDS)
            elif method.lower() == "delete":
                response = self._session.delete(url, timeout=TIMEOUT_SECONDS)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except requests.exceptions.RequestException as exc:
            logger.error("Supermemory backend unreachable at %s: %s", path, type(exc).__name__)
            raise SupermemoryError(f"Supermemory backend unreachable ({type(exc).__name__}). Check SUPERMEMORY_API_URL and that the instance is running.") from exc

        if not response.ok:
            logger.error("Supermemory %s returned %s", path, response.status_code)
            raise SupermemoryError(f"Supermemory returned HTTP {response.status_code} for {path}.")

        try:
            return response.json() if response.content else {}
        except ValueError as exc:
            logger.error("Supermemory %s returned non-JSON body", path)
            raise SupermemoryError(f"Supermemory returned a non-JSON response for {path}.") from exc

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        """POST and return parsed JSON, or raise SupermemoryError."""
        return self._request("post", path, payload)
