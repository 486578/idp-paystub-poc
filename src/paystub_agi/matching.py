"""Whole-word, case-insensitive keyword matching shared by the rules and AGI."""

import re
from collections.abc import Iterable

# Letters and digits form separate words, so "401(k)", "401K" and "ROTH401K" all
# contain the words "401" and "k".
_WORD = re.compile(r"[a-z]+|[0-9]+")


def tokens(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(text.lower()))


def _contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    width = len(needle)
    return width > 0 and any(
        haystack[i : i + width] == needle for i in range(len(haystack) - width + 1)
    )


def contains_any(text: str | None, keywords: Iterable[str]) -> str | None:
    """Return the first keyword whose words appear adjacently in `text`, else None."""
    if text is None:
        return None
    words = tokens(text)
    for keyword in keywords:
        if _contains(words, tokens(keyword)):
            return keyword
    return None
