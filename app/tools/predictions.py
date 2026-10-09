"""Tools for executing predictions on Replicate models.
Provides typed wrappers around model execution, status checking, cancellation,
and polling operations while preserving credential privacy.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from fastmcp.tools import ToolResult
from starlette.exceptions import HTTPException

from app.connection_store import get_active_store


def _datetime_to_iso(dt_str: str | None) -> str | None:
    """Convert ISO datetime string to normalized format."""
    if not dt_str:
        return None
    return dt_str.replace("Z", "+00:00").strip()


async def create_prediction(
    model_version_id: str,
    input_data: dict[str, Any],
) -> ToolResult:
    """Execute a Replicate model with provided inputs.

    Use this tool when the user wants to run an AI model and receive
    generated output such as text, images, audio, or video. The tool
    automatically polls for completion and returns results.

    Args:
        model_version_id: Full version identifier e.g. "replicate/model:v1"
            or owner/model@uuid40hexchars format
        input_data: Model-specific parameters as JSON object. Required fields
            depend on the target model; refer to model documentation for details.

    Returns:
        Dictionary with prediction status, output preview, and metadata

    Raises:
        HTTPException: If missing credentials, invalid model format, or API error

    Examples:
        create_prediction(
            model_version_id="stability-ai/stable-diffusion",
            input_data={"prompt": "A cat on a window mat"}
        )
    """
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    store = get_active_store()
    if not store:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )

    identity = await get_identity_from_headers(get_http_headers())

    connection = await store.get(identity.user_id, identity.persona_id)
    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    # For Replicate API - we need to send the full model identifier
    headers = {"Authorization": f"Token {connection['api_token']}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Prepare the payload
        payload = {
            "input": input_data,
            "version": model_version_id.split(":")[-1]
            if ":" in model_version_id
            else model_version_id.split("@")[-1]
            if "@" in model_version_id
            else model_version_id,
        }

        response = await client.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 201:
        result = response.json()
        return ToolResult(
            content=f"Prediction started: {result.get('id', 'unknown')}",
            structured_content={
                "prediction_id": result.get("id"),
                "status": result.get("status", "pending"),
                "created_at": result.get("created_at"),
                "model_version": model_version_id,
                "input_data_preview": str(input_data)[:300],
            },
        )

    elif response.status_code == 400:
        raise HTTPException(
            status_code=400, detail=f"Invalid input for model: {response.text[:200]}"
        )

    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to create prediction: {response.text[:300]}",
        )


async def get_prediction(prediction_id: str) -> ToolResult:
    """Fetch current status of an existing prediction.

    Use this tool to check the progress or final result of a previously
    executed model run without re-triggering the original operation.

    Args:
        prediction_id: Replicate prediction identifier from a prior call

    Returns:
        PredictionInfo containing state, logs, and output preview

    Raises:
        HTTPException: If missing credentials or prediction not found
    """
    store = get_active_store()
    if not store:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )

    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    identity = await get_identity_from_headers(get_http_headers())

    connection = await store.get(identity.user_id, identity.persona_id)
    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Token {connection['api_token']}"}
        response = await client.get(
            f"https://api.replicate.com/v1/predictions/{prediction_id}",
            headers=headers,
        )

    if response.status_code == 200:
        data = response.json()
        status_val = data.get("status", "unknown")

        output_preview = None
        output_data = data.get("output")
        if output_data:
            if isinstance(output_data, list) and len(output_data) > 0:
                output_preview = [str(o)[:100] for o in output_data[:3]]
            else:
                output_preview = str(output_data)[:500]

        return ToolResult(
            content=f"Status: {status_val.replace('_', ' ').title()}",
            structured_content={
                "prediction_id": prediction_id,
                "status": status_val.title(),
                "created_at": _datetime_to_iso(data.get("created_at")),
                "started_at": _datetime_to_iso(data.get("started_at")),
                "completed_at": _datetime_to_iso(data.get("completed_at")),
                "logs": data.get("logs", "")[:1000],
                "error": data.get("error"),
                "output_preview": output_preview,
                "output_full_available": bool(output_data and len(output_data) > 3),
            },
        )

    elif response.status_code == 404:
        raise HTTPException(
            status_code=404, detail=f"Prediction {prediction_id} not found"
        )

    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to fetch prediction: {response.text[:200]}",
        )


async def cancel_prediction(prediction_id: str) -> ToolResult:
    """Cancel an active prediction.

    Use this tool when the user wants to stop a long-running model execution
    that is no longer needed (e.g., after finding output satisfactory or
    realizing input was incorrect).

    Args:
        prediction_id: Replicate prediction identifier of the job to cancel

    Returns:
        Cancellation confirmation with status and prediction ID

    Raises:
        HTTPException: If missing credentials, prediction not found, or terminal state
    """
    store = get_active_store()
    if not store:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )

    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    identity = await get_identity_from_headers(get_http_headers())

    connection = await store.get(identity.user_id, identity.persona_id)
    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Token {connection['api_token']}"}
        response = await client.post(
            f"https://api.replicate.com/v1/predictions/{prediction_id}/cancel",
            headers=headers,
        )

    if response.status_code in (200, 204):
        return ToolResult(
            content=f"Prediction {prediction_id} has been successfully cancelled",
            structured_content={
                "status": "cancelled",
                "prediction_id": prediction_id,
                "message": f"Prediction {prediction_id} cancellation confirmed",
            },
        )

    elif response.status_code == 404:
        raise HTTPException(
            status_code=404, detail=f"Prediction {prediction_id} not found"
        )

    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to cancel prediction: {response.text[:200]}",
        )


async def list_predictions(limit: int = 50) -> ToolResult:
    """List predictions accessible to the connected Replicate account.

    Use this tool to view history of model executions for auditing or
    re-accessing outputs from previous runs.

    Args:
        limit: Maximum predictions to return (default: 50, max: 100)

    Returns:
        Dictionary with prediction summaries and pagination info

    Raises:
        HTTPException: If missing credentials or API error
    """
    store = get_active_store()
    if not store:
        raise HTTPException(
            status_code=503, detail="Connection storage service unavailable"
        )

    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    identity = await get_identity_from_headers(get_http_headers())

    connection = await store.get(identity.user_id, identity.persona_id)
    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Token {connection['api_token']}"}
        response = await client.get(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            params={"limit": min(limit, 100)},
        )

    if response.status_code == 200:
        data = response.json()
        predictions = [
            {
                "id": p.get("id", ""),
                "status": p.get("status", "unknown"),
                "created_at": _datetime_to_iso(p.get("created_at")),
                "model_id": p.get("version", "").split(":")[0]
                if p.get("version")
                else "",
            }
            for p in data.get("results", [])
        ]

        return ToolResult(
            content=f"Found {len(predictions)} predictions",
            structured_content={
                "predictions": predictions,
                "has_more": bool(data.get("next")),
                "total_count": len(predictions),
            },
        )

    elif response.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Replicate API token")

    else:
        raise RuntimeError(f"Failed to list predictions: {response.text[:200]}")


async def wait_for_prediction(
    prediction_id: str,
    poll_interval: float = 2.0,
    max_wait_seconds: float = 300.0,
) -> ToolResult:
    """Poll prediction until terminal status or timeout.

    Use this tool when you need to wait for a long-running model execution
    with continuous updates rather than checking at random intervals.

    Args:
        prediction_id: Replicate prediction identifier
        poll_interval: Seconds between checks (default: 2.0)
        max_wait_seconds: Maximum total wait time (default: 300s)

    Returns:
        Final status dictionary with completion state and metadata

    Raises:
        HTTPException: If missing credentials during monitoring
        TimeoutError: If prediction exceeds max_wait_seconds
        RuntimeError: If final status is failed or requires additional input
    """
    from fastmcp.server.dependencies import get_http_headers

    from app.auth import get_identity_from_headers

    store = get_active_store()
    identity = await get_identity_from_headers(get_http_headers())

    connection = await store.get(identity.user_id, identity.persona_id)
    if not connection or "api_token" not in connection:
        raise HTTPException(
            status_code=401, detail="Replicate API token not configured"
        )

    import asyncio

    async with httpx.AsyncClient(timeout=max_wait_seconds) as client:
        headers = {"Authorization": f"Token {connection['api_token']}"}
        start_time = datetime.now(UTC)

        while True:
            elapsed = (datetime.now(UTC) - start_time).total_seconds()

            if elapsed > max_wait_seconds:
                raise HTTPException(
                    status_code=408,
                    detail=f"Timeout after {max_wait_seconds}s polling for prediction {prediction_id}",
                )

            response = await client.get(
                f"https://api.replicate.com/v1/predictions/{prediction_id}",
                headers=headers,
            )

            if response.status_code == 401:
                raise HTTPException(
                    status_code=401, detail="Invalid Replicate API token"
                )
            elif response.status_code != 200:
                raise RuntimeError(f"Failed to check prediction: {response.text[:200]}")

            data = response.json()
            status = data.get("status", "unknown")

            # Terminal states
            if status in ("succeeded", "failed", "cancelled"):
                return ToolResult(
                    content=f"Prediction completed: {status.title()}",
                    structured_content={
                        "prediction_id": prediction_id,
                        "final_status": status,
                        "created_at": _datetime_to_iso(data.get("created_at")),
                        "completed_at": _datetime_to_iso(data.get("completed_at")),
                        "logs": data.get("logs", "")[:2000],
                        "error": data.get("error"),
                        "output_preview": str(data.get("output", []))[:500]
                        if data.get("output")
                        else None,
                    },
                )

            # Input required state - needs manual intervention
            if status == "inputs_required":
                raise RuntimeError(
                    f"Prediction {prediction_id} requires additional input to continue"
                )

            await asyncio.sleep(poll_interval)


def _extract_version_uuid(model_or_version: str) -> str:
    """Extract 40-char UUID from model version identifier."""
    import re

    # Already UUID format - return as-is if valid hex of length 40
    if re.match(r"^[a-fA-F0-9]{40}$", model_or_version):
        return model_or_version

    # Extract UUID at end: owner/model:uuid or owner:model@uuid
    match = re.search(r":([a-fA-F0-9]{40})$", model_or_version)
    if match:
        return match.group(1)

    match_at = re.search(r"\\@([a-fA-F0-9]{40})$", model_or_version)
    if match_at:
        return match_at.group(1)

    raise ValueError(
        f"Invalid model version identifier: {model_or_version}. "
        "Expected format: UUID (40 hex chars)"
    )
