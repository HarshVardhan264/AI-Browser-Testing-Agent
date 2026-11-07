"""
Browser page observer for the AI browser testing agent.

Returns a structured snapshot of visible interactive elements.
References are temporary and must be refreshed after page changes.
"""

from playwright.async_api import Page


async def observe_page(page: Page):
    """Inspect visible interactive controls and return structured metadata."""

    observation = await page.evaluate("""
    () => {
        const MAX_ELEMENTS = 180;
        const MAX_PAGE_TEXT = 6000;
        const MAX_ELEMENT_TEXT = 250;
        const MAX_CONTEXT_TEXT = 500;

        // References belong to one observation only. Remove old references
        // before assigning new ones so stale nodes cannot collide.
        document.querySelectorAll('[data-agent-ref]').forEach(el => {
            el.removeAttribute('data-agent-ref');
        });

        const selector = [
            'input:not([type="hidden"])',
            'button',
            'textarea',
            'select',
            'a',
            '[role="button"]',
            '[role="textbox"]',
            '[role="combobox"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[role="option"]',
            '[role="switch"]',
            '[role="menuitem"]',
            '[role="tab"]',
            '[role="listbox"]',
            '[role="searchbox"]',
            '[contenteditable="true"]',
            '[tabindex]:not([tabindex="-1"])'
        ].join(',');

        const candidates = Array.from(document.querySelectorAll(selector));
        const discovered = [];

        function isVisible(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            if (
                rect.width <= 0 || rect.height <= 0 ||
                style.display === 'none' ||
                style.visibility === 'hidden' ||
                Number(style.opacity) === 0
            ) return false;

            let parent = el.parentElement;
            while (parent && parent !== document.body) {
                const ps = window.getComputedStyle(parent);
                if (
                    ps.display === 'none' ||
                    ps.visibility === 'hidden' ||
                    Number(ps.opacity) === 0
                ) return false;
                parent = parent.parentElement;
            }
            return true;
        }

        function cleanText(value, limit = MAX_ELEMENT_TEXT) {
            return String(value || '').replace(/\\s+/g, ' ').trim().slice(0, limit);
        }

        function getLabels(el) {
            const labels = Array.from(el.labels || [])
                .map(label => cleanText(label.innerText))
                .filter(Boolean);

            const wrapping = el.closest('label');
            if (wrapping) {
                const labelText = cleanText(wrapping.innerText);
                if (labelText) labels.push(labelText);
            }
            return [...new Set(labels)].join(' ');
        }

        function getLabelledBy(el) {
            const ids = (el.getAttribute('aria-labelledby') || '')
                .split(/\\s+/).filter(Boolean);
            return ids.map(id => document.getElementById(id))
                .filter(Boolean)
                .map(node => cleanText(node.innerText))
                .filter(Boolean).join(' ');
        }

        function getFieldsetLegend(el) {
            const fieldset = el.closest('fieldset');
            const legend = fieldset && fieldset.querySelector('legend');
            return legend ? cleanText(legend.innerText) : '';
        }

        function getNearbyContext(el) {
            // Prefer semantic form/group context; then inspect a few ancestors.
            const pieces = [];
            const legend = getFieldsetLegend(el);
            if (legend) pieces.push(legend);

            const labelledBy = getLabelledBy(el);
            if (labelledBy) pieces.push(labelledBy);

            let node = el.parentElement;
            let depth = 0;
            while (node && node !== document.body && depth < 3) {
                const text = cleanText(node.innerText, MAX_CONTEXT_TEXT);
                if (text && !pieces.includes(text)) pieces.push(text);
                node = node.parentElement;
                depth++;
            }
            return cleanText(pieces.join(' | '), MAX_CONTEXT_TEXT);
        }

        function getRole(el) {
            const explicit = el.getAttribute('role');
            if (explicit) return explicit;

            const tag = el.tagName.toLowerCase();
            const type = (el.getAttribute('type') || '').toLowerCase();

            if (tag === 'button') return 'button';
            if (tag === 'a') return 'link';
            if (tag === 'select') return 'combobox';
            if (tag === 'textarea') return 'textbox';
            if (type === 'checkbox') return 'checkbox';
            if (type === 'radio') return 'radio';
            if (['submit', 'button', 'reset'].includes(type)) return 'button';
            if (el.isContentEditable) return 'textbox';
            if (tag === 'input') return 'textbox';
            return 'unknown';
        }

        function isRequired(el) {
            return Boolean(
                el.hasAttribute('required') ||
                el.getAttribute('aria-required') === 'true'
            );
        }

        function isDisabled(el) {
            return Boolean(
                el.disabled ||
                el.getAttribute('aria-disabled') === 'true' ||
                el.matches(':disabled')
            );
        }

        candidates.forEach(el => {
            if (discovered.length >= MAX_ELEMENTS || !isVisible(el)) return;

            const tag = el.tagName.toLowerCase();
            const type = (el.getAttribute('type') || '').toLowerCase();
            const rect = el.getBoundingClientRect();
            const labels = getLabels(el);
            const labelledBy = getLabelledBy(el);
            const role = getRole(el);
            const sensitive = ['password', 'hidden'].includes(type);

            const value = sensitive
                ? ''
                : (typeof el.value === 'string' ? el.value : '');

            let options = [];
            if (tag === 'select') {
                options = Array.from(el.options).slice(0, 60).map(option => ({
                    text: cleanText(option.text, 150),
                    value: option.value,
                    selected: option.selected,
                    disabled: option.disabled
                }));
            }

            const form = el.form || el.closest('form');
            const formInfo = form ? {
                id: form.id || '',
                name: form.getAttribute('name') || '',
                action: form.getAttribute('action') || '',
                method: (form.getAttribute('method') || 'get').toLowerCase()
            } : null;

            const fieldsetLegend = getFieldsetLegend(el);
            const parentText = getNearbyContext(el);
            const text = sensitive ? '' : cleanText(
                el.innerText || el.getAttribute('alt') || value
            );

            const ref = `element_${discovered.length}`;
            el.setAttribute('data-agent-ref', ref);

            discovered.push({
                ref,
                tag,
                type,
                role,
                label: labels,
                accessibleName: cleanText(
                    el.getAttribute('aria-label') ||
                    labelledBy ||
                    labels ||
                    el.getAttribute('placeholder') ||
                    el.getAttribute('title') ||
                    el.getAttribute('alt') ||
                    el.innerText
                ),
                ariaLabel: el.getAttribute('aria-label') || '',
                labelledBy,
                placeholder: el.getAttribute('placeholder') || '',
                name: el.getAttribute('name') || '',
                id: el.id || '',
                title: el.getAttribute('title') || '',
                alt: el.getAttribute('alt') || '',
                autocomplete: el.getAttribute('autocomplete') || '',
                text,
                value,
                parentText,
                groupLabel: fieldsetLegend,
                options,
                required: isRequired(el),
                disabled: isDisabled(el),
                readonly: Boolean(el.readOnly),
                checked: Boolean(el.checked),
                selected: Boolean(el.selected),
                multiple: Boolean(el.multiple),
                contentEditable: Boolean(el.isContentEditable),
                inputMode: el.getAttribute('inputmode') || '',
                min: el.getAttribute('min') || '',
                max: el.getAttribute('max') || '',
                pattern: el.getAttribute('pattern') || '',
                form: formInfo,
                href: el.href || '',
                formAction: el.formAction || '',
                inViewport: (
                    rect.bottom > 0 && rect.right > 0 &&
                    rect.top < window.innerHeight &&
                    rect.left < window.innerWidth
                ),
                bounds: {
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height)
                }
            });
        });

        return {
            url: window.location.href,
            title: document.title,
            pageText: cleanText(document.body.innerText, MAX_PAGE_TEXT),
            totalElements: discovered.length,
            elements: discovered
        };
    }
    """)

    return observation
