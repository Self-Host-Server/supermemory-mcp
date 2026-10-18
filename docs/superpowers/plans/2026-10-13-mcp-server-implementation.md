# Self-Hosted Supermemory MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. **The repo owner chose subagent-driven execution on 2026-10-13 — do not re-ask.** Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status:** Approved, not started. Begin at Task 0, which is a hard prerequisite — Task 2's REST field names are unverified until it runs.

**Goal:** Build an MCP server that exposes `addToSupermemory` and `searchSupermemory` tools plus a static prompt over HTTP, forwarding every call to a self-hosted Supermemory REST API instance, deployed via Docker Compose behind an Authentik-backed OAuth2 proxy.

**Architecture:** A thin shim in four modules. `config.py` loads and validates env vars. `client.py` wraps the two Supermemory REST calls, passing errors through and keeping the API key out of logs. `mcp_server.py` builds an `MCPServer` with two tools, one prompt, and a `/health` route. `main.py` exposes the Starlette ASGI app with an auth-header gate. No FastAPI, no local cache, no retries.

**Tech Stack:**

- Python 3.11+ (SDK floor is 3.10)
- `mcp==2.3.0` — v2.x API, class is `MCPServer`
- Starlette (transitive via `mcp`), uvicorn, pydantic-settings v2, requests
- Docker Compose: `mcp-server` + `oauth2-proxy`

**Spec:** [docs/superpowers/specs/2026-10-13-self-hosted-mcp-design.md](../specs/2026-10-13-self-hosted-mcp-design.md)

---

## Spec Deviations — Read Before Executing

Three places where this plan departs from the spec. Each is flagged because the spec's author should confirm, not because the plan quietly overrode them.

1. **Transport: Streamable HTTP (`/mcp`), not SSE (`/sse`).** Spec constraint 4 says SSE. The SDK still ships `sse_app()` and has no runtime deprecation on it, but Claude Desktop's Custom Connectors require Streamable HTTP (an SSE-only server needs the `mcp-remote` bridge), and Claude Code treats SSE as legacy. Both are one method call on the same server object, so Task 4 builds Streamable HTTP and notes the one-line swap. **Confirm before executing** if SSE is a hard requirement for a client not listed here.
2. **No FastAPI.** Spec constraint 5 says "FastAPI + mcp SDK". `MCPServer.streamable_http_app()` already returns a Starlette app, and `@mcp.custom_route()` already adds `/health`. FastAPI would be a second framework wrapping the first for no added capability. Dropped.
3. **`mcp` 2.x, not 1.x.** `FastMCP` was renamed `MCPServer` in v2; `from mcp.server.fastmcp import FastMCP` now raises on current installs. Pinning `mcp<2` is the alternative if some dependency needs the old name.

---

## Global Constraints

- Python 3.11+; `mcp==2.3.0`
- Transport: Streamable HTTP at `/mcp` (see deviation 1)
- Deployment: Docker Compose only — no pip or npm package
- Auth: oauth2-proxy in front; MCP server trusts `X-Forwarded-User` from it
- Single user per deployment; one API key, one container tag
- Errors from the backend propagate to the MCP client — no silent failure, no retry
- The API key and OAuth client secret never appear in logs, errors, or responses
- Tool names are exactly `addToSupermemory` and `searchSupermemory` (camelCase, matching the official server)
- Conventional Commits — `feat:`, `fix:`, `docs:`, `test:` (drives release versioning)
- `tox -e github` must pass; jscpd threshold is `0`, so no copy-pasted blocks between files

---

## Review Focus

Five conditions the spec implies but names no test for. Each has a test assigned to the task that owns the code.

1. **Backend unreachable** — Supermemory instance down or wrong URL. Expect a clear MCP-visible error, not a hang or a stack trace. Timeout is bounded. → Task 2, Step 5.
2. **API key in log output** — a request failure logs the request. Expect the key absent from every log record and every error string returned to the client. → Task 2, Step 6.
3. **Unauthenticated request reaching a tool** — a request arriving without `X-Forwarded-User` (proxy bypassed, port exposed directly). Expect 401 before any tool runs. Note `custom_route` handlers bypass MCP auth by design, so `/health` must stay non-sensitive. → Task 4, Step 4.
4. **Empty search result** — a query matching nothing. Expect a stated "no memories found", not an empty string or a null that renders as "None" in the client. → Task 3, Step 3.
5. **Missing required env var** — deploy with `SUPERMEMORY_API_KEY` unset. Expect startup to fail loudly naming the missing var, not to boot and fail on first tool call. → Task 1, Step 4.

---

## File Structure

**Create:**

| Path                   | Responsibility                                                              |
| ---------------------- | --------------------------------------------------------------------------- |
| `server/__init__.py`   | Package marker                                                              |
| `server/config.py`     | `Settings` — env loading + validation                                       |
| `server/client.py`     | `SupermemoryClient` — the two REST calls, error passthrough, log sanitizing |
| `server/mcp_server.py` | `build_server()` — tools, prompt, `/health`                                 |
| `server/main.py`       | ASGI app + auth gate; uvicorn entry point                                   |
| `tests/test_config.py` | Env validation                                                              |
| `tests/test_client.py` | REST client against mocked HTTP                                             |
| `tests/test_server.py` | Tool behavior, auth gate, health                                            |
| `Dockerfile`           | Python slim, non-root, uvicorn                                              |
| `docs/DEPLOY.md`       | `.env` setup, compose, MCP client config, troubleshooting                   |

