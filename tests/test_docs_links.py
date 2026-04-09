"""Regression checks for public docs link configuration."""

from __future__ import annotations

import json
from pathlib import Path


def test_footer_website_uses_opensre_domain() -> None:
    """Keep footer website on the OpenSRE domain to avoid broken /docs links."""
    repo_root = Path(__file__).resolve().parents[1]
    docs_json_path = repo_root / "docs" / "docs.json"
    docs_config = json.loads(docs_json_path.read_text(encoding="utf-8"))

    website = docs_config["footer"]["socials"]["website"]
    assert website == "https://www.opensre.com"
