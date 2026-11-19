"""Tests for AI provider adapters."""

import pytest
from starlette.testclient import TestClient

from server.client import SupermemoryError
from server.main import create_app
from server.providers import base as provider_base
from server.providers import openai as openai_provider


class FakeClient:
    """Mock SupermemoryClient for provider tests."""

    def __init__(self, results=None, raise_on=None):
        self.results = results or {
            "add": "Stored memory mem_123.",
            "search": "Found memory about X.",
            "delete": "Deleted memory mem_123.",
            "modify": "Updated memory mem_123.",
        }
        self.raise_on = raise_on
        self.calls = []

    def add(self, text):
        self.calls.append(("add", text))
        if self.raise_on == "add":
            raise SupermemoryError("Backend unreachable.")
        return self.results["add"]

    def search(self, query):
        self.calls.append(("search", query))
        if self.raise_on == "search":
            raise SupermemoryError("Search failed.")
        return self.results["search"]

    def delete(self, memory_id):
        self.calls.append(("delete", memory_id))
        if self.raise_on == "delete":
            raise SupermemoryError("Not found.")
        return self.results["delete"]

    def modify(self, memory_id, new_content):
        self.calls.append(("modify", memory_id, new_content))
        if self.raise_on == "modify":
            raise SupermemoryError("Not found.")
        return self.results["modify"]


def test_openai_provider_returns_function_schema():
    """OpenAI provider exports tools in Function Calling format."""
    schema = openai_provider.get_tools_schema()

    assert "tools" in schema
    assert len(schema["tools"]) == 4

    # Check structure of first tool
    tool = schema["tools"][0]
    assert tool["type"] == "function"
    assert "name" in tool["function"]
    assert "description" in tool["function"]
    assert "parameters" in tool["function"]


@pytest.mark.asyncio
async def test_provider_call_add():
    """Calling add_to_memory maps to client.add()."""
    client = FakeClient()

    result = await provider_base.call_function(client, "add_to_memory", {"content": "test fact"})

    assert client.calls == [("add", "test fact")]
    assert "mem_123" in result


@pytest.mark.asyncio
async def test_provider_call_search():
    """Calling search_memory maps to client.search()."""
    client = FakeClient()

    result = await provider_base.call_function(client, "search_memory", {"query": "what is X"})

    assert client.calls == [("search", "what is X")]
    assert "Found memory" in result


@pytest.mark.asyncio
async def test_provider_call_delete():
    """Calling delete_memory maps to client.delete()."""
    client = FakeClient()

    result = await provider_base.call_function(client, "delete_memory", {"memory_id": "mem_123"})

    assert client.calls == [("delete", "mem_123")]
    assert "Deleted" in result


@pytest.mark.asyncio
async def test_provider_call_modify():
    """Calling modify_memory maps to client.modify()."""
    client = FakeClient()

    result = await provider_base.call_function(client, "modify_memory", {"memory_id": "mem_123", "new_content": "updated"})

    assert client.calls == [("modify", "mem_123", "updated")]
    assert "Updated" in result


@pytest.mark.asyncio
async def test_provider_handles_errors():
    """Provider catches SupermemoryError and returns as string."""
    client = FakeClient(raise_on="add")

    result = await provider_base.call_function(client, "add_to_memory", {"content": "test"})

    assert "error" in result.lower() or "unreachable" in result.lower()


@pytest.mark.asyncio
async def test_provider_unknown_function():
    """Provider returns error for unknown function names."""
    client = FakeClient()

    result = await provider_base.call_function(client, "unknown_function", {})

    assert "unknown" in result.lower()


@pytest.mark.asyncio
async def test_provider_missing_arguments():
    """Provider returns error when required arguments are missing."""
    client = FakeClient()

    result = await provider_base.call_function(client, "add_to_memory", {})

    assert "error" in result.lower() or "missing" in result.lower()


def test_openai_tools_endpoint():
    """GET /api/providers/openai/tools returns function schema."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/providers/openai/tools")

    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 4
    assert response.headers.get("Access-Control-Allow-Origin") == "*"


def test_openai_call_endpoint_requires_auth():
    """POST /api/providers/openai/call requires X-Forwarded-User header."""
    app = create_app()
    client = TestClient(app)

    response = client.post("/api/providers/openai/call", json={"function_name": "add_to_memory", "arguments": {"content": "test"}})

    assert response.status_code == 401


def test_openai_call_endpoint_with_auth():
    """POST /api/providers/openai/call with auth executes function."""
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/providers/openai/call",
        json={"function_name": "add_to_memory", "arguments": {"content": "test"}},
        headers={"X-Forwarded-User": "test-user"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert data["error"] is None
