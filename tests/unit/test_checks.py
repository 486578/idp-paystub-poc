from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pytest

from paystub_agi.checks import (
    DEFAULT_CHECKS,
    CheckContext,
    apply_review,
    run_checks,
)
from paystub_agi.config import ChecksConfig, RulesConfig
from paystub_agi.errors import InputMismatchError
from paystub_agi.models import (
    CheckCode,
    CheckFlag,
    CheckName,
    CheckReport,
    Decision,
    DeductionDecision,
    PaystubEvidence,
    RuleId,
)
from paystub_agi.rules import classify

# Synthetic stub modelled on stub_0006 (numbers only).
DOCUMENT = """
ACME TOWN PAYROLL  Pay Period 07/01/2026 - 07/14/2026
Earnings  Regular 80.00 22.00 1,760.00   Gross Pay $1,760.00
Taxes  Federal Income Tax 158.40  Social Security 109.12  Medicare 25.52
Deductions  Medical 85.00  Dental 12.00  401k 70.40
Benefits  Pension ER 88.00
Net Pay 1,299.56
"""


def _row(label: str, amount: str | None, heading: str = "Deductions") -> dict[str, Any]:
    return {
        "label": label,
        "amount": amount,
        "section_heading": heading,
        "codes": [],
        "markers": [],
        "in_employer_section": heading == "Benefits",
    }


def _evidence(**overrides: Any) -> PaystubEvidence:
    values: dict[str, Any] = {
        "gross": "1760.00",
        "net": "1299.56",
        "pay_frequency": None,
        "period_start": "2026-07-01",
        "period_end": "2026-07-14",
        "pay_date": None,
        "federal_taxable_wages": None,
        "earnings": [{"label": "Regular", "amount": "1760.00"}],
        "taxes": [
            {"label": "Federal Income Tax", "amount": "158.40"},
            {"label": "Social Security", "amount": "109.12"},
            {"label": "Medicare", "amount": "25.52"},
        ],
        "deductions": [
            _row("Medical", "85.00"),
            _row("Dental", "12.00"),
            _row("401k", "70.40"),
            _row("Pension ER", "88.00", "Benefits"),
        ],
        "footnotes": [],
    }
    values.update(overrides)
    return PaystubEvidence.model_validate(values)


def _run(
    evidence: PaystubEvidence,
    document: str | None = DOCUMENT,
    *,
    rules: dict[str, Any] | None = None,
    decisions: Sequence[DeductionDecision] | None = None,
    send_to_review: bool = False,
) -> CheckReport:
    decided = (
        classify(evidence, RulesConfig.model_validate(rules or {}))
        if decisions is None
        else tuple(decisions)
    )
    config = ChecksConfig(send_to_review=send_to_review)
    return run_checks(evidence, decided, config, document)


REVIEW_RULES = {"bare_benefit_names": "needs_review", "unclear_default": "needs_review"}


def _codes(report: CheckReport) -> list[tuple[CheckCode, int | None, bool]]:
    return [(f.code, f.deduction_index, f.send_to_review) for f in report.flags]


def test_checks_consistent_stub_has_no_flags() -> None:
    report = _run(_evidence())

    assert report.flags == ()
    assert report.not_run == (CheckName.FEDERAL_TAXABLE_WAGES,)


def test_checks_default_checks_cover_every_check_name() -> None:
    assert [c.name for c in DEFAULT_CHECKS] == list(CheckName)


# --- grounding ------------------------------------------------------------------------


def test_checks_grounding_without_document_text_is_not_run() -> None:
    assert CheckName.GROUNDING in _run(_evidence(), document=None).not_run


def test_checks_grounding_flags_deduction_amount_missing_from_document() -> None:
    evidence = _evidence(deductions=[_row("Medical", "95.00")])

    report = _run(evidence)

    assert (CheckCode.AMOUNT_NOT_IN_DOCUMENT, 0, False) in _codes(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [("gross", "1700.00"), ("net", "1300.00"), ("federal_taxable_wages", "999.99")],
)
def test_checks_grounding_flags_stub_amount_missing_from_document(
    field: str, value: str
) -> None:
    report = _run(_evidence(**{field: value}))

    flags = [f for f in report.flags if f.code is CheckCode.AMOUNT_NOT_IN_DOCUMENT]
    assert [(f.deduction_index, field in f.message) for f in flags] == [(None, True)]


