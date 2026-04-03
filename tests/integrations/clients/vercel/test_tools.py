"""Unit tests for Vercel investigation tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.clients.vercel import VercelConfig
from app.tools.VercelDeploymentStatusTool import _resolve_config as deployment_resolve_config
from app.tools.VercelDeploymentStatusTool import vercel_deployment_status
from app.tools.VercelLogsTool import _resolve_config as logs_resolve_config
from app.tools.VercelLogsTool import vercel_logs


class TestVercelDeploymentStatusTool:
    """Tests for VercelDeploymentStatusTool."""

    def test_resolve_config_from_args(self) -> None:
        """Test config resolution from provided arguments."""
        config = deployment_resolve_config("token-123", "team-456")
        assert config is not None
        assert config.api_token == "token-123"
        assert config.team_id == "team-456"

    def test_resolve_config_no_token(self) -> None:
        """Test config resolution returns None when no token."""
        config = deployment_resolve_config(None, None)
        assert config is None

    @patch.dict(
        "os.environ", {"VERCEL_API_TOKEN": "env-token", "VERCEL_TEAM_ID": "env-team"}, clear=True
    )
    def test_resolve_config_from_env(self) -> None:
        """Test config resolution from environment variables."""
        config = deployment_resolve_config(None, None)
        assert config is not None
        assert config.api_token == "env-token"
        assert config.team_id == "env-team"

    def test_vercel_available_true(self) -> None:
        """Test availability check with verified connection."""
        sources = {"vercel": {"connection_verified": True}}
        from app.tools.VercelDeploymentStatusTool import _vercel_available

        assert _vercel_available(sources) is True

    def test_vercel_available_false(self) -> None:
        """Test availability check without verified connection."""
        sources = {"vercel": {"connection_verified": False}}
        from app.tools.VercelDeploymentStatusTool import _vercel_available

        assert _vercel_available(sources) is False

    def test_vercel_available_missing(self) -> None:
        """Test availability check with missing vercel source."""
        sources = {}
        from app.tools.VercelDeploymentStatusTool import _vercel_available

        assert _vercel_available(sources) is False

    def test_deployment_status_extract_params(self) -> None:
        """Test parameter extraction from sources."""
        sources = {
            "vercel": {
                "vercel_api_token": "token-123",
                "vercel_team_id": "team-456",
                "project_id": "proj-789",
            }
        }
        from app.tools.VercelDeploymentStatusTool import _deployment_status_extract_params

        params = _deployment_status_extract_params(sources)
        assert params["vercel_api_token"] == "token-123"
        assert params["vercel_team_id"] == "team-456"
        assert params["project_id"] == "proj-789"
        assert params["limit"] == 10

    def test_deployment_status_no_config(self) -> None:
        """Test deployment status when no config is available."""
        result = vercel_deployment_status("", "", "")
        assert result["available"] is False
        assert "not configured" in result["error"].lower()

    @patch("app.tools.VercelDeploymentStatusTool.VercelClient")
    def test_deployment_status_success(self, mock_client_class: MagicMock) -> None:
        """Test successful deployment status fetch."""
        mock_client = MagicMock()
        mock_client.list_deployments.return_value = {
            "success": True,
            "deployments": [
                {
                    "id": "dep-1",
                    "name": "my-app",
                    "url": "my-app.vercel.app",
                    "state": "READY",
                    "created_at": "2024-01-01",
                    "project_id": "proj-1",
                    "meta": {
                        "githubCommitSha": "abc123",
                        "githubCommitMessage": "Fix bug",
                        "githubCommitRef": "main",
                        "githubCommitAuthor": "user",
                    },
                }
            ],
        }
        mock_client_class.return_value = mock_client

        result = vercel_deployment_status("token-123", "team-456", "proj-1")

        assert result["available"] is True
        assert result["total"] == 1
        assert result["deployments"][0]["git"]["commit_sha"] == "abc123"
        assert result["deployments"][0]["git"]["commit_message"] == "Fix bug"

    @patch("app.tools.VercelDeploymentStatusTool.VercelClient")
    def test_deployment_status_api_error(self, mock_client_class: MagicMock) -> None:
        """Test deployment status when API returns error."""
        mock_client = MagicMock()
        mock_client.list_deployments.return_value = {
            "success": False,
            "error": "API rate limit exceeded",
        }
        mock_client_class.return_value = mock_client

        result = vercel_deployment_status("token-123", "", "")

        assert result["available"] is False
        assert "rate limit" in result["error"].lower()


class TestVercelLogsTool:
    """Tests for VercelLogsTool."""

    def test_resolve_config_from_args(self) -> None:
        """Test config resolution from provided arguments."""
        config = logs_resolve_config("token-123", "team-456")
        assert config is not None
        assert config.api_token == "token-123"
        assert config.team_id == "team-456"

    def test_resolve_config_no_token(self) -> None:
        """Test config resolution returns None when no token."""
        config = logs_resolve_config(None, None)
        assert config is None

    def test_logs_extract_params(self) -> None:
        """Test parameter extraction from sources."""
        sources = {
            "vercel": {
                "vercel_api_token": "token-123",
                "vercel_team_id": "team-456",
                "deployment_id": "dep-789",
            }
        }
        from app.tools.VercelLogsTool import _logs_extract_params

        params = _logs_extract_params(sources)
        assert params["vercel_api_token"] == "token-123"
        assert params["vercel_team_id"] == "team-456"
        assert params["deployment_id"] == "dep-789"
        assert params["limit"] == 100

    def test_logs_no_config(self) -> None:
        """Test logs when no config is available."""
        result = vercel_logs("", "dep-123")
        assert result["available"] is False
        assert "not configured" in result["error"].lower()

    def test_logs_no_deployment_id(self) -> None:
        """Test logs when deployment_id is missing."""
        result = vercel_logs("token-123", "")
        assert result["available"] is False
        assert "deployment_id is required" in result["error"].lower()

    @patch("app.tools.VercelLogsTool.VercelClient")
    def test_logs_runtime_success(self, mock_client_class: MagicMock) -> None:
        """Test successful runtime logs fetch."""
        mock_client = MagicMock()
        mock_client.get_runtime_logs.return_value = {
            "success": True,
            "logs": [
                {"timestamp": 1234567890, "message": "Hello", "level": "info", "source": "stdout"},
                {"timestamp": 1234567891, "message": "Error", "level": "error", "source": "stderr"},
            ],
        }
        mock_client_class.return_value = mock_client

        result = vercel_logs("token-123", "dep-456", log_type="runtime", limit=50)

        assert result["available"] is True
        assert result["log_type"] == "runtime"
        assert result["total"] == 2
        assert result["logs"][0]["message"] == "Hello"
        mock_client.get_runtime_logs.assert_called_once_with("dep-456", limit=50)

    @patch("app.tools.VercelLogsTool.VercelClient")
    def test_logs_build_success(self, mock_client_class: MagicMock) -> None:
        """Test successful build logs (events) fetch."""
        mock_client = MagicMock()
        mock_client.get_deployment_events.return_value = {
            "success": True,
            "events": [
                {"type": "build", "created_at": "2024-01-01", "payload": {"message": "Building"}},
            ],
        }
        mock_client_class.return_value = mock_client

        result = vercel_logs("token-123", "dep-456", log_type="build")

        assert result["available"] is True
        assert result["log_type"] == "build"
        assert result["total"] == 1
        mock_client.get_deployment_events.assert_called_once_with("dep-456")

    @patch("app.tools.VercelLogsTool.VercelClient")
    def test_logs_api_error(self, mock_client_class: MagicMock) -> None:
        """Test logs when API returns error."""
        mock_client = MagicMock()
        mock_client.get_runtime_logs.return_value = {
            "success": False,
            "error": "Deployment not found",
        }
        mock_client_class.return_value = mock_client

        result = vercel_logs("token-123", "dep-456")

        assert result["available"] is False
        assert "deployment not found" in result["error"].lower()
