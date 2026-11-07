"""
Playwright browser actions for the AI browser testing agent.

The public function names and signatures are kept compatible with agent.py:
    get_element
    fill_element
    click_element
    select_element
    check_element
    uncheck_element
    scroll_element
    hover_element
    wait_page
    navigate_page

Element references are temporary. If a reference is missing or ambiguous,
the caller should refresh the page observation and request a new action.
"""

import re
from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

ACTION_TIMEOUT = 10000
NAVIGATION_TIMEOUT = 30000


def normalize_text(value):
    """Normalize text for case-insensitive option matching."""
    return " ".join(str(value or "").split()).casefold()


async def get_element(page: Page, ref: str, require_enabled: bool = True):
    """
    Locate exactly one visible element by its temporary observer reference.

    If duplicate references exist but only one matching element is visible,
    use that visible element. If multiple matches are visible, fail safely
    rather than clicking or filling an arbitrary element.
    """
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("A valid element reference is required.")

    ref = ref.strip()

    if not re.fullmatch(r"element_\d+", ref):
        raise ValueError(f"Invalid element reference: {ref}")

    locator = page.locator(f'[data-agent-ref="{ref}"]')
    count = await locator.count()

    if count == 0:
        raise ValueError(
            f"Element {ref} was not found. "
            "The page may have changed. Observe the page again."
        )

    visible_matches = []
    for index in range(count):
        candidate = locator.nth(index)
        try:
            if await candidate.is_visible():
                visible_matches.append(candidate)
        except Exception:
            # The DOM may have changed while resolving the reference.
            continue

    if not visible_matches:
        raise ValueError(
            f"Element {ref} exists but is not visible. "
            "Refresh the page observation."
        )

    if len(visible_matches) > 1:
        raise ValueError(
            f"Element {ref} is ambiguous: found {count} matching "
            f"elements and {len(visible_matches)} are visible. "
            "Refresh the page observation; do not choose arbitrarily."
        )

    resolved = visible_matches[0]

    if require_enabled:
        try:
            if not await resolved.is_enabled():
                raise ValueError(f"Element {ref} is disabled.")
        except ValueError:
            raise
        except Exception as error:
            raise RuntimeError(
                f"Could not check whether element {ref} is enabled: {error}"
            ) from error

    return resolved


async def fill_element(page: Page, ref: str, value: str):
    """Fill a native text input, textarea, or supported custom textbox."""
    locator = await get_element(page, ref)

    if value is None:
        raise ValueError(f"Cannot fill element {ref} with an empty value.")

    value = str(value)

    tag = (
        await locator.evaluate("(el) => el.tagName.toLowerCase()")
    )
    element_type = (
        await locator.get_attribute("type") or ""
    ).lower()
    role = (
        await locator.get_attribute("role") or ""
    ).lower()
    is_contenteditable = await locator.evaluate(
        "(el) => el.isContentEditable"
    )
    readonly = await locator.get_attribute("readonly")

    supported_custom_roles = {"textbox", "searchbox"}
    unsupported_types = {
        "button", "submit", "reset", "checkbox",
        "radio", "file", "image", "hidden",
    }

    if tag == "textarea":
        pass
    elif tag == "input":
        if element_type in unsupported_types:
            raise ValueError(
                f"Cannot fill an input of type '{element_type}'."
            )
        if readonly is not None:
            raise ValueError(f"Input {ref} is read-only.")
    elif is_contenteditable:
        pass
    elif role in supported_custom_roles:
        pass
    else:
        raise ValueError(
            f"Element {ref} is not a supported text field."
        )

    try:
        await locator.fill(value, timeout=ACTION_TIMEOUT)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            f"Timed out while filling element {ref}."
        ) from error
    except Exception as error:
        raise RuntimeError(
            f"Could not fill element {ref}: {error}"
        ) from error

    print(f"Filled element: {ref}")


