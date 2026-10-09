"""Tools for interacting with connections and credentials.

Provides safe connection retrieval that never exposes secrets through MCP responses or logs.
"""

from fastmcp.server.dependencies import get_http_headers
from starlette.exceptions import HTTPException

from app.auth import get_identity_from_headers
from app.connection_store import get_active_store


class ConnectionError(Exception):
    """Raised when connection operations fail."""

    pass


async def get_current_connection() -> dict | None:
    """Return decrypted credentials for verified user/persona pair.

    Call this inside tool handlers. Never accept user_id/persona_id as tool
    arguments: the MCP host supplies authenticated identity and Persona-Id headers.

    Raises:
        HTTPException: If identity cannot be resolved or stored unavailable
    """
    identity = await get_identity_from_headers(get_http_headers())
    store = get_active_store()

    if store is None:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )

    return await store.get(identity.user_id, identity.persona_id)


async def verify_connection_exists() -> bool:
    """Check if credentials exist without exposing them.

    Returns:
        True if connection exists for authenticated identity
    """
    from fastmcp.server.dependencies import get_http_headers

    try:
        identity = await get_identity_from_headers(get_http_headers())
        store = get_active_store()
        if store is None:
            return False

        # Just check existence, don't decrypt or expose credentials
        document = list(
            store.collection.find(
                {"user_id": identity.user_id, "persona_id": identity.persona_id},
                {"_id": 1},
            ).limit(1)
        )
        return len(document) > 0
    except Exception:
        return False


async def get_connection_metadata() -> dict | None:
    """Return display metadata without credentials.

    Returns:
        Metadata dictionary with name and ID, or None if no connection exists
    """
    from fastmcp.server.dependencies import get_http_headers

    identity = await get_identity_from_headers(get_http_headers())
    store = get_active_store()
    if store is None:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )

    return await store.public_metadata(identity.user_id, identity.persona_id)