def test_checks_grounding_flags_tax_and_earning_amounts() -> None:
    evidence = _evidence(
        earnings=[{"label": "Regular", "amount": "1750.00"}],
        taxes=[{"label": "Medicare", "amount": "26.00"}],
    )

    flags = [
        f for f in _run(evidence).flags if f.code is CheckCode.AMOUNT_NOT_IN_DOCUMENT
    ]

    assert len(flags) == 2


def test_checks_grounding_matches_amount_written_with_commas_and_dollar() -> None:
    document = DOCUMENT.replace("1,760.00", "$1,760")

    report = _run(_evidence(), document)

    assert CheckCode.AMOUNT_NOT_IN_DOCUMENT not in [f.code for f in report.flags]


def test_checks_grounding_matches_negative_amount_by_size() -> None:
    evidence = _evidence(deductions=[_row("Medical", "-85.00")])

    report = _run(evidence)

    assert CheckCode.AMOUNT_NOT_IN_DOCUMENT not in [f.code for f in report.flags]


def test_checks_grounding_skips_missing_amounts() -> None:
    evidence = _evidence(net=None, deductions=[_row("Medical", None)])

    report = _run(evidence)

    assert CheckCode.AMOUNT_NOT_IN_DOCUMENT not in [f.code for f in report.flags]


def test_checks_grounding_flags_invented_label() -> None:
    evidence = _evidence(deductions=[_row("Pre-Tax Medical", "85.00")])

    report = _run(evidence)

    assert (CheckCode.TEXT_NOT_IN_DOCUMENT, 0, False) in _codes(report)


def test_checks_grounding_flags_invented_heading() -> None:
    evidence = _evidence(deductions=[_row("Medical", "85.00", "Pre-Tax Deductions")])

    report = _run(evidence)

    assert (CheckCode.TEXT_NOT_IN_DOCUMENT, 0, False) in _codes(report)


def test_checks_grounding_flags_invented_code() -> None:
    row = _row("Medical", "85.00")
    row["codes"] = [{"column": "Type", "value": "PRE"}]

    report = _run(_evidence(deductions=[row]))

    assert (CheckCode.TEXT_NOT_IN_DOCUMENT, 0, False) in _codes(report)


def test_checks_grounding_flags_invented_footnote() -> None:
    evidence = _evidence(footnotes=[{"marker": "*", "text": "Excluded from wages"}])

    report = _run(evidence)

    assert (CheckCode.TEXT_NOT_IN_DOCUMENT, None, False) in _codes(report)


def test_checks_grounding_flags_invented_earning_and_tax_labels() -> None:
    evidence = _evidence(
        earnings=[{"label": "Holiday Bonus", "amount": "1760.00"}],
        taxes=[{"label": "State Tax", "amount": "25.52"}],
    )

    flags = [
        f for f in _run(evidence).flags if f.code is CheckCode.TEXT_NOT_IN_DOCUMENT
    ]

    assert len(flags) == 2


def test_checks_grounding_ignores_case_and_punctuation_in_text() -> None:
    evidence = _evidence(deductions=[_row("MEDICAL:", "85.00", "deductions")])

    report = _run(evidence)

    assert CheckCode.TEXT_NOT_IN_DOCUMENT not in [f.code for f in report.flags]


# --- net reconciliation ---------------------------------------------------------------


def test_checks_net_mismatch_is_flagged_on_the_stub_only() -> None:
    report = _run(_evidence(net="1300.00"), document=None)

    assert _codes(report) == [(CheckCode.NET_MISMATCH, None, False)]


def test_checks_net_within_tolerance_is_not_flagged() -> None:
    report = _run(_evidence(net="1299.58"), document=None)

    assert report.flags == ()


def test_checks_net_ignores_employer_rows_but_counts_taxes_in_deductions() -> None:
    evidence = _evidence(
        taxes=[],
        deductions=[
            _row("Federal Income Tax", "158.40"),
            _row("Social Security", "109.12"),
            _row("Medicare", "25.52"),
            _row("Medical", "85.00"),
            _row("Dental", "12.00"),
            _row("401k", "70.40"),
            _row("Pension ER", "88.00", "Benefits"),
        ],
    )

    assert _run(evidence, document=None).flags == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"gross": None},
        {"net": None},
        {"taxes": [{"label": "Medicare", "amount": None}]},
        {"deductions": [_row("Medical", None)]},
    ],
)
def test_checks_net_with_missing_amount_is_not_run(overrides: dict[str, Any]) -> None:
    assert CheckName.NET in _run(_evidence(**overrides), document=None).not_run


# --- federal taxable wages ------------------------------------------------------------


