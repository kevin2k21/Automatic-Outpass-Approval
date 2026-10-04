from datetime import date, datetime
from pathlib import Path

import pytest

from outpass.daily import build_daily_request, run_daily, should_report


def settings() -> dict:
    return {
        "timezone": "UTC",
        "schedule_time": "11:00",
        "latest_attempt_time": "16:00",
        "check_interval_seconds": 300,
        "network_timeout_seconds": 10,
        "portal_config": "config.json",
        "auth_state": "auth-state.json",
        "attempt_directory": "attempts",
        "request": {
            "request_type": "Evening Out Pass",
            "holiday_subtype": "",
            "departure_time": "16:00",
            "return_time": "21:25",
            "place": "City center",
            "purpose": "Personal errand",
        },
    }


def project(tmp_path: Path) -> Path:
    (tmp_path / "config.json").write_text(
        '{"portal":{"login_url":"https://example.test/login"}}', encoding="utf-8"
    )
    return tmp_path


def test_builds_custom_same_day_request() -> None:
    custom = settings()["request"]
    custom["place"] = "Custom destination"
    request = build_daily_request(date(2026, 10, 6), custom)
    assert request.departure_date == request.return_date == "2026-10-06"
    assert request.place == "Custom destination"


def test_attempts_only_once_per_day(tmp_path: Path) -> None:
    calls = []

    def submitter(*args, **kwargs):
        calls.append((args, kwargs))
        return Path("artifacts/submitted.png")

    now = datetime.fromisoformat("2026-10-06T11:00:00+00:00")
    first = run_daily(
        project(tmp_path),
        settings(),
        now=now,
        submitter=submitter,
        reachability_check=lambda *_: True,
    )
    second = run_daily(
        tmp_path,
        settings(),
        now=now,
        submitter=submitter,
        reachability_check=lambda *_: True,
    )

    assert first.startswith("Submitted Evening Out Pass")
    assert second.startswith("Skipped")
    assert len(calls) == 1


def test_offline_does_not_consume_attempt(tmp_path: Path) -> None:
    now = datetime.fromisoformat("2026-10-07T11:30:00+00:00")
    message = run_daily(
        project(tmp_path), settings(), now=now, reachability_check=lambda *_: False
    )
    assert message.startswith("Deferred")
    assert not (tmp_path / "attempts" / "2026-10-07.json").exists()


def test_after_cutoff_never_submits(tmp_path: Path) -> None:
    called = False

    def submitter(*args, **kwargs):
        nonlocal called
        called = True

    now = datetime.fromisoformat("2026-10-08T16:00:00+00:00")
    message = run_daily(project(tmp_path), settings(), now=now, submitter=submitter)
    assert message.startswith("Missed")
    assert called is False


def test_before_schedule_waits(tmp_path: Path) -> None:
    now = datetime.fromisoformat("2026-10-09T10:59:00+00:00")
    message = run_daily(project(tmp_path), settings(), now=now)
    assert message.startswith("Waiting")


def test_failed_real_attempt_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def submitter(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("portal rejected submission")

    now = datetime.fromisoformat("2026-10-10T11:00:00+00:00")
    with pytest.raises(RuntimeError):
        run_daily(
            project(tmp_path),
            settings(),
            now=now,
            submitter=submitter,
            reachability_check=lambda *_: True,
        )
    second = run_daily(
        tmp_path,
        settings(),
        now=now,
        submitter=submitter,
        reachability_check=lambda *_: True,
    )
    assert second.startswith("Skipped")
    assert calls == 1


def test_only_meaningful_outcomes_are_logged() -> None:
    assert should_report("Submitted Evening Out Pass") is True
    assert should_report("Missed: cutoff passed") is True
    assert should_report("Skipped: already handled") is False
    assert should_report("Waiting: not time yet") is False
    assert should_report("Deferred: portal unreachable") is False
