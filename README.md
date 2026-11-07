# AI-Powered Browser Testing Agent

An AI-powered browser automation tool that converts plain-English test cases into automated browser actions using **Python, Playwright, and Google Gemini**.

The agent understands natural-language instructions, observes website elements, plans actions, interacts with the browser, verifies results, and generates a test execution report.


## 1. Project Overview

Traditional browser automation tools often require developers to write individual scripts for every website and test scenario.

This project aims to simplify browser testing by allowing users to describe their test requirements in plain English.

Instead of manually writing browser automation scripts, users provide:

- A website URL.
- A test case written in natural language.
- Test data, when required.

The AI agent interprets the instructions, identifies relevant website elements, performs browser interactions, and evaluates whether the requested task was completed successfully.

**Example:**

```text
Website URL:
https://phptravels.com/demo

Test Case:
Open the demo form and complete all required fields.

First name: Tripti
Last name: Kumari
Business name: EZ Labs
Country: India
WhatsApp number: 9876543210
```

The agent observes the page, identifies the relevant fields, fills in the supplied information, verifies the values, and generates a test report.


## 2. Objectives

The main objectives of this project are:

- Convert plain-English test cases into automated browser tests.
- Use AI to understand testing instructions and plan browser actions.
- Automate website interactions without requiring website-specific scripts.
- Support different websites and previously unseen test scenarios.
- Identify missing test data and request user input when necessary.
- Verify actual browser results instead of relying only on AI predictions.
- Generate structured test execution reports.


## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| Playwright | Browser automation and interaction |
| Google Gemini | Natural-language understanding and AI planning |
| Asyncio | Asynchronous browser execution |
| python-dotenv | Environment variable management |
| JSON | Structured actions and execution reports |


## 4. System Architecture

The application follows an AI-driven browser testing workflow.

```text
             USER INPUT
                  |
                  v
       Website URL + Test Case
                  |
                  v
          TEST DATA EXTRACTION
                  |
                  v
          AI TEST PLANNER
          (Google Gemini)
                  |
                  v
          BROWSER OBSERVER
             (Playwright)
                  |
                  v
          PAGE INFORMATION
       Elements, Labels, Fields
                  |
                  v
          AI ACTION PLANNER
                  |
                  v
          BROWSER ACTIONS
       Fill | Click | Select | Wait
                  |
                  v
          RESULT VERIFICATION
                  |
                  v
          OUTCOME EVALUATION
                  |
                  v
          TEST EXECUTION REPORT
                  |
                  v
             PASS / FAIL
             / INCONCLUSIVE
```

### Workflow Explanation

**1. User Input**

The user provides a website URL and describes the test scenario in plain English.

**2. Test Data Extraction**

The system extracts relevant test values from the supplied instructions and configured environment variables.

**3. AI Test Planning**

Google Gemini interprets the test case and generates a structured testing plan.

**4. Browser Observation**

Playwright opens the website and collects information about visible elements, form fields, labels, and other relevant page content.

**5. AI Action Planning**

The AI uses the test instructions and observed page information to determine the next browser action.

**6. Browser Execution**

Playwright performs the required actions, such as filling fields, clicking elements, selecting options, and waiting for page changes.

**7. Verification**

The agent checks the actual browser state and compares observed values with the expected test data.

**8. Test Reporting**

The system evaluates the available evidence and generates a structured report containing the test status, execution steps, verification results, and errors.


## 5. Project Structure

The project is organized into separate modules to keep browser automation, AI planning, data management, and reporting responsibilities independent.

```text
AI-Browser-Testing-Agent/
│
├── agent.py
│   └── Main application and test execution workflow
│
├── ai_planner.py
│   └── Gemini integration, test planning,
│       browser action planning and outcome evaluation
│
├── browser_observer.py
│   └── Observes website elements and page information
│
├── browser_actions.py
│   └── Executes browser actions using Playwright
│
├── test_data.py
│   └── Loads and manages reusable test data
│
├── inspect_page.py
│   └── Helps inspect website elements and page structure
│
├── neki.css
│   └── [Include only if this file is actually used by the project]
│
├── requirements.txt
│   └── Python dependencies
│
├── .env
│   └── Local environment variables and test data
│
├── .env.example
│   └── Example environment configuration
│
├── .gitignore
│   └── Files excluded from Git tracking
│
└── README.md
    └── Project documentation
```


