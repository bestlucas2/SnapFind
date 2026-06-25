"""Auto-tag generation from OCR text.

Goes beyond raw word frequency: it pulls out the *key terms and phrases* by
combining single words with two-word phrases (bigrams), boosting capitalised
terms (titles / proper nouns usually carry the main idea), and de-duplicating
single words that are already covered by a chosen phrase.
"""
from __future__ import annotations

import re
from collections import Counter

STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can",
    "had", "her", "was", "one", "our", "out", "has", "him", "his", "how",
    "man", "new", "now", "old", "see", "two", "way", "who", "boy", "did",
    "its", "let", "put", "say", "she", "too", "use", "that", "this", "with",
    "have", "from", "they", "will", "your", "what", "when", "make", "like",
    "time", "just", "know", "take", "into", "year", "good", "some", "them",
    "than", "then", "look", "only", "come", "over", "also", "back", "after",
    "work", "first", "well", "even", "want", "because", "these", "give",
    "most", "http", "https", "www", "com", "org", "net", "would", "could",
    "should", "about", "there", "their", "which", "been", "were", "here",
    "more", "very", "such", "each", "many", "must", "into", "onto", "upon",
    "while", "where", "still", "being", "those", "every", "again", "around",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+#-]{2,}")
_PHRASE_STOP_TAIL = STOPWORDS | {"a", "an", "of", "to", "in", "on", "at", "by", "is"}


def _acceptable(word: str) -> bool:
    return (
        len(word) >= 4
        and word not in STOPWORDS
        and not word.isdigit()
        and not word.replace("-", "").isdigit()
    )


def generate_tags(text: str, limit: int = 6) -> list[str]:
    """Return up to `limit` lowercase key terms / phrases from OCR text."""
    if not text or not text.strip():
        return []

    all_words: list[str] = []
    cap_terms: set[str] = set()
    bigrams: Counter[str] = Counter()

    # Process line by line so phrases never bridge unrelated lines.
    for line in text.splitlines():
        raw = _WORD_RE.findall(line)
        if not raw:
            continue
        lower = [w.lower() for w in raw]
        all_words.extend(lower)
        for w in raw:
            if w[:1].isupper() and len(w) >= 4:
                cap_terms.add(w.lower())
        for a, b in zip(lower, lower[1:]):
            if (
                a not in _PHRASE_STOP_TAIL
                and b not in _PHRASE_STOP_TAIL
                and len(a) >= 3
                and len(b) >= 4
            ):
                bigrams[f"{a} {b}"] += 1

    if not all_words:
        return []

    # Single-word frequencies.
    unigrams = Counter(w for w in all_words if _acceptable(w))

    scored: dict[str, float] = {}
    for term, count in unigrams.items():
        score = count * (1.0 + len(term) / 12.0)
        if term in cap_terms:
            score *= 1.6
        scored[term] = score

    for phrase, count in bigrams.items():
        parts = phrase.split()
        is_title = all(p in cap_terms for p in parts)
        # Keep a phrase if it recurs or reads like a title (e.g. "Binary Search").
        if count >= 2 or is_title:
            score = count * 2.4 + (1.5 if is_title else 0)
            scored[phrase] = score

    ranked = sorted(scored.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)

    chosen: list[str] = []
    covered: set[str] = set()
    for term, _ in ranked:
        parts = term.split()
        if len(parts) == 1 and parts[0] in covered:
            continue  # already represented by a chosen phrase
        chosen.append(term)
        covered.update(parts)
        if len(chosen) >= limit:
            break
    return chosen


def normalize_tag(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())[:80]
