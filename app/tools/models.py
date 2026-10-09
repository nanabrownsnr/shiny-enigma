"""Tools for discovering and describing Replicate models.
Provides search, listing, and metadata retrieval operations to help users
identify suitable models for their use cases without executing predictions.
"""

import httpx
from fastmcp.tools import ToolResult
from starlette.exceptions import HTTPException

from app.connection_store import get_active_store


async def list_models(limit: int = 50) -> ToolResult:
    """List publicly available Replicate models.

    Use this tool to browse the catalog of AI models when you need to discover
    what models exist or search through available options.

    Args:
        limit: Maximum number of models to return (default: 50)

    Returns:
        Dictionary with model listings containing:
            - models: List of model summaries with id, name, description
            - has_more: Boolean indicating if additional pages exist
            - next_cursor: Cursor for fetching more results

    Raises:
        RuntimeError: If connection storage unavailable or API error
    """
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    store = get_active_store()
    if not store:
        raise HTTPException(status_code=503, detail="Connection storage unavailable")

    identity = await get_identity_from_headers(get_http_headers())
    connection = await store.get(identity.user_id, identity.persona_id)

    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    headers = {"Authorization": f"Token {connection['api_token']}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://api.replicate.com/v1/models",
            headers=headers,
            params={"limit": min(limit, 100)},
        )

    if response.status_code == 200:
        data = response.json()
        models = []

        for model in data.get("results", [])[:limit]:
            model_id = model.get("id", "")
            name = model.get(
                "name", model_id.split(":")[0] if ":" in model_id else model_id
            )

            models.append(
                {
                    "id": model_id,
                    "name": name,
                    "description": model.get("description", "No description available"),
                }
            )

        return ToolResult(
            content=f"Found {len(models)} publicly listed models",
            structured_content={
                "models": models,
                "has_more": bool(data.get("next")),
                "next_cursor": data.get("next"),
            },
        )

    elif response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Replicate API token")

    else:
        raise RuntimeError(f"Failed to list models: {response.status_code}")


async def search_models(query: str, limit: int = 25) -> ToolResult:
    """Search for matching AI models by name or description.

    Use this tool when you have specific model characteristics in mind and
    want to find models that match those criteria through keyword search.

    Args:
        query: Search keywords (name, description, tags)
        limit: Maximum results to return (default: 25)

    Returns:
        Dictionary with matching models contained:
            - results: List of model summaries sorted by relevance
            - total: Total number of matching models

    Raises:
        RuntimeError: If connection storage unavailable or API error

    Examples:
        search_models("image generation")  # Find image generation models
        search_models("text to speech")  # Find audio synthesis models
    """
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    store = get_active_store()
    if not store:
        raise RuntimeError("Connection storage unavailable")

    identity = await get_identity_from_headers(get_http_headers())
    connection = await store.get(identity.user_id, identity.persona_id)

    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    headers = {"Authorization": f"Token {connection['api_token']}"}

    # For search we need to collect all models to do client-side search
    page_size = 100
    limit = min(limit, 500)  # Limit for reasonable search load
    models = []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First get the first page
            response = await client.get(
                "https://api.replicate.com/v1/models",
                headers=headers,
                params={"limit": min(page_size, 100)},
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch models for search: {response.status_code}"
                )

            data = response.json()
            filtered = []
            query_lower = query.lower()

            for model in data.get("results", []):
                searchable = f"{model.get('name', '').lower()} {model.get('description', '').lower()}".strip()

                if (
                    query_lower in searchable
                    or query_lower in model.get("id", "").lower()
                ):
                    filtered.append(
                        {
                            "id": model.get("id", ""),
                            "name": model.get("name", ""),
                            "description": model.get(
                                "description", "No description available"
                            ),
                        }
                    )

            models.extend(filtered)

    except Exception as exc:
        raise RuntimeError(f"Failed to search models: {exc}") from exc

    return ToolResult(
        content=f"Found {len(models)} models matching '{query}'",
        structured_content={
            "results": models[:limit],
            "total": len(models),
        },
    )