**Modify:** `requirements.txt` (runtime deps), `compose.yml` (currently empty), `.env.example` (currently only `conda_name`), `README.md` (still the template's), `pyproject.toml` (pytest + tox `test` env).

---

## Task 0: Confirm the Supermemory REST Contract

**Why this is first:** every later task is a shim over two endpoints whose request and response shapes are not recorded anywhere in this repo. The spec names the paths (`/v4/memories/add`, `/v4/search`) but not the field names. Guessing them produces a server that imports cleanly and fails on every real call. This task costs ten minutes and de-risks Tasks 2 and 3 entirely.

**Files:**

- Create: `docs/superpowers/specs/supermemory-api-contract.md`

**Interfaces:**

- Produces: documented request/response JSON for both endpoints, consumed by Task 2.

- [ ] **Step 1: Find the API key and URL for the running instance**

The spec's example is `http://192.168.1.246:6767`. Confirm the real value with the operator, and get a key.

- [ ] **Step 2: Probe the add endpoint**

```bash
curl -sS -X POST "$SUPERMEMORY_API_URL/v4/memories/add" \
  -H "Authorization: Bearer $SUPERMEMORY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content": "plan probe: remember the blue folder", "containerTag": "probe_tag"}' \
  -i
```

If that 400s, the field names are wrong. Try `thingToRemember` / `container_tag` / `containerTags` and record which combination returns 2xx. Capture the exact response body.

- [ ] **Step 3: Probe the search endpoint**

```bash
curl -sS -X POST "$SUPERMEMORY_API_URL/v4/search" \
  -H "Authorization: Bearer $SUPERMEMORY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "blue folder", "containerTag": "probe_tag"}' \
  -i
```

Same approach — try `query` / `informationToGet` if `q` fails. Record the response shape: is it `{"results": [...]}`, a bare list, or `{"chunks": [...]}`? Note which field holds the text.

- [ ] **Step 4: Probe the failure modes Task 2 must handle**

```bash
# Bad key -- record the status code and body
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$SUPERMEMORY_API_URL/v4/search" \
  -H "Authorization: Bearer sm_definitely_invalid" \
  -H "Content-Type: application/json" -d '{"q": "x"}'

# Search with no matches -- record whether results is [] or absent
curl -sS -X POST "$SUPERMEMORY_API_URL/v4/search" \
  -H "Authorization: Bearer $SUPERMEMORY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "zzz_no_such_memory_zzz", "containerTag": "probe_tag"}'
```

- [ ] **Step 5: Write the findings to the contract doc**

Record, for each endpoint: method, path, exact request JSON, exact success response JSON, status code and body for auth failure, and the empty-result shape. Mark anything still unknown as unknown — do not fill gaps with plausible guesses.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/supermemory-api-contract.md
git commit -m "docs: record self-hosted Supermemory REST contract from probing"
```

**If the instance is unreachable:** stop and raise it. Do not proceed to Task 2 on guessed field names — note the blocker and ask the operator for a sample request/response pair or the backend's route definitions.

---

## Task 1: Configuration

**Files:**

- Create: `server/__init__.py`, `server/config.py`, `tests/test_config.py`
- Modify: `requirements.txt`, `.env.example`

**Interfaces:**

- Produces: `Settings` (pydantic-settings `BaseSettings`) with fields `supermemory_api_url: str`, `supermemory_api_key: str`, `supermemory_container_tag: str`, and `get_settings() -> Settings`. Consumed by Tasks 2, 3, 4.
- Note: Authentik's client ID and secret are consumed by oauth2-proxy (Task 5), **not** by this app — the app only ever sees the proxy's forwarded header. They belong in `.env` but not in `Settings`.

- [ ] **Step 1: Add runtime dependencies**

`requirements.txt` currently holds dev tooling (`ruff`, `tox`, `nodeenv`). Append the runtime deps:

```
mcp==2.3.0
uvicorn[standard]
pydantic-settings
requests
```

Only `mcp` is pinned — its major version is load-bearing (v1 vs v2 rename). Step 3 captures the resolved versions of the rest.

- [ ] **Step 2: Install and verify the SDK import**

```bash
pip install -r requirements.txt
python -c "from mcp.server import MCPServer; print('ok')"
```

Expected: `ok`. A `ModuleNotFoundError` mentioning `fastmcp` means an `mcp<2` got installed — check the pin.

- [ ] **Step 3: Pin the resolved versions**

```bash
pip freeze | grep -iE '^(mcp|uvicorn|pydantic-settings|requests)='
```

Copy the exact `==` versions into `requirements.txt`, replacing the unpinned lines from Step 1.

- [ ] **Step 4: Write the failing test for env validation**

`tests/test_config.py`:

```python
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
```

- [ ] **Step 5: Run it and watch it fail**

```bash
python -m pytest tests/test_config.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'server'`.

- [ ] **Step 6: Write `server/__init__.py`**

```python
"""Self-hosted Supermemory MCP server."""
```

- [ ] **Step 7: Write `server/config.py`**

```python
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

    @field_validator("supermemory_api_url")
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
```

- [ ] **Step 8: Run the tests and watch them pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 9: Replace `.env.example`**

It currently holds only `conda_name=memory-mcp`. Keep that line — the Makefile reads it — and add the rest. This is the single authoritative copy; no later task restates it.

```
# Conda env name, used by the Makefile
conda_name=memory-mcp

# --- Supermemory backend (required) ---
# Base URL of your self-hosted Supermemory REST API
SUPERMEMORY_API_URL=http://192.168.1.246:6767
# API key from that instance
SUPERMEMORY_API_KEY=sm_replace_me

# --- Supermemory namespace (optional) ---
# Memories are scoped to this tag. Leave unset and a new one is generated at
# each start, which will NOT see memories written under a previous tag. Set it
# explicitly to point at an existing namespace.
SUPERMEMORY_CONTAINER_TAG=

# --- OAuth2 proxy (required for deployment; read by the proxy, not the app) ---
AUTHENTIK_HOST=https://authentik.example.com
AUTHENTIK_CLIENT_ID=replace_me
AUTHENTIK_CLIENT_SECRET=replace_me
# Random 32-byte base64 value: openssl rand -base64 32
OAUTH2_PROXY_COOKIE_SECRET=replace_me
```

- [ ] **Step 10: Commit**

```bash
git add server/__init__.py server/config.py tests/test_config.py requirements.txt .env.example
git commit -m "feat: add env configuration with validation"
```

---

## Task 2: Supermemory REST Client

**Files:**

- Create: `server/client.py`, `tests/test_client.py`

**Interfaces:**

- Consumes: `Settings` from Task 1.
- Produces:
  - `class SupermemoryError(Exception)`
  - `class SupermemoryClient` with `__init__(self, settings: Settings)`, `add(self, text: str) -> str` (returns a human-readable confirmation), `search(self, query: str) -> str` (returns joined memory text, `""` when nothing matched).
  - Both raise `SupermemoryError` on any transport or HTTP error, with the key redacted.

**Before starting:** open `docs/superpowers/specs/supermemory-api-contract.md` from Task 0 and use its real field names. The names below (`content`, `containerTag`, `q`, `results[].content`) are the shapes to verify, not confirmed facts — if the contract doc disagrees, the contract doc wins, and update the tests to match.

- [ ] **Step 1: Write the failing tests**

`tests/test_client.py`:

```python
"""SupermemoryClient against a mocked backend."""

import logging

import pytest
import requests

from server.client import SupermemoryClient, SupermemoryError
from server.config import Settings

API_KEY = "sm_secret_key_do_not_log"


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://backend:6767")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", API_KEY)
    monkeypatch.setenv("SUPERMEMORY_CONTAINER_TAG", "test_tag")
    return Settings()


@pytest.fixture
def client(settings):
    return SupermemoryClient(settings)


def test_add_posts_to_add_endpoint(client, requests_mock):
    requests_mock.post(
        "http://backend:6767/v4/memories/add",
        json={"id": "mem_abc123"},
        status_code=200,
    )

    result = client.add("the blue folder is on the desk")

    assert "mem_abc123" in result
    sent = requests_mock.last_request.json()
    assert sent["content"] == "the blue folder is on the desk"
    assert sent["containerTag"] == "test_tag"
    assert requests_mock.last_request.headers["Authorization"] == f"Bearer {API_KEY}"


def test_search_posts_to_search_endpoint_and_joins_results(client, requests_mock):
    requests_mock.post(
        "http://backend:6767/v4/search",
        json={"results": [{"content": "first memory"}, {"content": "second memory"}]},
        status_code=200,
    )

    result = client.search("blue folder")

    assert "first memory" in result
    assert "second memory" in result
    sent = requests_mock.last_request.json()
    assert sent["q"] == "blue folder"
    assert sent["containerTag"] == "test_tag"


def test_search_returns_empty_string_when_no_results(client, requests_mock):
    """Review Focus 4: the no-match shape is distinguishable from a hit."""
    requests_mock.post("http://backend:6767/v4/search", json={"results": []}, status_code=200)

    assert client.search("nothing matches this") == ""


def test_search_tolerates_bare_list_response(client, requests_mock):
    """The contract doc may show a bare list; handle both without crashing."""
    requests_mock.post(
        "http://backend:6767/v4/search",
        json=[{"content": "only memory"}],
        status_code=200,
    )

    assert "only memory" in client.search("anything")


def test_backend_http_error_raises_supermemory_error(client, requests_mock):
    """Review Focus 1: a backend 401 surfaces as a clear error, not a crash."""
    requests_mock.post(
        "http://backend:6767/v4/search",
        json={"error": "invalid key"},
        status_code=401,
    )

    with pytest.raises(SupermemoryError) as exc:
        client.search("anything")

    assert "401" in str(exc.value)


def test_backend_unreachable_raises_supermemory_error(client, requests_mock):
    """Review Focus 1: connection failure is bounded and reported."""
    requests_mock.post(
        "http://backend:6767/v4/memories/add",
        exc=requests.exceptions.ConnectTimeout,
    )

    with pytest.raises(SupermemoryError) as exc:
        client.add("anything")

    assert "unreachable" in str(exc.value).lower()


def test_api_key_absent_from_logs_and_errors(client, requests_mock, caplog):
    """Review Focus 2: the key leaks into neither logs nor the raised message."""
    requests_mock.post(
        "http://backend:6767/v4/search",
        json={"error": "boom"},
        status_code=500,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(SupermemoryError) as exc:
            client.search("anything")

    assert API_KEY not in caplog.text
    assert API_KEY not in str(exc.value)
```

- [ ] **Step 2: Add the test dependency**

```bash
pip install requests-mock
```

Add `requests-mock` to the `test` tox env's deps in Task 7 (not to `requirements.txt` — it is not a runtime dep).

- [ ] **Step 3: Run the tests and watch them fail**

```bash
python -m pytest tests/test_client.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'server.client'`.

- [ ] **Step 4: Write `server/client.py`**

```python
"""HTTP client for the self-hosted Supermemory REST API.

A thin shim: no caching, no retries. Backend errors become SupermemoryError
with the API key redacted.
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
        payload = {"content": text, "containerTag": self._container_tag}
        data = self._post("/v4/memories/add", payload)
        memory_id = data.get("id") if isinstance(data, dict) else None
        return f"Stored memory {memory_id}." if memory_id else "Stored memory."

    def search(self, query: str) -> str:
        """Search memories. Returns joined text, or "" when nothing matched."""
        payload = {"q": query, "containerTag": self._container_tag}
        data = self._post("/v4/search", payload)
        return "\n\n".join(self._extract_texts(data))

    @staticmethod
    def _extract_texts(data: Any) -> list[str]:
        """Pull memory text out of either response shape, skipping blanks."""
        if isinstance(data, dict):
            items = data.get("results") or data.get("chunks") or []
        elif isinstance(data, list):
            items = data
        else:
            return []

        texts = []
        for item in items:
            if isinstance(item, dict):
                text = item.get("content") or item.get("text") or ""
            else:
                text = str(item)
            if text.strip():
                texts.append(text.strip())
        return texts

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
            raise SupermemoryError(
                f"Supermemory backend unreachable ({type(exc).__name__}). "
                "Check SUPERMEMORY_API_URL and that the instance is running."
            ) from exc

        if not response.ok:
            logger.error("Supermemory %s returned %s", path, response.status_code)
            raise SupermemoryError(
                f"Supermemory returned HTTP {response.status_code} for {path}."
            )

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Supermemory %s returned non-JSON body", path)
            raise SupermemoryError(f"Supermemory returned a non-JSON response for {path}.") from exc
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
python -m pytest tests/test_client.py -v
```

Expected: 7 passed. If the field-name assertions fail, reconcile against the Task 0 contract doc — change both the client and the test to the real names.

- [ ] **Step 6: Confirm the key-redaction test is real**

Make it fail on purpose: temporarily add `logger.debug("headers=%s", self._session.headers)` inside `_post`, rerun, and confirm `test_api_key_absent_from_logs_and_errors` fails. Then remove the line and confirm it passes again. A redaction test that cannot fail is not protecting anything.

- [ ] **Step 7: Commit**

```bash
git add server/client.py tests/test_client.py
git commit -m "feat: add Supermemory REST client with error passthrough"
```

---

## Task 3: MCP Tools, Prompt, and Health Route

**Files:**

- Create: `server/mcp_server.py`, `tests/test_server.py`

**Interfaces:**

- Consumes: `SupermemoryClient` from Task 2.
- Produces: `build_server(client: SupermemoryClient) -> MCPServer`, with tools `addToSupermemory(thingToRemember: str) -> str` and `searchSupermemory(informationToGet: str) -> str`, a `supermemory_prompt` prompt, and a `GET /health` custom route.
- Tool parameter names are part of the public contract — `thingToRemember` and `informationToGet`, camelCase, matching the official server.

- [ ] **Step 1: Write the failing tests**

`tests/test_server.py`:

```python
"""MCP tool behavior, exercised through the registered tool functions."""

import pytest

from server.client import SupermemoryError
from server.mcp_server import build_server


class FakeClient:
    """Stands in for SupermemoryClient; records calls, raises on demand."""

    def __init__(self, add_result="Stored memory mem_1.", search_result="a memory", raise_on=None):
        self.add_result = add_result
        self.search_result = search_result
        self.raise_on = raise_on
        self.added = []
        self.searched = []

    def add(self, text):
        self.added.append(text)
        if self.raise_on == "add":
            raise SupermemoryError("Supermemory backend unreachable (ConnectTimeout).")
        return self.add_result

    def search(self, query):
        self.searched.append(query)
        if self.raise_on == "search":
            raise SupermemoryError("Supermemory returned HTTP 500 for /v4/search.")
        return self.search_result


async def call_tool(server, name, arguments):
    """Invoke a registered tool by name and return its text output."""
    result = await server.call_tool(name, arguments)
    return result if isinstance(result, str) else str(result)


@pytest.mark.asyncio
async def test_add_tool_forwards_text_to_client():
    client = FakeClient()
    server = build_server(client)

    output = await call_tool(server, "addToSupermemory", {"thingToRemember": "blue folder"})

    assert client.added == ["blue folder"]
    assert "mem_1" in output


@pytest.mark.asyncio
async def test_search_tool_forwards_query_and_returns_text():
    client = FakeClient(search_result="the blue folder is on the desk")
    server = build_server(client)

    output = await call_tool(server, "searchSupermemory", {"informationToGet": "blue folder"})

    assert client.searched == ["blue folder"]
    assert "blue folder is on the desk" in output


@pytest.mark.asyncio
async def test_search_tool_states_when_nothing_matched():
    """Review Focus 4: an empty backend result reads as a sentence, not "" or None."""
    client = FakeClient(search_result="")
    server = build_server(client)

    output = await call_tool(server, "searchSupermemory", {"informationToGet": "nothing"})

    assert "no memories" in output.lower()
    assert output.strip() != ""
    assert "none" != output.strip().lower()


@pytest.mark.asyncio
async def test_add_tool_reports_backend_failure():
    client = FakeClient(raise_on="add")
    server = build_server(client)

    output = await call_tool(server, "addToSupermemory", {"thingToRemember": "x"})

    assert "unreachable" in output.lower()


@pytest.mark.asyncio
async def test_search_tool_reports_backend_failure():
    client = FakeClient(raise_on="search")
    server = build_server(client)

    output = await call_tool(server, "searchSupermemory", {"informationToGet": "x"})

    assert "500" in output


@pytest.mark.asyncio
async def test_tools_are_registered_under_official_names():
    server = build_server(FakeClient())

    names = {tool.name for tool in await server.list_tools()}

    assert "addToSupermemory" in names
    assert "searchSupermemory" in names
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
python -m pytest tests/test_server.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'server.mcp_server'`.

The `call_tool` / `list_tools` helpers above assume `MCPServer` exposes those coroutines. If they are named differently on 2.3.0, adjust the two helpers only — the assertions stay. Check with:

```bash
python -c "from mcp.server import MCPServer; print([n for n in dir(MCPServer) if 'tool' in n.lower()])"
```

- [ ] **Step 3: Write `server/mcp_server.py`**

```python
"""MCP server: two tools, one prompt, one health route."""

import logging

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from server.client import SupermemoryClient, SupermemoryError

logger = logging.getLogger(__name__)

PROMPT_TEXT = (
    "You have a persistent memory store reachable through this server. "
    "Call searchSupermemory before answering anything that depends on prior "
    "context, decisions, or facts about the user -- do it without being asked. "
    "Call addToSupermemory whenever the user states a durable preference, "
    "decision, or fact worth having later. Store the fact itself, concisely, "
    "not the conversation around it."
)


def build_server(client: SupermemoryClient) -> MCPServer:
    """Build the MCP server, wiring both tools to `client`."""
    server = MCPServer(
        name="supermemory",
        instructions="Read and write long-term memories in a self-hosted Supermemory instance.",
    )

    @server.tool()
    def addToSupermemory(thingToRemember: str) -> str:  # noqa: N802 - public MCP tool name
        """Store a fact in long-term memory for later recall."""
        try:
            return client.add(thingToRemember)
        except SupermemoryError as exc:
            # Surfaced as tool output so the model can tell the user, per spec:
            # errors pass through, nothing fails silently.
            logger.error("addToSupermemory failed: %s", exc)
            return f"Could not store the memory. {exc}"

    @server.tool()
    def searchSupermemory(informationToGet: str) -> str:  # noqa: N802 - public MCP tool name
        """Search long-term memory for information about the user or past decisions."""
        try:
            found = client.search(informationToGet)
        except SupermemoryError as exc:
            logger.error("searchSupermemory failed: %s", exc)
            return f"Could not search memory. {exc}"
        return found or "No memories found for that query."

    @server.prompt()
    def supermemory_prompt() -> str:
        """Prime the model to use the memory tools proactively."""
        return PROMPT_TEXT

    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        """Liveness only. Deliberately reveals nothing -- custom routes skip auth."""
        return JSONResponse({"ok": True})

    return server
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
python -m pytest tests/test_server.py -v
```

Expected: 6 passed. Needs `pytest-asyncio` (added to the tox env in Task 7); install it now with `pip install pytest-asyncio` and add `asyncio_mode = "auto"` to the pytest config if the `@pytest.mark.asyncio` markers are reported as unknown.

- [ ] **Step 5: Commit**

```bash
git add server/mcp_server.py tests/test_server.py
git commit -m "feat: add MCP tools, memory prompt, and health route"
```

---

## Task 4: ASGI App and Auth Gate

**Files:**

- Create: `server/main.py`
- Modify: `tests/test_server.py` (append the app-level tests)

**Interfaces:**

- Consumes: `get_settings()` (Task 1), `SupermemoryClient` (Task 2), `build_server()` (Task 3).
- Produces: `create_app() -> Starlette` and a module-level `app` for uvicorn (`server.main:app`). Serves MCP at `/mcp`, health at `/health`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server.py`:

```python
from starlette.testclient import TestClient

from server.main import create_app


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://backend:6767")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_key")
    monkeypatch.setenv("SUPERMEMORY_CONTAINER_TAG", "test_tag")
    return TestClient(create_app())


def test_health_is_reachable_without_auth(app_client):
    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_mcp_endpoint_rejects_request_without_forwarded_user(app_client):
    """Review Focus 3: no tool runs for a request that bypassed the proxy."""
    response = app_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 401


def test_mcp_endpoint_accepts_request_with_forwarded_user(app_client):
    """The gate lets a proxied request through -- it is not rejecting everything."""
    response = app_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"X-Forwarded-User": "alice"},
    )

    assert response.status_code != 401
```

- [ ] **Step 2: Run them and watch them fail**

```bash
python -m pytest tests/test_server.py -v
```

Expected: the three new tests error on `ModuleNotFoundError: No module named 'server.main'`; the six from Task 3 still pass.

- [ ] **Step 3: Write `server/main.py`**

```python
"""ASGI entry point.

Transport is Streamable HTTP at /mcp. To serve SSE instead, swap
streamable_http_app() for sse_app() -- that mounts /sse plus /messages/,
and PROTECTED_PREFIXES below must then cover both.
"""

import logging
import os

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from server.client import SupermemoryClient
from server.config import get_settings
from server.mcp_server import build_server

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# Paths the proxy must have authenticated. /health is deliberately absent.
PROTECTED_PREFIXES = ("/mcp", "/messages", "/sse")


class ForwardedUserRequired(BaseHTTPMiddleware):
    """Reject MCP traffic that did not come through the OAuth2 proxy.

    The proxy sets X-Forwarded-User after a successful login. A request
    without it reached this container directly, so refuse it before any
    tool runs.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(PROTECTED_PREFIXES) and not request.headers.get("X-Forwarded-User"):
            logger.warning("Rejected unauthenticated %s %s", request.method, path)
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_app() -> Starlette:
    """Build the ASGI app: MCP at /mcp, health at /health, auth gate in front."""
    settings = get_settings()  # raises here, at startup, if a var is missing
    client = SupermemoryClient(settings)
    server = build_server(client)

    app = server.streamable_http_app()
    app.add_middleware(ForwardedUserRequired)
    logger.info("MCP server ready (containerTag=%s)", settings.supermemory_container_tag)
    return app


app = create_app()
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
python -m pytest tests/test_server.py -v
```

Expected: 9 passed. If `app.add_middleware` raises because the Starlette app has already started, wrap instead: return `ForwardedUserRequired(app)` as a plain ASGI wrapper.

- [ ] **Step 5: Start it for real and hit both endpoints**

```bash
SUPERMEMORY_API_URL=http://127.0.0.1:6767 SUPERMEMORY_API_KEY=sm_dummy \
  python -m uvicorn server.main:app --host 127.0.0.1 --port 5555 &
sleep 2
curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:5555/health
curl -sS -o /dev/null -w 'mcp_noauth=%{http_code}\n' -X POST http://127.0.0.1:5555/mcp \
  -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
kill %1
```

Expected: `health=200`, `mcp_noauth=401`.

- [ ] **Step 6: Commit**

```bash
git add server/main.py tests/test_server.py
git commit -m "feat: serve MCP over streamable HTTP behind a forwarded-user gate"
```

---

## Task 5: Docker and Compose

**Files:**

- Create: `Dockerfile`, `.dockerignore`
- Modify: `compose.yml` (currently empty)

**Interfaces:**

- Consumes: `requirements.txt`, `server/`, the env vars documented in Task 1's `.env.example`.
- Produces: an image running `uvicorn server.main:app` on 5555, and a two-service stack exposing the proxy on 4180.

- [ ] **Step 1: Write `.dockerignore`**

`.env` must never enter the image — it holds the API key, and build context secrets persist in layers. It is also gitignored, so a `COPY .env` would break the build anyway.

```
.env
.git
.github
.tox
node_modules
tests
docs
*.md
__pycache__
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first so code edits do not invalidate the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/

# Non-root: nothing here needs write access.
RUN useradd --create-home --uid 10001 mcp
USER mcp

EXPOSE 5555

# Config arrives as env vars from compose, never baked into the image.
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "5555"]
```

- [ ] **Step 3: Write `compose.yml`**

```yaml
services:
  mcp-server:
    build: .
    restart: unless-stopped
    environment:
      SUPERMEMORY_API_URL: ${SUPERMEMORY_API_URL:?set SUPERMEMORY_API_URL in .env}
      SUPERMEMORY_API_KEY: ${SUPERMEMORY_API_KEY:?set SUPERMEMORY_API_KEY in .env}
      SUPERMEMORY_CONTAINER_TAG: ${SUPERMEMORY_CONTAINER_TAG:-}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    # No ports: -- only the proxy may reach it. Publishing 5555 would expose
    # the MCP endpoint with nothing in front but the forwarded-user check.
    networks: [mcp]
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5555/health',timeout=3).status==200 else 1)",
        ]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  oauth2-proxy:
    image: quay.io/oauth2-proxy/oauth2-proxy:v7.7.1
    restart: unless-stopped
    depends_on:
      mcp-server:
        condition: service_healthy
    environment:
      OAUTH2_PROXY_PROVIDER: oidc
      OAUTH2_PROXY_OIDC_ISSUER_URL: ${AUTHENTIK_HOST:?set AUTHENTIK_HOST in .env}/application/o/supermemory-mcp/
      OAUTH2_PROXY_CLIENT_ID: ${AUTHENTIK_CLIENT_ID:?set AUTHENTIK_CLIENT_ID in .env}
      OAUTH2_PROXY_CLIENT_SECRET: ${AUTHENTIK_CLIENT_SECRET:?set AUTHENTIK_CLIENT_SECRET in .env}
      OAUTH2_PROXY_COOKIE_SECRET: ${OAUTH2_PROXY_COOKIE_SECRET:?run: openssl rand -base64 32}
      OAUTH2_PROXY_REDIRECT_URL: ${OAUTH2_PROXY_REDIRECT_URL:-http://localhost:4180/oauth2/callback}
      OAUTH2_PROXY_HTTP_ADDRESS: 0.0.0.0:4180
      OAUTH2_PROXY_UPSTREAMS: http://mcp-server:5555
      OAUTH2_PROXY_EMAIL_DOMAINS: "*"
      OAUTH2_PROXY_SET_XAUTHREQUEST: "true"
      # Sends X-Forwarded-User upstream -- the header server/main.py requires.
      OAUTH2_PROXY_PASS_BASIC_AUTH: "true"
      OAUTH2_PROXY_SKIP_PROVIDER_BUTTON: "true"
      # Let Docker's healthcheck through without a login round-trip.
      OAUTH2_PROXY_SKIP_AUTH_ROUTES: ^/health$$
    ports:
      - "${MCP_PUBLIC_PORT:-4180}:4180"
    networks: [mcp]

networks:
  mcp:
    driver: bridge
```

- [ ] **Step 4: Build the image**

```bash
docker build -t supermemory-mcp:dev .
```

Expected: build succeeds. A failure mentioning `.env` means `.dockerignore` is missing or `COPY .env` crept into the Dockerfile.

- [ ] **Step 5: Verify the image starts and serves health**

```bash
docker run --rm -d --name smcp-test -p 5555:5555 \
  -e SUPERMEMORY_API_URL=http://127.0.0.1:6767 \
  -e SUPERMEMORY_API_KEY=sm_dummy \
  supermemory-mcp:dev
sleep 3
curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:5555/health
docker logs smcp-test | tail -5
docker rm -f smcp-test
```

Expected: `health=200`, and the logs show the ready line with no API key in it.

- [ ] **Step 6: Verify the config-missing failure is loud**

```bash
docker run --rm supermemory-mcp:dev; echo "exit=$?"
```

Expected: non-zero exit, with a validation error naming `supermemory_api_url` / `supermemory_api_key` (Review Focus 5 at the container level).

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore compose.yml
git commit -m "feat: add Dockerfile and compose stack behind oauth2-proxy"
```

---

## Task 6: Tox Test Env

**Files:**

- Modify: `pyproject.toml`

**Interfaces:**

- Produces: `tox -e test`, and `test` added to the `github` CI chain so the tests actually gate pushes.

- [ ] **Step 1: Add the pytest config**

Append a section to `pyproject.toml` (after the ruff block, before the tox block):

```toml
# =============================================================================
# PYTEST
# =============================================================================

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
asyncio_mode = "auto"
addopts = "-v --tb=short"
```

- [ ] **Step 2: Add the tox test env**

Add alongside the other `[tool.tox.env.*]` tables:

```toml
[tool.tox.env.test]
skip_install = true
base_python = "python3"
deps = [
  "-r requirements.txt",
  "pytest",
  "pytest-asyncio",
  "requests-mock",
  "httpx",
]
commands = [["pytest", "tests"]]
```

`httpx` is what `starlette.testclient.TestClient` needs. `skip_install = true` with `tests/` importing `server/` works because tox runs from the repo root, which is on `sys.path`.

- [ ] **Step 3: Register it in both chains**

In `[tool.tox]`, add `"test"` as the first entry of `env_list`. In `[tool.tox.env.github]`, add `["tox", "-e", "test"]` as the first command — without this, CI never runs the suite.

- [ ] **Step 4: Run the env**

```bash
tox -e test
```

Expected: all tests from Tasks 1–4 pass (4 + 7 + 9 = 20).

- [ ] **Step 5: Run the full CI chain**

```bash
tox -e format
tox -e github
```

Expected: `github` passes. Two likely snags: ruff flagging the camelCase tool names (the `# noqa: N802` comments in Task 3 cover it, and `N` is not in the selected rule set anyway), and jscpd flagging the near-identical `add`/`search` bodies in `client.py`. If jscpd fails, that is a real signal — fold the shared part into `_post` further rather than raising the threshold.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml
git commit -m "test: add pytest tox env and wire it into the CI chain"
```

---

## Task 7: README and Deployment Docs

**Files:**

- Modify: `README.md`
- Create: `docs/DEPLOY.md`

**Interfaces:**

- Consumes: the `.env.example` from Task 1 and the compose stack from Task 5. Reference them; do not restate their contents (jscpd threshold is `0`).

- [ ] **Step 1: Replace `README.md`**

It is still the upstream template's README, describing the template rather than this server. Replace it:

````markdown
# Supermemory MCP Server

An MCP server for a **self-hosted** Supermemory instance.

The official server at `mcp.supermemory.ai` only talks to the hosted
Supermemory API. If you run Supermemory yourself, this bridges your instance's
REST API to MCP, so Claude can read and write your memories without them
leaving your network.

## What it exposes

|                                       |                                                           |
| ------------------------------------- | --------------------------------------------------------- |
| `addToSupermemory(thingToRemember)`   | Stores a memory. Same signature as the official server.   |
| `searchSupermemory(informationToGet)` | Searches memories. Same signature as the official server. |
| `supermemory_prompt`                  | Primes the model to use both tools unprompted.            |
| `GET /health`                         | Liveness check for Docker.                                |

MCP is served over Streamable HTTP at `/mcp`, behind
[oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/) pointed at your
Authentik instance.

## Requirements

- A reachable self-hosted Supermemory instance and an API key for it
- An Authentik (or other OIDC) application for the proxy
- Docker and Docker Compose

## Quick start

```bash
cp .env.example .env
# fill in SUPERMEMORY_API_URL, SUPERMEMORY_API_KEY, and the AUTHENTIK_* vars
docker compose up -d
curl http://localhost:4180/health
```

Then point your MCP client at `http://localhost:4180/mcp`. Full walkthrough,
including client config and troubleshooting: **[docs/DEPLOY.md](docs/DEPLOY.md)**.

## Development

```bash
make conda        # create the conda env from environment.yml
tox -e test       # run the test suite
tox -e format     # ruff + prettier + taplo
tox -e github     # the full CI chain
```

Design notes live in [docs/superpowers/specs/](docs/superpowers/specs/).

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) — Conventional Commits, which drive
versioning and the changelog.
````

