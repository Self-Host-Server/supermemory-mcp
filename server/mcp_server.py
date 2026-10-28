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


OAUTH_SCOPES = ["openid", "email", "profile", "offline_access"]


def build_server(client: SupermemoryClient, public_url: str = "", authentik_host: str = "") -> MCPServer:
    """Build the MCP server, wiring both tools to `client`.

    With `public_url` and `authentik_host` set, also serve OAuth discovery
    metadata (RFC 9728 + RFC 8414) pointing MCP clients at Authentik.
    """
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

    if public_url and authentik_host:
        resource_metadata = {
            "resource": f"{public_url}/mcp",
            # This server, not Authentik: Authentik serves no RFC 8414 document,
            # so the one below re-publishes its endpoints.
            "authorization_servers": [public_url],
            "scopes_supported": OAUTH_SCOPES,
            "bearer_methods_supported": ["header"],
        }
        server_metadata = {
            "issuer": public_url,
            "authorization_endpoint": f"{authentik_host}/application/o/authorize/",
            "token_endpoint": f"{authentik_host}/application/o/token/",
            "scopes_supported": OAUTH_SCOPES,
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        }

        # Clients try the path-suffixed form first, then the root.
        @server.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
        @server.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
        async def protected_resource(request: Request) -> JSONResponse:
            return JSONResponse(resource_metadata)

        @server.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
        async def authorization_server(request: Request) -> JSONResponse:
            return JSONResponse(server_metadata)

    return server
