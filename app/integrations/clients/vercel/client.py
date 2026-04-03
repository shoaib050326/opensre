"""Vercel API client for querying deployments, projects, and runtime logs.

Uses the Vercel REST API directly via httpx.
Credentials come from the user's Vercel integration stored in the Tracer web app DB.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx
from pydantic import field_validator

from app.strict_config import StrictConfigModel

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
VERCEL_API_BASE_URL = "https://api.vercel.com"

# API limits and defaults
MAX_PROJECTS_LIMIT = 100
MAX_DEPLOYMENTS_LIMIT = 100
MAX_LOGS_LIMIT = 1000
DEFAULT_LOGS_LIMIT = 100
DEFAULT_DEPLOYMENTS_LIMIT = 20
DEFAULT_PROJECTS_LIMIT = 20

# ID validation patterns (Vercel uses 24-char hex IDs)
_DEPLOYMENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_PROJECT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class VercelConfig(StrictConfigModel):
    """Normalized Vercel credentials for API access."""

    api_token: str
    team_id: str = ""

    @field_validator("team_id", mode="before")
    @classmethod
    def _normalize_team_id(cls, value: object) -> str:
        return str(value or "").strip()

    @property
    def base_url(self) -> str:
        return VERCEL_API_BASE_URL

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _build_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build query params including team_id if configured."""
        params: dict[str, Any] = {}
        if self.team_id:
            params["teamId"] = self.team_id
        if extra:
            params.update(extra)
        return params


def _validate_id(value: str, pattern: re.Pattern[str], name: str) -> str:
    """Validate an ID against a regex pattern."""
    if not value:
        raise ValueError(f"{name} cannot be empty")
    if not pattern.match(value):
        raise ValueError(f"Invalid {name} format: {value}")
    return value


