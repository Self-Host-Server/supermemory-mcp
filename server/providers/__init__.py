"""AI provider adapters.

Each provider implements a standard interface to expose Supermemory tools
in that provider's native format and handle function calls consistently.
"""

from abc import ABC, abstractmethod

from server.client import SupermemoryClient, SupermemoryError
from server.tools import TOOL_NAMES_TO_CLIENT_METHODS, TOOLS


class Provider(ABC):
    """Base class for all AI provider adapters."""

    def __init__(self, client: SupermemoryClient):
        self.client = client

    @abstractmethod
    def get_tools_schema(self) -> dict:
        """Return all tools in this provider's schema format."""
        pass

    async def call_function(self, function_name: str, arguments: dict) -> str:
        """Execute a function call. Returns result as string (never raises)."""
        try:
            method_name = TOOL_NAMES_TO_CLIENT_METHODS.get(function_name)
            if not method_name:
                return f"Unknown function: {function_name}"

            method = getattr(self.client, method_name, None)
            if not method:
                return f"Function {function_name} not implemented."

            if method_name == "add":
                result = method(arguments["content"])
            elif method_name == "search":
                result = method(arguments["query"])
            elif method_name == "delete":
                result = method(arguments["memory_id"])
            elif method_name == "modify":
                result = method(arguments["memory_id"], arguments["new_content"])
            else:
                return f"Unhandled function: {function_name}"

            if not result:
                return f"No result from {function_name}."
            return result

        except SupermemoryError as exc:
            return f"Supermemory error: {exc}"
        except KeyError as exc:
            return f"Missing required argument: {exc}"
        except Exception as exc:
            return f"Error executing {function_name}: {type(exc).__name__}: {exc}"
