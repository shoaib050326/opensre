"""Tests for BaseTool and RegisteredTool callable behavior."""

from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool
from app.tools.registered_tool import RegisteredTool
from app.types.evidence import EvidenceSource


def test_basetool_call_delegates_to_run() -> None:
    class _FailingTool(BaseTool):
        name: str = "failing_tool"
        description: str = "A tool that always fails"
        input_schema: dict[str, Any] = {"type": "object", "properties": {}}
        source: EvidenceSource = "knowledge"

        def run(self, **kwargs: Any) -> dict[str, Any]:
            return {"received": kwargs}

    tool = _FailingTool()
    assert tool(answer=42) == {"received": {"answer": 42}}


def test_basetool_call_propagates_exceptions() -> None:
    class _FailingTool(BaseTool):
        name: str = "failing_tool"
        description: str = "A tool that always fails"
        input_schema: dict[str, Any] = {"type": "object", "properties": {}}
        source: EvidenceSource = "knowledge"

        def run(self, **_kwargs: Any) -> dict[str, Any]:
            raise ValueError("something went wrong")

    tool = _FailingTool()
    try:
        tool()
    except ValueError as exc:
        assert str(exc) == "something went wrong"
    else:
        raise AssertionError("Expected BaseTool.__call__ to propagate run() exceptions")


def test_registered_tool_call_delegates_to_run() -> None:
    def _func(**kwargs: Any) -> Any:
        return {"received": kwargs}

    registered = RegisteredTool(
        name="decorated_tool",
        description="A @tool-decorated function",
        input_schema={"type": "object", "properties": {}},
        source="knowledge",
        run=_func,
    )

    assert registered(answer=42) == {"received": {"answer": 42}}


def test_registered_tool_call_propagates_exceptions() -> None:
    def _failing_func(**kwargs: Any) -> Any:
        raise RuntimeError("decorated tool failed")

    registered = RegisteredTool(
        name="decorated_fail",
        description="A @tool-decorated function that fails",
        input_schema={"type": "object", "properties": {}},
        source="knowledge",
        run=_failing_func,
    )

    try:
        registered()
    except RuntimeError as exc:
        assert str(exc) == "decorated tool failed"
    else:
        raise AssertionError("Expected RegisteredTool.__call__ to propagate run() exceptions")
