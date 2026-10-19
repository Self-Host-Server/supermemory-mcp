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
