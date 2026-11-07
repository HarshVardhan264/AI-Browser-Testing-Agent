"""
AI browser testing agent.

Usage:
    python agent.py https://example.com -t "Log in as a customer and verify the dashboard is shown"
    python agent.py https://example.com -f testcase.txt --headless --non-interactive

Exit code: 0 = PASS, 1 = FAIL or INCONCLUSIVE.
"""

import argparse
import asyncio
import getpass
import json
import os
import re
import sys
import time

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from browser_observer import observe_page
from browser_actions import (
    fill_element,
    click_element,
    select_element,
    scroll_element,
    hover_element,
    wait_page,
    navigate_page,
)
from ai_planner import (
    get_next_action,
    create_test_plan,
    extract_test_data,
    judge_outcome,
)
from test_data import get_test_data

load_dotenv()

DEFAULT_MAX_STEPS = 30
ACTION_TIMEOUT = 15000
MAX_CONSECUTIVE_ERRORS = 3
MAX_REPEATS = 3
MAX_SUBMIT_BLOCKS = 2

NON_INTERACTIVE = False


class MissingDataError(Exception):
    """A value the test needs was neither supplied nor available."""


# ---------------------------------------------------------------------
# TEXT HELPERS
# ---------------------------------------------------------------------

def normalize(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def squash(value):
    return " ".join(str(value or "").split()).casefold()


SECRET_KEY = re.compile(
    r"(?:^|_)(?:password|passcode|pwd|secret|token|otp|pin|cvv|card_number|api_key)(?:_|$)"
)


def is_secret_key(key):
    return bool(SECRET_KEY.search(normalize(key)))


def read_multiline_test_case():
    print("\nEnter your test case.")
    print("Paste multiple lines if needed. Type END on its own line when finished.\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


NON_DATA_KEYS = {
    "expected", "expected_result", "expected_results", "result", "results",
    "step", "steps", "test_data", "note", "notes", "verify", "assert",
    "precondition", "preconditions", "test_case", "objective", "description",
    "scenario", "title", "given", "when", "then",
}


def fallback_extract_data(test_case):
    """Used only if the model-based extraction fails. Never removes text."""
    data = {}
    for line in test_case.splitlines():
        match = re.match(
            r"^\s*([A-Za-z][A-Za-z0-9 _-]{1,40})\s*[:=]\s*(.+?)\s*$", line
        )
        if not match:
            continue
        key = normalize(match.group(1))
        value = match.group(2).strip().strip("\"'")
        if key and value and key not in NON_DATA_KEYS and not key.startswith("step_"):
            data[key] = value
    return data


def mask_values(text, data):
    """Replace supplied values in the test case with {{key}} placeholders."""
    result = str(text or "")
    for key, value in sorted(
        data.items(), key=lambda kv: len(str(kv[1])), reverse=True
    ):
        value = str(value)
        if not value:
            continue
        result = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])",
            "{{" + key + "}}",
            result,
            flags=re.IGNORECASE,
        )
    return result


def secret_values(data):
    return [
        str(v) for k, v in data.items()
        if is_secret_key(k) and len(str(v)) >= 4
    ]


def redact_secrets(text, data):
    """Hide only secret values, only as whole tokens, case-sensitively."""
    result = str(text or "")
    for value in sorted(secret_values(data), key=len, reverse=True):
        result = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])",
            "[REDACTED]",
            result,
        )
    return result


def report_value(key, value):
    return "[REDACTED]" if is_secret_key(key) else str(value)


# ---------------------------------------------------------------------
# FIELD MATCHING (generic, label based)
# ---------------------------------------------------------------------

def data_key_aliases(key):
    aliases = {
        "name": {"name", "full_name", "your_name"},
        "full_name": {"name", "full_name", "your_name"},
        "first_name": {"first_name", "given_name"},
        "last_name": {"last_name", "surname", "family_name"},
        "email": {"email", "email_address", "e_mail"},
        "phone": {"phone", "phone_number", "mobile", "mobile_number", "telephone"},
        "username": {"username", "user_name", "login", "user_id"},
        "password": {"password", "passcode"},
        "company": {"company", "company_name", "business_name", "organization", "organisation"},
        "country": {"country", "country_region"},
        "city": {"city", "town"},
        "state": {"state", "province", "region"},
        "zip": {"zip", "zip_code", "postal_code", "postcode"},
        "address": {"address", "street_address", "your_address"},
        "gender": {"gender", "sex"},
        "date_of_birth": {"date_of_birth", "dob", "birth_date", "birthday"},
    }
    normalized = normalize(key)
    return {normalize(a) for a in aliases.get(normalized, {normalized})}


def element_label(element):
    return (
        element.get("label")
        or element.get("accessibleName")
        or element.get("ariaLabel")
        or element.get("placeholder")
        or element.get("name")
        or element.get("id")
        or element.get("text")
        or "Required field"
    )


def is_field(element):
    tag = element.get("tag")
    kind = str(element.get("type", "")).lower()
    if tag in {"textarea", "select"}:
        return True
    if tag == "input":
        return kind not in {"button", "submit", "reset", "image", "hidden", "file"}
    return element.get("role") in {
        "textbox", "searchbox", "combobox", "checkbox", "radio", "switch",
    }


