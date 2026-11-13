# Approach and limitations

## Approach

The runner observes the live page, sends the visible controls and test case to
Gemini, validates the single action it returns, and performs that action with
Playwright. It repeats this loop until the task is complete, then verifies form
values and concrete checks such as expected URL, title, text, or visible
elements before reporting `PASS`, `FAIL`, or `INCONCLUSIVE`.

## Limitations

Results depend on the Gemini model, site availability, and clear test-case
wording. CAPTCHAs, multi-factor login, anti-bot systems, inaccessible custom
controls, and complex dynamic workflows may result in `INCONCLUSIVE`. Use
dedicated test accounts and environments for any workflow that changes data.
