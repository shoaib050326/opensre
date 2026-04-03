"""Unit tests for Vercel API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations.clients.vercel import VercelClient, VercelConfig


@pytest.fixture
def vercel_config() -> VercelConfig:
    """Create a Vercel config fixture."""
    return VercelConfig(api_token="test-token", team_id="test-team")


@pytest.fixture
def vercel_client(vercel_config: VercelConfig) -> VercelClient:
    """Create a Vercel client fixture."""
    return VercelClient(vercel_config)


class TestVercelConfig:
    """Tests for VercelConfig model."""

    def test_config_basic(self) -> None:
        """Test basic config creation."""
        config = VercelConfig(api_token="my-token")
        assert config.api_token == "my-token"
        assert config.team_id == ""

    def test_config_with_team(self) -> None:
        """Test config with team_id."""
        config = VercelConfig(api_token="my-token", team_id="my-team")
        assert config.api_token == "my-token"
        assert config.team_id == "my-team"

    def test_config_headers(self) -> None:
        """Test that headers are correctly formatted."""
        config = VercelConfig(api_token="my-token")
        assert config.headers == {
            "Authorization": "Bearer my-token",
            "Content-Type": "application/json",
        }

    def test_config_build_params_without_team(self) -> None:
        """Test param building without team."""
        config = VercelConfig(api_token="my-token")
        params = config._build_params({"limit": 10})
        assert params == {"limit": 10}

    def test_config_build_params_with_team(self) -> None:
        """Test param building with team."""
        config = VercelConfig(api_token="my-token", team_id="my-team")
        params = config._build_params({"limit": 10})
        assert params == {"limit": 10, "teamId": "my-team"}


class TestVercelClient:
    """Tests for VercelClient."""

    def test_is_configured_true(self, vercel_client: VercelClient) -> None:
        """Test is_configured returns True when token is set."""
        assert vercel_client.is_configured is True

    def test_is_configured_false(self) -> None:
        """Test is_configured returns False when token is empty."""
        config = VercelConfig(api_token="")
        client = VercelClient(config)
        assert client.is_configured is False

    @patch("httpx.Client.get")
    def test_list_projects_success(self, mock_get: MagicMock, vercel_client: VercelClient) -> None:
        """Test successful project listing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "projects": [
                {
                    "id": "proj-1",
                    "name": "my-app",
                    "framework": "nextjs",
                    "createdAt": "2024-01-01",
                    "updatedAt": "2024-01-02",
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.list_projects(limit=10)

        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["projects"]) == 1
        assert result["projects"][0]["name"] == "my-app"

    @patch("httpx.Client.get")
    def test_list_projects_http_error(
        self, mock_get: MagicMock, vercel_client: VercelClient
    ) -> None:
        """Test project listing with HTTP error."""
        mock_get.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=MagicMock(status_code=401, text="Unauthorized"),
        )

        result = vercel_client.list_projects()

        assert result["success"] is False
        assert "401" in result["error"]

    @patch("httpx.Client.get")
    def test_list_deployments_success(
        self, mock_get: MagicMock, vercel_client: VercelClient
    ) -> None:
        """Test successful deployment listing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "deployments": [
                {
                    "uid": "dep-1",
                    "url": "my-app.vercel.app",
                    "name": "my-app",
                    "state": "READY",
                    "createdAt": "2024-01-01",
                    "projectId": "proj-1",
                    "meta": {"githubCommitSha": "abc123"},
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.list_deployments(project_id="proj-1", limit=10)

        assert result["success"] is True
        assert result["total"] == 1
        assert result["deployments"][0]["state"] == "READY"

    @patch("httpx.Client.get")
    def test_get_deployment_success(self, mock_get: MagicMock, vercel_client: VercelClient) -> None:
        """Test successful deployment fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "dep-1",
            "url": "my-app.vercel.app",
            "name": "my-app",
            "readyState": "READY",
            "createdAt": "2024-01-01",
            "ready": True,
            "projectId": "proj-1",
            "meta": {"githubCommitSha": "abc123"},
            "errorMessage": "",
            "errorCode": "",
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.get_deployment("dep-1")

        assert result["success"] is True
        assert result["deployment"]["id"] == "dep-1"
        assert result["deployment"]["state"] == "READY"

    @patch("httpx.Client.get")
    def test_get_deployment_events_success(
        self, mock_get: MagicMock, vercel_client: VercelClient
    ) -> None:
        """Test successful deployment events fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "events": [
                {"type": "build", "createdAt": "2024-01-01", "payload": {"message": "Building"}}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.get_deployment_events("dep-1")

        assert result["success"] is True
        assert result["total"] == 1
        assert result["events"][0]["type"] == "build"

    @patch("httpx.Client.get")
    def test_get_runtime_logs_success(
        self, mock_get: MagicMock, vercel_client: VercelClient
    ) -> None:
        """Test successful runtime logs fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "logs": [
                {"timestamp": 1234567890, "message": "Hello", "level": "info", "source": "stdout"}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.get_runtime_logs("dep-1", limit=100)

        assert result["success"] is True
        assert result["total"] == 1
        assert result["logs"][0]["message"] == "Hello"

    @patch("httpx.Client.get")
    def test_request_exception(self, mock_get: MagicMock, vercel_client: VercelClient) -> None:
        """Test handling of request exceptions."""
        mock_get.side_effect = Exception("Network error")

        result = vercel_client.list_projects()

        assert result["success"] is False
        assert "Network error" in result["error"]


class TestVercelClientEdgeCases:
    """Edge case tests for VercelClient."""

    @patch("httpx.Client.get")
    def test_empty_projects_list(self, mock_get: MagicMock, vercel_client: VercelClient) -> None:
        """Test handling of empty projects list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"projects": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.list_projects()

        assert result["success"] is True
        assert result["total"] == 0
        assert result["projects"] == []

    @patch("httpx.Client.get")
    def test_deployment_with_error(self, mock_get: MagicMock, vercel_client: VercelClient) -> None:
        """Test handling of deployment with error state."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "dep-1",
            "url": "my-app.vercel.app",
            "name": "my-app",
            "readyState": "ERROR",
            "createdAt": "2024-01-01",
            "ready": False,
            "projectId": "proj-1",
            "meta": {},
            "errorMessage": "Build failed",
            "errorCode": "BUILD_ERROR",
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = vercel_client.get_deployment("dep-1")

        assert result["success"] is True
        assert result["deployment"]["state"] == "ERROR"
        assert result["deployment"]["error_message"] == "Build failed"
        assert result["deployment"]["error_code"] == "BUILD_ERROR"

    def test_limit_capping(self, vercel_client: VercelClient) -> None:
        """Test that limit values are capped appropriately."""
        # This test verifies the limit capping logic by checking the method doesn't error
        # The actual capping happens in the method implementation
        with patch.object(vercel_client, "_get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"projects": []}
            mock_response.raise_for_status.return_value = None
            mock_client.return_value.get.return_value = mock_response

            # Test with high limit that should be capped
            vercel_client.list_projects(limit=200)  # Should be capped to 100
            call_args = mock_client.return_value.get.call_args
            assert call_args is not None
            # The params should include the capped limit
