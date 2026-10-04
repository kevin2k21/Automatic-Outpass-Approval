# Automatic Outpass Request

A configurable browser automation tool for preparing outpass requests on your own college account. It previews requests by default and submits only when `--submit` is explicitly supplied.

It does **not** bypass CAPTCHA, OTP, MFA, approval rules, or portal access controls. Use it only where your college permits automation.

## Requirements

- Python 3.11 or newer
- A supported macOS, Linux, or Windows environment for Playwright
- Access to your college portal
- Permission to automate your own account

The optional daily background scheduler uses macOS `launchd` and therefore only works on macOS.

## 1. Install the project

Clone the repository and enter its directory:

```bash
git clone https://github.com/kevin2k21/Automatic-Outpass-Approval.git
cd Automatic-Outpass-Approval
```

Create a virtual environment, install the project, and install Chromium for Playwright:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
playwright install chromium
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## 2. Create your local configuration

Copy the sanitized examples:

```bash
cp config.example.json config.json
cp request.example.json request.json
cp daily-config.example.json daily-config.json
```

On Windows PowerShell, use:

```powershell
Copy-Item config.example.json config.json
Copy-Item request.example.json request.json
Copy-Item daily-config.example.json daily-config.json
```

These local files are excluded from Git because they may contain portal details, schedules, destinations, or other personal information. Commit only the `.example.json` files.

## 3. Configure your portal

Open `config.json` and replace the example URLs and selectors with values from your portal.

```json
{
  "portal": {
    "login_url": "https://portal.example.edu/login",
    "request_url": "https://portal.example.edu/student/outpass/new"
  },
  "login": {
    "username_selector": "input[name='username']",
    "password_selector": "input[name='password']",
    "submit_selector": "button[type='submit']",
    "success_selector": "nav .student-profile"
  },
  "request": {
    "fields": {
      "request_type": "select[name='requestType']",
      "holiday_subtype": "select[name='holidaySubtype']",
      "departure_date": "input[name='departureDate']",
      "departure_time": "input[name='departureTime']",
      "return_date": "input[name='returnDate']",
      "return_time": "input[name='returnTime']",
      "place": "input[name='place']",
      "purpose": "textarea[name='purpose']"
    },
    "submit_selector": "button[type='submit']",
    "success_selector": ".alert-success"
  }
}
```

The selectors above are examples; most portals use different HTML.

### Finding selectors

1. Sign in to the portal normally and open its outpass form.
2. Open the browser developer tools and choose the element inspector.
3. Select each input, dropdown, submit button, and success message.
4. Prefer a stable `id`, `name`, or `data-*` attribute over generated class names.
5. Enter the resulting CSS selectors in `config.json`.

Examples of useful selectors:

```text
#departure-date
input[name='departureDate']
select[data-field='request-type']
button[type='submit']
```

Every configured field name must be one of:

- `request_type`
- `holiday_subtype`
- `departure_date`
- `departure_time`
- `return_date`
- `return_time`
- `place`
- `purpose`

If your portal opens the form from a button, add `request.open_button_text` with the button's exact visible text. If your SSO flow starts from a button, add `login.sso_button_text` in the same way. See `config.example.json` for the basic structure.

Custom date pickers, non-standard dropdowns, multi-step forms, or different fields may require an adapter change in `src/outpass/cli.py`.

## 4. Sign in safely

### SSO, OTP, or MFA portals

Save an authenticated browser session:

```bash
outpass login
```

A browser opens. Complete the login yourself, including any OTP or MFA prompt, then return to the terminal and press Enter. The browser session is saved locally as `auth-state.json`.

Treat `auth-state.json` like a password. Never commit, upload, or share it. The file is already excluded by `.gitignore`.

If the saved session expires, run `outpass login` again.

### Username and password portals

Only use this option if the portal provides a normal username/password form without CAPTCHA, OTP, or MFA.

```bash
cp .env.example .env
```

Set your credentials in `.env`:

```dotenv
COLLEGE_USERNAME=your_username
COLLEGE_PASSWORD=your_password
```

The `.env` file is excluded from Git. Do not place real credentials in `config.json`, source files, command-line arguments, or screenshots.

