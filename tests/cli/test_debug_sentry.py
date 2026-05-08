from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from click.testing import CliRunner

sys.modules.setdefault("psutil", SimpleNamespace(pid_exists=lambda _pid: False))

from app.cli.commands.debug import debug_group
from app.utils import sentry_sdk as sentry_mod


class _Scope:
    def __init__(self) -> None:
        self.tags: dict[str, str] = {}

    def __enter__(self) -> _Scope:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value


def test_debug_sentry_exits_when_telemetry_disabled(monkeypatch) -> None:
    monkeypatch.setattr(sentry_mod, "_is_sentry_disabled", lambda: True)
    init_mock = MagicMock()
    monkeypatch.setattr(sentry_mod, "init_sentry", init_mock)

    result = CliRunner().invoke(debug_group, ["sentry"])

    assert result.exit_code == 1
    assert "Sentry telemetry is disabled" in result.output
    init_mock.assert_not_called()


def test_debug_sentry_uses_scoped_debug_tag(monkeypatch) -> None:
    scope = _Scope()
    set_tag_mock = MagicMock()
    captured_contexts: list[str | None] = []

    monkeypatch.setattr(sentry_mod, "_is_sentry_disabled", lambda: False)
    monkeypatch.setattr(
        sentry_mod,
        "_resolved_dsn",
        lambda: "https://public@example.invalid/1",
    )
    monkeypatch.setattr(sentry_mod, "init_sentry", lambda **_kwargs: None)
    monkeypatch.setattr(
        sentry_mod,
        "capture_exception",
        lambda _exc, *, context=None, _extra=None: captured_contexts.append(context),
    )
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk",
        SimpleNamespace(
            push_scope=lambda: scope,
            flush=lambda **_kwargs: True,
            set_tag=set_tag_mock,
        ),
    )

    result = CliRunner().invoke(debug_group, ["sentry"])

    assert result.exit_code == 0
    assert scope.tags == {"debug": "true"}
    assert captured_contexts == ["debug.sentry_test"]
    set_tag_mock.assert_not_called()