## 6. Installation and Setup

### Prerequisites

Install the following before running the project:

- Python 3.10 or a compatible version supported by the installed dependencies.
- Google Gemini API key.
- Google Chrome or another Playwright-supported browser.
- Git (optional, for repository management).

### Step 1: Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
```

Navigate into the project directory:

```bash
cd AI-Browser-Testing-Agent
```

### Step 2: Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

On macOS/Linux:

```bash
source venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Install Playwright browsers

```bash
python -m playwright install chromium
```

### Step 5: Configure environment variables

Create a `.env` file in the project root.

Add your Gemini API key and any reusable test data.

Example:

```env
GEMINI_API_KEY=your_gemini_api_key

TEST_EMAIL=your_test_email@example.com
TEST_PHONE=9876543210
TEST_USERNAME=testuser
TEST_PASSWORD=your_test_password

TEST_FIRST_NAME=Test
TEST_LAST_NAME=User
TEST_FULL_NAME=Test User
TEST_COMPANY=Example Company
TEST_COUNTRY=India
```

Use the exact Gemini API-key variable name expected by your `ai_planner.py` configuration. Keep API keys and real credentials private.

**Important:** Never upload your actual `.env` file to GitHub.


## 7. Running the Application

The application can be executed through the command line.

### Option 1: Provide a test case directly

```bash
python agent.py https://phptravels.com/demo -t "Open the demo form and complete all required fields."
```

### Option 2: Enter a test case interactively

```bash
python agent.py
```

If prompted, enter the website URL and test case.

### Option 3: Run a test case from a file

Create a text file such as `testcase.txt` containing your instructions.

Example:

```text
Open the demo form and complete all required fields.

First name: Test
Last name: User
Business name: Example Company
Country: India
WhatsApp number: 9876543210
```

Run:

```bash
python agent.py https://phptravels.com/demo -f testcase.txt
```

*Command-line options should match the arguments supported by the current version of `agent.py`.*


## 8. Key Features

### 8.1 Natural-Language Test Execution

Users can write test cases in plain English instead of manually creating browser automation scripts.

### 8.2 AI-Based Test Planning

Google Gemini interprets the instructions and helps determine the browser actions needed to complete the requested task.

### 8.3 Dynamic Browser Observation

The agent observes website elements and uses their available information to identify fields and interactive controls.

### 8.4 Automated Browser Interaction

Playwright performs browser operations, including:

- Filling text fields.
- Clicking buttons and links.
- Selecting dropdown options.
- Scrolling through pages.
- Waiting for page changes.

### 8.5 Missing Test Data Handling

When a required value is missing, the agent can request the user to provide it through the terminal or directly through the highlighted browser field.

The system is designed to avoid inventing missing test values.

### 8.6 Environment-Based Test Data

Reusable test values can be configured through environment variables.

Values explicitly supplied in the test case take priority over configured defaults.

### 8.7 Result Verification

The agent checks actual browser values and available page evidence to evaluate the requested outcome.

### 8.8 Submission Protection

The agent avoids submitting forms unless submission is requested by the test case.

### 8.9 Structured Test Reports

The system generates a JSON report containing execution steps, verification results, submission information, errors, and the final verdict.

---

## 9. Example Test Scenarios

### Scenario 1: Form Completion

**Input:**

```text
Open the PHPTRAVELS demo page and complete the form.

First name: Test
Last name: User
Business name: Example Company
Country: India
WhatsApp number: 9876543210
```

**Expected behaviour:**

