"""Provider-agnostic tool definitions.

Each tool describes its interface so it can be exposed to any AI provider
(MCP, OpenAI Function Calling, Google Gemini, etc.) without duplication.
"""

from dataclasses import dataclass


@dataclass
class ToolParameter:
    """A single parameter of a tool."""

    name: str
    type: str
    description: str
    required: bool = True


@dataclass
class ToolDefinition:
    """A tool description that can convert to any provider format."""

    name: str
    description: str
    parameters: list[ToolParameter]

    def to_openai_format(self) -> dict:
        """Convert to OpenAI Function Calling schema."""
        properties = {}
        required_names = []

        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }
            if param.required:
                required_names.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_names,
                },
            },
        }

    def to_gemini_format(self) -> dict:
        """Convert to Google Gemini tool format."""
        properties = {}

        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description,
            }

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": [p.name for p in self.parameters if p.required],
            },
        }


TOOLS = [
    ToolDefinition(
        name="add_to_memory",
        description="Store a fact or decision in long-term memory for later recall.",
        parameters=[
            ToolParameter(
                name="content",
                type="string",
                description="The fact or decision to remember. Be concise and specific.",
            ),
        ],
    ),
    ToolDefinition(
        name="search_memory",
        description="Search long-term memory for information about the user, past decisions, or stored facts.",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="What information are you looking for?",
            ),
        ],
    ),
    ToolDefinition(
        name="delete_memory",
        description="Delete a specific memory by its ID.",
        parameters=[
            ToolParameter(
                name="memory_id",
                type="string",
                description="The ID of the memory to delete.",
            ),
        ],
    ),
    ToolDefinition(
        name="modify_memory",
        description="Update the content of an existing memory by its ID.",
        parameters=[
            ToolParameter(
                name="memory_id",
                type="string",
                description="The ID of the memory to update.",
            ),
            ToolParameter(
                name="new_content",
                type="string",
                description="The updated content for the memory.",
            ),
        ],
    ),
]

TOOL_NAMES_TO_CLIENT_METHODS = {
    "add_to_memory": "add",
    "search_memory": "search",
    "delete_memory": "delete",
    "modify_memory": "modify",
}