def element_metadata(element):
    fields = [
        "label", "accessibleName", "ariaLabel", "labelledBy",
        "placeholder", "name", "id", "groupLabel",
    ]
    # innerText of select/textarea/input is options or content, not a label.
    if element.get("tag") not in {"select", "textarea", "input"}:
        fields.append("text")
    return normalize(" ".join(str(element.get(f, "") or "") for f in fields))


def matched_aliases(element, key):
    metadata = element_metadata(element)
    aliases = data_key_aliases(key)
    found = {
        a for a in aliases
        if a and re.search(rf"(?:^|_){re.escape(a)}(?:_|$)", metadata)
    }
    # Radio buttons are often identified only by their group's text.
    if not found and str(element.get("type", "")).lower() == "radio":
        group = normalize(element.get("parentText", ""))
        found = {
            a for a in aliases
            if a and re.search(rf"(?:^|_){re.escape(a)}(?:_|$)", group)
        }
    return found


def best_match(element, data):
    """Return (key, value) of the most specific supplied key for this field."""
    if not is_field(element):
        return None
    scored = []
    for key, value in data.items():
        found = matched_aliases(element, key)
        if found:
            scored.append((max(len(a) for a in found), key, value))
    if not scored:
        return None
    top_score = max(s[0] for s in scored)
    top = [s for s in scored if s[0] == top_score]
    if len({str(s[2]) for s in top}) != 1:
        return None  # ambiguous: do not guess
    return top[0][1], top[0][2]


def match_test_data(element, data):
    match = best_match(element, data)
    return match[1] if match else None


# ---------------------------------------------------------------------
# PROMPTING THE PERSON
# ---------------------------------------------------------------------

def ask_for_value(label):
    if NON_INTERACTIVE:
        raise MissingDataError(f"Missing test data for: {label}")

    print(f"\nValue needed for: {label}")
    print("1. Enter in terminal")
    print("2. Enter directly in the browser")
    while True:
        choice = input("Choose 1 or 2: ").strip()
        if choice == "1":
            value = (
                getpass.getpass("Enter value: ")
                if "password" in label.lower()
                else input(f"Enter {label}: ").strip()
            )
            if value:
                return "terminal", value
        elif choice == "2":
            return "browser", None
        print("Please choose 1 or 2 and provide a value.")


async def current_value(locator, element):
    kind = str(element.get("type", "")).lower()
    if kind in {"checkbox", "radio"}:
        return await locator.is_checked()
    return await locator.input_value()


async def fill_value(page, element, value):
    target = element["ref"]
    kind = str(element.get("type", "")).lower()

    if kind in {"checkbox", "radio"}:
        locator = page.locator(f'[data-agent-ref="{target}"]')
        want = str(value).strip().lower() in {"true", "yes", "1", "checked", "on"}
        if want and not await locator.is_checked():
            await locator.check(timeout=ACTION_TIMEOUT)
        elif not want and kind == "checkbox" and await locator.is_checked():
            await locator.uncheck(timeout=ACTION_TIMEOUT)
    elif element.get("tag") == "select":
        await select_element(page, target, str(value))
    else:
        await fill_element(page, target, str(value))


async def ask_for_browser_value(page, element, data):
    if NON_INTERACTIVE:
        raise MissingDataError(
            f"Missing test data for: {element_label(element)}"
        )

    target = element["ref"]
    label = element_label(element)
    locator = page.locator(f'[data-agent-ref="{target}"]')

    await locator.scroll_into_view_if_needed()
    await locator.focus()
    await locator.evaluate(
        "el => { el.style.outline = '3px solid #16a34a'; el.focus(); }"
    )
    print(f"\nEnter the value in the highlighted browser field: {label}")
    input("Press Enter here when finished...")

    try:
        value = await current_value(locator, element)
    finally:
        await locator.evaluate("el => el.style.outline = ''")

    if value in ("", None, False):
        raise ValueError(f"No value entered for {label}")
    data[normalize(label)] = value


# ---------------------------------------------------------------------
# REQUIRED FIELDS
# ---------------------------------------------------------------------

