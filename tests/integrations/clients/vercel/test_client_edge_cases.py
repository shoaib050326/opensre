"""Enhanced unit tests for Vercel API client edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations.clients.vercel.client import (
    MAX_DEPLOYMENTS_LIMIT,
    MAX_LOGS_LIMIT,
    MAX_PROJECTS_LIMIT,
    RETRYABLE_STATUS_CODES,
    VercelClient,
    VercelConfig,
    _validate_id,
)


class TestIdValidation:
    """Tests for ID validation helper."""

    def test_validate_id_valid(self) -> None:
        """Test validation passes for valid IDs."""
        import re

        pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
        assert _validate_id("dpl_123abc", pattern, "deployment_id") == "dpl_123abc"
        assert _validate_id("my-project-123", pattern, "project_id") == "my-project-123"

    def test_validate_id_empty_raises(self) -> None:
        """Test validation fails for empty IDs."""
        import re

        pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_id("", pattern, "deployment_id")

    def test_validate_id_invalid_format(self) -> None:
        """Test validation fails for invalid ID formats."""
        import re

        pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
        with pytest.raises(ValueError, match="Invalid deployment_id format"):
            _validate_id("invalid@id#here", pattern, "deployment_id")


class TestVercelClientRetryLogic:
    """Tests for retry logic with exponential backoff."""

    @pytest.fixture
    def config(self) -> VercelConfig:
        return VercelConfig(api_token="test-token", team_id="test-team")

    @pytest.fixture
    def client(self, config: VercelConfig) -> VercelClient:
        return VercelClient(config)

    @patch("time.sleep")
    @patch("httpx.Client.get")
    def test_retry_on_rate_limit(
        self, mock_get: MagicMock, mock_sleep: MagicMock, client: VercelClient
    ) -> None:
        """Test retry on 429 rate limit with exponential backoff."""
        # First two calls fail with 429, third succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 429
        mock_response_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Rate limited", request=MagicMock(), response=mock_response_fail
        )

        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {"projects": []}
        mock_response_success.raise_for_status.return_value = None

        mock_get.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success,
        ]

        result = client.list_projects()

        assert result["success"] is True
        assert mock_get.call_count == 3
        # Verify exponential backoff: 1s, 2s
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch("time.sleep")
    @patch("httpx.Client.get")
    def test_no_retry_on_4xx_error(
        self, mock_get: MagicMock, mock_sleep: MagicMock, client: VercelClient
    ) -> None:
        """Test no retry on non-retryable 4xx errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_get.return_value = mock_response

        result = client.list_projects()

        assert result["success"] is False
        assert mock_get.call_count == 1  # No retries
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("httpx.Client.get")
    def test_retry_on_500_error(
        self, mock_get: MagicMock, mock_sleep: MagicMock, client: VercelClient
    ) -> None:
        """Test retry on 500 internal server error."""
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response_fail
        )

        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {"projects": []}
        mock_response_success.raise_for_status.return_value = None

        mock_get.side_effect = [mock_response_fail, mock_response_success]

        result = client.list_projects()

        assert result["success"] is True
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("time.sleep")
    @patch("httpx.Client.get")
    def test_max_retries_exhausted(
        self, mock_get: MagicMock, mock_sleep: MagicMock, client: VercelClient
    ) -> None:
        """Test failure after max retries exhausted."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service unavailable", request=MagicMock(), response=mock_response
        )
        mock_get.return_value = mock_response

        result = client.list_projects()

        assert result["success"] is False
        assert mock_get.call_count == 3  # MAX_RETRIES
        assert mock_sleep.call_count == 2  # Retries after 1st and 2nd attempts


class TestVercelClientLimits:
    """Tests for API limit enforcement."""

    @pytest.fixture
    def client(self) -> VercelClient:
        return VercelClient(VercelConfig(api_token="test-token"))

    @patch("httpx.Client.get")
    def test_list_projects_limit_capping(self, mock_get: MagicMock, client: VercelClient) -> None:
        """Test that limit is capped at MAX_PROJECTS_LIMIT."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"projects": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Request more than max
        client.list_projects(limit=200)

        call_args = mock_get.call_args
        assert call_args is not None
        params = call_args.kwargs.get("params", {})
        assert params["limit"] == MAX_PROJECTS_LIMIT

    @patch("httpx.Client.get")
    def test_list_deployments_limit_capping(
        self, mock_get: MagicMock, client: VercelClient
    ) -> None:
        """Test that limit is capped at MAX_DEPLOYMENTS_LIMIT."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"deployments": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client.list_deployments(limit=500)

        call_args = mock_get.call_args
        assert call_args is not None
        params = call_args.kwargs.get("params", {})
        assert params["limit"] == MAX_DEPLOYMENTS_LIMIT

    @patch("httpx.Client.get")
    def test_get_runtime_logs_limit_capping(
        self, mock_get: MagicMock, client: VercelClient
    ) -> None:
        """Test that limit is capped at MAX_LOGS_LIMIT."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"logs": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client.get_runtime_logs("dpl_123", limit=5000)

        call_args = mock_get.call_args
        assert call_args is not None
        params = call_args.kwargs.get("params", {})
        assert params["limit"] == MAX_LOGS_LIMIT


