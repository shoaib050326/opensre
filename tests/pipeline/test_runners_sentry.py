from __future__ import annotations

from typing import Any, cast

import pytest

from app.pipeline import runners
from app.state import AgentState
from app.utils import errors


def test_run_chat_initializes_sentry_and_captures_unhandled_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentry_init_calls: list[None] = []
    captured_errors: list[BaseException] = []
    expected_error = RuntimeError("router failed")

    def failing_router(_state: AgentState) -> dict[str, object]:
        raise expected_error

    def capture_stub(exc: BaseException, **_kwargs: object) -> None:
        captured_errors.append(exc)

    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: sentry_init_calls.append(None))
    monkeypatch.setattr(errors, "capture_exception", capture_stub)
    monkeypatch.setattr(runners, "router_node", failing_router)

    with pytest.raises(RuntimeError, match="router failed"):
        runners.run_chat(cast(AgentState, {}))

    assert sentry_init_calls == [None]
    assert captured_errors == [expected_error]


def test_run_investigation_captures_node_internal_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_calls: list[None] = []
    captured_errors: list[BaseException] = []
    expected_error = RuntimeError("internal node failure")

    def capture_stub(exc: BaseException, **_kwargs: object) -> None:
        captured_errors.append(exc)

    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: init_calls.append(None))
    monkeypatch.setattr(errors, "capture_exception", capture_stub)

    class _FailingGraph:
        def invoke(self, _initial: Any, _config: Any) -> Any:
            raise expected_error

    monkeypatch.setattr("app.pipeline.graph.graph", _FailingGraph())

    with pytest.raises(RuntimeError, match="internal node failure"):
        runners.run_investigation(
            alert_name="test-alert",
            pipeline_name="test-pipeline",
            severity="critical",
        )

    assert init_calls == [None]
    assert captured_errors == [expected_error]