class VercelClient:
    """Synchronous client for querying Vercel deployments, projects, and logs.

    Features:
    - Automatic retry with exponential backoff for transient errors
    - Input validation for all IDs
    - Pagination support for large datasets
    - Secure credential handling
    """

    def __init__(self, config: VercelConfig) -> None:
        self.config = config
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.base_url,
                headers=self.config.headers,
                timeout=_DEFAULT_TIMEOUT,
            )
        return self._client

    def _request_with_retry(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute request with exponential backoff retry logic."""
        client = self._get_client()
        last_exception: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                if method == "GET":
                    response = client.get(path, params=params)
                elif method == "POST":
                    response = client.post(path, params=params, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Check if we should retry
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY_SECONDS * (2**attempt)
                    logger.warning(
                        "[vercel] Request failed with %s, retrying in %.1fs (attempt %d/%d)",
                        response.status_code,
                        wait_time,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                last_exception = e
                if (
                    e.response.status_code not in RETRYABLE_STATUS_CODES
                    or attempt >= MAX_RETRIES - 1
                ):
                    raise
                wait_time = RETRY_DELAY_SECONDS * (2**attempt)
                time.sleep(wait_time)
            except Exception as e:
                last_exception = e
                if attempt >= MAX_RETRIES - 1:
                    raise
                wait_time = RETRY_DELAY_SECONDS * (2**attempt)
                time.sleep(wait_time)

        # Should never reach here, but satisfy type checker
        raise last_exception or Exception("Request failed after all retries")

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_token)

    def list_projects(
        self,
        limit: int = DEFAULT_PROJECTS_LIMIT,
    ) -> dict[str, Any]:
        """List Vercel projects accessible to the token.

        Args:
            limit: Maximum number of projects to return (capped at MAX_PROJECTS_LIMIT).

        Returns:
            dict with success flag, projects list, and total count.
        """
        params = self.config._build_params({"limit": min(limit, MAX_PROJECTS_LIMIT)})

        try:
            resp = self._request_with_retry("GET", "/v9/projects", params=params)
            data = resp.json()

            projects = []
            for project in data.get("projects", []):
                projects.append(
                    {
                        "id": project.get("id"),
                        "name": project.get("name", ""),
                        "framework": project.get("framework", ""),
                        "created_at": project.get("createdAt", ""),
                        "updated_at": project.get("updatedAt", ""),
                    }
                )

            return {"success": True, "projects": projects, "total": len(projects)}
        except httpx.HTTPStatusError as e:
            logger.warning(
                "[vercel] List projects HTTP failure status=%s (check API token permissions)",
                e.response.status_code,
            )
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.warning(
                "[vercel] List projects request error type=%s detail=%s",
                type(e).__name__,
                e,
            )
            return {"success": False, "error": str(e)}

    def list_deployments(
        self,
        project_id: str | None = None,
        limit: int = DEFAULT_DEPLOYMENTS_LIMIT,
        state: str | None = None,
    ) -> dict[str, Any]:
        """List recent deployments with status.

        Args:
            project_id: Filter deployments by project ID (validated format).
            limit: Maximum number of deployments to return (capped at MAX_DEPLOYMENTS_LIMIT).
            state: Filter by state (READY, ERROR, BUILDING, CANCELED).

        Returns:
            dict with success flag, deployments list, and total count.
        """
        extra: dict[str, Any] = {"limit": min(limit, MAX_DEPLOYMENTS_LIMIT)}
        if project_id:
            extra["projectId"] = _validate_id(project_id, _PROJECT_ID_PATTERN, "project_id")
        if state:
            extra["state"] = state

        params = self.config._build_params(extra)

        try:
            resp = self._request_with_retry("GET", "/v6/deployments", params=params)
            data = resp.json()

            deployments = []
            for deployment in data.get("deployments", []):
                deployments.append(
                    {
                        "id": deployment.get("uid") or deployment.get("id"),
                        "url": deployment.get("url", ""),
                        "name": deployment.get("name", ""),
                        "state": deployment.get("state", ""),
                        "created_at": deployment.get("createdAt", ""),
                        "project_id": deployment.get("projectId", ""),
                        "meta": deployment.get("meta", {}),
                    }
                )

            return {"success": True, "deployments": deployments, "total": len(deployments)}
        except httpx.HTTPStatusError as e:
            logger.warning(
                "[vercel] List deployments HTTP failure status=%s "
                "(check API token permissions and project_id)",
                e.response.status_code,
            )
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.warning(
                "[vercel] List deployments request error type=%s detail=%s",
                type(e).__name__,
                e,
            )
            return {"success": False, "error": str(e)}

    def get_deployment(
        self,
        deployment_id: str,
    ) -> dict[str, Any]:
        """Fetch deployment details including build logs, error messages, and git metadata.

        Args:
            deployment_id: The deployment ID (uid) to fetch (validated format).

        Returns:
            dict with success flag and deployment details.
        """
        validated_id = _validate_id(deployment_id, _DEPLOYMENT_ID_PATTERN, "deployment_id")
        params = self.config._build_params()

        try:
            resp = self._request_with_retry(
                "GET", f"/v13/deployments/{validated_id}", params=params
            )
            data = resp.json()

            # Extract relevant fields from the deployment
            deployment = {
                "id": data.get("id", deployment_id),
                "url": data.get("url", ""),
                "name": data.get("name", ""),
                "state": data.get("readyState") or data.get("state", ""),
                "created_at": data.get("createdAt", ""),
                "ready": data.get("ready", False),
                "building": data.get("buildingAt", ""),
                "project_id": data.get("projectId", ""),
                "meta": data.get("meta", {}),
                "target": data.get("target", ""),
                "error_message": data.get("errorMessage", ""),
                "error_code": data.get("errorCode", ""),
            }

            return {"success": True, "deployment": deployment}
        except httpx.HTTPStatusError as e:
            logger.warning(
                "[vercel] Get deployment HTTP failure status=%s deployment_id=%s",
                e.response.status_code,
                deployment_id,
            )
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.warning(
                "[vercel] Get deployment request error type=%s detail=%s",
                type(e).__name__,
                e,
            )
            return {"success": False, "error": str(e)}

    def get_deployment_events(
        self,
        deployment_id: str,
    ) -> dict[str, Any]:
        """Fetch build and runtime event stream for a deployment.

        Args:
            deployment_id: The deployment ID to fetch events for (validated format).

        Returns:
            dict with success flag and event list.
        """
        validated_id = _validate_id(deployment_id, _DEPLOYMENT_ID_PATTERN, "deployment_id")
        params = self.config._build_params()

        try:
            resp = self._request_with_retry(
                "GET", f"/v2/deployments/{validated_id}/events", params=params
            )
            data = resp.json()

            events = []
            for event in data.get("events", []):
                events.append(
                    {
                        "type": event.get("type", ""),
                        "created_at": event.get("createdAt", ""),
                        "payload": event.get("payload", {}),
                    }
                )

            return {"success": True, "events": events, "total": len(events)}
        except httpx.HTTPStatusError as e:
            logger.warning(
                "[vercel] Get deployment events HTTP failure status=%s deployment_id=%s",
                e.response.status_code,
                deployment_id,
            )
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.warning(
                "[vercel] Get deployment events request error type=%s detail=%s",
                type(e).__name__,
                e,
            )
            return {"success": False, "error": str(e)}

    def get_runtime_logs(
        self,
        deployment_id: str,
        limit: int = DEFAULT_LOGS_LIMIT,
        since: int | None = None,
        until: int | None = None,
    ) -> dict[str, Any]:
        """Fetch serverless function runtime logs (stdout/stderr) for a deployment.

        Args:
            deployment_id: The deployment ID to fetch logs for (validated format).
            limit: Maximum number of log entries to return (capped at MAX_LOGS_LIMIT).
            since: Start timestamp (ms since epoch).
            until: End timestamp (ms since epoch).

        Returns:
            dict with success flag and log entries.
        """
        validated_id = _validate_id(deployment_id, _DEPLOYMENT_ID_PATTERN, "deployment_id")
        extra: dict[str, Any] = {"limit": min(limit, MAX_LOGS_LIMIT)}
        if since:
            extra["since"] = since
        if until:
            extra["until"] = until

        params = self.config._build_params(extra)

        try:
            resp = self._request_with_retry(
                "GET", f"/v3/deployments/{validated_id}/logs", params=params
            )
            data = resp.json()

            logs = []
            for entry in data.get("logs", []):
                logs.append(
                    {
                        "timestamp": entry.get("timestamp", ""),
                        "message": entry.get("message", ""),
                        "level": entry.get("level", ""),
                        "source": entry.get("source", ""),  # 'stdout' or 'stderr'
                    }
                )

            return {"success": True, "logs": logs, "total": len(logs)}
        except httpx.HTTPStatusError as e:
            logger.warning(
                "[vercel] Get runtime logs HTTP failure status=%s deployment_id=%s",
                e.response.status_code,
                deployment_id,
            )
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            logger.warning(
                "[vercel] Get runtime logs request error type=%s detail=%s",
                type(e).__name__,
                e,
            )
            return {"success": False, "error": str(e)}