## 5. Prepare a request

Edit `request.json` with the request you want to create:

```json
{
  "request_type": "Working Day Pass",
  "holiday_subtype": "",
  "departure_date": "2026-10-05",
  "departure_time": "09:00",
  "return_date": "2026-10-05",
  "return_time": "18:00",
  "place": "City center",
  "purpose": "Personal errand"
}
```

Dates use `YYYY-MM-DD`, and times use 24-hour `HH:MM` format. The return date and time must be later than the departure date and time.

Supported request types are:

- `Weekend Pass`
- `Evening Out Pass`
- `Working Day Pass`
- `Holiday Pass`

For `Holiday Pass`, set `holiday_subtype` to `Study Holiday`, `Semester Break`, or `Declared Holiday`. For other request types, leave it empty.

## 6. Preview before submitting

Always begin with a visible preview:

```bash
outpass apply request.json --show-browser
```

Without `--submit`, the tool fills the form and takes a screenshot but does not intentionally click the submit button. Review the browser and the image under `artifacts/` to confirm that:

- every field contains the expected value;
- dates and times are correct;
- the request type is correct;
- no unrelated control was changed; and
- the submit and success selectors match the correct elements.

If the preview is incorrect, close the browser, update `config.json`, and repeat the preview.

## 7. Submit the request

Once the preview is correct, explicitly enable submission:

```bash
outpass apply request.json --show-browser --submit
```

The tool waits for `request.success_selector` after clicking submit. If it cannot confirm success, it exits with an error and saves a failure screenshot under `artifacts/`. Check the portal directly before retrying so that you do not create a duplicate request.

The portal's normal approval workflow remains unchanged; this tool only creates the request.

## Optional: daily automation on macOS

Daily automation is intentionally opt-in. First complete a successful manual preview and submission so you know the portal configuration works.

Edit `daily-config.json`:

```json
{
  "timezone": "UTC",
  "schedule_time": "11:00",
  "latest_attempt_time": "16:00",
  "check_interval_seconds": 300,
  "network_timeout_seconds": 10,
  "portal_config": "config.json",
  "auth_state": "auth-state.json",
  "attempt_directory": "artifacts/daily-attempts",
  "headless": true,
  "request": {
    "request_type": "Evening Out Pass",
    "holiday_subtype": "",
    "departure_time": "16:00",
    "return_time": "21:00",
    "place": "City center",
    "purpose": "Personal errand"
  }
}
```

The scheduler uses the current date for both the departure and return dates. Do not use it for overnight or future-date requests without adapting the code.

Test the daily command manually before installing it:

```bash
./run-daily-outpass --verbose
```

Be aware that running it within the configured time window can submit a real request. The daily command always invokes the submission path; it is not a preview command.

Install and load the macOS LaunchAgent:

```bash
outpass-install-macos install
```

The agent runs at the scheduled time and checks periodically until the cutoff. It atomically records the first real attempt under `artifacts/daily-attempts/`; success and failure both consume that day's attempt to prevent duplicate submissions.

After changing `schedule_time` or `check_interval_seconds`, reinstall the LaunchAgent so `launchd` receives the new schedule:

```bash
outpass-install-macos install
```

Remove the background agent with:

```bash
outpass-install-macos uninstall
```

## Troubleshooting

### `File not found: config.json`

Copy `config.example.json` to `config.json` and run the command from the project directory.

### A field cannot be found or remains empty

Reinspect the element and update its selector. Confirm that the form is visible before the tool tries to fill it. If the form opens from a button, configure `request.open_button_text`.

### Login is not recognized

Run `outpass login` again and fully complete the login before pressing Enter. If the portal exposes a session endpoint, `portal.session_url` can be configured so the tool verifies that an authenticated user is present.

### Submission cannot be confirmed

Check the failure screenshot and inspect the portal directly before retrying. Update `request.success_selector` so it identifies an element that appears only after a successful submission.

### Playwright cannot launch Chromium

Run:

```bash
playwright install chromium
```

On Linux, additional system packages may be required; follow Playwright's installation message for your distribution.

## Development checks

Run the test suite with:

```bash
python -m pytest -q
```
