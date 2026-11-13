# Plain-English Browser Test Runner

Runs a natural-language test case against a real browser and reports `PASS`,
`FAIL`, or `INCONCLUSIVE`. It is not tied to a particular site: the runner
observes the current page, has Gemini choose one grounded browser action at a
time, and only lets it target controls found in that observation.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file with:

```text
GEMINI_API_KEY=your_key
# Optional; defaults to gemini-2.5-flash
GEMINI_MODEL=gemini-2.5-flash
```

Optional reusable test values can also be set in `.env`, for example
`TEST_EMAIL` and `TEST_PASSWORD`. Values written directly in a test case are
extracted and used for that run.

## Run

```powershell
python agent.py https://phptravels.com/demo --headless --non-interactive -t "Verify that the page title contains PHPTRAVELS."
```

For a multi-line case, put the case in a text file and use `-f`:

```powershell
python agent.py https://example.com -f testcase.txt --headless --non-interactive
```

The process exits `0` only for `PASS`; `1` means `FAIL` or `INCONCLUSIVE`.
Each run writes JSON evidence to `reports/latest_report.json` by default. A
non-pass result also attempts to save `reports/failure.png`.

## Safety and scope

The runner allows only Playwright actions against element references produced
from the live page, refreshes those references after each action, and refuses
to submit a form unless the test case asks for submission. It does not bypass
CAPTCHAs or anti-bot challenges. For any test that can create accounts, place
orders, or otherwise change external data, use a dedicated test environment.

## Approach and limitations

The runner turns a test case into a closed loop: it inventories the visible
interactive elements, supplies that constrained page state to Gemini, validates
the single action Gemini returns, performs it with Playwright, and observes the
page again. It separately verifies form values and deterministic checks (URL,
title, text, and element visibility) before asking the model to judge the final
outcome. This keeps the model from using invented selectors or issuing arbitrary
browser code.

It is a lightweight test agent rather than a replacement for stable,
maintained Playwright tests. Dynamic interfaces, inaccessible custom controls,
multi-factor authentication, CAPTCHAs, rate limiting, and ambiguous natural
language can lead to `INCONCLUSIVE`. The quality and latency of a run also
depend on the configured Gemini model and network availability. Use explicit
expected outcomes and dedicated non-production accounts for reliable results.