- Open the website.
- Identify the relevant form fields.
- Fill in the supplied values.
- Verify the actual field values.
- Avoid submitting the form unless requested.
- Generate the execution report.

### Scenario 2: Missing Test Data

**Input:**

```text
Open the demo form and complete it.

First name: Test
Last name: User
Business name:
Country: India
```

**Expected behaviour:**

If Business Name is required and no usable value is available, the agent should request the missing value rather than inventing one.

### Scenario 3: Login and Dashboard Verification

**Input:**

```text
Log in as a customer and verify that the dashboard is shown.
```

**Expected behaviour:**

- Identify the login fields.
- Use available login credentials.
- Perform the login action.
- Observe the resulting page.
- Verify evidence that the dashboard is displayed.

This scenario requires valid test credentials and a website that supports the requested login workflow.


## 10. Test Execution Report

The agent produces a structured JSON report.

Example:

```json
{
  "website": "https://phptravels.com/demo",
  "status": "PASS",
  "reason": "All requested form fields were successfully filled and verified.",
  "steps": [
    {
      "step": 1,
      "action": {
        "action": "fill",
        "target": "first_name",
        "value": "Test"
      },
      "result": "Filled field"
    }
  ],
  "data_verification": [
    {
      "field": "first_name",
      "expected": "Test",
      "actual": "Test",
      "status": "PASS"
    }
  ],
  "submission": {
    "allowed_by_test_case": false,
    "clicked": false
  },
  "error": null
}
```

### Test Verdicts

| Verdict | Meaning |
|---|---|
| PASS | The requested outcome was achieved and supported by verification evidence. |
| FAIL | The requested outcome was not achieved or a required check failed. |
| INCONCLUSIVE | The available evidence was insufficient to determine the result reliably. |

A successful form-filling test does not require submission when the user only requested field completion.


## 11. Limitations

Although the agent supports general-purpose browser testing, it has some limitations:

1. **Dynamic websites:** Complex JavaScript-heavy pages and frequently changing layouts may affect element identification.
2. **Authentication:** Login workflows require valid credentials and may encounter additional security checks.
3. **CAPTCHA:** CAPTCHA and other anti-bot mechanisms may require manual interaction. The agent does not guarantee automated CAPTCHA solving.
4. **Website compatibility:** Some websites may block automation or restrict browser access.
5. **AI interpretation:** Gemini may misunderstand ambiguous or incomplete instructions.
6. **Complex workflows:** Multi-page workflows, unusual widgets, and advanced interactions may require additional planning and verification.
7. **Verification:** A test cannot be considered successful when the required result cannot be independently verified.

The tool is intended for authorized testing and demonstration websites.

## 12. Security Considerations

- Store API keys and test credentials in local environment variables.
- Do not commit `.env` files to GitHub.
- Use dedicated test accounts instead of personal accounts.
- Avoid using sensitive production data.
- Do not perform unauthorized testing on third-party websites.
- Review browser actions before executing tests that could submit forms, make payments, or modify real data.

## 13. Future Enhancements

Possible future improvements include:

- Support for more complex multi-page test workflows.
- Screenshot-based test evidence.
- HTML and PDF test reports.
- Improved handling of dynamic web elements.
- Test execution history and dashboard.
- Parallel browser testing.
- Support for additional AI models.
- Better handling of authentication and session management.


## 14. Conclusion

The AI-Powered Browser Testing Agent demonstrates how artificial intelligence can simplify browser automation by converting natural-language test instructions into executable browser actions.

By combining Google Gemini's language understanding capabilities with Playwright's browser automation functionality, the project provides a flexible approach to automated website testing.

The system reduces the need to write individual automation scripts for every test scenario and aims to support testing across different websites using a common natural-language interface.

## 15. Author and Project Information

**Project:** AI-Powered Browser Testing Agent

**Programming Language:** Python

**AI Model:** Google Gemini

**Automation Framework:** Playwright

**Project Type:** AI-Based Software Testing Automation

**Repository:** Add your GitHub repository URL here.
