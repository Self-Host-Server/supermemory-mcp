"""MCP tool behavior, exercised through the registered tool functions."""

import pytest
from starlette.testclient import TestClient

from server.client import SupermemoryError
from server.main import create_app
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


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://backend:6767")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_key")
    monkeypatch.setenv("SUPERMEMORY_CONTAINER_TAG", "test_tag")
    # Empty env beats a developer's .env, keeping OAuth metadata off by default.
    monkeypatch.setenv("MCP_PUBLIC_URL", "")
    monkeypatch.setenv("AUTHENTIK_HOST", "")
    # Context-manager form: streamable_http_app()'s session manager needs the
    # ASGI lifespan to run (it initializes an anyio task group in `run()`),
    # which TestClient only sends when entered via `with`/`__enter__`.
    with TestClient(create_app()) as client:
        yield client


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


def test_oauth_metadata_absent_when_not_configured(app_client):
    assert app_client.get("/.well-known/oauth-protected-resource").status_code == 404


def test_oauth_metadata_points_clients_at_authentik(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://mcp.example.com/")
    monkeypatch.setenv("AUTHENTIK_HOST", "https://auth.example.com")
    with TestClient(create_app()) as client:
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            resource = client.get(path).json()
            assert resource["resource"] == "https://mcp.example.com/mcp"
            assert resource["authorization_servers"] == ["https://mcp.example.com"]

        server = client.get("/.well-known/oauth-authorization-server").json()

    assert server["issuer"] == "https://mcp.example.com"
    assert server["authorization_endpoint"] == "https://auth.example.com/application/o/authorize/"
    assert server["token_endpoint"] == "https://auth.example.com/application/o/token/"
