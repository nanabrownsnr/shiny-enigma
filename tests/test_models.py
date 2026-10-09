"""Tests for Replicate MCP server tools - model discovery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.exceptions import HTTPException


class MockIdentity:
    def __init__(self, user_id="user123", persona_id="persona456"):
        self.user_id = user_id
        self.persona_id = persona_id


@pytest.fixture
def mock_connection_store():
    """Mock connection store for testing."""
    with patch("app.tools.models.get_active_store") as mock_store:
        yield mock_store


@pytest.fixture
def mock_identity():
    """Mock identity for testing."""
    with patch("app.tools.models.get_identity_from_headers") as mock_identity:
        mock_identity.return_value = MockIdentity()
        yield mock_identity


def _make_store_mock():
    """Helper to create a properly set up async store mock."""
    mock_store_instance = AsyncMock()
    mock_store_instance.get = AsyncMock(return_value={"api_token": "test-token"})
    return mock_store_instance


class TestListModels:
    """Tests for list_models tool."""

    @pytest.mark.asyncio
    async def test_list_models_success(self):
        """Test successful model listing."""
        from app.tools.models import list_models

        with (
            patch("app.tools.models.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.models.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "results": [
                    {"id": "model-1", "name": "Model 1", "description": "Description 1"}
                ],
                "next": None,
            }
            mock_client_class.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await list_models(limit=10)

            assert hasattr(result, "structured_content")
            assert len(result.structured_content["models"]) == 1
            assert result.structured_content["models"][0]["id"] == "model-1"

    @pytest.mark.asyncio
    async def test_list_models_api_error(self):
        """Test handling of API errors."""
        from app.tools.models import list_models

        with (
            patch("app.tools.models.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.models.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_client_class.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            with pytest.raises(RuntimeError) as exc_info:
                await list_models(limit=10)

            assert "Failed to list models" in str(exc_info.value)


class TestSearchModels:
    """Tests for search_models tool."""

    @pytest.mark.asyncio
    async def test_search_matches(self):
        """Test successful model search."""
        from app.tools.models import search_models

        with (
            patch("app.tools.models.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.models.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "results": [
                    {
                        "id": "image-gen-model",
                        "name": "Image Gen Pro",
                        "description": "High quality image generation",
                    },
                    {
                        "id": "text-to-speech",
                        "name": "TTS Engine",
                        "description": "Text to speech synthesis",
                    },
                ],
            }
            mock_client_class.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await search_models("image", 5)

            assert hasattr(result, "structured_content")
            results = result.structured_content["results"]
            ids = [r["id"] for r in results]
            assert "image-gen-model" in ids

    @pytest.mark.asyncio
    async def test_search_no_matches(self):
        """Test search with no matching models."""
        from app.tools.models import search_models

        with (
            patch("app.tools.models.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.models.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"results": []}
            mock_client_class.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await search_models("nonexistent-model-xyz", 10)

            assert result.structured_content["total"] == 0


class TestGetModelInfo:
    """Tests for get_model_info tool."""

    @pytest.mark.asyncio
    async def test_get_model_info_success(self):
        """Test successful model info retrieval."""
        from app.tools.models import get_model_info

        with (
            patch("app.tools.models.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.models.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "id": "stability-ai/stable-diffusion",
                "name": "Stable Diffusion XL",
                "description": "High quality image generation model",
                "versions": [
                    {
                        "id": "v1.0",
                        "input": {"prompt": "string"},
                        "output": "array[string]",
                    }
                ],
            }
            mock_client_class.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await get_model_info("stability-ai/stable-diffusion")

            assert hasattr(result, "structured_content")
            assert (
                result.structured_content["model_id"] == "stability-ai/stable-diffusion"
            )
            assert len(result.structured_content["versions"]) > 0

    @pytest.mark.asyncio
    async def test_get_model_not_found(self):
        """Test handling of non-existent model."""
        from app.tools.models import get_model_info

        with (
            patch("app.tools.models.get_active_store") as mock_store,
            patch("app.auth.get_identity_from_headers", return_value=MockIdentity()),
            patch("app.tools.models.httpx.AsyncClient") as mock_client_class,
        ):
            mock_store.return_value = _make_store_mock()

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client_class.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_model_info("non-existent-model")

            assert exc_info.value.status_code == 404
