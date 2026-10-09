"""Complete Replicate MCP Server implementation for Twynity platform.

This module provides a production-ready server that enables authenticated Twynity personas
to connect their Replicate accounts, discover available models, execute predictions,
and access generated outputs through MCP tools and a dedicated UI.
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from logging import getLogger

# Third-party imports
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware as MCPMiddleware
from fastmcp.server.middleware import MiddlewareContext
from pymongo import AsyncMongoClient
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Project imports
from app.auth import get_auth_provider
from app.config import settings
from app.connection_store import ConnectionStore, set_active_store
from app.license import license_watcher
from app.tools.replicate import register_tools
from app.usage import save_usage_report

logger = getLogger(__name__)


@asynccontextmanager
async def app_lifespan(server):
    """Initialize and clean up async resources during application lifecycle.

    Creates MongoDB connection, initializes encrypted connection store,
    starts the license watcher coroutine, and sets up cleanup handlers.
    """
    mongo = AsyncMongoClient(settings.MONGODB_URI, tz_aware=True)
    task = None
    try:
        store = ConnectionStore(
            mongo[settings.DATABASE_NAME]["project_connections"],
            settings.ENCRYPTION_KEY,
        )
        await store.setup()
        set_active_store(store)

        # Start the license watcher background task
        task = asyncio.create_task(license_watcher())

        logger.info("Replicate MCP server started")
        yield

    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        set_active_store(None)
        await mongo.close()
        logger.info("Replicate MCP server shutdown complete")


# Create the FastMCP server instance with Twynity authentication
mcp = FastMCP(
    settings.APP_TITLE,
    auth=get_auth_provider(),
    lifespan=app_lifespan,
)

# Register Replicate tools following template conventions
register_tools(mcp)


class UsageTrackingMiddleware(MCPMiddleware):
    """Track tool usage for analytics and billing."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        try:
            headers = get_http_headers()

            # Extract user identity if available (may fail in tests without JWT)
            user_id = "unknown"
            persona_id = "unknown"
            try:
                from app.auth import get_identity_from_headers

                identity = await get_identity_from_headers(headers)
                user_id = identity.user_id[:8] + "..."  # Truncate for logs
                persona_id = (
                    identity.persona_id[:16] + "..."
                    if len(identity.persona_id) > 16
                    else identity.persona_id
                )
            except Exception:
                pass

            await save_usage_report(
                method="TOOL_CALL",
                endpoint=context.message.name,
                user_id=user_id,
                persona_id=persona_id,
            )
        except Exception:
            logger.exception("Usage tracking failed—continuing with tool call anyway")

        return await call_next(context)


# Add middleware after registering tools to ensure order of execution
mcp.add_middleware(UsageTrackingMiddleware())

origins = [
    origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )
]

# Create the ASGI application with middleware
app = mcp.http_app(middleware=middleware)


if __name__ == "__main__":
    import uvicorn

    # Load environment variables from .env if present
    from dotenv import load_dotenv

    load_dotenv()

    logger.info(f"Starting Replicate MCP server on {settings.PUBLIC_URL}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
