"""SupermemoryClient against a mocked backend.

Request/response shapes come from docs/superpowers/specs/supermemory-api-contract.md
(probed live in Task 0), not from the plan's original guesses.
"""

import logging

import pytest
import requests

from server.client import SupermemoryClient, SupermemoryError
from server.config import Settings

API_KEY = "sm_secret_key_do_not_log"
MEMORIES_URL = "http://backend:6767/v4/memories"
SEARCH_URL = "http://backend:6767/v4/search"


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPERMEMORY_API_URL", "http://backend:6767")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", API_KEY)
    monkeypatch.setenv("SUPERMEMORY_CONTAINER_TAG", "test_tag")
    return Settings()


@pytest.fixture
def client(settings):
    return SupermemoryClient(settings)


def test_add_posts_memories_array_to_memories_endpoint(client, requests_mock):
    """Contract: `memories` is a required array, and 201 is the success code."""
    requests_mock.post(
        MEMORIES_URL,
        json={
            "documentId": "jG6XA2dDuVnDdSCPixaBj3",
            "memories": [
                {
                    "id": "mem_abc123",
                    "memory": "the blue folder is on the desk",
                    "isStatic": False,
                    "createdAt": "2026-10-18T03:36:23.954Z",
                    "metadata": None,
                }
            ],
        },
        status_code=201,
    )

    result = client.add("the blue folder is on the desk")

    assert "mem_abc123" in result
    sent = requests_mock.last_request.json()
    assert sent["memories"] == [{"content": "the blue folder is on the desk"}]
    assert sent["containerTag"] == "test_tag"
    assert requests_mock.last_request.headers["Authorization"] == f"Bearer {API_KEY}"


def test_add_falls_back_to_document_id(client, requests_mock):
    """A 201 without a memories array still confirms rather than crashing."""
    requests_mock.post(MEMORIES_URL, json={"documentId": "doc_xyz789"}, status_code=201)

    assert "doc_xyz789" in client.add("anything")


def test_search_posts_q_and_joins_memory_fields(client, requests_mock):
    """Contract: query key is `q`; stored text lives in results[].memory."""
    requests_mock.post(
        SEARCH_URL,
        json={
            "results": [
                {"id": "a", "memory": "first memory", "similarity": 0.85, "version": 1},
                {"id": "b", "memory": "second memory", "similarity": 0.71, "version": 1},
            ],
            "timing": 64,
            "total": 2,
        },
        status_code=200,
    )

    result = client.search("blue folder")

    assert "first memory" in result
    assert "second memory" in result
    sent = requests_mock.last_request.json()
    assert sent["q"] == "blue folder"
    # Binding ruling from Task 0: never omit containerTag -- doing so searches
    # every container on the instance and leaks other deployments' memories.
    assert sent["containerTag"] == "test_tag"


def test_search_returns_empty_string_when_no_results(client, requests_mock):
    """Review Focus 4: the no-match shape is distinguishable from a hit."""
    requests_mock.post(SEARCH_URL, json={"results": [], "timing": 106, "total": 0}, status_code=200)

    assert client.search("nothing matches this") == ""


def test_search_skips_results_with_null_memory(client, requests_mock):
    """A forgotten/redacted result carries `memory: null` -- it must not crash the call.

    `dict.get("memory", "")` returns None for a present-but-null key, so calling a
    string method on it unguarded raises AttributeError. Remove the guard in
    search() and this test fails.
    """
    requests_mock.post(
        SEARCH_URL,
        json={
            "results": [
                {"id": "a", "memory": None, "similarity": 0.9, "version": 1},
                {"id": "b", "memory": "surviving memory", "similarity": 0.8, "version": 1},
            ],
            "timing": 51,
            "total": 2,
        },
        status_code=200,
    )

    result = client.search("blue folder")

    assert result == "surviving memory"


def test_search_returns_empty_string_when_every_memory_is_null(client, requests_mock):
    """All-null results degrade to the no-match answer rather than raising."""
    requests_mock.post(
        SEARCH_URL,
        json={"results": [{"id": "a", "memory": None}], "timing": 40, "total": 1},
        status_code=200,
    )

    assert client.search("blue folder") == ""


def test_backend_http_error_raises_supermemory_error(client, requests_mock):
    """Review Focus 1: a backend 401 surfaces as a clear error, not a crash."""
    requests_mock.post(SEARCH_URL, json={"error": "Unauthorized"}, status_code=401)

    with pytest.raises(SupermemoryError) as exc:
        client.search("anything")

    assert "401" in str(exc.value)


def test_backend_unreachable_raises_supermemory_error(client, requests_mock):
    """Review Focus 1: connection failure is bounded and reported."""
    requests_mock.post(MEMORIES_URL, exc=requests.exceptions.ConnectTimeout)

    with pytest.raises(SupermemoryError) as exc:
        client.add("anything")

    assert "unreachable" in str(exc.value).lower()


def test_non_json_body_raises_supermemory_error(client, requests_mock):
    """A 200 with an HTML error page (proxy in the path) must not crash."""
    requests_mock.post(SEARCH_URL, text="<html>502 upstream</html>", status_code=200)

    with pytest.raises(SupermemoryError) as exc:
        client.search("anything")

    assert "non-json" in str(exc.value).lower()


def test_api_key_absent_from_logs_and_errors(client, requests_mock, caplog):
    """Review Focus 2: the key leaks into neither logs nor the raised message."""
    requests_mock.post(SEARCH_URL, json={"error": "boom"}, status_code=500)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(SupermemoryError) as exc:
            client.search("anything")

    assert API_KEY not in caplog.text
    assert API_KEY not in str(exc.value)
