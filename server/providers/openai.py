"""OpenAI Function Calling provider adapter."""

from server.client import SupermemoryClient
from server.providers import Provider
from server.tools import TOOLS


class OpenAIProvider(Provider):
    """Adapts Supermemory tools to OpenAI Function Calling format."""

    def get_tools_schema(self) -> dict:
        """Return all tools in OpenAI Function Calling format."""
        return {"tools": [tool.to_openai_format() for tool in TOOLS]}