async def click_element(page: Page, ref: str):
    """Click one visible and enabled element."""
    locator = await get_element(page, ref)

    try:
        await locator.click(timeout=ACTION_TIMEOUT)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            f"Timed out while clicking element {ref}. "
            "The element may be covered or not interactable."
        ) from error
    except Exception as error:
        raise RuntimeError(
            f"Could not click element {ref}: {error}"
        ) from error

    print(f"Clicked element: {ref}")


async def select_element(page: Page, ref: str, value: str):
    """
    Select an option from a native HTML select or a custom dropdown.

    Matching is exact first. Partial matching is accepted only when it
    produces exactly one option.
    """
    locator = await get_element(page, ref)
    requested = normalize_text(value)

    if not requested:
        raise ValueError("A dropdown option value is required.")

    tag = await locator.evaluate(
        "(el) => el.tagName.toLowerCase()"
    )

    # Native HTML select.
    if tag == "select":
        options = await locator.locator("option").evaluate_all(
            """
            elements => elements.map(option => ({
                text: option.textContent.trim(),
                value: option.value,
                disabled: option.disabled
            }))
            """
        )

        exact_matches = [
            option for option in options
            if not option["disabled"] and (
                normalize_text(option["text"]) == requested
                or normalize_text(option["value"]) == requested
            )
        ]

        matches = exact_matches
        if not matches:
            matches = [
                option for option in options
                if not option["disabled"] and (
                    requested in normalize_text(option["text"])
                    or requested in normalize_text(option["value"])
                )
            ]

        # De-duplicate options that matched both text and value.
        unique_matches = {
            (option["text"], option["value"]): option
            for option in matches
        }
        matches = list(unique_matches.values())

        if len(matches) != 1:
            available = [
                option["text"] for option in options
                if not option["disabled"]
            ]
            raise RuntimeError(
                f"Could not uniquely match '{value}' in {ref}. "
                f"Available options: {available}"
            )

        selected = matches[0]
        try:
            await locator.select_option(
                value=selected["value"],
                timeout=ACTION_TIMEOUT,
            )
        except Exception as error:
            raise RuntimeError(
                f"Could not select '{value}' in native dropdown "
                f"{ref}: {error}"
            ) from error

        print(f"Selected '{value}' in native dropdown {ref}")
        return

    # Custom dropdown.
    try:
        await locator.click(timeout=ACTION_TIMEOUT)
        await page.wait_for_timeout(300)

        escaped = re.escape(str(value).strip())
        exact_pattern = re.compile(
            rf"^\s*{escaped}\s*$",
            re.IGNORECASE,
        )

        # Prefer semantic ARIA options.
        for role_name in ("option", "menuitem"):
            candidates = page.get_by_role(
                role_name,
                name=exact_pattern,
            )
            visible = []
            for index in range(await candidates.count()):
                candidate = candidates.nth(index)
                if await candidate.is_visible():
                    visible.append(candidate)

            if len(visible) == 1:
                await visible[0].click(timeout=ACTION_TIMEOUT)
                print(f"Selected '{value}' in custom dropdown {ref}")
                return
            if len(visible) > 1:
                raise RuntimeError(
                    f"Multiple visible {role_name} elements match "
                    f"'{value}'. Cannot safely choose one."
                )

        # Search within visible listboxes.
        listboxes = page.locator('[role="listbox"]:visible')
        for index in range(await listboxes.count()):
            listbox = listboxes.nth(index)
            candidates = listbox.get_by_text(
                exact_pattern,
                exact=True,
            )
            visible = []
            for candidate_index in range(await candidates.count()):
                candidate = candidates.nth(candidate_index)
                if await candidate.is_visible():
                    visible.append(candidate)

            if len(visible) == 1:
                await visible[0].click(timeout=ACTION_TIMEOUT)
                print(f"Selected '{value}' in custom dropdown {ref}")
                return
            if len(visible) > 1:
                raise RuntimeError(
                    f"Multiple visible options match '{value}' "
                    "inside the dropdown."
                )

        # Last resort: one exact visible text match on the page.
        candidates = page.get_by_text(exact_pattern, exact=True)
        visible = []
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if await candidate.is_visible():
                visible.append(candidate)

        if len(visible) == 1:
            await visible[0].click(timeout=ACTION_TIMEOUT)
            print(f"Selected '{value}' in custom dropdown {ref}")
            return

        if len(visible) > 1:
            raise RuntimeError(
                f"Multiple visible elements match '{value}'. "
                "Cannot safely identify the dropdown option."
            )

        visible_options = await page.locator(
            '[role="option"]:visible'
        ).all_text_contents()

        raise RuntimeError(
            f"Could not find option '{value}' after opening "
            f"custom dropdown {ref}. "
            f"Visible options: {visible_options[:30]}"
        )

    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            f"Timed out while opening or selecting '{value}' "
            f"in dropdown {ref}."
        ) from error
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            f"Could not select '{value}' in custom dropdown "
            f"{ref}: {error}"
        ) from error