def test_checks_federal_wages_matching_pretax_is_not_flagged() -> None:
    evidence = _evidence(federal_taxable_wages="1592.60")

    report = _run(evidence, document=None, rules={"bare_benefit_names": "pretax"})

    assert report.flags == ()


def test_checks_federal_wages_mismatch_sends_r9_r10_rows_to_review() -> None:
    evidence = _evidence(
        federal_taxable_wages="1592.60",
        deductions=[
            _row("Medical", "85.00"),
            _row("Hospital Indemnity", "12.00"),
            _row("Pre-Tax 401k", "70.40"),
        ],
    )

    report = _run(evidence, document=None, send_to_review=True)

    assert _codes(report) == [
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, None, False),
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, 0, True),
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, 1, True),
    ]


def test_checks_federal_wages_mismatch_by_default_only_marks_rows() -> None:
    report = _run(_evidence(federal_taxable_wages="1592.60"), document=None)

    assert _codes(report) == [
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, None, False),
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, 0, False),
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, 1, False),
        (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, 2, False),
    ]


def test_checks_federal_wages_mismatch_skips_rows_already_in_review() -> None:
    evidence = _evidence(federal_taxable_wages="1592.60")

    report = _run(evidence, document=None, rules=REVIEW_RULES, send_to_review=True)

    assert _codes(report) == [(CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, None, False)]


def test_checks_federal_wages_skip_pretax_rows_without_amount() -> None:
    evidence = _evidence(
        federal_taxable_wages="1760.00",
        deductions=[_row("Pre-Tax Medical", None)],
    )

    report = _run(evidence, document=None)

    assert CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH not in [
        f.code for f in report.flags
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"federal_taxable_wages": None},
        {"gross": None, "federal_taxable_wages": "1592.60"},
    ],
)
def test_checks_federal_wages_without_values_is_not_run(
    overrides: dict[str, Any],
) -> None:
    report = _run(_evidence(**overrides), document=None)

    assert CheckName.FEDERAL_TAXABLE_WAGES in report.not_run


# --- payroll-tax gap ----------------------------------------------------------------------

# Modelled on stub_0010: both taxes imply about $1,725 of wages, below gross.
GAP_TAXES = [
    {"label": "Social Security", "amount": "106.95"},
    {"label": "Medicare", "amount": "25.01"},
]


def _gap_evidence(**overrides: Any) -> PaystubEvidence:
    values: dict[str, Any] = {
        "gross": "1836.22",
        "net": None,
        "taxes": GAP_TAXES,
        "deductions": [
            _row("Vision Insurance", "11.91"),
            _row("Hospital Indemnity", "6.76"),
            _row("Health Opt 2", "55.53"),
        ],
    }
    values.update(overrides)
    return _evidence(**values)


def test_checks_gap_sends_not_pretax_cafeteria_rows_to_review() -> None:
    report = _run(_gap_evidence(), document=None, send_to_review=True)

    assert _codes(report) == [
        (CheckCode.PAYROLL_TAX_GAP, None, False),
        (CheckCode.PAYROLL_TAX_GAP, 0, True),
        (CheckCode.PAYROLL_TAX_GAP, 2, True),
    ]


def test_checks_gap_by_default_only_marks_rows() -> None:
    report = _run(_gap_evidence(), document=None)

    assert _codes(report) == [
        (CheckCode.PAYROLL_TAX_GAP, None, False),
        (CheckCode.PAYROLL_TAX_GAP, 0, False),
        (CheckCode.PAYROLL_TAX_GAP, 2, False),
    ]


def test_checks_gap_leaves_pretax_and_review_rows_alone() -> None:
    report = _run(
        _gap_evidence(), document=None, rules=REVIEW_RULES, send_to_review=True
    )

    assert _codes(report) == [(CheckCode.PAYROLL_TAX_GAP, None, False)]


def test_checks_gap_needs_both_taxes_to_show_it() -> None:
    taxes = [
        {"label": "Social Security", "amount": "106.95"},
        {"label": "Medicare", "amount": "26.63"},
    ]

    report = _run(_gap_evidence(taxes=taxes), document=None)

    assert report.flags == ()


def test_checks_gap_uses_one_tax_when_only_one_is_printed() -> None:
    taxes = [{"label": "OASDI", "amount": "106.95"}]

    report = _run(_gap_evidence(taxes=taxes), document=None, rules=REVIEW_RULES)

    assert _codes(report) == [(CheckCode.PAYROLL_TAX_GAP, None, False)]


