"""Replay test (architecture step 7a).

Feeds each answer key's own amounts and labels into `compute_agi` and requires the
key's `calculated` block to be reproduced exactly. Skipped when the keys haven't
been downloaded into `data/answer_keys/` (they stay out of git).
"""

from decimal import Decimal
from pathlib import Path

import pytest

from evaluation.answer_keys import load_answer_key, reference_decisions, to_evidence
from paystub_agi.agi import compute_agi
from paystub_agi.config import AgiConfig

KEYS_DIR = Path(__file__).parents[2] / "data" / "answer_keys"
KEY_FILES = sorted(KEYS_DIR.glob("*/*.json")) if KEYS_DIR.is_dir() else []

pytestmark = pytest.mark.skipif(
    not KEY_FILES, reason=f"answer keys not downloaded into {KEYS_DIR}"
)


@pytest.mark.parametrize(
    "path", KEY_FILES, ids=[f"{p.parent.name}/{p.stem}" for p in KEY_FILES]
)
def test_replay_reproduces_answer_key_agi(path: Path) -> None:
    key = load_answer_key(path)
    expected = key.calculated

    result = compute_agi(to_evidence(key), reference_decisions(key), AgiConfig())

    assert result.agi == expected.agi
    assert result.pay_frequency == expected.pay_frequency
    assert result.periods_per_year == expected.periods_per_year
    assert (result.frequency_source or None) == expected.frequency_source
    assert (result.method or None) == expected.method
    assert result.one_time_total == expected.one_time_total
    assert list(result.warnings) == expected.warnings
    if expected.agi is not None:
        assert result.pretax_total == (expected.pretax_deductions or Decimal("0"))


def test_replay_found_all_82_keys() -> None:
    assert len(KEY_FILES) == 82
