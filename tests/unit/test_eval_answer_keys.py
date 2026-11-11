from decimal import Decimal
from typing import Any

import pytest

from evaluation.answer_keys import AnswerKey, reference_decisions, to_evidence
from paystub_agi.models import Decision


def _key(**overrides: Any) -> AnswerKey:
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "stub_id": "stub_x",
        "category": "mid",
        "amounts": {"gross": 1000.0, "net": 800.0, "bonus": None, "overtime": 50.0},
        "deductions": [{"type": "401k", "amount": 70.4, "employee_pretax": True}],
        "period": {
            "start_date": "2026-07-01",
            "end_date": "2026-07-14",
            "pay_date": None,
        },
        "calculated": {
            "agi": None,
            "annual_gross": None,
            "pay_frequency": None,
            "periods_per_year": None,
            "frequency_source": None,
            "method": None,
            "one_time_total": 0.0,
            "pretax_deductions": None,
            "warnings": [],
        },
    }
    values.update(overrides)
    return AnswerKey.model_validate(values)


@pytest.mark.parametrize(
    ("kind", "flag", "expected"),
    [
        ("401k", True, Decision.PRETAX),
        ("401k", False, Decision.NOT_PRETAX),
        ("roth_401k", True, Decision.NOT_PRETAX),
        ("pension", True, Decision.NOT_PRETAX),
        ("Life Insurance", True, Decision.NOT_PRETAX),
        ("post-tax medical", True, Decision.NOT_PRETAX),
        ("pretax roth", False, Decision.PRETAX),
        ("medicare", True, Decision.NOT_PRETAX),
    ],
)
def test_answer_keys_reference_pretax_check(
    kind: str, flag: bool, expected: Decision
) -> None:
    key = _key(deductions=[{"type": kind, "amount": 10, "employee_pretax": flag}])

    assert reference_decisions(key)[0].decision is expected


def test_answer_keys_bonus_and_overtime_become_earnings() -> None:
    evidence = to_evidence(_key())

    assert [(e.label, e.amount) for e in evidence.earnings] == [
        ("overtime", Decimal("50.0"))
    ]


def test_answer_keys_evidence_keeps_gross_dates_and_deductions() -> None:
    evidence = to_evidence(_key())

    assert evidence.gross == Decimal("1000.0")
    assert evidence.period_start is not None
    assert evidence.pay_frequency is None
    assert evidence.deductions[0].label == "401k"
