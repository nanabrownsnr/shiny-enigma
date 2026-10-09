"""Tests for Replicate MCP server tools - prediction execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.exceptions import HTTPException


class MockIdentity:
    def __init__(self, user_id="user123", persona_id="persona456"):
        self.user_id = user_id
        self.persona_id = persona_id


def _make_store_mock():
    """Helper to create a properly set up async store mock."""
    mock_store_instance = AsyncMock()
    mock_store_instance.get = AsyncMock(return_value={"api_token": "test-token"})
    return mock_store_instance


def _make_response(status_code, json_data, text="OK"):
    """Helper to create a mocked httpx response."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.text = text
    return mock_response


def _make_client_response(mock_resp):
    """Configure httpx.AsyncClient mock for a single response."""
    mock_client_class = MagicMock()
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.post.return_value = mock_resp
    mock_client_class.return_value.__aenter__.return_value = mock_client
    return mock_client_class


class TestCreatePrediction:
    """Tests for create_prediction tool."""

    @pytest.mark.asyncio
    async def test_create_prediction_success(self):
        """Test successful prediction creation."""
        from app.tools.predictions import create_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(
                201,
                {
                    "id": "pred-123",
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                },
            )

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await create_prediction(
                model_version_id="stability-ai/stable-diffusion:v1.0",
                input_data={"prompt": "A cat"},
            )

            assert hasattr(result, "structured_content")
            assert result.structured_content["prediction_id"] == "pred-123"
            assert result.structured_content["status"] == "queued"

    @pytest.mark.asyncio
    async def test_create_prediction_invalid_input(self):
        """Test handling of invalid input."""
        from app.tools.predictions import create_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(400, {}, "Invalid input for model")

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await create_prediction(
                    model_version_id="stability-ai/stable-diffusion:v1.0",
                    input_data={"prompt": "A cat"},
                )

            assert exc_info.value.status_code == 400
            assert "Invalid input" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_prediction_no_credentials(self):
        """Test handling of missing credentials."""
        from app.tools.predictions import create_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
        ):
            mock_store_instance = AsyncMock()
            mock_store_instance.get = AsyncMock(return_value=None)
            mock_store.return_value = mock_store_instance

            with pytest.raises(HTTPException) as exc_info:
                await create_prediction(
                    model_version_id="stability-ai/stable-diffusion:v1.0",
                    input_data={"prompt": "A cat"},
                )

            assert exc_info.value.status_code == 401
            assert "Replicate API token not configured" in str(exc_info.value.detail)


class TestGetPrediction:
    """Tests for get_prediction tool."""

    @pytest.mark.asyncio
    async def test_get_prediction_success(self):
        """Test successful prediction status retrieval."""
        from app.tools.predictions import get_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(
                200,
                {
                    "id": "pred-123",
                    "status": "succeeded",
                    "created_at": "2023-01-01T00:00:00Z",
                    "completed_at": "2023-01-01T00:01:00Z",
                    "output": ["output1.jpg", "output2.jpg"],
                    "logs": "Processing completed",
                },
            )

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await get_prediction("pred-123")

            assert hasattr(result, "structured_content")
            assert result.structured_content["prediction_id"] == "pred-123"
            assert result.structured_content["status"] == "Succeeded"

    @pytest.mark.asyncio
    async def test_get_prediction_not_found(self):
        """Test handling of non-existent prediction."""
        from app.tools.predictions import get_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(404, {})

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await get_prediction("pred-123")

            assert exc_info.value.status_code == 404


class TestCancelPrediction:
    """Tests for cancel_prediction tool."""

    @pytest.mark.asyncio
    async def test_cancel_prediction_success(self):
        """Test successful prediction cancellation."""
        from app.tools.predictions import cancel_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(200, {})

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await cancel_prediction("pred-123")

            assert hasattr(result, "structured_content")
            assert result.structured_content["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_prediction_not_found(self):
        """Test handling of attempt to cancel non-existent prediction."""
        from app.tools.predictions import cancel_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(404, {})

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await cancel_prediction("pred-123")

            assert exc_info.value.status_code == 404


class TestListPredictions:
    """Tests for list_predictions tool."""

    @pytest.mark.asyncio
    async def test_list_predictions_success(self):
        """Test successful prediction listing."""
        from app.tools.predictions import list_predictions

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(
                200,
                {
                    "results": [
                        {
                            "id": "pred-1",
                            "status": "succeeded",
                            "created_at": "2023-01-01T00:00:00Z",
                            "version": "stability-ai/stable-diffusion:v1",
                        },
                        {
                            "id": "pred-2",
                            "status": "queued",
                            "created_at": "2023-01-01T00:01:00Z",
                            "version": "stability-ai/stable-diffusion:v1",
                        },
                    ],
                    "next": None,
                },
            )

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await list_predictions(limit=10)

            assert hasattr(result, "structured_content")
            assert len(result.structured_content["predictions"]) == 2
            assert result.structured_content["total_count"] == 2

    @pytest.mark.asyncio
    async def test_list_predictions_no_credentials(self):
        """Test handling of missing credentials."""
        from app.tools.predictions import list_predictions

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
        ):
            mock_store_instance = AsyncMock()
            mock_store_instance.get = AsyncMock(return_value=None)
            mock_store.return_value = mock_store_instance

            with pytest.raises(HTTPException) as exc_info:
                await list_predictions(limit=10)

            assert exc_info.value.status_code == 401
            assert "Replicate API token not configured" in str(exc_info.value.detail)


class TestWaitForPrediction:
    """Tests for wait_for_prediction tool."""

    @pytest.mark.asyncio
    async def test_wait_for_prediction_success(self):
        """Test successful prediction waiting."""
        from app.tools.predictions import wait_for_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response_1 = _make_response(
                200,
                {
                    "id": "pred-123",
                    "status": "in_progress",
                    "created_at": "2023-01-01T00:00:00Z",
                },
            )

            mock_response_2 = _make_response(
                200,
                {
                    "id": "pred-123",
                    "status": "succeeded",
                    "created_at": "2023-01-01T00:00:00Z",
                    "completed_at": "2023-01-01T00:01:00Z",
                    "output": ["output.jpg"],
                },
            )

            mock_client = AsyncMock()
            mock_client.get.side_effect = [mock_response_1, mock_response_2]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await wait_for_prediction("pred-123", poll_interval=0.01)

                assert hasattr(result, "structured_content")
                assert result.structured_content["final_status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_wait_for_prediction_timeout(self):
        """Test handling of prediction timeout."""
        from app.tools.predictions import wait_for_prediction

        with (
            patch("app.tools.predictions.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.predictions.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = _make_response(
                200,
                {
                    "id": "pred-123",
                    "status": "in_progress",
                    "created_at": "2023-01-01T00:00:00Z",
                },
            )

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(HTTPException) as exc_info:
                    await wait_for_prediction(
                        "pred-123", poll_interval=0.01, max_wait_seconds=0.01
                    )

                assert exc_info.value.status_code == 408
