"""ASGI entry point.

Transport is Streamable HTTP at /mcp. To serve SSE instead, swap
streamable_http_app() for sse_app() -- that mounts /sse plus /messages/,
and PROTECTED_PREFIXES below must then cover both.
"""

import logging
import os

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from server.client import SupermemoryClient
from server.config import get_settings
from server.mcp_server import build_server
from server.providers import base as provider_base
from server.providers import openai as openai_provider

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# Paths the proxy must have authenticated. /health and /api/providers/*/tools are deliberately absent.
PROTECTED_PREFIXES = ("/mcp", "/messages", "/sse", "/api/providers/*/call")


class ForwardedUserRequired(BaseHTTPMiddleware):
    """Reject traffic that did not come through the OAuth2 proxy.

    The proxy sets X-Forwarded-User after a successful login. A request
    without it to a protected path reached this container directly, so refuse it.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_protected = path.startswith(PROTECTED_PREFIXES) or path.startswith("/api/providers/") and path.endswith("/call")
        if is_protected and not request.headers.get("X-Forwarded-User"):
            logger.warning("Rejected unauthenticated %s %s", request.method, path)
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_app() -> Starlette:
    """Build the ASGI app: MCP at /mcp, health at /health, auth gate in front."""
    settings = get_settings()  # raises here, at startup, if a var is missing
    client = SupermemoryClient(settings)
    server = build_server(client, settings.mcp_public_url, settings.authentik_host)

    # The SDK's default Host check only allows localhost, which 421s every
    # proxied request. Rebinding protection guards localhost-bound servers;
    # this one is reachable only through oauth2-proxy + the gate below.
    app = server.streamable_http_app(transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    # Add OpenAI provider endpoints
    async def openai_tools(request: Request) -> JSONResponse:
        """Return tools in OpenAI Function Calling format. No auth required (like /health)."""
        schema = openai_provider.get_tools_schema()
        response = JSONResponse(schema)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    async def openai_call(request: Request) -> JSONResponse:
        """Execute an OpenAI function call. Requires X-Forwarded-User header."""
        try:
            body = await request.json()
            function_name = body.get("function_name")
            arguments = body.get("arguments", {})

            if not function_name:
                return JSONResponse({"error": "Missing function_name"}, status_code=400)

            result = await provider_base.call_function(client, function_name, arguments)
            return JSONResponse({"result": result, "error": None})
        except Exception as exc:
            logger.error("OpenAI call failed: %s", exc)
            return JSONResponse({"result": None, "error": str(exc)}, status_code=500)

    app.routes.append(Route("/api/providers/openai/tools", openai_tools, methods=["GET"]))
    app.routes.append(Route("/api/providers/openai/call", openai_call, methods=["POST"]))

    app.add_middleware(ForwardedUserRequired)
    logger.info("MCP server ready (containerTag=%s)", settings.supermemory_container_tag)
    return app


app = create_app()
