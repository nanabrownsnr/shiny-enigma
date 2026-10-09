"""Usage reporting and analytics tracking.

Provides functionality to record tool usage, API calls, and consumption metrics
for billing, analytics, and quota management by the Twynity platform.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from starlette.status import HTTP_200_OK


async def save_usage_report(
    method: str,
    endpoint: str,
    user_id: str = "unknown",
    persona_id: str = "unknown",
    success: bool = True,
    response_time_ms: float = 0.0,
) -> dict[str, Any]:
    """Save usage report to configured endpoint.

    Records tool calls, API requests, and execution metrics for analytics
    and billing purposes. All reports are sent asynchronously without blocking
    the calling operation.

    Args:
        method: Operation type e.g., "TOOL_CALL", "HTTP_REQUEST"
        endpoint: Specific operation name (tool name or route path)
        user_id: User identifier for analytics grouping
        persona_id: Persona/project identifier for multi-project support
        success: Boolean indicating whether the operation succeeded
        response_time_ms: Response time in milliseconds

    Returns:
        Dictionary with status and report ID if successful, error info otherwise

    Notes:
        - Reports are sent to USAGE_REPORT_ENDPOINT from .env configuration
        - Failures are logged but do not affect calling operations
        - All personally identifiable information is preserved per platform policy
    """
    from app.config import settings

    try:
        # Build report payload
        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "method": method,
            "endpoint": endpoint,
            "user_id": user_id,
            "persona_id": persona_id,
            "success": success,
            "response_time_ms": response_time_ms,
            "environment": settings.ENVIRONMENT,
        }

        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                settings.USAGE_REPORT_ENDPOINT,
                json=report,
                headers={"Content-Type": "application/json"},
            )

        if response.status_code in (HTTP_200_OK, 201):
            return {
                "status": "reported",
                "endpoint_reported_to": settings.USAGE_REPORT_ENDPOINT,
            }
        else:
            return {
                "status": "failed",
                "error": f"Status {response.status_code}",
            }

    except httpx.TimeoutException as exc:
        # Connection timeout - log and discard silently to avoid blocking
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Usage report timeout for {endpoint}: {exc}")

        return {
            "status": "timeout",
            "method": method,
            "endpoint": endpoint,
        }
    except httpx.ConnectError as exc:
        # Can't reach reporting service - silent failure is acceptable
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Usage report connection failed for {endpoint}: {exc}")

        return {
            "status": "connection_failed",
            "endpoint": endpoint,
        }
    except Exception as exc:
        # Unexpected error - log but continue operation normally
        import logging

        logger = logging.getLogger(__name__)
        logger.exception(f"Usage report failed for {endpoint}: {exc}")

        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "endpoint": endpoint,
        }


class UsageRecorder:
    """Class-based usage recorder with buffered writes."""

    def __init__(self, batch_size: int = 100, flush_interval: float = 60.0):
        """Initialize buffered usage recorder.

        Args:
            batch_size: Number of metrics to buffer before sending report
            flush_interval: Seconds between forced flushes if batch incomplete
        """
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffer: list[dict[str, Any]] = []

    def record(
        self,
        tool_name: str,
        input_params: dict | None = None,
        output_length: int | None = None,
    ) -> None:
        """Record a single usage event to the buffer.

        Args:
            tool_name: Name of the MCP tool being called
            input_params: Input parameter sizes (not contents) for analytics
            output_length: Output token/character count
        """
        self.buffer.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "tool": tool_name,
                "input_size_bytes": len(str(input_params or {})),
                "output_length": output_length,
            }
        )

    def flush(self) -> dict[str, Any]:
        """Send buffered metrics to reporting endpoint.

        Returns:
            Report status with details about the submission
        """
        if not self.buffer:
            return {"status": "nothing_to_flush"}

        result = save_usage_report(
            method="BATCH_USAGE",
            endpoint=self.flush_endpoint_name(),
            user_id="batch",
        )

        self.buffer.clear()
        return result

    def flush_endpoint_name(self) -> str:
        """Generate a unique name for the batch endpoint."""
        return f"usage_batch_{len(self.buffer)}_entries"


# Global recorder instance for module-level usage tracking
recorder = UsageRecorder()
