from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


DEFAULT_AUTH_STATE = Path("auth-state.json")
DEFAULT_ARTIFACT_DIR = Path("artifacts")


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RequestData:
    request_type: str
    departure_date: str
    departure_time: str
    return_date: str
    return_time: str
    place: str
    purpose: str
    holiday_subtype: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RequestData":
        required = (
            "request_type",
            "departure_date",
            "departure_time",
            "return_date",
            "return_time",
            "place",
            "purpose",
        )
        missing = [name for name in required if not str(value.get(name, "")).strip()]
        if missing:
            raise ConfigurationError(f"Missing request fields: {', '.join(missing)}")
        request = cls(**{name: str(value.get(name, "")).strip() for name in cls.__annotations__})
        request.validate()
        return request

    def validate(self) -> None:
        try:
            start = datetime.combine(
                date.fromisoformat(self.departure_date), time.fromisoformat(self.departure_time)
            )
            end = datetime.combine(date.fromisoformat(self.return_date), time.fromisoformat(self.return_time))
        except ValueError as error:
            raise ConfigurationError(
                "Dates must use YYYY-MM-DD and times must use HH:MM (24-hour format)."
            ) from error
        if end <= start:
            raise ConfigurationError("The return date/time must be after the departure date/time.")
        allowed_types = {"Weekend Pass", "Evening Out Pass", "Working Day Pass", "Holiday Pass"}
        if self.request_type not in allowed_types:
            raise ConfigurationError(f"Unsupported pass type: {self.request_type}")
        if self.request_type == "Holiday Pass" and self.holiday_subtype not in {
            "Study Holiday",
            "Semester Break",
            "Declared Holiday",
        }:
            raise ConfigurationError("Holiday Pass requires a valid holiday_subtype.")
        if len(self.place) > 60 or len(self.purpose) > 60:
            raise ConfigurationError("Place and purpose must each be 60 characters or fewer.")

    def as_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__annotations__}


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as error:
        raise ConfigurationError(f"File not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected a JSON object in {path}")
    return value


def require_config(config: dict[str, Any]) -> None:
    paths = (
        ("portal", "login_url"),
        ("portal", "request_url"),
        ("request", "fields"),
        ("request", "submit_selector"),
        ("request", "success_selector"),
    )
    missing = [".".join(path) for path in paths if not nested_get(config, *path)]
    if missing:
        raise ConfigurationError(f"Missing configuration values: {', '.join(missing)}")


def nested_get(value: dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def save_manual_login(config: dict[str, Any], auth_state: Path) -> None:
    login_url = nested_get(config, "portal", "login_url")
    if not login_url:
        raise ConfigurationError("Missing configuration value: portal.login_url")
    auth_state.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")
        sso_button_text = nested_get(config, "login", "sso_button_text")
        if sso_button_text:
            page.get_by_role("button", name=sso_button_text, exact=True).click()
        print("Complete Microsoft login in the browser, including any MFA. Then return here and press Enter.")
        input()
        session_url = nested_get(config, "portal", "session_url")
        if session_url:
            response = context.request.get(session_url)
            try:
                session = response.json()
            except Exception as error:
                raise RuntimeError("The portal did not return a valid login session.") from error
            if not response.ok or not session.get("user"):
                raise RuntimeError("Microsoft login was not completed; browser session was not saved.")
        context.storage_state(path=str(auth_state))
        browser.close()
    print(f"Saved browser session to {auth_state}")


def fill_field(page: Page, selector: str, value: str) -> None:
    locator = page.locator(selector).first
    locator.wait_for(state="visible")
    tag_name = locator.evaluate("element => element.tagName.toLowerCase()")
    role = locator.get_attribute("role")
    if locator.get_attribute("readonly") is not None:
        current_value = locator.input_value()
        if current_value == value:
            return
        raise ConfigurationError(
            f"The portal locked {selector} to {current_value!r}, which does not match {value!r}."
        )
    if tag_name == "select":
        locator.select_option(value=value)
    elif role == "combobox":
        locator.click()
        page.get_by_role("option", name=value, exact=True).click()
    else:
        locator.fill(value)


def credential_login(page: Page, config: dict[str, Any]) -> None:
    username = os.getenv("COLLEGE_USERNAME")
    password = os.getenv("COLLEGE_PASSWORD")
    if not username or not password:
        raise ConfigurationError(
            "No saved session was found. Run `outpass login` or set COLLEGE_USERNAME and COLLEGE_PASSWORD."
        )
    login = nested_get(config, "login") or {}
    required = ("username_selector", "password_selector", "submit_selector", "success_selector")
    missing = [name for name in required if not login.get(name)]
    if missing:
        raise ConfigurationError(f"Missing login configuration values: {', '.join(missing)}")
    page.goto(config["portal"]["login_url"], wait_until="domcontentloaded")
    fill_field(page, login["username_selector"], username)
    fill_field(page, login["password_selector"], password)
    page.locator(login["submit_selector"]).first.click()
    try:
        page.locator(login["success_selector"]).first.wait_for(state="visible")
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            "Login did not complete. If the site uses CAPTCHA, SSO, or OTP, run `outpass login` manually."
        ) from error