- [ ] **Step 2: Write `docs/DEPLOY.md`**

````markdown
# Deploying

## 1. Configure

```bash
cp .env.example .env
```

`.env.example` documents every variable. The two that must be right before
anything works are `SUPERMEMORY_API_URL` (your instance's base URL, reachable
_from inside Docker_ — `localhost` there is the container, not your host) and
`SUPERMEMORY_API_KEY`.

Generate the proxy cookie secret:

```bash
openssl rand -base64 32
```

### Container tag

`SUPERMEMORY_CONTAINER_TAG` namespaces your memories. Leave it empty and a new
tag is generated **on every start**, so nothing written under the previous tag
is visible. Set it explicitly to keep memories across restarts, or to point at
a namespace that already has them.

## 2. Authentik application

Create an OAuth2/OIDC provider in Authentik:

- Redirect URI: `http://localhost:4180/oauth2/callback` (match
  `OAUTH2_PROXY_REDIRECT_URL`)
- Client type: Confidential
- Copy the client ID and secret into `.env`

The compose file expects the issuer at
`${AUTHENTIK_HOST}/application/o/supermemory-mcp/`. If your application slug is
not `supermemory-mcp`, change `OAUTH2_PROXY_OIDC_ISSUER_URL` to match.

## 3. Start

```bash
docker compose up -d
docker compose ps        # mcp-server should be (healthy)
docker compose logs -f mcp-server
```

