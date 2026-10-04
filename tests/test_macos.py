from pathlib import Path

from outpass.macos import build_launch_agent
from test_daily import settings


def test_launch_agent_uses_configured_schedule_and_interval(tmp_path: Path) -> None:
    custom = settings()
    custom["schedule_time"] = "12:15"
    custom["check_interval_seconds"] = 600
    payload = build_launch_agent(tmp_path, custom)
    assert payload["StartCalendarInterval"] == {"Hour": 12, "Minute": 15}
    assert payload["StartInterval"] == 600
    assert payload["RunAtLoad"] is True
