"""OpenAI Function Calling provider adapter."""

from server.tools import TOOLS


def get_tools_schema() -> dict:
    """Return all tools in OpenAI Function Calling format."""
    return {"tools": [tool.to_openai_format() for tool in TOOLS]}
