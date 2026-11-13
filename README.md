# AI-Powered Browser Testing Agent

An AI-powered browser automation tool that turns plain-English test cases into
browser actions using **Python, Playwright, and Google Gemini**.

Instead of writing a separate automation script for each website, provide a
website URL and describe the test in plain English. The agent observes the live
page, selects one grounded action at a time, runs it in Chromium, and reports
`PASS`, `FAIL`, or `INCONCLUSIVE` with a JSON execution report.

## Project overview

The runner follows this workflow:

1. You provide a URL and a test case.
2. Gemini extracts supplied test data and creates checks for the expected result.
3. Playwright opens the page and observes visible interactive elements.
4. Gemini selects one next action from those observed elements.
5. The runner executes the action, observes the updated page, and repeats.
6. The runner verifies form values and expected page evidence before reporting
   the result.

## Features

- Natural-language test cases instead of page-specific scripts.
- Dynamic discovery of visible inputs, buttons, dropdowns, links, and controls.
- Playwright actions for filling, clicking, selecting, scrolling, hovering,
  waiting, and navigation.
- Gemini retry handling for temporary API failures.
- Protection against stale element references and repeated identical actions.
- Form submission is blocked unless the test case explicitly requests it.
- JSON result report and a screenshot for non-passing runs.

## Technology stack

| Technology | Purpose |
|---|---|
| Python | Application runtime |
| Playwright | Browser automation |
| Google Gemini | Natural-language planning and test-result judging |
| Google Gen AI SDK | Gemini API integration |
| python-dotenv | Local environment-variable loading |
| Chromium | Browser used by Playwright |

## Project structure

```text
AI-Browser-Testing-Agent/
|
├── agent.py                     # Command-line runner and execution loop
├── ai_planner.py                # Gemini planning and outcome evaluation
├── browser_observer.py          # Live-page element discovery
├── browser_actions.py           # Safe Playwright browser actions
├── test_data.py                 # Test data loaded from .env
├── requirements.txt             # Python dependencies
├── .gitignore                   # Keeps .env and virtual environments private
├── README.md                    # Setup and run instructions
├── APPROACH_AND_LIMITATIONS.md  # Short design and limitations note
└── reports/
    ├── latest_report.json       # Most recent execution result
    └── failure.png              # Screenshot created for a non-pass result
```

## Installation and setup

### 1. Install prerequisites

Install these before continuing:

- [Python 3.10 or later](https://www.python.org/downloads/)
- Git (only needed to clone the repository)
- A Google Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

Open **PowerShell** and confirm that Python is available:

```powershell
python --version
```

### 2. Clone the repository

```powershell
git clone https://github.com/HarshVardhan264/AI-Browser-Testing-Agent.git
cd AI-Browser-Testing-Agent
```

If you already have the project folder, open PowerShell in that folder instead.

### 3. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once for the current PowerShell
window, then activate the environment again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 4. Install Python packages

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Install the Playwright browser

```powershell
python -m playwright install chromium
```

### 6. Create your local `.env` file

Create a file named `.env` in the project root. Add your Gemini API key:

```env
GEMINI_API_KEY=your_gemini_api_key

# Optional: use a different supported Gemini model.
GEMINI_MODEL=gemini-2.5-flash

# Optional reusable values for tests that need them.
TEST_USERNAME=
TEST_PASSWORD=
TEST_EMAIL=
TEST_PHONE=
```

Values written directly in a test case are used for that test. The optional
`TEST_*` values are useful for credentials or other data you do not want to put
in every command. `.env` is ignored by Git; never commit it.

## Running the project

Run every command from the project folder with the virtual environment active.

### Run a test supplied directly on the command line

```powershell
python agent.py https://phptravels.com/demo --headless --non-interactive -t "Verify that the page title contains PHPTRAVELS."
```

Remove `--headless` if you want to watch the Chromium browser while the test
runs.

### Run a login test

Use an authorized test account only. For example, after setting `TEST_USERNAME`
and `TEST_PASSWORD` in `.env`:

```powershell
python agent.py https://example.com/login --headless --non-interactive -t "Log in as a customer using the configured username and password, then verify the dashboard is shown."
```

### Run a multi-line test from a file

1. Create a file named `testcase.txt` in the project folder.
2. Add the test case, for example:

```text
Open the PHPTRAVELS demo form and fill these fields without submitting it.
First name: Test
Last name: User
Country: India
WhatsApp number: 9876543210
```

3. Run it:

```powershell
python agent.py https://phptravels.com/demo -f testcase.txt --headless --non-interactive
```

### Useful command options

| Option | Description |
|---|---|
| `-t`, `--test-case` | Test case supplied directly in the command |
| `-f`, `--test-case-file` | Path to a file containing the test case |
| `--headless` | Run without showing the browser window |
| `--max-steps 40` | Set the maximum number of AI-selected actions |
| `--report reports/my_report.json` | Save the report at a custom path |

The command exits with code `0` only when the result is `PASS`. `FAIL` and
`INCONCLUSIVE` return code `1`, which makes the tool suitable for CI checks.

## Test output and failures

Every run writes a structured report to `reports/latest_report.json` unless you
provide `--report`. The report includes the test status, actions taken, field
verification, assertions, URLs, and any error.

For a non-pass result, the runner also attempts to save a full-page screenshot
to `reports/failure.png`.

## Approach and limitations

The agent observes before acting: it sends only the currently observed page
controls to Gemini, validates the action Gemini returns, and performs it with
Playwright. This prevents invented selectors and arbitrary browser code. Read
the short [approach and limitations note](APPROACH_AND_LIMITATIONS.md) for the
design details and known constraints.

## Security

- Keep Gemini keys and test credentials in `.env`.
- Do not commit `.env` or use personal credentials in test cases.
- Use dedicated test accounts and environments.
- Do not use the runner to submit payments, place orders, or change production
  data unless you have explicit authorization.