Only the proxy publishes a port (4180). The MCP server is reachable only on the
internal network — that is deliberate, since the server's own auth check is a
header check, not a full OAuth flow.

## 4. Connect a client

**Claude Code:**

```bash
claude mcp add --transport http supermemory http://localhost:4180/mcp
```

**Claude Desktop:** add it as a Custom Connector (Pro/Max/Team/Enterprise)
pointing at the same URL. Desktop's connectors need Streamable HTTP, which is
what this server speaks.

Both will send you through Authentik's login the first time.

## Troubleshooting

**401 on every MCP call.** The request is not carrying the proxy's
`X-Forwarded-User` header. Either you are hitting the server's port directly
instead of the proxy's 4180, or `OAUTH2_PROXY_SET_XAUTHREQUEST` /
`OAUTH2_PROXY_PASS_BASIC_AUTH` are not set.

**`Supermemory backend unreachable`.** The container cannot reach
`SUPERMEMORY_API_URL`. Check from inside it:

```bash
docker compose exec mcp-server python -c \
  "import urllib.request,os; print(urllib.request.urlopen(os.environ['SUPERMEMORY_API_URL'],timeout=5).status)"
```

A `localhost` URL is the usual cause — use the host's LAN IP, or
`host.docker.internal`.

**`Supermemory returned HTTP 401`.** The backend rejected the API key. The
proxy login succeeded and the problem is one layer further in.