async def check_required_fields(page, observation, data, auto_log):
    """
    Complete required controls the planner left empty. Never invents values:
    uses supplied data, otherwise asks (or raises in non-interactive mode).
    Every automatic action is appended to auto_log.
    """
    elements = observation.get("elements", [])
    missing = []
    handled_groups = set()

    for element in elements:
        if not element.get("required") or element.get("disabled"):
            continue
        tag = element.get("tag")
        kind = str(element.get("type", "")).lower()
        if tag not in {"input", "textarea", "select"}:
            continue
        if kind in {"file", "button", "submit", "image", "reset", "hidden"}:
            continue
        target = element.get("ref")
        if not target:
            continue
        locator = page.locator(f'[data-agent-ref="{target}"]')
        if not await locator.is_visible():
            continue

        label = element_label(element)

        if kind == "radio":
            group_key = element.get("name") or normalize(
                element.get("groupLabel") or element.get("parentText", "")
            )
            if group_key in handled_groups:
                continue
            handled_groups.add(group_key)

            group = [
                item for item in elements
                if str(item.get("type", "")).lower() == "radio"
                and (
                    (element.get("name") and item.get("name") == element.get("name"))
                    or (
                        not element.get("name")
                        and normalize(item.get("parentText", ""))
                        == normalize(element.get("parentText", ""))
                    )
                )
            ]
            already = False
            for item in group:
                radio = page.locator(f'[data-agent-ref="{item["ref"]}"]')
                if await radio.is_checked():
                    already = True
                    break
            if already:
                auto_log.append({"field": label, "result": "already selected"})
                continue

            group_label = element.get("groupLabel") or element.get("parentText") or "Required choice"
            supplied = match_test_data(element, data)
            if supplied is None:
                _, supplied = ask_for_value(group_label + " (choose one option)")
            requested = normalize(supplied)
            choices = []
            for item in group:
                text = normalize(
                    " ".join(
                        str(item.get(k, "") or "")
                        for k in ("value", "label", "accessibleName", "text")
                    )
                )
                if requested == text or requested in text.split("_"):
                    choices.append(item)
            if len(choices) != 1:
                missing.append(group_label)
                continue
            await click_element(page, choices[0]["ref"])
            auto_log.append({"field": group_label, "result": "option selected"})
            continue

        current = await current_value(locator, element)
        if current not in ("", None, False):
            auto_log.append({"field": label, "result": "already filled (prefilled or earlier step)"})
            continue

        supplied = match_test_data(element, data)

        if kind == "checkbox":
            if supplied is None:
                _, supplied = ask_for_value(label + " (yes/no)")
            if str(supplied).strip().lower() in {"yes", "true", "1", "checked", "on"}:
                await locator.check(timeout=ACTION_TIMEOUT)
                auto_log.append({"field": label, "result": "checked"})
            else:
                missing.append(label)  # a required box cannot stay unchecked
            continue

        if supplied is None:
            mode, supplied = ask_for_value(label)
            if mode == "browser":
                await ask_for_browser_value(page, element, data)
            else:
                await fill_value(page, element, supplied)
                data[normalize(label)] = supplied
        else:
            await fill_value(page, element, supplied)

        current = await current_value(locator, element)
        if current in ("", None, False):
            missing.append(label)
        else:
            auto_log.append({"field": label, "result": "filled automatically"})

    return missing


# ---------------------------------------------------------------------
# SUBMIT DETECTION
# ---------------------------------------------------------------------

SUBMIT_WORDS = (
    "submit", "register", "sign up", "signup", "sign in", "log in", "login",
    "create account", "place order", "checkout", "pay", "send", "save",
    "book", "reserve", "subscribe", "apply",
)


def is_submit(element):
    """True for buttons or inputs that submit something. Plain links are not."""
    if not element:
        return False
    kind = str(element.get("type", "")).lower()
    if kind == "submit":
        return True
    if element.get("tag") not in {"button", "input"} and element.get("role") != "button":
        return False
    description = " ".join(
        str(element.get(k, "") or "")
        for k in ("text", "label", "accessibleName", "ariaLabel", "value")
    ).lower()
    return any(
        re.search(rf"\b{re.escape(word)}\b", description) for word in SUBMIT_WORDS
    )


def submission_is_required(test_case):
    text = test_case.lower()
    if re.search(
        r"\b(do not|don't|dont|without|never)\s+(click\s+|press\s+)?(submit|submitting|send|sending)",
        text,
    ):
        return False
    keywords = (
        "submit", "register", "registration", "sign up", "sign in", "log in",
        "login", "log into", "create account", "place order", "checkout",
        "send", "book", "reserve", "subscribe", "pay",
    )
    return any(re.search(rf"\b{re.escape(k)}\b", text) for k in keywords)


def is_fill_only_task(test_case):
    """Identify explicit form-population tasks that do not ask for submission."""
    text = str(test_case or "").lower()
    if submission_is_required(text):
        return False
    fill_intent = re.search(
        r"\b(fill|complete|populate|enter)\b.{0,100}\b"
        r"(required\s+)?(form\s+)?(fields?|inputs?|details|information)\b",
        text,
    )
    fields_intent = re.search(
        r"\b(complete|fill|populate)\s+(all\s+)?(the\s+)?"
        r"(required\s+)?fields?\b",
        text,
    )
    return bool(fill_intent or fields_intent)


# ---------------------------------------------------------------------
# ACTIONS
# ---------------------------------------------------------------------

def find_element(observation, target):
    return next(
        (e for e in observation.get("elements", []) if e.get("ref") == target), {}
    )


def resolve_value(value, data):
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\s*\{\{?([A-Za-z0-9_-]+)\}?\}\s*", value)
    if not match:
        return value
    return data.get(normalize(match.group(1)))


def resolve_radio_target(observation, element, data):
    requested = match_test_data(element, data)
    if requested is None:
        return element.get("ref")

    requested_text = normalize(requested)
    requested_number = re.search(r"\d+(?:\.\d+)?", str(requested))
    group_name = element.get("name", "")
    group_context = normalize(element.get("parentText", ""))

    candidates = []
    for item in observation.get("elements", []):
        if item.get("type") != "radio":
            continue
        same_group = group_name and item.get("name") == group_name
        same_context = (
            group_context and normalize(item.get("parentText", "")) == group_context
        )
        if same_group or same_context:
            candidates.append(item)

    matches = []
    for c in candidates:
        text = normalize(
            " ".join(
                str(c.get(k, "")) for k in ("value", "label", "accessibleName", "text")
            )
        )
        if requested_text == text:
            matches.append(c)
        elif requested_number:
            number = re.search(r"\d+(?:\.\d+)?", text)
            if number and number.group() == requested_number.group():
                matches.append(c)

    if len(matches) == 1:
        return matches[0]["ref"]
    if len(matches) > 1:
        raise ValueError(f"Multiple radio buttons match '{requested}'.")
    raise ValueError(f"Could not find radio option '{requested}'.")


