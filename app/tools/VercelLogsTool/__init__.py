"""Vercel logs investigation tool."""

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


def _logs_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    vercel = sources["vercel"]
    return {
        **_vercel_creds(vercel),
        "deployment_id": vercel.get("deployment_id", ""),
        "limit": 100,
    }


@tool(
    name="vercel_logs",
    source="vercel",
    description="Pull Vercel build output and serverless function runtime logs for a specific deployment, useful for diagnosing build failures and runtime errors.",
    use_cases=[
        "Diagnosing Vercel build failures",
        "Investigating serverless function runtime errors",
        "Correlating deployment logs with application errors",
    ],
    requires=["vercel_api_token", "deployment_id"],
    input_schema={
        "type": "object",
        "properties": {
            "vercel_api_token": {"type": "string"},
            "vercel_team_id": {"type": "string", "default": ""},
            "deployment_id": {"type": "string"},
            "log_type": {"type": "string", "default": "runtime"},
            "limit": {"type": "integer", "default": 100},
        },
        "required": ["vercel_api_token", "deployment_id"],
    },
    is_available=_vercel_available,
    extract_params=_logs_extract_params,
    surfaces=("investigation", "chat"),
)
def vercel_logs(
    vercel_api_token: str,
    deployment_id: str,
    vercel_team_id: str = "",
    log_type: str = "runtime",
    limit: int = 100,
) -> dict[str, Any]:
    """Pull Vercel build output and serverless function runtime logs."""
    config = _resolve_config(vercel_api_token, vercel_team_id)
    if config is None:
        return {
            "source": "vercel",
            "available": False,
            "error": "Vercel integration is not configured. Set VERCEL_API_TOKEN.",
            "logs": [],
        }

    if not deployment_id:
        return {
            "source": "vercel",
            "available": False,
            "error": "deployment_id is required to fetch logs.",
            "logs": [],
        }

    client = VercelClient(config)

    # Fetch based on log_type
    if log_type == "build":
        result = client.get_deployment_events(deployment_id)
    else:  # runtime or default
        result = client.get_runtime_logs(deployment_id, limit=limit)

    if not result.get("success"):
        return {
            "source": "vercel",
            "available": False,
            "error": result.get("error", "Unknown error"),
            "logs": [],
        }

    if log_type == "build":
        logs = []
        for event in result.get("events", []):
            logs.append(
                {
                    "type": event.get("type"),
                    "created_at": event.get("created_at"),
                    "payload": event.get("payload"),
                }
            )
        return {
            "source": "vercel",
            "available": True,
            "log_type": "build",
            "deployment_id": deployment_id,
            "logs": logs,
            "total": len(logs),
        }

    # Runtime logs
    logs = []
    for entry in result.get("logs", []):
        logs.append(
            {
                "timestamp": entry.get("timestamp"),
                "message": entry.get("message"),
                "level": entry.get("level"),
                "source": entry.get("source"),
            }
        )

    return {
        "source": "vercel",
        "available": True,
        "log_type": "runtime",
        "deployment_id": deployment_id,
        "logs": logs,
        "total": len(logs),
    }
