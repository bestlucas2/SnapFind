"""Parse the global search box into structured filters + free text.

Supported operators:  before:  after:  tag:  collection:  favorite:
Everything else is treated as free-text matched against OCR text, filename and
notes. Quotes group a phrase, e.g.  tag:"order #123"  amazon
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class ParsedQuery:
    text: str = ""
    tags: list[str] = field(default_factory=list)
    collection: str | None = None
    favorite: bool | None = None
    before: date | None = None
    after: date | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            [self.text, self.tags, self.collection, self.favorite is not None,
             self.before, self.after]
        )


_TRUTHY = {"true", "yes", "1", "on", "fav"}
_FALSY = {"false", "no", "0", "off"}


def _parse_date(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_query(raw: str) -> ParsedQuery:
    pq = ParsedQuery()
    if not raw or not raw.strip():
        return pq

    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()

    free_terms: list[str] = []
    for tok in tokens:
        low = tok.lower()
        if low.startswith("tag:"):
            val = tok[4:].strip().lower()
            if val:
                pq.tags.append(val)
        elif low.startswith("collection:") or low.startswith("col:"):
            val = tok.split(":", 1)[1].strip()
            if val:
                pq.collection = val
        elif low.startswith("favorite:") or low.startswith("fav:"):
            val = tok.split(":", 1)[1].strip().lower()
            if val in _TRUTHY:
                pq.favorite = True
            elif val in _FALSY:
                pq.favorite = False
        elif low.startswith("before:"):
            d = _parse_date(tok[7:].strip())
            if d:
                pq.before = d
        elif low.startswith("after:"):
            d = _parse_date(tok[6:].strip())
            if d:
                pq.after = d
        else:
            free_terms.append(tok)

    pq.text = " ".join(free_terms).strip()
    return pq