async def execute_action(page, action, data, observation):
    kind = action.get("action")
    target = action.get("target")
    value = resolve_value(action.get("value", ""), data)
    element = find_element(observation, target)

    if kind in {"fill", "select"}:
        supplied = match_test_data(element, data)
        if supplied is not None:
            value = supplied
        if value in (None, ""):
            label = element_label(element)
            mode, value = ask_for_value(label)
            if mode == "browser":
                await ask_for_browser_value(page, element, data)
                return "Entered manually in browser"
            data[normalize(label)] = value
        if kind == "fill":
            await fill_value(page, element, value)
            return "Filled field"
        await select_element(page, target, str(value))
        return "Selected option"

    if kind == "click":
        if element.get("type") == "radio":
            target = resolve_radio_target(observation, element, data)
        await click_element(page, target)
        return "Clicked element"

    if kind == "wait":
        if target:
            await page.locator(f'[data-agent-ref="{target}"]').wait_for(
                state="visible", timeout=ACTION_TIMEOUT
            )
        else:
            ms = max(0, min(int(action.get("milliseconds", 1500)), 10000))
            await wait_page(page, ms)
        return "Waited"

    if kind == "scroll":
        if target:
            await scroll_element(page, target)
        else:
            direction = -600 if str(value).lower() == "up" else 600
            await page.mouse.wheel(0, direction)
        return "Scrolled"

    if kind == "hover":
        await hover_element(page, target)
        return "Hovered"

    if kind == "navigate":
        if not value:
            raise ValueError("Navigation action is missing its URL.")
        await navigate_page(page, str(value))
        return "Navigated"

    raise ValueError(f"Unsupported action: {kind}")


# ---------------------------------------------------------------------
# PAGE HANDLING
# ---------------------------------------------------------------------

async def settle(page, extra=600):
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    await page.wait_for_timeout(extra)


async def safe_observe(page):
    for attempt in range(3):
        try:
            return await observe_page(page)
        except Exception:
            if attempt == 2:
                raise
            await settle(page, 300)


def latest_page(context, current):
    """Follow popups and new tabs: the newest open page wins."""
    open_pages = [p for p in context.pages if not p.is_closed()]
    return open_pages[-1] if open_pages else current


async def safe_observation(page, observation, data):
    """Copy of the observation that is safe to send to the model."""
    safe = json.loads(json.dumps(observation))
    safe["pageText"] = redact_secrets(safe.get("pageText", ""), data)
    secrets = set(secret_values(data))

    for element in safe.get("elements", []):
        if element.get("tag") in {"input", "textarea", "select"}:
            value = element.get("value", "")
            if str(element.get("type", "")).lower() == "password":
                try:
                    locator = page.locator(f'[data-agent-ref="{element["ref"]}"]')
                    value = await locator.input_value(timeout=1000)
                except Exception:
                    value = ""
                element["value"] = "[VALUE PRESENT]" if value else ""
            elif value in secrets:
                element["value"] = "[VALUE PRESENT]"
        for key in ("text", "parentText"):
            element[key] = redact_secrets(element.get(key, ""), data)
    return safe


# ---------------------------------------------------------------------
# VERIFICATION
# ---------------------------------------------------------------------

def values_match(expected, actual, loose=False):
    expected_text = normalize(expected)
    actual_text = normalize(actual)
    if not expected_text:
        return False
    if expected_text == actual_text:
        return True

    if not re.search(r"[A-Za-z]", str(expected)):
        e_digits = re.sub(r"\D", "", str(expected))
        a_digits = re.sub(r"\D", "", str(actual))
        if len(e_digits) >= 7 and a_digits.endswith(e_digits):
            return True

    if loose:
        if re.search(rf"(?:^|_){re.escape(expected_text)}(?:_|$)", actual_text):
            return True
        e_num = re.search(r"\d+(?:\.\d+)?", str(expected))
        a_num = re.search(r"\d+(?:\.\d+)?", str(actual))
        return bool(e_num and a_num and e_num.group() == a_num.group())
    return False


async def read_actual(page, element):
    locator = page.locator(f'[data-agent-ref="{element["ref"]}"]')
    if element.get("tag") == "select":
        selected = locator.locator("option:checked")
        if await selected.count():
            return await selected.first.inner_text()
        return await locator.input_value()
    if str(element.get("type", "")).lower() == "checkbox":
        return "checked" if await locator.is_checked() else "unchecked"
    if element.get("tag") in {"input", "textarea"}:
        return await locator.input_value()
    return await locator.inner_text()


def narrow_candidates(candidates, key):
    aliases = data_key_aliases(key)
    exact = [c for c in candidates if normalize(element_label(c)) in aliases]
    if exact:
        return exact
    prefixed = [
        c for c in candidates
        if any(normalize(element_label(c)).startswith(a + "_") for a in aliases)
    ]
    return prefixed or candidates


