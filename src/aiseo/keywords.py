"""Free keyword research from Google autocomplete. No API key, no account.

The workflow (expand a seed with question and alphabet variants) follows the
same idea as open-seo's keyword research, but uses only free suggestion data
instead of a paid provider. Original code; see NOTICE.
"""

from __future__ import annotations

import string

import requests

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
QUESTION_PREFIXES = ["how", "what", "why", "when", "where", "which", "is", "are", "can", "best", "vs", "for", "without"]
USER_AGENT = "Mozilla/5.0 (compatible; aiseo-toolkit/0.1)"


def _suggest(query: str) -> list[str]:
    try:
        resp = requests.get(
            SUGGEST_URL,
            params={"client": "firefox", "q": query, "hl": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        data = resp.json()
        return [s for s in (data[1] if len(data) > 1 else []) if isinstance(s, str)]
    except (requests.RequestException, ValueError, IndexError):
        return []


def expand_keywords(seed: str, alphabet: bool = True, questions: bool = True) -> list[dict]:
    """Return [{'keyword': str, 'source': str}] deduped, seed first."""
    seen: dict[str, dict] = {}

    def add(query: str, source: str):
        for s in _suggest(query):
            key = s.strip().lower()
            if key and key not in seen:
                seen[key] = {"keyword": s.strip(), "source": source}

    add(seed, "seed")
    if questions:
        for prefix in QUESTION_PREFIXES:
            add(f"{prefix} {seed}", "question")
    if alphabet:
        for letter in string.ascii_lowercase:
            add(f"{seed} {letter}", "alphabet")
    return list(seen.values())
