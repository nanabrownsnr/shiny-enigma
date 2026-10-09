"""Main entry point for registering Replicate MCP tools.

Exports tool registration functions that integrate with FastMCP's tool system.
Each tool is fully documented and follows the template's patterns.
"""

from typing import Any

from fastmcp.apps import AppConfig

# Shared view URI for Replicate MCP App UI
VIEW_URI = "ui://replicate/main.html"


def register_tools(mcp):
    """Register all Replicate tools with the given FastMCP instance.

    Args:
        mcp: FastMCP server instance to register tools on

    Returns:
        List of registered tool names for verification

    The registration uses FastMCP's decorator and AppConfig patterns to enable
    MCP App UI integration along with standard tool calls.
    """
    from app.tools.models import (
        get_model_info,
        get_model_version,
        list_models,
        search_models,
    )
    from app.tools.predictions import (
        cancel_prediction,
        create_prediction,
        get_prediction,
    )

    # Model discovery tools - no UI needed, standard tools
    @mcp.tool()
    async def search_models_tool(
        query: str = "image generation", limit: int = 25
    ) -> dict[str, Any]:
        """Search for matching AI models by name or description.

        Args:
            query: Search keywords (name, description, tags)
            limit: Maximum results to return (default: 25)

        Returns:
            Dictionary with matching models
        """
        result = await search_models(query, limit)
        return (
            result.structured_content
            if hasattr(result, "structured_content")
            else {"models": [], "has_more": False}
        )

    @mcp.tool()
    async def list_models_tool(
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List publicly available Replicate models.

        Args:
            limit: Maximum number of models to return (default: 50)
            cursor: Optional pagination cursor for next page

        Returns:
            Dictionary with model listings
        """
        result = await list_models(limit)
        return (
            result.structured_content
            if hasattr(result, "structured_content")
            else {
                "models": [],
                "has_more": False,
            }
        )

    @mcp.tool()
    async def get_model_info_tool(model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific model.

        Args:
            model_id: Model identifier e.g. "stability-ai/stable-diffusion"

        Returns:
            Complete model information dictionary
        """
        try:
            result = await get_model_info(model_id)
            return (
                result.structured_content
                if hasattr(result, "structured_content")
                else result
            )
        except Exception as e:
            return {"error": str(e), "model_id": model_id}

    @mcp.tool()
    async def get_model_version_tool(model_version_id: str) -> dict[str, Any]:
        """Get detailed information about a specific model version.

        Args:
            model_version_id: Full version identifier e.g. "replicate/model:v1"

        Returns:
            Complete version information dictionary
        """
        try:
            result = await get_model_version(model_version_id)
            return (
                result.structured_content
                if hasattr(result, "structured_content")
                else result
            )
        except Exception as e:
            return {"error": str(e), "version_id": model_version_id}

    # Prediction execution tools - these benefit from the MCP App UI
    @mcp.tool(
        app=AppConfig(
            resource_uri=VIEW_URI,
            visibility=["model", "app"],
        )
    )
    async def create_prediction_tool(
        model_version_id: str, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a Replicate model with the provided inputs.

        Use this tool when the user wants to generate AI output such as text,
        images, audio, or video using a specified model version. The tool
        automatically polls for completion and returns results.

        Args:
            model_version_id: Full version identifier e.g. "replicate/model:v1"
                Must be the complete Replicate model path including owner/name
            input_data: Model-specific parameters as JSON object. Requires:
                - prompt (for image generation): "A description of what to generate"
                - num_images (optional for images): Number of images to produce
                - width/height (for images): Output dimensions in pixels
                Refer to model documentation for all available parameters.

        Returns:
            Dictionary with prediction status, output preview, and metadata

        Raises:
            ValueError: If model_id is invalid format or input missing required fields
            HTTPException: API errors or authentication failures

        Examples:
            create_prediction_tool(
                model_version_id="stability-ai/stable-diffusion",
                input_data={"prompt": "A cat sitting on a window mat"}
            )

        Notes:
            - Long-running predictions are automatically polled up to ~5 minutes
            - For very long jobs, use get_prediction_status instead
            - Model-specific parameters must match the target model signature
        """
        # Call the prediction tool from predictions module directly
        result = await create_prediction(model_version_id, input_data)
        return (
            result.structured_content
            if hasattr(result, "structured_content")
            else result
        )

    @mcp.tool(
        app=AppConfig(
            resource_uri=VIEW_URI,
            visibility=["model", "app"],
        )
    )
    async def get_prediction_status_tool(prediction_id: str) -> dict[str, Any]:
        """Fetch current status of an existing prediction.

        Use this tool to check progress of a model execution or retrieve final results
        after completion without re-triggering the original operation.

        Args:
            prediction_id: Replicate prediction identifier from prior run

        Returns:
            Prediction status with output preview and logs
        """
        try:
            result = await get_prediction(prediction_id)
            return (
                result.structured_content
                if hasattr(result, "structured_content")
                else result
            )
        except Exception as e:
            return {"error": str(e), "prediction_id": prediction_id}

    @mcp.tool()
    async def cancel_prediction_tool(prediction_id: str) -> dict[str, Any]:
        """Cancel a running prediction.

        Args:
            prediction_id: Replicate prediction identifier of job to cancel

        Returns:
            Cancellation confirmation
        """
        try:
            result = await cancel_prediction(prediction_id)
            return (
                result.structured_content
                if hasattr(result, "structured_content")
                else {
                    "status": "cancelled",
                    "prediction_id": prediction_id,
                }
            )
        except Exception as e:
            return {"error": str(e), "prediction_id": prediction_id}

    # Connection health tool - useful for debugging
    @mcp.tool()
    async def check_replicate_connection() -> dict[str, Any]:
        """Check if Replicate API connection is valid.

        Use this tool to verify credentials and connectivity before running expensive predictions.

        Returns:
            Connection status with account info if available

        Examples:
            check_replicate_connection()  # Verify before batch operations
        """
        from fastmcp.server.dependencies import get_http_headers

        from app.auth import get_identity_from_headers
        from app.connection_store import get_active_store

        store = get_active_store()
        if not store:
            return {"status": "storage_unavailable", "available": False}

        identity = await get_identity_from_headers(get_http_headers())
        connection = await store.get(identity.user_id, identity.persona_id)

        if not connection or "api_token" not in connection:
            return {
                "status": "no_credentials",
                "error": "Replicate token required before using this MCP server",
                "available": False,
            }

        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"Authorization": f"Token {connection['api_token']}"}
            response = await client.get(
                "https://api.replicate.com/v1/models",
                headers=headers,
            )

        if response.status_code == 200:
            return {
                "status": "connected",
                "available": True,
                "message": "Replicate API connection successful",
            }
        elif response.status_code == 401:
            return {
                "status": "invalid_token",
                "error": "Replicate API token is invalid or expired",
                "available": False,
            }
        else:
            return {
                "status": "api_error",
                "error_code": response.status_code,
                "message": f"Connection test failed with status {response.status_code}",
                "available": False,
            }

    # List all registered tool names for verification
    registered = [
        "search_models",
        "list_models",
        "get_model_info",
        "get_model_version",
        "create_prediction",
        "get_prediction_status",
        "cancel_prediction",
        "check_replicate_connection",
    ]

    return registered


def register_ui_resource(mcp):
    """Register Replicate MCP App UI resource.

    Args:
        mcp: FastMCP server instance to register UI resource on

    This enables the MCP App interface for Replicate operations when the
    tool returns structured content with the ui:// URI reference.
    """
    from app.ui.replicate.resource import register_resource

    return register_resource(mcp)