async def check_element(page: Page, ref: str):
    """Check a native checkbox or radio button."""
    locator = await get_element(page, ref)
    element_type = (
        await locator.get_attribute("type") or ""
    ).lower()
    role = (
        await locator.get_attribute("role") or ""
    ).lower()

    if not (
        element_type in {"checkbox", "radio"}
        or role in {"checkbox", "radio"}
    ):
        raise ValueError(
            f"Element {ref} is not a checkbox or radio button."
        )

    try:
        if not await locator.is_checked():
            await locator.check(timeout=ACTION_TIMEOUT)
    except Exception as error:
        raise RuntimeError(
            f"Could not check element {ref}: {error}"
        ) from error

    print(f"Checked element: {ref}")


async def uncheck_element(page: Page, ref: str):
    """Uncheck a checkbox. Radio buttons cannot be unchecked independently."""
    locator = await get_element(page, ref)
    element_type = (
        await locator.get_attribute("type") or ""
    ).lower()
    role = (
        await locator.get_attribute("role") or ""
    ).lower()

    if element_type == "radio" or role == "radio":
        raise ValueError(
            "A radio button cannot be independently unchecked."
        )

    if not (element_type == "checkbox" or role == "checkbox"):
        raise ValueError(f"Element {ref} is not a checkbox.")

    try:
        if await locator.is_checked():
            await locator.uncheck(timeout=ACTION_TIMEOUT)
    except Exception as error:
        raise RuntimeError(
            f"Could not uncheck element {ref}: {error}"
        ) from error

    print(f"Unchecked element: {ref}")


async def scroll_element(page: Page, ref: str):
    """Scroll an element into the visible browser viewport."""
    locator = await get_element(page, ref)
    try:
        await locator.scroll_into_view_if_needed(
            timeout=ACTION_TIMEOUT
        )
    except Exception as error:
        raise RuntimeError(
            f"Could not scroll to element {ref}: {error}"
        ) from error

    print(f"Scrolled to element: {ref}")


async def hover_element(page: Page, ref: str):
    """Move the mouse over an element."""
    locator = await get_element(page, ref)
    try:
        await locator.hover(timeout=ACTION_TIMEOUT)
    except Exception as error:
        raise RuntimeError(
            f"Could not hover over element {ref}: {error}"
        ) from error

    print(f"Hovered over element: {ref}")


async def wait_page(page: Page, milliseconds: int = 1500):
    """Wait for a bounded period."""
    milliseconds = max(0, min(int(milliseconds), 10000))
    await page.wait_for_timeout(milliseconds)
    print(f"Waited {milliseconds} milliseconds")


async def navigate_page(page: Page, url: str):
    """Navigate to an HTTP or HTTPS URL."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("A valid navigation URL is required.")

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            "Navigation URL must start with http:// or https://."
        )

    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT,
        )
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            f"Navigation timed out: {url}"
        ) from error
    except Exception as error:
        raise RuntimeError(
            f"Could not navigate to {url}: {error}"
        ) from error

    print(f"Navigated to: {url}")
