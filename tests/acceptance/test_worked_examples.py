"""Architecture section 6 worked examples, end to end through classify + compute_agi.

The evidence is hand-built from the stubs (numbers only, no personal data).
"""

from decimal import Decimal
from typing import Any

from paystub_agi.agi import compute_agi
from paystub_agi.config import AnalyzerConfig
from paystub_agi.models import Decision, PaystubEvidence, RuleId
from paystub_agi.rules import classify


def _row(label: str, amount: str, heading: str, **extra: Any) -> dict[str, Any]:
    return {
        "label": label,
        "amount": amount,
        "section_heading": heading,
        "codes": [],
        "markers": extra.get("markers", []),
        "in_employer_section": extra.get("employer", False),
    }


STUB_0006 = PaystubEvidence.model_validate(
    {
        "gross": "1760.00",
        "net": "1224.70",
        "pay_frequency": None,
        "period_start": "2026-07-01",
        "period_end": "2026-07-14",
        "pay_date": "2026-07-17",
        "federal_taxable_wages": None,
        "earnings": [{"label": "Regular", "amount": "1760.00"}],
        "taxes": [
            {"label": "Federal Income Tax", "amount": "158.40"},
            {"label": "Social Security", "amount": "109.12"},
            {"label": "Medicare", "amount": "25.52"},
        ],
        "deductions": [
            _row("Medical", "85.00", "Deductions"),
            _row("Dental", "12.00", "Deductions"),
            _row("401k", "70.40", "Deductions"),
            _row("Pension ER", "88.00", "Benefits", employer=True),
        ],
        "footnotes": [],
    }
)

STUB_0002 = PaystubEvidence.model_validate(
    {
        "gross": "1052.70",
        "net": None,
        "pay_frequency": "Biweekly",
        "period_start": None,
        "period_end": None,
        "pay_date": None,
        "federal_taxable_wages": "965.70",
        "earnings": [{"label": "Regular", "amount": "1052.70"}],
        "taxes": [],
        "deductions": [_row("Health", "-87.00", "Deductions", markers=["*"])],
        "footnotes": [{"marker": "*", "text": "Excluded from federal taxable wages"}],
    }
)


def test_worked_example_stub_0006_unmarked_benefits_are_post_tax() -> None:
    config = AnalyzerConfig()

    decided = classify(STUB_0006, config.rules)
    result = compute_agi(STUB_0006, decided, config.agi)

    assert [(d.decision, d.rule_id) for d in decided] == [
        (Decision.NOT_PRETAX, RuleId.R9),
        (Decision.NOT_PRETAX, RuleId.R9),
        (Decision.NOT_PRETAX, RuleId.R9),
        (Decision.EXCLUDED, RuleId.R1),
    ]
    assert result.agi == Decimal("45760.00")
    assert result.agi_if_review_pretax == Decimal("45760.00")


def test_worked_example_stub_0006_review_setting_gives_a_range() -> None:
    config = AnalyzerConfig.from_mapping(
        {"rules": {"bare_benefit_names": "needs_review"}}
    )

    decided = classify(STUB_0006, config.rules)
    result = compute_agi(STUB_0006, decided, config.agi)

    assert result.agi == Decimal("45760.00")
    assert result.agi_if_review_pretax == Decimal("41407.60")


def test_worked_example_stub_0006_benefit_names_as_pretax() -> None:
    config = AnalyzerConfig.from_mapping({"rules": {"bare_benefit_names": "pretax"}})

    decided = classify(STUB_0006, config.rules)

    assert compute_agi(STUB_0006, decided, config.agi).agi == Decimal("41407.60")


def test_worked_example_stub_0002_footnote_makes_health_pretax() -> None:
    config = AnalyzerConfig()

    decided = classify(STUB_0002, config.rules)
    result = compute_agi(STUB_0002, decided, config.agi)

    assert (decided[0].decision, decided[0].rule_id) == (Decision.PRETAX, RuleId.R6)
    assert decided[0].evidence == 'footnote "* Excluded from federal taxable wages"'
    assert result.agi == Decimal("25108.20")


def test_worked_example_stub_0002_uniform_only_makes_health_post_tax() -> None:
    config = AnalyzerConfig.from_mapping({"rules": {"asterisk_scope": "uniform_only"}})

    decided = classify(STUB_0002, config.rules)
    result = compute_agi(STUB_0002, decided, config.agi)

    assert (decided[0].decision, decided[0].rule_id) == (
        Decision.NOT_PRETAX,
        RuleId.R9,
    )
    assert result.agi == Decimal("27370.20")