async def _verify_candidates(page, elements, candidates, key, expected):
    """Return (status, actual_text)."""
    radios = [c for c in candidates if str(c.get("type", "")).lower() == "radio"]

    if radios:
        names = {c.get("name") for c in radios if c.get("name")}
        contexts = {
            normalize(c.get("parentText", "")) for c in radios if c.get("parentText")
        }
        group = [
            item for item in elements
            if str(item.get("type", "")).lower() == "radio"
            and (
                (item.get("name") and item.get("name") in names)
                or normalize(item.get("parentText", "")) in contexts
            )
        ]
        selected = None
        for item in group:
            radio = page.locator(f'[data-agent-ref="{item["ref"]}"]')
            if await radio.is_checked():
                selected = item
                break
        if selected is None:
            return "UNVERIFIED", ""
        actual = (
            selected.get("label") or selected.get("accessibleName")
            or selected.get("value") or selected.get("text") or ""
        )
        ok = values_match(expected, actual, loose=True)
        return ("PASS" if ok else "FAIL"), actual

    pool = narrow_candidates(candidates, key)
    readings = []
    for candidate in pool:
        try:
            value = await read_actual(page, candidate)
            readings.append((value, candidate.get("tag") == "select"))
        except Exception:
            pass  # hidden or unreadable

    for value, loose in readings:
        if values_match(expected, value, loose):
            return "PASS", value
    if len(readings) == 1:
        return "FAIL", readings[0][0]
    return "UNVERIFIED", ""


async def verify_supplied_values(page, observation, data, required_keys=None):
    """
    Read supplied values back from the live form.

    PASS / FAIL: field found and compared.
    UNVERIFIED: found but ambiguous or unreadable.
    NOT_ON_PAGE: a key from this test case has no matching field on this page.
    Keys that come only from .env defaults are skipped when no field matches.
    """
    elements = observation.get("elements", [])
    required_keys = {normalize(k) for k in (required_keys or set())}

    owners = {}
    for element in elements:
        match = best_match(element, data)
        if match:
            owners.setdefault(match[0], []).append(element)

    results = []
    for key, expected in data.items():
        candidates = owners.get(key, [])
        if not candidates:
            if normalize(key) in required_keys:
                results.append(
                    {
                        "field": key,
                        "expected": report_value(key, expected),
                        "actual": "No matching field on this page",
                        "status": "NOT_ON_PAGE",
                    }
                )
            continue
        try:
            status, actual = await _verify_candidates(
                page, elements, candidates, key, expected
            )
        except Exception:
            status, actual = "UNVERIFIED", ""
        results.append(
            {
                "field": key,
                "expected": report_value(key, expected),
                "actual": report_value(key, actual) if actual != "" else "Could not read field",
                "status": status,
            }
        )
    return results


ARITHMETIC = re.compile(r"(\d+)\s*([+\-\u2212x\u00d7*/\u00f7])\s*(\d+)\s*=")
CHALLENGE_WORDS = re.compile(
    r"captcha|security|human|verif|answer|math|sum|result|robot", re.IGNORECASE
)


def solve_arithmetic(a, op, b):
    a, b = int(a), int(b)
    if op == "+":
        return a + b
    if op in {"-", "\u2212"}:
        return a - b
    if op in {"x", "\u00d7", "*"}:
        return a * b
    if op in {"/", "\u00f7"} and b != 0 and a % b == 0:
        return a // b
    return None


async def verify_arithmetic(page, observation):
    """
    If a simple arithmetic question labels an input, compute it in code and
    compare with what is in the field. Independent of the model's arithmetic.
    """
    results = []
    for element in observation.get("elements", []):
        if not is_field(element) or str(element.get("type", "")).lower() in {
            "checkbox", "radio"
        }:
            continue

        own = " ".join(
            str(element.get(k, "") or "")
            for k in ("label", "accessibleName", "placeholder")
        )
        match = ARITHMETIC.search(own)
        if not match:
            identity = " ".join(
                str(element.get(k, "") or "") for k in ("name", "id", "label", "placeholder")
            )
            if CHALLENGE_WORDS.search(identity):
                match = ARITHMETIC.search(str(element.get("parentText", "")))
        if not match:
            continue

        expected = solve_arithmetic(*match.groups())
        if expected is None:
            continue
        try:
            actual = (
                await page.locator(f'[data-agent-ref="{element["ref"]}"]').input_value()
            ).strip()
        except Exception:
            continue

        if actual == "":
            status = "UNVERIFIED"
        else:
            status = "PASS" if actual == str(expected) else "FAIL"
        results.append(
            {
                "expression": match.group(0),
                "expected": str(expected),
                "actual": actual,
                "status": status,
            }
        )
    return results


