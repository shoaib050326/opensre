"""Vercel deployment status investigation tool."""

from __future__ import annotations

from typing import Any

from app.integrations.clients.vercel import VercelClient, VercelConfig
from app.tools.tool_decorator import tool


def _resolve_config(
    vercel_api_token: str | None, vercel_team_id: str | None
) -> VercelConfig | None:
    """Build Vercel config from provided values or env."""
    import os

    token = vercel_api_token or os.getenv("VERCEL_API_TOKEN", "").strip()
    team_id = vercel_team_id or os.getenv("VERCEL_TEAM_ID", "").strip()

    if not token:
        return None

    return VercelConfig(api_token=token, team_id=team_id)


def _vercel_available(sources: dict[str, dict]) -> bool:
    return bool(sources.get("vercel", {}).get("connection_verified"))


def _vercel_creds(vercel: dict[str, Any]) -> dict[str, Any]:
    return {
        "vercel_api_token": vercel.get("vercel_api_token", ""),
        "vercel_team_id": vercel.get("vercel_team_id", ""),
    }


def _deployment_status_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    vercel = sources["vercel"]
    return {
        **_vercel_creds(vercel),
        "project_id": vercel.get("project_id", ""),
        "limit": 10,
    }


@tool(
    name="vercel_deployment_status",
    source="vercel",
    description="Fetch recent Vercel deployment status for a project, including failed deployments with error details, git commit info, and timestamps.",
    use_cases=[
        "Investigating failed Vercel deployments",
        "Correlating deployment failures with alerts from other sources",
        "Checking recent deployment history for a project",
    ],
    requires=["vercel_api_token"],
    input_schema={
        "type": "object",
        "properties": {
            "vercel_api_token": {"type": "string"},
            "vercel_team_id": {"type": "string", "default": ""},
            "project_id": {"type": "string", "default": ""},
            "state": {"type": "string", "default": ""},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["vercel_api_token"],
    },
    is_available=_vercel_available,
    extract_params=_deployment_status_extract_params,
    surfaces=("investigation", "chat"),
)
def vercel_deployment_status(
    vercel_api_token: str,
    vercel_team_id: str = "",
    project_id: str = "",
    state: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Fetch recent Vercel deployment status for a project."""
    config = _resolve_config(vercel_api_token, vercel_team_id)
    if config is None:
        return {
            "source": "vercel",
            "available": False,
            "error": "Vercel integration is not configured. Set VERCEL_API_TOKEN.",
            "deployments": [],
        }

    client = VercelClient(config)
    result = client.list_deployments(
        project_id=project_id or None, limit=limit, state=state or None
    )

    if not result.get("success"):
        return {
            "source": "vercel",
            "available": False,
            "error": result.get("error", "Unknown error"),
            "deployments": [],
        }

    # Enrich deployments with git metadata from the meta field
    deployments = []
    for deployment in result.get("deployments", []):
        meta = deployment.get("meta", {})
        enriched = {
            "id": deployment.get("id"),
            "name": deployment.get("name"),
            "url": deployment.get("url"),
            "state": deployment.get("state"),
            "created_at": deployment.get("created_at"),
            "project_id": deployment.get("project_id"),
            "git": {
                "commit_sha": meta.get("githubCommitSha") or meta.get("commitSha", ""),
                "commit_message": meta.get("githubCommitMessage") or meta.get("commitMessage", ""),
                "branch": meta.get("githubCommitRef") or meta.get("branch", ""),
                "author": meta.get("githubCommitAuthor") or meta.get("commitAuthor", ""),
            },
        }
        deployments.append(enriched)

    return {
        "source": "vercel",
        "available": True,
        "deployments": deployments,
        "total": len(deployments),
    }
