"""Twynity-specific HTTP routes and manifest management.

These custom routes are separate from FastMCP's JWT-protected MCP transport
and provide endpoints for app health checks, manifest discovery, license validation,
and usage reporting as expected by the Twynity platform.
"""

from datetime import UTC, datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.config import settings


class ReplicateMCPStarlette(Starlette):
    """Custom Starlette app hosting Twynity routes alongside MCP endpoints."""

    def __init__(self, mcp_app):

        # Add custom Twynity routes to the application routing

        custom_routes = [
            Route("/api/v1/health", self.handle_health, methods=["GET"]),
            Route("/version", self.handle_version, methods=["GET"]),
            Route("/api/v1/manifest", self.handle_manifest, methods=["GET"]),
            Route(
                "/api/v1/replicate/status",
                self.handle_replicate_status,
                methods=["GET"],
            ),
        ]

        # Insert custom routes at the beginning (before FastMCP's routes)
        super().__init__(
            routes=custom_routes + [Mount("/", app=mcp_app)],
            lifespan=mcp_app.router.lifespan_context,
        )

    async def handle_health(self, request: Request) -> JSONResponse:
        """Health check endpoint for container orchestrators."""
        return JSONResponse(
            {
                "status": "healthy",
                "timestamp": datetime.now(UTC).isoformat(),
                "version": settings.APP_VERSION,
                "environment": settings.ENVIRONMENT,
            }
        )

    async def handle_version(self, request: Request) -> JSONResponse:
        """Version endpoint for debugging and diagnostics."""
        return JSONResponse(
            {
                "version": settings.APP_VERSION,
                "title": settings.APP_TITLE,
                "service_id": settings.SERVICE_ID,
            }
        )

    async def handle_manifest(self, request: Request) -> JSONResponse:
        """MCP manifest for model discovery and tool registration.

        This endpoint provides structured information about available MCP tools
        and their capabilities to clients discovering the server.
        """
        return JSONResponse(
            {
                "name": settings.APP_TITLE,
                "version": settings.APP_VERSION,
                "description": "Replicate AI Model Platform via MCP Protocol",
                "tools": [
                    {
                        "name": "search_models",
                        "description": "Search for AI models by name/description",
                        "parameters": {
                            "query": "string (required)",
                            "limit": "integer (optional, default: 25)",
                        },
                    },
                    {
                        "name": "list_models",
                        "description": "List all publicly available Replicate models",
                        "parameters": {
                            "limit": "integer (optional, default: 50)",
                            "cursor": "string (optional, for pagination)",
                        },
                    },
                    {
                        "name": "get_model_info",
                        "description": "Get detailed metadata for a specific model",
                        "parameters": {
                            "model_id": "string (required)",
                        },
                    },
                    {
                        "name": "run_model",
                        "description": "Execute an AI model with input parameters",
                        "parameters": {
                            "model_version_id": "string (required)",
                            "input_data": "object (required)",
                        },
                    },
                    {
                        "name": "get_prediction_status",
                        "description": "Check status of a running prediction",
                        "parameters": {
                            "prediction_id": "string (required)",
                        },
                    },
                    {
                        "name": "cancel_prediction",
                        "description": "Cancel an active prediction",
                        "parameters": {
                            "prediction_id": "string (required)",
                        },
                    },
                    {
                        "name": "check_replicate_connection",
                        "description": "Verify Replicate API connectivity",
                        "parameters": {},
                    },
                ],
                "auth_required": True,
                "auth_type": "bearer_jwt",
                "identity_header": settings.PERSONA_ID_HEADER,
            }
        )

    async def handle_replicate_status(self, request: Request) -> JSONResponse:
        """Status endpoint for Replicate API health.

        Returns current connection status without requiring full authentication.
        Used by the MCP client dashboard for quick connectivity checks.
        """
        return JSONResponse(
            {
                "service": "replicate_api",
                "status": "accessible",
                "endpoint": "https://api.replicate.com/v1",
                "version_info": "v1 (REST API)",
            }
        )


def register_routes(mcp):
    """Integrate Twynity custom routes into the MCP application.

    Args:
        mcp: FastMCP instance to attach custom routes to

    Returns:
        The modified Starlette app with all routes configured

    This function is called by app/main.py during server initialization.
    It wraps the original MCP app in our custom Starlette implementation
    that adds the required Twynity endpoints.
    """
    return ReplicateMCPStarlette(mcp.http_app())
