from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from outpass.cli import RequestData, apply_request, load_json


def parse_clock(value: str, setting_name: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{setting_name} must use HH:MM in 24-hour format.") from error


def build_daily_request(day: date, request_settings: dict[str, Any]) -> RequestData:
    day_text = day.isoformat()
    return RequestData.from_mapping(
        {
            **request_settings,
            "departure_date": day_text,
            "return_date": day_text,
        }
    )


def claim_attempt(attempt_dir: Path, day: date, now: datetime, status: str = "started") -> Path | None:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    attempt_file = attempt_dir / f"{day.isoformat()}.json"
    payload = {
        "date": day.isoformat(),
        "started_at": now.isoformat(),
        "status": status,
    }
    try:
        descriptor = os.open(attempt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return attempt_file


def update_attempt(attempt_file: Path, status: str, detail: str, now: datetime) -> None:
    payload = load_json(attempt_file)
    payload.update(
        {
            "finished_at": now.isoformat(),
            "status": status,
            "detail": detail,
        }
    )
    attempt_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def portal_is_reachable(url: str, timeout_seconds: float) -> bool:
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout_seconds):
            return True
    except Exception:
        return False


def resolve_project_path(project_dir: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else project_dir / path


def validate_settings(settings: dict[str, Any]) -> None:
    required = (
        "timezone",
        "schedule_time",
        "latest_attempt_time",
        "check_interval_seconds",
        "network_timeout_seconds",
        "portal_config",
        "auth_state",
        "attempt_directory",
        "request",
    )
    missing = [name for name in required if name not in settings]
    if missing:
        raise ValueError(f"Missing daily settings: {', '.join(missing)}")
    if int(settings["check_interval_seconds"]) < 60:
        raise ValueError("check_interval_seconds must be at least 60.")
    if float(settings["network_timeout_seconds"]) <= 0:
        raise ValueError("network_timeout_seconds must be positive.")
    schedule = parse_clock(str(settings["schedule_time"]), "schedule_time")
    cutoff = parse_clock(str(settings["latest_attempt_time"]), "latest_attempt_time")
    if cutoff <= schedule:
        raise ValueError("latest_attempt_time must be after schedule_time.")
    build_daily_request(date.today(), settings["request"])
    try:
        ZoneInfo(str(settings["timezone"]))
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown timezone: {settings['timezone']}") from error


def run_daily(
    project_dir: Path,
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
    submitter: Callable[..., Path] = apply_request,
    reachability_check: Callable[[str, float], bool] = portal_is_reachable,
) -> str:
    validate_settings(settings)
    timezone = ZoneInfo(str(settings["timezone"]))
    current = now.astimezone(timezone) if now else datetime.now(timezone)
    day = current.date()
    schedule = parse_clock(str(settings["schedule_time"]), "schedule_time")
    cutoff = parse_clock(str(settings["latest_attempt_time"]), "latest_attempt_time")
    attempt_dir = resolve_project_path(project_dir, str(settings["attempt_directory"]))
    attempt_file = attempt_dir / f"{day.isoformat()}.json"

    if attempt_file.exists():
        return f"Skipped: today's automation has already been handled ({attempt_file})."
    if current.time() < schedule:
        return f"Waiting: scheduled time is {settings['schedule_time']} {settings['timezone']}."
    if current.time() >= cutoff:
        missed_file = claim_attempt(attempt_dir, day, current, status="missed")
        if missed_file:
            update_attempt(
                missed_file,
                "missed",
                f"Mac became available at or after the {settings['latest_attempt_time']} cutoff; no portal request was made.",
                current,
            )
        return f"Missed: current time is at or after {settings['latest_attempt_time']}; no request was made."

    portal_config_path = resolve_project_path(project_dir, str(settings["portal_config"]))
    portal_config = load_json(portal_config_path)
    reachability_url = str(
        settings.get("reachability_url") or portal_config.get("portal", {}).get("login_url", "")
    )
    if not reachability_url:
        raise ValueError("Set reachability_url or portal.login_url.")
    if not reachability_check(reachability_url, float(settings["network_timeout_seconds"])):
        return "Deferred: the portal is unreachable. No application attempt was recorded."

    claimed_file = claim_attempt(attempt_dir, day, current)
    if claimed_file is None:
        return f"Skipped: another process already handled {day.isoformat()}."

    request = build_daily_request(day, settings["request"])
    auth_state = resolve_project_path(project_dir, str(settings["auth_state"]))
    try:
        screenshot = submitter(
            portal_config,
            request,
            auth_state,
            submit=True,
            headless=bool(settings.get("headless", True)),
        )
    except Exception as error:
        update_attempt(claimed_file, "failed", str(error), datetime.now(timezone))
        raise

    detail = (
        f"Submitted {request.request_type} for {day.isoformat()}, "
        f"{request.departure_time}-{request.return_time}. Screenshot: {screenshot}"
    )
    update_attempt(claimed_file, "submitted", detail, datetime.now(timezone))
    return detail


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the configurable once-daily outpass automation.")
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="Daily settings JSON; defaults to daily-config.json beside the project executable.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print waiting, deferred, and already-handled status messages.",
    )
    return parser


def should_report(message: str) -> bool:
    return message.startswith(("Submitted", "Missed"))


def main() -> None:
    args = build_parser().parse_args()
    project_dir = Path(__file__).resolve().parents[2]
    settings_path = args.settings or project_dir / "daily-config.json"
    if not settings_path.is_absolute():
        settings_path = project_dir / settings_path
    try:
        settings = load_json(settings_path)
        message = run_daily(project_dir, settings)
        if args.verbose or should_report(message):
            print(message)
    except Exception as error:
        print(f"Daily outpass automation failed and will not retry after a real attempt: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
