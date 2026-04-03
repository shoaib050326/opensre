"""Vercel API client for deployment and runtime log access."""

from app.integrations.clients.vercel.client import VercelClient, VercelConfig

__all__ = ["VercelClient", "VercelConfig"]