async def verify_test_plan(page, plan):
    results = []
    for check in plan.get("checks", []):
        kind = check.get("type")
        expected = str(check.get("value", ""))
        passed = False
        actual = ""
        try:
            if kind == "url_contains":
                actual = page.url
                passed = expected.lower() in actual.lower()
            elif kind == "title_contains":
                actual = await page.title()
                passed = expected.lower() in actual.lower()
            elif kind == "text_contains":
                text = await page.locator("body").inner_text()
                passed = expected.lower() in text.lower()
                actual = "Found" if passed else "Not found"
            elif kind == "element_visible":
                locator = page.get_by_text(expected, exact=False)
                passed = await locator.first.is_visible()
                actual = "Visible" if passed else "Not visible"
        except Exception as error:
            actual = type(error).__name__

        results.append(
            {
                "type": kind,
                "description": check.get("description", ""),
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
        )
        print("PASSED:" if passed else "FAILED:", check.get("description", kind))
    return results


SUCCESS_HINTS = (
    "success", "thank you", "confirmed", "welcome", "dashboard",
    "submitted", "registered", "recorded", "logged in",
)
ERROR_HINTS = (
    "error", "invalid", "incorrect", "failed", "required", "try again",
    "not found", "denied", "wrong",
)


def page_signals(page_text):
    lowered = page_text.lower()
    return {
        "success_words_seen": [w for w in SUCCESS_HINTS if w in lowered],
        "error_words_seen": [w for w in ERROR_HINTS if w in lowered],
    }


def evidence_on_page(evidence, page_text, url, title):
    needle = squash(evidence)
    if len(needle) < 3:
        return False
    return needle in squash(page_text) or needle in squash(url) or needle in squash(title)


# ---------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------

def save_report(report, path):
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    print(f"\nReport saved: {path}")


def failure_screenshot_path(report_path):
    folder = os.path.dirname(report_path) or "."
    return os.path.join(folder, "failure.png")


# ---------------------------------------------------------------------
# MAIN RUN
# ---------------------------------------------------------------------

async def run_test(website_url, test_case, headless, max_steps, report_path):
    started = time.time()

    env_data = get_test_data(test_case)
    try:
        prompt_data = await asyncio.to_thread(extract_test_data, test_case)
    except Exception as error:
        print(f"Model-based data extraction failed ({error}); using fallback.")
        prompt_data = {}
    if not prompt_data:
        prompt_data = fallback_extract_data(test_case)

    data = {**env_data, **prompt_data}
    required_keys = set(prompt_data.keys())
    masked_case = mask_values(test_case, prompt_data)

    submit_allowed = submission_is_required(test_case)

    report = {
        "website": website_url,
        "test_case": masked_case,
        "test_data_keys_from_test_case": sorted(prompt_data.keys()),
        "test_data_keys_from_environment": sorted(set(env_data) - set(prompt_data)),
        "status": "INCONCLUSIVE",
        "reason": "",
        "steps": [],
        "auto_actions": [],
        "assertions": [],
        "data_verification": [],
        "arithmetic_verification": [],
        "submission": {"allowed_by_test_case": submit_allowed, "clicked": False},
        "submission_verification": {
            "required": False,
            "clicked": False,
            "verified": None,
            "evidence": "",
            "message": "No submission has been attempted.",
        },
        "verdict": None,
        "error": None,
    }

    history = []
    auto_log = []
    submit_clicked = False
    filled_any = False
    consecutive_errors = 0
    submit_blocks = 0
    signatures = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        context.set_default_timeout(ACTION_TIMEOUT)
        page = await context.new_page()

        try:
            await page.goto(website_url, wait_until="domcontentloaded", timeout=60000)
            await settle(page)
            initial_url = page.url

            print("\nCreating test plan...")
            first_observation = await safe_observe(page)
            plan = await asyncio.to_thread(
                create_test_plan, masked_case, website_url, first_observation
            )
            if not plan["checks"]:
                print("No pre-computable checks; the final verdict will rely on page evidence.")

            completed = False

            for step in range(1, max_steps + 1):
                page = latest_page(context, page)
                observation = await safe_observe(page)
                model_view = await safe_observation(page, observation, data)

                try:
                    action = await asyncio.to_thread(
                        get_next_action,
                        masked_case,
                        model_view,
                        history,
                        list(data.keys()),
                        plan,
                    )
                except Exception as error:
                    consecutive_errors += 1
                    history.append({"step": step, "error": f"planner: {str(error)[:200]}"})
                    print(f"\nStep {step}: planner problem: {str(error)[:200]}")
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        raise
                    continue

                kind = action["action"]
                print(f"\nStep {step}: {kind}")
                safe_action = dict(action)
                if kind in {"fill", "select"}:
                    safe_action["value"] = "[REDACTED]"

                # ---- done ------------------------------------------------
                if kind == "done":
                    if filled_any and not submit_clicked:
                        missing = await check_required_fields(
                            page, observation, data, auto_log
                        )
                        if missing:
                            print("Required fields still missing:", ", ".join(missing))
                            history.append(
                                {
                                    "step": step,
                                    "action": safe_action,
                                    "error": "Required fields still incomplete: "
                                    + ", ".join(missing),
                                }
                            )
                            continue
                    completed = True
                    break

                # ---- submit guard ---------------------------------------
                target_element = find_element(observation, action.get("target"))
                if kind == "click" and is_submit(target_element):
                    if not submit_allowed:
                        submit_blocks += 1
                        history.append(
                            {
                                "step": step,
                                "action": safe_action,
                                "error": "Blocked: the test case does not ask to submit. "
                                "If all requested actions are complete, return done.",
                            }
                        )
                        print("Blocked a submit click the test case did not ask for.")
                        if submit_blocks >= MAX_SUBMIT_BLOCKS:
                            completed = True
                            break
                        continue

                    missing = await check_required_fields(
                        page, observation, data, auto_log
                    )
                    if missing:
                        print("Submission paused. Missing:", ", ".join(missing))
                        history.append(
                            {
                                "step": step,
                                "action": safe_action,
                                "error": "Required fields incomplete: " + ", ".join(missing),
                            }
                        )
                        continue

                    fresh = await safe_observe(page)
                    arithmetic = await verify_arithmetic(page, fresh)
                    report["arithmetic_verification"] = arithmetic
                    if any(r["status"] == "FAIL" for r in arithmetic):
                        raise RuntimeError(
                            "The security-question answer does not match the "
                            "displayed arithmetic; the form was not submitted."
                        )

                    results = await verify_supplied_values(
                        page, fresh, data, required_keys
                    )
                    report["data_verification"] = results
                    if any(r["status"] == "FAIL" for r in results):
                        raise RuntimeError(
                            "Pre-submission check found a field whose value does "
                            "not match the supplied data; the form was not submitted."
                        )

                # ---- execute --------------------------------------------
                url_before = page.url
                try:
                    result = await execute_action(page, action, data, observation)
                except MissingDataError:
                    raise
                except Exception as error:
                    consecutive_errors += 1
                    message = f"{type(error).__name__}: {str(error)[:250]}"
                    print("Action failed:", message)
                    history.append({"step": step, "action": safe_action, "error": message})
                    report["steps"].append(
                        {"step": step, "action": safe_action, "error": message}
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        raise RuntimeError(
                            f"{MAX_CONSECUTIVE_ERRORS} consecutive failed actions. "
                            f"Last error: {message}"
                        )
                    await settle(page, 300)
                    continue

                consecutive_errors = 0
                if kind in {"fill", "select"}:
                    filled_any = True
                if kind == "click" and is_submit(target_element):
                    submit_clicked = True
                    report["submission"]["clicked"] = True

                await settle(page, 2000 if (kind == "click" and is_submit(target_element)) else 700)
                page = latest_page(context, page)

                history.append(
                    {
                        "step": step,
                        "action": safe_action,
                        "result": result,
                        "page_changed": page.url != url_before,
                    }
                )
                report["steps"].append(
                    {"step": step, "action": safe_action, "result": result}
                )

                signature = (kind, action.get("target"), str(action.get("value")))
                signatures.append(signature)
                if (
                    len(signatures) >= MAX_REPEATS
                    and len(set(signatures[-MAX_REPEATS:])) == 1
                    and kind not in {"wait", "scroll"}
                ):
                    raise RuntimeError(
                        f"Stuck: repeated the same action {MAX_REPEATS} times."
                    )

            if not completed:
                raise RuntimeError("Maximum steps reached before the test completed.")

            # ---- final state --------------------------------------------
            await settle(page, 1000)
            page = latest_page(context, page)
            final_observation = await safe_observe(page)

            report["auto_actions"] = auto_log

            if not report["data_verification"]:
                report["data_verification"] = await verify_supplied_values(
                    page, final_observation, data, required_keys
                )
            if not report["arithmetic_verification"]:
                report["arithmetic_verification"] = await verify_arithmetic(
                    page, final_observation
                )

            report["assertions"] = await verify_test_plan(page, plan)

            try:
                page_text = await page.locator("body").inner_text()
            except Exception:
                page_text = (final_observation or {}).get("pageText", "")
            title = await page.title()

            final_state = {
                "url": page.url,
                "title": title,
                "pageText": redact_secrets(page_text, data)[:6000],
                "signals": page_signals(page_text),
            }

            verdict = await asyncio.to_thread(
                judge_outcome,
                masked_case,
                history,
                final_state,
                [
                    {k: r[k] for k in ("field", "status")}
                    for r in report["data_verification"]
                ],
                report["assertions"],
                submit_clicked,
            )
            report["verdict"] = verdict

            evidence_found = bool(
                verdict.get("evidence")
                and evidence_on_page(verdict["evidence"], page_text, page.url, title)
            )
            report["submission_verification"] = {
                "required": bool(submit_allowed),
                "clicked": bool(submit_clicked),
                "verified": evidence_found if submit_clicked else None,
                "evidence": verdict.get("evidence", "") if evidence_found else "",
                "message": (
                    "Submission outcome confirmed by evidence on the resulting page."
                    if submit_clicked and evidence_found
                    else (
                        "Submission was requested but no independent confirmation was found."
                        if submit_allowed and not submit_clicked
                        else (
                            "Submit was clicked, but no independent confirmation was found."
                            if submit_clicked
                            else "Submission was not requested; the test is evaluated against its non-submission goal."
                        )
                    )
                ),
            }

            reasons = []
            data_failed = [
                r["field"] for r in report["data_verification"]
                if r["status"] == "FAIL"
            ]
            data_unverified = [
                r["field"] for r in report["data_verification"]
                if r["status"] in {"UNVERIFIED", "NOT_ON_PAGE"}
            ]
            arithmetic_failed = any(
                r["status"] == "FAIL" for r in report["arithmetic_verification"]
            )
            arithmetic_unverified = any(
                r["status"] == "UNVERIFIED"
                for r in report["arithmetic_verification"]
            )
            failed_checks = [
                a["description"] or a["type"]
                for a in report["assertions"]
                if not a["passed"]
            ]
            fill_only = is_fill_only_task(test_case) and not submit_clicked
            all_supplied_values_verified = bool(required_keys) and all(
                r["status"] == "PASS"
                for r in report["data_verification"]
                if normalize(r["field"]) in required_keys
            ) and all(
                any(normalize(r["field"]) == key and r["status"] == "PASS"
                    for r in report["data_verification"])
                for key in required_keys
            )

            # Explicit, independently verified failures always take precedence.
            if data_failed:
                report["status"] = "FAIL"
                reasons.append("Field values did not match: " + ", ".join(data_failed))
            if arithmetic_failed:
                report["status"] = "FAIL"
                reasons.append("Security-question answer was wrong.")
            if failed_checks:
                report["status"] = "FAIL"
                reasons.append("Failed checks: " + "; ".join(failed_checks))

            if report["status"] != "FAIL":
                if verdict["verdict"] == "FAIL":
                    report["status"] = "FAIL"
                    reasons.append("Judge: " + verdict["reason"])
                elif data_unverified:
                    report["status"] = "INCONCLUSIVE"
                    reasons.append(
                        "Could not independently verify these supplied fields: "
                        + ", ".join(data_unverified)
                    )
                elif arithmetic_unverified:
                    report["status"] = "INCONCLUSIVE"
                    reasons.append(
                        "The security-question answer could not be independently verified."
                    )
                elif submit_allowed and not submit_clicked:
                    report["status"] = "INCONCLUSIVE"
                    reasons.append(
                        "The test requested submission, but no submit action was completed."
                    )
                elif submit_clicked and not evidence_found:
                    report["status"] = "INCONCLUSIVE"
                    reasons.append(
                        "Submit was clicked, but the submission outcome could not be independently verified."
                    )
                elif fill_only and all_supplied_values_verified:
                    # For a fill-only task, read-back verification of every value
                    # is direct evidence of the requested outcome. A page title is
                    # not required to prove that the fields were populated.
                    report["status"] = "PASS"
                    report["completion_basis"] = (
                        "All test-case-supplied form values were read back and matched; "
                        "submission was not requested."
                    )
                    if verdict["verdict"] == "INCONCLUSIVE":
                        reasons.append(
                            "The judge could not find separate page-text evidence, "
                            "but independent field verification confirms this fill-only task."
                        )
                elif verdict["verdict"] == "INCONCLUSIVE":
                    report["status"] = "INCONCLUSIVE"
                    reasons.append("Judge: " + verdict["reason"])
                elif verdict["verdict"] == "PASS" and evidence_found:
                    report["status"] = "PASS"
                else:
                    report["status"] = "INCONCLUSIVE"
                    reasons.append(
                        "The judge did not provide verifiable evidence from the resulting page."
                    )

            report["reason"] = " ".join(reasons) if reasons else verdict["reason"]

            report["initial_url"] = initial_url
            report["final_url"] = page.url
            report["page_title"] = title

            if report["status"] != "PASS":
                try:
                    await page.screenshot(
                        path=failure_screenshot_path(report_path), full_page=True
                    )
                except Exception:
                    pass

        except MissingDataError as error:
            report["error"] = f"MissingDataError: {error}"
            report["reason"] = str(error)
            print("\nTest failed:", report["reason"])
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
            report["reason"] = report["error"]
            print("\nTest failed:", report["error"])
            try:
                await page.screenshot(
                    path=failure_screenshot_path(report_path), full_page=True
                )
            except Exception:
                pass
        finally:
            report["auto_actions"] = auto_log
            report["duration_seconds"] = round(time.time() - started, 1)
            save_report(report, report_path)
            await browser.close()

    print("\nTEST RESULT:", report["status"])
    if report["reason"]:
        print("Reason:", report["reason"])
    return report


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a plain-English test case in a real browser."
    )
    parser.add_argument("url", nargs="?", help="Website URL to test")
    parser.add_argument("-t", "--test-case", help="Test case text")
    parser.add_argument("-f", "--test-case-file", help="Read the test case from a file")
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Never prompt; fail with a clear reason if data is missing",
    )
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--report", default="reports/latest_report.json")
    return parser.parse_args()


def main():
    global NON_INTERACTIVE
    args = parse_args()
    NON_INTERACTIVE = args.non_interactive or not sys.stdin.isatty()

    url = (args.url or "").strip()
    if not url and not NON_INTERACTIVE:
        url = input("Enter website URL: ").strip()

    test_case = (args.test_case or "").strip()
    if args.test_case_file:
        with open(args.test_case_file, "r", encoding="utf-8") as file:
            test_case = file.read().strip()
    if not test_case and not NON_INTERACTIVE:
        test_case = read_multiline_test_case()

    if not url.startswith(("http://", "https://")) or not test_case:
        print("A valid URL (http:// or https://) and a test case are required.")
        sys.exit(2)

    report = asyncio.run(
        run_test(url, test_case, args.headless, args.max_steps, args.report)
    )
    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()