import pytest

from paystub_agi.matching import contains_any, tokens


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pre-Tax Medical", ("pre", "tax", "medical")),
        ("PreTax", ("pretax",)),
        ("401(k)", ("401", "k")),
        ("401K", ("401", "k")),
        ("ROTH401K", ("roth", "401", "k")),
        ("DENTAL EE/SPOUSE", ("dental", "ee", "spouse")),
        ("  ", ()),
        ("", ()),
    ],
)
def test_matching_tokens_split_words_and_numbers(
    text: str, expected: tuple[str, ...]
) -> None:
    assert tokens(text) == expected


def test_matching_phrase_matches_across_punctuation() -> None:
    assert contains_any("PRE-TAX DEDUCTIONS", ["pre tax"]) == "pre tax"


def test_matching_is_case_insensitive() -> None:
    assert contains_any("medical", ["MEDICAL"]) == "MEDICAL"


def test_matching_requires_whole_words() -> None:
    assert contains_any("Premium Plan", ["pre"]) is None


def test_matching_phrase_words_must_be_adjacent() -> None:
    assert contains_any("Pre Medical Tax", ["pre tax"]) is None


def test_matching_returns_first_keyword_that_matches() -> None:
    assert contains_any("Roth 401k", ["401k", "roth"]) == "401k"


def test_matching_none_text_never_matches() -> None:
    assert contains_any(None, ["pre"]) is None


def test_matching_no_keywords_never_matches() -> None:
    assert contains_any("Pre-Tax", []) is None


def test_matching_keyword_longer_than_text_does_not_match() -> None:
    assert contains_any("tax", ["pre tax"]) is None


@pytest.mark.parametrize("empty", ["", "-/*"])
def test_matching_keyword_without_words_never_matches(empty: str) -> None:
    assert contains_any("Medical", [empty]) is None
