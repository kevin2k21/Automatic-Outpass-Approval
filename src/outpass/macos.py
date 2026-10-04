from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any

from outpass.cli import load_json
from outpass.daily import parse_clock, validate_settings


LABEL = "com.automatic-outpass.daily"


def build_launch_agent(
    project_dir: Path, settings: dict[str, Any], settings_path: Path | None = None
) -> dict[str, Any]:
    validate_settings(settings)
    schedule = parse_clock(str(settings["schedule_time"]), "schedule_time")
    artifact_dir = project_dir / "artifacts"
    configured_settings_path = settings_path or project_dir / "daily-config.json"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(project_dir / "run-daily-outpass"),
            "--settings",
            str(configured_settings_path),
        ],
        "WorkingDirectory": str(project_dir),
        "RunAtLoad": True,
        "StartCalendarInterval": {"Hour": schedule.hour, "Minute": schedule.minute},
        "StartInterval": int(settings["check_interval_seconds"]),
        "StandardOutPath": str(artifact_dir / "launchd.stdout.log"),
        "StandardErrorPath": str(artifact_dir / "launchd.stderr.log"),
        "ProcessType": "Background",
    }


def install(project_dir: Path, settings_path: Path) -> Path:
    settings = load_json(settings_path)
    payload = build_launch_agent(project_dir, settings, settings_path)
    (project_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents / f"{LABEL}.plist"
    temporary_path = plist_path.with_suffix(".plist.tmp")
    with temporary_path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    temporary_path.replace(plist_path)

    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist_path)], check=False, capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
    subprocess.run(["launchctl", "enable", f"{domain}/{LABEL}"], check=True)
    return plist_path


def uninstall() -> Path:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist_path)], check=False)
    plist_path.unlink(missing_ok=True)
    return plist_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Install or uninstall the macOS outpass LaunchAgent.")
    parser.add_argument("action", choices=("install", "uninstall"), nargs="?", default="install")
    parser.add_argument("--settings", type=Path, default=None)
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parents[2]
    settings_path = args.settings or project_dir / "daily-config.json"
    if not settings_path.is_absolute():
        settings_path = project_dir / settings_path
    if args.action == "install":
        path = install(project_dir, settings_path)
        print(f"Installed and loaded: {path}")
    else:
        path = uninstall()
        print(f"Uninstalled: {path}")


if __name__ == "__main__":
    main()
