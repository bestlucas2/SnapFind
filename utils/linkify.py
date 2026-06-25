"""Render-time entity detection for OCR text.

Detects URLs, emails, phone numbers, and order/confirmation numbers and turns
them into links (URLs/emails) or quick-copy chips (phone/order). The stored OCR
text is never modified. Plain text is HTML-escaped first; matched values are
escaped before being placed into attributes/markup, so OCR content can never
inject HTML.
"""
from __future__ import annotations

import html
import re

from markupsafe import Markup

_PATTERN = re.compile(
    r'(?P<url>https?://[^\s<>"]+)'
    r"|(?P<email>[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
    r"|(?P<order>(?:order|conf(?:irmation)?|invoice|booking)\s*#?:?\s*[A-Z0-9]{4,}"
    r"|#[A-Za-z0-9]{4,})"
    r"|(?P<phone>\+?\d[\d\-\s().]{7,}\d)",
    re.IGNORECASE,
)

_LINK_CLS = (
    "text-brand-600 dark:text-brand-400 underline decoration-dotted "
    "hover:decoration-solid break-all"
)
_CHIP_CLS = (
    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-neutral-200 "
    "dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 "
    "hover:bg-brand-100 dark:hover:bg-brand-900/50 text-xs align-middle cursor-pointer"
)


def _is_phone(value: str) -> bool:
    digits = sum(c.isdigit() for c in value)
    return 10 <= digits <= 15


def linkify_ocr(text: str | None) -> Markup:
    if not text:
        return Markup("")

    out: list[str] = []
    last = 0
    for m in _PATTERN.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        value = m.group(0)
        kind = m.lastgroup
        shown = html.escape(value)
        attr = html.escape(value, quote=True)

        if kind == "url":
            out.append(
                f'<a href="{attr}" target="_blank" rel="noopener noreferrer" '
                f'class="{_LINK_CLS}">{shown}</a>'
            )
        elif kind == "email":
            out.append(f'<a href="mailto:{attr}" class="{_LINK_CLS}">{shown}</a>')
        elif kind == "phone" and not _is_phone(value):
            out.append(shown)  # too few/many digits — treat as plain text
        else:  # phone or order -> quick-copy chip
            out.append(
                f'<button type="button" onclick="copyValue(this)" data-copy="{attr}" '
                f'title="Copy" class="{_CHIP_CLS}">{shown}</button>'
            )
        last = m.end()

    out.append(html.escape(text[last:]))
    return Markup("".join(out))