class TestVercelClientInputValidation:
    """Tests for input validation in client methods."""

    @pytest.fixture
    def client(self) -> VercelClient:
        return VercelClient(VercelConfig(api_token="test-token"))

    def test_get_deployment_invalid_id(self, client: VercelClient) -> None:
        """Test that invalid deployment_id raises error."""
        with pytest.raises(ValueError, match="Invalid deployment_id format"):
            client.get_deployment("invalid@id")

    def test_get_deployment_empty_id(self, client: VercelClient) -> None:
        """Test that empty deployment_id raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            client.get_deployment("")

    def test_get_deployment_events_invalid_id(self, client: VercelClient) -> None:
        """Test that invalid deployment_id raises error in events."""
        with pytest.raises(ValueError, match="Invalid deployment_id format"):
            client.get_deployment_events("bad@id")

    def test_get_runtime_logs_invalid_id(self, client: VercelClient) -> None:
        """Test that invalid deployment_id raises error in logs."""
        with pytest.raises(ValueError, match="Invalid deployment_id format"):
            client.get_runtime_logs("bad@id")

    def test_list_deployments_invalid_project_id(self, client: VercelClient) -> None:
        """Test that invalid project_id raises error."""
        with pytest.raises(ValueError, match="Invalid project_id format"):
            client.list_deployments(project_id="invalid#id")


class TestVercelClientMalformedResponses:
    """Tests for handling malformed API responses."""

    @pytest.fixture
    def client(self) -> VercelClient:
        return VercelClient(VercelConfig(api_token="test-token"))

    @patch("httpx.Client.get")
    def test_list_projects_non_dict_response(
        self, mock_get: MagicMock, client: VercelClient
    ) -> None:
        """Test handling when API returns non-dict."""
        mock_response = MagicMock()
        mock_response.json.return_value = "invalid json"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = client.list_projects()

        # Should handle gracefully and return empty list
        assert result["success"] is True
        assert result["projects"] == []

    @patch("httpx.Client.get")
    def test_list_deployments_missing_key(self, mock_get: MagicMock, client: VercelClient) -> None:
        """Test handling when deployments key is missing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # No 'deployments' key
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = client.list_deployments()

        assert result["success"] is True
        assert result["deployments"] == []
        assert result["total"] == 0

    @patch("httpx.Client.get")
    def test_get_deployment_null_response(self, mock_get: MagicMock, client: VercelClient) -> None:
        """Test handling when deployment API returns null."""
        mock_response = MagicMock()
        mock_response.json.return_value = None
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = client.get_deployment("dpl_123")

        # Should handle gracefully
        assert result["success"] is True
        assert result["deployment"]["id"] == "dpl_123"


class TestVercelClientRetryableStatusCodes:
    """Tests to verify all retryable status codes."""

    @pytest.mark.parametrize("status_code", list(RETRYABLE_STATUS_CODES))
    @patch("time.sleep")
    @patch("httpx.Client.get")
    def test_all_retryable_codes(
        self, mock_get: MagicMock, mock_sleep: MagicMock, status_code: int
    ) -> None:
        """Test that all defined retryable status codes trigger retries."""
        client = VercelClient(VercelConfig(api_token="test-token"))

        mock_response_fail = MagicMock()
        mock_response_fail.status_code = status_code
        mock_response_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response_fail
        )

        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {"projects": []}
        mock_response_success.raise_for_status.return_value = None

        mock_get.side_effect = [mock_response_fail, mock_response_success]

        result = client.list_projects()

        assert result["success"] is True
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once()