def test_checks_gap_ignores_tax_label_printed_twice() -> None:
    taxes = [
        {"label": "Social Security", "amount": "106.95"},
        {"label": "Social Security Adj", "amount": "1.00"},
        {"label": "Medicare", "amount": "26.63"},
    ]

    report = _run(_gap_evidence(taxes=taxes), document=None)

    assert report.flags == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"gross": None},
        {"taxes": []},
        {"taxes": [{"label": "Social Security", "amount": None}]},
    ],
)
def test_checks_gap_without_values_is_not_run(overrides: dict[str, Any]) -> None:
    report = _run(_gap_evidence(**overrides), document=None)

    assert CheckName.PAYROLL_TAX_GAP in report.not_run


# --- custom checks and escalation ---------------------------------------------------


class _AlwaysFlag:
    name = CheckName.NET

    def run(self, context: CheckContext) -> tuple[CheckFlag, ...] | None:
        return (CheckFlag(code=CheckCode.NET_MISMATCH, message="custom"),)


def test_checks_custom_check_list_is_used() -> None:
    evidence = _evidence()
    decided = classify(evidence, RulesConfig())

    report = run_checks(evidence, decided, ChecksConfig(), None, (_AlwaysFlag(),))

    assert [f.message for f in report.flags] == ["custom"]
    assert report.not_run == ()


def test_checks_apply_review_moves_flagged_rows_and_records_why() -> None:
    evidence = _evidence()
    decided = classify(evidence, RulesConfig(bare_benefit_names="not_pretax"))
    report = CheckReport(
        flags=(
            CheckFlag(
                code=CheckCode.PAYROLL_TAX_GAP,
                message="gap",
                deduction_index=1,
                send_to_review=True,
            ),
        ),
        not_run=(),
    )

    reviewed = apply_review(decided, report)

    assert reviewed[1].decision is Decision.NEEDS_REVIEW
    assert reviewed[1].escalated_from is Decision.NOT_PRETAX
    assert reviewed[1].escalated_by is CheckCode.PAYROLL_TAX_GAP
    assert reviewed[1].rule_id is RuleId.R9
    assert reviewed[0] == decided[0]


def test_checks_apply_review_ignores_flags_without_review() -> None:
    evidence = _evidence()
    decided = classify(evidence, RulesConfig(bare_benefit_names="not_pretax"))
    report = CheckReport(
        flags=(
            CheckFlag(
                code=CheckCode.AMOUNT_NOT_IN_DOCUMENT, message="x", deduction_index=0
            ),
            CheckFlag(code=CheckCode.NET_MISMATCH, message="y", send_to_review=True),
        ),
        not_run=(),
    )

    assert apply_review(decided, report) == decided


def test_checks_apply_review_keeps_first_reason_and_skips_review_rows() -> None:
    evidence = _evidence()
    decided = classify(evidence, RulesConfig(bare_benefit_names="not_pretax"))
    flags = tuple(
        CheckFlag(code=code, message="m", deduction_index=i, send_to_review=True)
        for code, i in [
            (CheckCode.PAYROLL_TAX_GAP, 0),
            (CheckCode.FEDERAL_TAXABLE_WAGES_MISMATCH, 0),
        ]
    )

    once = apply_review(decided, CheckReport(flags=flags, not_run=()))
    twice = apply_review(once, CheckReport(flags=flags, not_run=()))

    assert once[0].escalated_by is CheckCode.PAYROLL_TAX_GAP
    assert twice == once


def test_checks_flags_never_change_extracted_values() -> None:
    evidence = _evidence(net="1300.00", federal_taxable_wages="1.00")
    before = evidence.model_dump()

    _run(evidence)

    assert evidence.model_dump() == before
    assert Decimal("1300.00") == evidence.net


def test_checks_decisions_for_other_rows_are_rejected() -> None:
    decided = classify(_evidence(), RulesConfig())

    with pytest.raises(InputMismatchError, match="decisions"):
        run_checks(_evidence(), decided[:2], ChecksConfig())


def test_checks_decisions_in_other_order_are_rejected() -> None:
    decided = classify(_evidence(), RulesConfig())

    with pytest.raises(InputMismatchError, match="decisions"):
        run_checks(_evidence(), tuple(reversed(decided)), ChecksConfig())


def test_checks_apply_review_flag_for_missing_row_is_rejected() -> None:
    decided = classify(_evidence(), RulesConfig())
    flag = CheckFlag(
        code=CheckCode.PAYROLL_TAX_GAP,
        message="m",
        deduction_index=9,
        send_to_review=True,
    )

    with pytest.raises(InputMismatchError, match="row 9"):
        apply_review(decided, CheckReport(flags=(flag,), not_run=()))