**Container exits immediately.** A required variable is missing; the startup
error names it. `docker compose logs mcp-server`.

**Searches return nothing, but memories exist.** Almost always
`SUPERMEMORY_CONTAINER_TAG` — see above.
````

- [ ] **Step 3: Check the prose linters**

```bash
tox -e prettier
tox -e txt-lint
```

Expected: pass. `prettier` covers Markdown here and will rewrite tables and wrapping; run `tox -e format` to apply.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/DEPLOY.md
git commit -m "docs: replace template README and add deployment guide"
```

---

## Task 8: End-to-End Verification

**Files:** none created — this task only runs things and records the result.

- [ ] **Step 1: Full local suite**

```bash
tox -e format && tox -e github
```

Expected: both pass, including the `test` env added in Task 6.

- [ ] **Step 2: Bring up the real stack**

Against a real Supermemory instance, with `.env` filled in:

```bash
docker compose up -d --build
docker compose ps
```

Expected: `mcp-server` reports `(healthy)`; `oauth2-proxy` is up.

- [ ] **Step 3: Confirm the proxy gate**

```bash
curl -sS -o /dev/null -w 'proxy_mcp=%{http_code}\n' -X POST http://localhost:4180/mcp \
  -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Expected: 302 (redirect to Authentik) or 401 — not 200. A 200 means unauthenticated callers reach the tools.

