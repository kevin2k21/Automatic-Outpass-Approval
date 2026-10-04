# Automatic Outpass Request

A configurable browser automation tool for preparing outpass requests on your own college account. It previews requests by default and submits only when `--submit` is explicitly supplied.

It does **not** bypass CAPTCHA, OTP, approval rules, or portal access controls. Use it only where your college permits automation.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
cp config.example.json config.json
cp request.example.json request.json
```

`config.json` is already configured for SSN's Microsoft login and the discovered `/dashboard/request` route. The request-form selectors still need to be captured after an authenticated login.

## Login

For SSO or OTP portals, save a browser session:

```bash
outpass login
```

Complete login yourself in the opened browser and press Enter in the terminal. The resulting `auth-state.json` is sensitive and excluded from Git.

For SSN, the tool clicks **Sign in with Microsoft** automatically and verifies that the portal reports an authenticated user before saving the session. Your Microsoft password and MFA are never read or stored by this project.

For a basic username/password form, copy `.env.example` to `.env` and enter credentials. Never commit `.env`.

## Prepare and submit

First run a visible, non-submitting preview:

```bash
outpass apply request.json --show-browser
```

Check the screenshot under `artifacts/`. Once the selectors and values are correct, explicitly submit:

```bash
outpass apply request.json --show-browser --submit
```

The portal's own approval workflow remains unchanged; this tool only creates the request.

## Native macOS daily automation

All scheduling and request values are editable in `daily-config.json`: timezone, normal run time, cutoff time, connectivity-check interval, portal/session paths, pass type, departure and return times, destination, and purpose.

Install the native macOS LaunchAgent with:

```bash
source .venv/bin/activate
pip install -e '.[dev]'
outpass-install-macos install
```

The agent runs at the configured time and periodically checks again. Before the scheduled time it waits. From the scheduled time until the cutoff it checks portal connectivity; if the Mac or network was unavailable, the next run in that window can proceed. At or after the cutoff it records the day as missed and does not apply.

Immediately before the first real submission attempt, it atomically creates `artifacts/daily-attempts/YYYY-MM-DD.json`. Success or failure both consume the day's single attempt, so duplicate launch events cannot create duplicate applications.

Routine five-minute checks are silent. Already-handled, waiting, and temporarily offline states do not append to the logs or modify an existing daily JSON record. Use `./run-daily-outpass --verbose` when running manually if you want to see those routine statuses.

After changing `schedule_time` or `check_interval_seconds`, rerun `outpass-install-macos install` so launchd receives the new schedule. Other request values are read fresh on every run.

To remove the background agent:

```bash
outpass-install-macos uninstall
```

The saved Microsoft session in `auth-state.json` must remain valid.

## Customizing the adapter

`config.json` is mapped to the current SSN request dialog. The supported request fields are:

- `request_type`: `Weekend Pass`, `Evening Out Pass`, `Working Day Pass`, or `Holiday Pass`
- `holiday_subtype`: required only for a Holiday Pass
- `departure_date`
- `departure_time`
- `return_date`
- `return_time`
- `place`
- `purpose`

If the portal uses different fields, dynamic calendars, multi-step forms, or custom dropdowns, the adapter in `src/outpass/cli.py` will need a small portal-specific change.
# Automatic-Outpass-Approval