def apply_request(
    config: dict[str, Any],
    request: RequestData,
    auth_state: Path,
    submit: bool,
    headless: bool,
) -> Path:
    require_config(config)
    DEFAULT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    screenshot = DEFAULT_ARTIFACT_DIR / f"{'submitted' if submit else 'preview'}-{stamp}.png"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context_options: dict[str, Any] = {}
        if auth_state.exists():
            context_options["storage_state"] = str(auth_state)
        context = browser.new_context(**context_options)
        page = context.new_page()
        if not auth_state.exists():
            credential_login(page, config)

        page.goto(config["portal"]["request_url"], wait_until="domcontentloaded")
        open_button_text = nested_get(config, "request", "open_button_text")
        if open_button_text:
            page.get_by_role("button", name=open_button_text, exact=True).click()
            page.get_by_role("dialog").wait_for(state="visible")
        for field_name, selector in config["request"]["fields"].items():
            if field_name not in request.as_dict():
                raise ConfigurationError(f"Configured field is not supported: {field_name}")
            value = request.as_dict()[field_name]
            if value:
                fill_field(page, selector, value)

        page.screenshot(path=str(screenshot), full_page=True)
        if submit:
            page.locator(config["request"]["submit_selector"]).first.click()
            try:
                page.locator(config["request"]["success_selector"]).first.wait_for(state="visible")
            except PlaywrightTimeoutError as error:
                failure = DEFAULT_ARTIFACT_DIR / f"submission-failed-{stamp}.png"
                page.screenshot(path=str(failure), full_page=True)
                raise RuntimeError(f"Submission could not be confirmed. Screenshot: {failure}") from error
            page.screenshot(path=str(screenshot), full_page=True)
        browser.close()
    return screenshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or submit a college outpass request.")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="Log in manually and save the browser session.")
    login.add_argument("--auth-state", type=Path, default=DEFAULT_AUTH_STATE)

    apply = subparsers.add_parser("apply", help="Fill an outpass request form.")
    apply.add_argument("request_file", type=Path)
    apply.add_argument("--auth-state", type=Path, default=DEFAULT_AUTH_STATE)
    apply.add_argument("--submit", action="store_true", help="Actually submit; omitted means preview only.")
    apply.add_argument("--show-browser", action="store_true")
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    try:
        config = load_json(args.config)
        if args.command == "login":
            save_manual_login(config, args.auth_state)
            return
        request = RequestData.from_mapping(load_json(args.request_file))
        screenshot = apply_request(
            config, request, args.auth_state, submit=args.submit, headless=not args.show_browser
        )
        action = "submitted" if args.submit else "prepared (not submitted)"
        print(f"Request {action}. Screenshot: {screenshot}")
    except (ConfigurationError, RuntimeError, PlaywrightTimeoutError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