- [ ] **Step 4: Round-trip a memory through a real client**

Connect Claude Code (`claude mcp add --transport http supermemory http://localhost:4180/mcp`), authenticate, then in a session: store a distinctive fact with `addToSupermemory`, start a **new** session, and retrieve it with `searchSupermemory`.

Expected: the fact comes back. Then confirm it landed in your own instance, not the cloud:

```bash
curl -sS -X POST "$SUPERMEMORY_API_URL/v4/search" \
  -H "Authorization: Bearer $SUPERMEMORY_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"q\": \"<the distinctive fact>\", \"containerTag\": \"$SUPERMEMORY_CONTAINER_TAG\"}"
```

- [ ] **Step 5: Audit the logs for secrets**

```bash
docker compose logs 2>&1 | grep -F "$SUPERMEMORY_API_KEY" && echo "LEAK" || echo "clean"
docker compose logs 2>&1 | grep -F "$AUTHENTIK_CLIENT_SECRET" && echo "LEAK" || echo "clean"
```

Expected: `clean` twice. A hit is a release blocker — fix the log statement before shipping.

- [ ] **Step 6: Confirm the repo is genuinely reusable**

```bash
git grep -nE '192\.168\.|10\.0\.0\.|sm_[A-Za-z0-9]{10,}|authentik\.(my|home)' -- . ':!docs/' ':!.env.example'
```