async def get_model_info(model_id: str) -> ToolResult:
    """Retrieve detailed information about a specific model.

    Use this tool to obtain complete metadata including supported input parameters,
    output types, and example usage for an individual model.

    Args:
        model_id: Model identifier e.g. "stability-ai/stable-diffusion" or full path

    Returns:
        Complete model information dictionary containing:
            - id: Full model identifier with version
            - name: Display name of the model
            - description: Model description and capabilities
            - versions: List of available version metadata (truncated)
            - example_inputs: Sample parameter values

    Raises:
        HTTPException: If missing credentials or model not found

    Examples:
        get_model_info("stability-ai/stable-diffusion")
    """
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    store = get_active_store()
    if not store:
        raise RuntimeError("Connection storage unavailable")

    identity = await get_identity_from_headers(get_http_headers())
    connection = await store.get(identity.user_id, identity.persona_id)

    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    headers = {"Authorization": f"Token {connection['api_token']}"}
    # Normalize model_id - extract owner/model without version suffix
    base_model_id = model_id.split(":")[0].split("@")[0]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://api.replicate.com/v1/models/{base_model_id}",
            headers=headers,
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    elif response.status_code != 200:
        raise RuntimeError(f"Failed to get model info: {response.text[:200]}")

    data = response.json()

    # Build version summaries from available metadata
    versions = []
    for i, version in enumerate(
        data.get("versions", [])[:10]
    ):  # Limit first 10 versions
        try_version = list(model_id.split(":"))[1] if ":" in model_id else None

        version_str = {
            "version": str(i + 1),
            "id": f"v{version.get('id', '')[:16]}...",
            "input_fields": len(version.get("input", {}).keys()),
            "output_type": version.get("output", "unknown"),
        }

        if try_version and version.get("id") == try_version:
            version_str["is_matching"] = True

        versions.append(version_str)

    return ToolResult(
        content=f"Model {data.get('name', model_id)}: {data.get('description', 'No description')} - {len(versions)} versions available",
        structured_content={
            "model_id": data.get("id", model_id),
            "name": data.get("name", "Unknown Model"),
            "description": data.get("description", "No description available"),
            "author": "replicate"
            if ":" not in model_id
            else base_model_id.split("/")[0],
            "versions_available": len(versions),
            "versions": versions,
        },
    )


async def get_model_version(model_version_id: str) -> ToolResult:
    """Retrieve detailed information about a specific model version.

    Use this tool to obtain complete metadata for a particular model version,
    including input/output schemas, parameters, and supported formats.

    Args:
        model_version_id: Full version identifier e.g. "replicate/model:v1"

    Returns:
        Complete version information dictionary containing:
            - version_id: Full version identifier
            - input_schema: JSON schema for input parameters
            - output_schema: JSON schema for outputs
            - example_inputs: Sample input structures

    Raises:
        HTTPException: If missing credentials or version not found

    Examples:
        get_model_version("stability-ai/stable-diffusion:v1")
    """
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    store = get_active_store()
    if not store:
        raise RuntimeError("Connection storage unavailable")

    identity = await get_identity_from_headers(get_http_headers())
    connection = await store.get(identity.user_id, identity.persona_id)

    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    headers = {"Authorization": f"Token {connection['api_token']}"}
    # Extract version UUID from the full ID
    # Handle format like 'owner/model:uuid' or 'owner/model@uuid'
    if ":" in model_version_id:
        model_version_id.split(":")[-1]
    elif "@" in model_version_id:
        model_version_id.split("@")[-1]
    else:
        raise HTTPException(status_code=400, detail="Invalid model version format")

    # Try to get the specific model first
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://api.replicate.com/v1/models/{model_version_id}",
            headers=headers,
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404, detail=f"Model version {model_version_id} not found"
        )
    elif response.status_code != 200:
        raise RuntimeError(f"Failed to get model version info: {response.text[:200]}")

    data = response.json()

    return ToolResult(
        content=f"Version {data.get('id', 'unknown')} schema",
        structured_content={
            "version_id": data.get("id", model_version_id),
            "input_schema": data.get("input", {}),
            "output_schema": data.get("output", {}),
            "description": data.get("description", ""),
            "author": data.get("owner", "unknown"),
        },
    )


def get_connection_or_raise():
    """Get active connection with API token or raise HTTPException."""
    from app.connection_store import get_active_store

    store = get_active_store()
    if not store:
        raise HTTPException(status_code=503, detail="Connection storage unavailable")

    connection = get_active_store()
    if not connection:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )
    # sync: connection_store.get() returns dict or None synchronously for token lookup
    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    return connection


async def _get_connection() -> dict | None:
    """Internal helper to get current credentials or None."""
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers
    from app.connection_store import get_active_store

    identity = get_identity_from_headers(get_http_headers())
    store = get_active_store()
    if not store:
        return None

    return await store.get(identity.user_id, identity.persona_id)
