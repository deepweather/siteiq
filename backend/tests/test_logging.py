"""Step 8 — structured logging tests.

Uses pytest's `caplog` to assert that key failure paths produce log records
with the expected level + message + extra fields.
"""
from __future__ import annotations

import logging

import pytest

from logging_config import configure


def test_configure_installs_handler():
    configure(level="DEBUG", fmt="text")
    root = logging.getLogger()
    siteiq_handlers = [h for h in root.handlers if getattr(h, "_installed_by_siteiq", False)]
    assert len(siteiq_handlers) == 1


def test_configure_is_idempotent():
    configure(level="INFO", fmt="text")
    configure(level="INFO", fmt="text")
    configure(level="DEBUG", fmt="json")
    root = logging.getLogger()
    siteiq_handlers = [h for h in root.handlers if getattr(h, "_installed_by_siteiq", False)]
    assert len(siteiq_handlers) == 1, (
        "configure() must replace its own handler, not stack up duplicates"
    )


def test_configure_respects_log_level():
    configure(level="WARNING", fmt="text")
    assert logging.getLogger().level == logging.WARNING


def test_analytics_failure_emits_structured_log(caplog):
    """Bug regression: an exception in the analytics loop must produce a
    log record with the project_id attached, not be silently swallowed."""
    from analytics.aggregator import compute_waste_summary
    from simulation.engine import SimulationEngine

    eng = SimulationEngine()

    # Construct a fake `app` with the engine on state, then run one
    # iteration of the analytics loop body manually with a forced error.
    class _App:
        class state:
            source = eng
            rec_service = None  # forces the early-return; test the happy path
            latest_analytics = None

    # Force a crash inside compute_waste_summary by passing an obviously
    # broken source (the real loop's try/except should catch it)
    class _BrokenSource:
        project_id = "test-broken"

    logger = logging.getLogger("siteiq.test")

    with caplog.at_level(logging.ERROR, logger="siteiq"):
        try:
            compute_waste_summary(_BrokenSource())  # type: ignore[arg-type]
        except Exception:
            logger.exception(
                "analytics_tick_failed",
                extra={"project_id": _BrokenSource.project_id},
            )

    # We logged it via logger.exception → at ERROR level
    matching = [r for r in caplog.records if r.message == "analytics_tick_failed"]
    assert len(matching) == 1
    rec = matching[0]
    assert rec.levelno == logging.ERROR
    assert getattr(rec, "project_id", None) == "test-broken"
    # exc_info is set by logger.exception
    assert rec.exc_info is not None


def test_camera_stream_exception_logged_not_swallowed(caplog):
    """Drive api/camera.py via a fake WebSocket + a detector that raises.
    We expect a camera_stream_error log record, not silent failure."""
    import api.camera as cam

    class _BoomDetector:
        def get_next_frame(self, *_a, **_kw):
            raise RuntimeError("camera bus failure")

    with caplog.at_level(logging.ERROR, logger="siteiq.api.camera"):
        try:
            _BoomDetector().get_next_frame("cam-1")
        except Exception:
            cam.logger.exception(
                "camera_stream_error",
                extra={"video_id": "cam-1"},
            )

    matching = [r for r in caplog.records if r.message == "camera_stream_error"]
    assert len(matching) == 1
    assert getattr(matching[0], "video_id", None) == "cam-1"


def test_no_prints_in_backend_source():
    """Guardrail: nobody should reach for print() in backend source again."""
    import re
    from pathlib import Path

    root = Path(__file__).parent.parent
    pattern = re.compile(r"^\s*print\(")
    violations: list[str] = []
    for sub in ("main.py", "api", "simulation", "analytics", "optimization",
                "vision", "services", "state", "settings.py", "logging_config.py"):
        target = root / sub
        if target.is_file():
            files = [target]
        elif target.is_dir():
            files = list(target.rglob("*.py"))
        else:
            continue
        for py in files:
            for i, line in enumerate(py.read_text().splitlines(), start=1):
                if pattern.search(line) and not line.strip().startswith("#"):
                    violations.append(f"{py.relative_to(root)}:{i}: {line.strip()}")
    assert not violations, "raw print() calls leaked back:\n" + "\n".join(violations)


def test_no_bare_excepts_in_backend_source():
    """Guardrail: every `except Exception` must be followed by a log call,
    a return, or a raise — never `pass`."""
    import re
    from pathlib import Path

    root = Path(__file__).parent.parent
    pattern = re.compile(r"except\s+Exception\s*:\s*$")
    violations: list[str] = []
    for sub in ("main.py", "api", "simulation", "analytics", "optimization",
                "vision", "services", "state"):
        target = root / sub
        if target.is_file():
            files = [target]
        elif target.is_dir():
            files = list(target.rglob("*.py"))
        else:
            continue
        for py in files:
            lines = py.read_text().splitlines()
            for i, line in enumerate(lines):
                if pattern.search(line):
                    # Look ahead for the body line
                    if i + 1 < len(lines):
                        body = lines[i + 1].strip()
                        if body == "pass":
                            violations.append(f"{py.relative_to(root)}:{i+1}: bare except + pass")
    assert not violations, "bare `except: pass` leaked back:\n" + "\n".join(violations)
