"""Replicate MCP App UI resource registration.

Provides the HTML view and routing for the interactive Replicate interface,
exposed through FastMCP's ui:// protocol with structured content integration.
"""

from pathlib import Path

from fastmcp.apps import AppConfig

VIEW_URI = "ui://replicate/main.html"
VIEW_PATH = Path(__file__).parent / "index.html"


def load_view_html() -> str:
    """Load the compiled UI template and explain how to build it if missing.

    Returns:
        The HTML content for the Replicate MCP App

    Raises:
        RuntimeError: If the view file does not exist (needs to be built first)
    """
    if not VIEW_PATH.is_file():
        raise RuntimeError(
            "The MCP App UI has not been built. Create app/ui/replicate/index.html "
            "with the React-based interface for model search, prediction execution, "
            "and output preview."
        )
    return VIEW_PATH.read_text(encoding="utf-8")


class ReplicateAppConfig(AppConfig):
    """Configuration for the Replicate MCP App.

    Configures visibility modes and routing parameters for optimal model/app integration.
    """

    resource_uri: str = VIEW_URI
    visibility: list[str] = ["model", "app"]
    title: str = "Replicate Model Execution"


def register_resource(mcp):
    """Register the Replicate MCP App UI with a FastMCP server instance.

    Args:
        mcp: The FastMCP server to attach the resource to

    Returns:
        None; registers the ui:// route directly on the mcp instance

    This function enables the MCP client (e.g., Twynity) to render the
    interactive Replicate interface when tool calls return structured content.
    """

    @mcp.resource(VIEW_URI, app=ReplicateAppConfig())
    def replicate_main_view():
        """Return the main HTML document for the Replicate MCP App."""
        return load_view_html()

    # Ensure the URI is accessible as both resource and direct route
    mcp.add_resource_endpoint(
        uri=VIEW_URI,
        handler=lambda: load_view_html(),
        content_type="text/html;charset=utf-8",
    )
