"""Replicate API client for model and prediction operations.

Provides typed wrappers around Replicate HTTP API for model discovery,
prediction execution, and status checking.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx


class PredictionStatus(Enum):
    """Replicate prediction lifecycle states."""

    UNKNOWN = "unknown"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    INPUTS_REQUIRED = "inputs_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PredictionInfo:
    """Prediction status and metadata."""

    id: str
    version_id: str
    workflow_id: str | None
    input_data: dict[str, Any]
    output_data: list[Any] | None
    logs: str
    error: str | None
    metrics: dict[str, float]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    status: PredictionStatus
    cancel_reason: str | None = None


@dataclass
class ReplicateClient:
    """Client for Replicate API operations."""

    api_token: str
    base_url: str = "https://api.replicate.com"
    timeout: float = 30.0

    def _get_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Get authorization headers for Replicate API."""
        headers = {
            "Authorization": f"Token {self.api_token}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    async def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """Make authenticated request to Replicate API."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(kwargs.pop("headers", {}))

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            return response

    async def get_version(self, version_url: str) -> dict[str, Any]:
        """Fetch specific model version details.

        Args:
            version_url: Full Replicate URL to a specific version ID

        Returns:
            Version metadata including input/output schemas

        Raises:
            RuntimeError: On API error or invalid version URL format
        """
        response = await self._request("GET", version_url)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to get version: {response.status_code} - {response.text}"
            )
        return response.json()

    async def create_prediction(
        self,
        model_version_id: str,
        input_data: dict[str, Any],
        stream: bool = False,
    ) -> dict[str, Any]:
        """Create a new prediction.

        Args:
            model_version_id: Full version URL (e.g. "replicate/anyscale/llama-2-13b-chat...")
            input_data: Model input parameters
            stream: Whether to request streaming response

        Returns:
            Prediction metadata with id, status, and URLs

        Raises:
            RuntimeError: On API error or invalid model version format
        """
        endpoint = "/v1/predictions"

        payload = {
            "version": model_version_id.split(":")[-1],
            "input": input_data,
        }

        if stream:
            payload["stream"] = True

        response = await self._request("POST", endpoint, json=payload)
        if response.status_code in (201, 200):
            return response.json()
        elif response.status_code == 400:
            raise RuntimeError(f"Invalid input for model: {response.text}")
        else:
            raise RuntimeError(
                f"Failed to create prediction ({response.status_code}): {response.text}"
            )

    async def get_prediction(self, prediction_id: str) -> PredictionInfo:
        """Fetch current prediction status.

        Args:
            prediction_id: Replicate prediction ID

        Returns:
            Fully parsed PredictionInfo with resolved status enum

        Raises:
            RuntimeError: On API error or invalid prediction state
        """
        response = await self._request("GET", f"/v1/predictions/{prediction_id}")
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to get prediction {prediction_id}: {response.text}"
            )

        data = response.json()
        return _parse_prediction_info(data)

    async def cancel_prediction(self, prediction_id: str) -> dict[str, Any]:
        """Cancel an active prediction.

        Args:
            prediction_id: Replicate prediction ID

        Returns:
            Cancellation confirmation from API
        """
        response = await self._request(
            "POST", f"/v1/predictions/{prediction_id}/cancel"
        )
        if response.status_code in (200, 204):
            return {"status": "cancelled", "prediction_id": prediction_id}
        elif response.status_code == 404:
            raise RuntimeError(f"Prediction {prediction_id} not found")
        else:
            raise RuntimeError(
                f"Failed to cancel prediction {prediction_id}: {response.text}"
            )

    async def wait_until_completed(
        self,
        prediction_id: str,
        max_wait_seconds: float = 300.0,
        poll_interval: float = 2.0,
    ) -> PredictionInfo:
        """Poll until prediction reaches terminal state.

        Args:
            prediction_id: Replicate prediction ID to monitor
            max_wait_seconds: Maximum total wait time before timeout
            poll_interval: Seconds between polling attempts

        Returns:
            Final prediction state when terminal status reached

        Raises:
            TimeoutError: If prediction exceeds max_wait_seconds
            RuntimeError: If final status is failed or inputs_required
        """
        start = datetime.now(UTC)

        while True:
            # Calculate remaining time to wait
            elapsed = (datetime.now(UTC) - start).total_seconds()
            if elapsed > max_wait_seconds:
                raise TimeoutError(
                    f"Predictions {prediction_id} exceeded {max_wait_seconds}s limit"
                )

            status_response = await self.get_prediction(prediction_id)

            # Terminal states
            if status_response.status in (
                PredictionStatus.SUCCEEDED,
                PredictionStatus.FAILED,
                PredictionStatus.CANCELLED,
            ):
                return status_response

            # Input required: cannot proceed, stop waiting
            if status_response.status == PredictionStatus.INPUTS_REQUIRED:
                raise RuntimeError(
                    f"Prediction {prediction_id} requires additional input and "
                    "cannot continue via automated polling"
                )

            # Not terminal: wait then retry
            await asyncio.sleep(poll_interval)


def _parse_prediction_info(data: dict[str, Any]) -> PredictionInfo:
    """Convert Replicate API response to structured PredictionInfo."""
    return PredictionInfo(
        id=data.get("id", ""),
        version_id=data.get("version", ""),
        workflow_id=data.get("workflow_id"),
        input_data=data.get("input", {}),
        output_data=data.get("output"),
        logs=data.get("logs", ""),
        error=data.get("error"),
        metrics=data.get("metrics", {}),
        created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
        started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
        if data.get("started_at")
        else None,
        completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
        if data.get("completed_at")
        else None,
        status=PREDICTION_STATUS_MAP.get(data.get("status"), PredictionStatus.UNKNOWN),
        cancel_reason=data.get("cancelled_by", {}).get("reason")
        if data.get("cancelled_by")
        else None,
    )


# Status code to enum mapping
PREDICTION_STATUS_MAP: dict[str, PredictionStatus] = {
    "queued": PredictionStatus.QUEUED,
    "in_progress": PredictionStatus.IN_PROGRESS,
    "input_required": PredictionStatus.INPUTS_REQUIRED,
    "succeeded": PredictionStatus.SUCCEEDED,
    "failed": PredictionStatus.FAILED,
    "cancelling": PredictionStatus.CANCELLED,  # Transitional state; treat as cancelled
    "cancelled": PredictionStatus.CANCELLED,
}
