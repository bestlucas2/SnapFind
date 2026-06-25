"""Rule-based auto-categorisation from OCR text.

Buckets: School, Chats, Receipts, Code, Shopping, Photos, Miscellaneous.
Scoring is intentionally simple and transparent — each category accrues points
from signal words / patterns, highest score wins.
"""
from __future__ import annotations

import re

# Keyword signals per category.
_SIGNALS: dict[str, list[str]] = {
    "Receipts": [
        "total", "subtotal", "tax", "receipt", "invoice", "amount", "qty",
        "order #", "order no", "payment", "card ending", "change due",
        "cash", "balance due", "thank you for your",
    ],
    "Code": [
        "def ", "function", "const ", "import ", "return", "class ", "void ",
        "public ", "private ", "console.log", "print(", "traceback",
        "exception", "null", "undefined", "var ", "let ", "=>", "();",
    ],
    "Shopping": [
        "add to cart", "add to bag", "checkout", "buy now", "in stock",
        "out of stock", "free shipping", "shipping", "price", "sale",
        "wishlist", "product", "reviews", "delivery",
    ],
    "School": [
        "lecture", "assignment", "homework", "exam", "quiz", "chapter",
        "professor", "syllabus", "course", "semester", "due date",
        "grade", "study", "university", "textbook",
    ],
    "Chats": [
        "delivered", "read", "typing", "reply", "sent", "message",
        "online", "last seen", "you:", "lol", "haha", "ok!", "good morning",
    ],
}

# A timestamp like 12:45 PM is a strong chat signal.
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s?(am|pm)\b", re.IGNORECASE)
# Currency amounts strongly imply receipts/shopping.
_MONEY_RE = re.compile(r"[$€£]\s?\d+([.,]\d{2})?")
# Code-ish punctuation density.
_CODE_RE = re.compile(r"[{};]|\b(0x[0-9a-f]+)\b")


def categorize(text: str) -> str:
    if not text or len(text.strip()) < 12:
        # Very little extractable text — most likely a photo/diagram.
        return "Photos"

    low = text.lower()
    scores: dict[str, int] = {k: 0 for k in _SIGNALS}

    for category, words in _SIGNALS.items():
        for w in words:
            if w in low:
                scores[category] += 1

    # Pattern-based boosts.
    money_hits = len(_MONEY_RE.findall(text))
    if money_hits:
        scores["Receipts"] += money_hits
        scores["Shopping"] += 1
    if _TIME_RE.search(text):
        scores["Chats"] += 2
    if len(_CODE_RE.findall(text)) >= 3:
        scores["Code"] += 2

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "Miscellaneous"
    return best
