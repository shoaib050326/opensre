"""Diagnostic / debug subcommands — ``opensre debug <subcommand>``.

Currently provides:
- ``opensre debug sentry`` — one-shot DSN smoke test.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import click
from rich.console import Console
from rich.text import Text

from app.cli.support.exit_codes import ERROR as EXIT_ERROR
from app.cli.support.exit_codes import SUCCESS


@click.group(name="debug")
def debug_group() -> None:
    """Diagnostic and debugging utilities."""


@debug_group.command(name="sentry")
def sentry_debug_command() -> None:
    """Verify Sentry DSN connectivity with a synthetic exception.

    Calls ``init_sentry(entrypoint="debug")``, captures a synthetic
    exception, flushes the event queue, and reports whether the event
    was transmitted successfully.

    The synthetic event is tagged with ``debug=true`` so it can be
    filtered out in Sentry's issue stream.

    Exit codes:
    0 — DSN configured and event transmitted.
    1 — DSN missing or event not transmitted.
    """
    from app.utils.sentry_sdk import (
        _is_sentry_disabled,
        _resolved_dsn,
        capture_exception,
        init_sentry,
    )

    console = Console(highlight=False, force_terminal=True, color_system="truecolor")
    if _is_sentry_disabled():
        console.print(Text("Sentry telemetry is disabled.", style="bold yellow"))
        console.print(
            Text(
                "Unset OPENSRE_NO_TELEMETRY, OPENSRE_SENTRY_DISABLED, or DO_NOT_TRACK to test Sentry.",
                style="dim",
            )
        )
        raise SystemExit(EXIT_ERROR)

    sentry_dsn = _resolved_dsn()

    if not sentry_dsn:
        console.print(
            Text("No Sentry DSN configured.", style="bold red"),
        )
        msg = (
            "Set OPENSRE_SENTRY_DSN (or SENTRY_DSN) in your environment, "
            "or leave unset to use the built-in DSN."
        )
        console.print(Text(msg, style="dim"))
        raise SystemExit(EXIT_ERROR)

    dsn_host = urlsplit(sentry_dsn).hostname or "unknown"
    console.print(f"DSN host: [bold]{dsn_host}[/bold]")

    try:
        init_sentry(entrypoint="debug")
    except Exception as exc:
        console.print(
            Text(f"Sentry initialization failed: {exc}", style="bold red"),
        )
        raise SystemExit(EXIT_ERROR) from exc

    import sentry_sdk

    try:
        raise RuntimeError("Sentry debug test — not a real error")
    except RuntimeError as exc:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("debug", "true")
            capture_exception(exc, context="debug.sentry_test")

    sentry_ok = sentry_sdk.flush(timeout=5)

    if sentry_ok:
        console.print(
            Text("Sentry event transmitted successfully.", style="bold green"),
        )
        raise SystemExit(SUCCESS)

    console.print(
        Text("Sentry event NOT transmitted — check DSN and network.", style="bold red"),
    )
    raise SystemExit(EXIT_ERROR)