Expected: no hits outside docs and `.env.example`. The spec requires no hardcoded IPs, keys, or user-specific values.

- [ ] **Step 7: Record the result**

Note in the PR description which steps passed, and anything deferred. If Step 4 could not run (no live instance), say so explicitly rather than implying the round trip was verified.

---

## Spec Coverage

| Spec item                                             | Where                                    |
| ----------------------------------------------------- | ---------------------------------------- |
| `addToSupermemory` → `/v4/memories/add`               | Tasks 2, 3                               |
| `searchSupermemory` → `/v4/search`                    | Tasks 2, 3                               |
| Static memory prompt                                  | Task 3                                   |
| `SUPERMEMORY_API_URL` / `_API_KEY` / `_CONTAINER_TAG` | Task 1                                   |
| Always-on Docker service                              | Task 5                                   |
| HTTP transport, configurable port                     | Tasks 4, 5                               |
| `GET /health`                                         | Task 3 (route), Task 5 (healthcheck)     |
| Authentik OAuth protection                            | Tasks 4 (gate), 5 (proxy)                |
| Unauthenticated requests rejected                     | Task 4 Step 1, Task 8 Step 3             |
| Errors pass through, nothing silent                   | Task 2 (`_post`), Task 3 (tool handlers) |
| API key never logged or returned                      | Task 2 Steps 1/6, Task 8 Step 5          |
| Thin shim — no cache, no retry                        | Task 2 by construction                   |
| `.env.example` documents every var                    | Task 1 Step 9                            |
| Deployment and client-config docs                     | Task 7                                   |
| Public and reusable, nothing hardcoded                | Task 8 Step 6                            |
| Semver via Conventional Commits                       | Commit messages throughout               |
| Transport is SSE                                      | **Deviated** — see Spec Deviations       |
| FastAPI                                               | **Deviated** — see Spec Deviations       |

---

## Execution Recommendation

**Subagent-driven.** Tasks 1→2→3→4 form an interface chain where each step's output is the next one's input, and the Interfaces block on each task is written so a fresh implementer can work from the task alone. A mistake in Task 2's field names propagates into every later task, which is exactly the case where a fresh reviewer between tasks pays for itself.

**Do Task 0 first and do not skip it.** The field names in Task 2 are marked as unverified for a reason — if the probing in Task 0 cannot run, the plan is blocked, not ready.
